"""건설신기술 LLM 평가 실험 메인 스크립트.

전체 실험 파이프라인:
  1. 테스트 케이스 선별 및 제안기술 구축
  2. 벡터 KB 구축 (테스트 케이스 제외)
  3. 반복 평가 실행
  4. 분석 실행 및 결과 출력

사용법:
    python scripts/run_experiment.py --phase all
    python scripts/run_experiment.py --phase prepare  # 테스트 케이스 + KB 준비만
    python scripts/run_experiment.py --phase evaluate  # 평가 실행만
    python scripts/run_experiment.py --phase analyze   # 분석만
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            settings.data_dir / "experiment.log",
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger(__name__)


def phase_prepare(args):
    """Phase 1: 테스트 케이스 선별 + 제안기술 구축 + KB 준비."""
    from src.pipeline.proposal_builder import ProposalBuilder

    builder = ProposalBuilder()

    # 테스트 케이스 선별
    if args.tech_numbers:
        tech_numbers = args.tech_numbers.split(",")
    else:
        tech_numbers = builder.select_test_cases(
            n_cases=args.n_cases,
            field_filter=args.field_filter,
            seed=args.seed,
        )

    if not tech_numbers:
        logger.error("테스트 케이스를 선별할 수 없습니다.")
        return

    logger.info("테스트 케이스 %d건: %s", len(tech_numbers), tech_numbers)

    # 제안기술 구축
    proposals = builder.build_from_tech_numbers(
        tech_numbers,
        download_pdfs=not args.no_pdf,
    )
    logger.info("제안기술 %d건 구축 완료", len(proposals))

    # 테스트 케이스 목록 저장
    test_cases_path = settings.data_dir / "test_cases.json"
    with open(test_cases_path, "w", encoding="utf-8") as f:
        json.dump({
            "tech_numbers": tech_numbers,
            "seed": args.seed,
            "n_cases": len(tech_numbers),
        }, f, ensure_ascii=False, indent=2)

    # 벡터 KB 구축 (테스트 케이스 제외)
    if not args.skip_vectorize:
        logger.info("벡터 KB 구축 시작 (제외: %d건)", len(tech_numbers))
        from src.vectordb.kb_vectorizer import KBVectorizer
        vectorizer = KBVectorizer()
        vectorizer.set_excluded_techs(tech_numbers)
        n_docs = vectorizer.build_from_store()
        logger.info("벡터 KB 구축 완료: %d건", n_docs)


def phase_evaluate(args):
    """Phase 2: 반복 평가 실행."""
    from src.pipeline.orchestrator import Orchestrator
    from src.pipeline.proposal_builder import ProposalBuilder

    # 테스트 케이스 로드
    test_cases_path = settings.data_dir / "test_cases.json"
    if not test_cases_path.exists():
        logger.error("테스트 케이스 파일이 없습니다. --phase prepare를 먼저 실행하세요.")
        return

    with open(test_cases_path, encoding="utf-8") as f:
        test_cases = json.load(f)

    tech_numbers = test_cases["tech_numbers"]

    # 제안기술 로드
    builder = ProposalBuilder()
    proposals = builder.load_proposals()
    proposal_map = {p["tech_number"]: p for p in proposals}

    # 통계적 최소 반복 횟수 확인
    from src.analysis.consistency_analyzer import compute_required_repetitions
    min_reps = compute_required_repetitions()
    if args.repetitions < min_reps:
        logger.warning(
            "반복 횟수 %d < 통계적 최소 권장 %d. "
            "일관성 분석의 통계적 유의성이 부족할 수 있습니다.",
            args.repetitions, min_reps,
        )

    # 벡터 KB 로드 (가능한 경우)
    from src.vectordb.kb_vectorizer import KBVectorizer
    from src.evaluation.kb_assembler import KBAssembler
    vectorizer = None
    try:
        vectorizer = KBVectorizer()
        vectorizer.set_excluded_techs(tech_numbers)
        # 테이블 존재 여부 확인
        vectorizer.db.open_table(KBVectorizer.TABLE_NAME)
        logger.info("벡터 KB 로드 완료 (제외: %d건)", len(tech_numbers))
    except Exception:
        logger.info("벡터 KB 없음 — JSON store 폴백 모드")
        vectorizer = None

    kb_assembler = KBAssembler(vectorizer=vectorizer)

    # 오케스트레이터 생성
    orchestrator = Orchestrator(
        kb_assembler=kb_assembler,
        max_workers=args.max_workers,
    )

    # 반복 평가
    total_runs = len(tech_numbers) * args.repetitions
    completed = 0

    for tech_num in tech_numbers:
        proposal = proposal_map.get(tech_num)
        if not proposal:
            logger.warning("제안기술 없음: %s", tech_num)
            continue

        for rep in range(args.repetitions):
            run_id = f"run_{tech_num}_{rep:03d}"
            seed = (args.seed or 0) + rep if args.seed is not None else None

            # 이미 완료된 결과 건너뛰기
            result_path = settings.results_dir / f"{run_id}.json"
            if result_path.exists() and not args.force:
                logger.info("건너뛰기 (완료됨): %s", run_id)
                completed += 1
                continue

            logger.info(
                "평가 실행 [%d/%d]: %s (반복 %d/%d)",
                completed + 1, total_runs, tech_num, rep + 1, args.repetitions,
            )

            try:
                orchestrator.evaluate(
                    proposal=proposal,
                    run_id=run_id,
                    seed=seed,
                    skip_chairman=args.skip_chairman,
                    exclude_tech_numbers=tech_numbers,
                )
            except Exception as e:
                logger.error("평가 실패 (%s): %s", run_id, e)

            completed += 1

    logger.info("평가 완료: %d/%d건", completed, total_runs)


def phase_analyze(args):
    """Phase 3: 분석 실행."""
    from src.analysis.accuracy_analyzer import AccuracyAnalyzer
    from src.analysis.consistency_analyzer import ConsistencyAnalyzer
    from src.analysis.score_pattern_analyzer import ScorePatternAnalyzer

    results_dir = settings.results_dir
    analysis_dir = settings.data_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    # 8-1: 정확도 분석
    logger.info("분석 8-1: 정확도 분석...")
    accuracy = AccuracyAnalyzer().analyze(results_dir)
    with open(analysis_dir / "accuracy.json", "w", encoding="utf-8") as f:
        json.dump(accuracy, f, ensure_ascii=False, indent=2, default=str)
    logger.info(
        "정확도: %.1f%% (%d/%d건 정확)",
        accuracy.get("overall_accuracy", 0) * 100,
        sum(1 for c in accuracy.get("case_results", []) if c.get("is_correct")),
        accuracy.get("total_cases", 0),
    )

    # 8-2: 일관성 분석
    logger.info("분석 8-2: 일관성 분석...")
    consistency = ConsistencyAnalyzer().analyze(results_dir)
    with open(analysis_dir / "consistency.json", "w", encoding="utf-8") as f:
        json.dump(consistency, f, ensure_ascii=False, indent=2, default=str)
    kappa = consistency.get("fleiss_kappa", {})
    logger.info(
        "일관성: 의결 안정성 %.1f%%, Fleiss' kappa %.3f (%s)",
        consistency.get("overall_verdict_stability", 0) * 100,
        kappa.get("kappa", 0) if kappa else 0,
        kappa.get("interpretation", "N/A") if kappa else "N/A",
    )

    # 8-3: 점수 패턴 분석
    logger.info("분석 8-3: 점수 패턴 분석...")
    patterns = ScorePatternAnalyzer().analyze(results_dir)
    with open(analysis_dir / "score_patterns.json", "w", encoding="utf-8") as f:
        json.dump(patterns, f, ensure_ascii=False, indent=2, default=str)
    logger.info("점수 패턴: %d건 투표 분석 완료", patterns.get("total_votes", 0))

    print("\n" + "=" * 60)
    print("분석 결과 요약")
    print("=" * 60)
    print(f"정확도 (8-1): {accuracy.get('overall_accuracy', 0):.1%}")
    print(f"일관성 (8-2): 의결 안정성 {consistency.get('overall_verdict_stability', 0):.1%}")
    if kappa:
        print(f"Fleiss' kappa: {kappa.get('kappa', 0):.3f} ({kappa.get('interpretation', '')})")
    print(f"점수 패턴 (8-3): {patterns.get('total_votes', 0)}건 투표 분석")
    print(f"\n결과 파일: {analysis_dir}")


def main():
    parser = argparse.ArgumentParser(description="건설신기술 LLM 평가 실험")
    parser.add_argument(
        "--phase",
        choices=["all", "prepare", "evaluate", "analyze"],
        default="all",
        help="실행할 단계",
    )
    parser.add_argument("--n-cases", type=int, default=10, help="테스트 케이스 수")
    parser.add_argument("--repetitions", type=int, default=5, help="반복 횟수")
    parser.add_argument("--seed", type=int, default=42, help="랜덤 시드")
    parser.add_argument("--tech-numbers", type=str, help="직접 지정할 기술 번호 (쉼표 구분)")
    parser.add_argument("--field-filter", type=str, help="분야 필터 (예: 토목)")
    parser.add_argument("--no-pdf", action="store_true", help="PDF 다운로드 생략")
    parser.add_argument("--skip-vectorize", action="store_true", help="벡터 KB 구축 생략")
    parser.add_argument("--skip-chairman", action="store_true", help="의장 검토 생략")
    parser.add_argument("--max-workers", type=int, default=5, help="동시 LLM 호출 수")
    parser.add_argument("--force", action="store_true", help="완료된 결과도 재실행")

    args = parser.parse_args()

    settings.data_dir.mkdir(parents=True, exist_ok=True)

    if args.phase in ("all", "prepare"):
        phase_prepare(args)

    if args.phase in ("all", "evaluate"):
        phase_evaluate(args)

    if args.phase in ("all", "analyze"):
        phase_analyze(args)


if __name__ == "__main__":
    main()
