"""건설신기술 LLM 평가 실험 메인 스크립트.

하이브리드 실험 설계:
  Phase 1 (prepare):  테스트 케이스 선별 + 제안기술 구축 + 벡터 KB 구축
  Phase 2 (evaluate): 평가 실행
    - 검증 1 (정확도, 8-1): 2018+ 기술, 커트오프 적용 (~175건)
    - 검증 2 (일관성, 8-2): 전체 기술, 커트오프 무관 (263건 × 반복)
    - 검증 3 (점수패턴, 8-3): 전체 평가 결과 대상
  Phase 3 (sensitivity): 민감도 분석용 평가
    - 검증 4 (8-4): 2013-2017 기술에 대해 커트오프 적용/미적용 2회 평가
  Phase 4 (analyze): 분석 실행

사용법:
    python scripts/run_experiment.py --phase all
    python scripts/run_experiment.py --phase prepare
    python scripts/run_experiment.py --phase evaluate
    python scripts/run_experiment.py --phase sensitivity
    python scripts/run_experiment.py --phase analyze
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

PROPOSALS_DIR = settings.data_dir / "proposals"

# 실험 설계 상수
ACCURACY_CUTOFF_YEAR = 2018        # 정확도 분석 대상: 이 연도 이후 지정 기술
SENSITIVITY_YEAR_RANGE = (2013, 2017)  # 민감도 분석 대상: 이 연도 범위 지정 기술

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(
            open(sys.stdout.fileno(), mode='w', encoding='utf-8', closefd=False)
        ),
        logging.FileHandler(
            settings.data_dir / "experiment.log",
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# 헬퍼: 프로포절 로드 및 분류
# ─────────────────────────────────────────────────────────────

def load_all_proposals() -> dict[str, dict]:
    """proposals 디렉토리에서 전체 프로포절을 로드."""
    proposals = {}
    for f in sorted(PROPOSALS_DIR.glob("proposal_*.json")):
        with open(f, encoding="utf-8") as fp:
            p = json.load(fp)
        tech_num = str(p.get("tech_number", ""))
        if tech_num:
            proposals[tech_num] = p
    return proposals


def classify_proposals(proposals: dict[str, dict]) -> dict:
    """프로포절을 실험 그룹별로 분류.

    Returns:
        {
            "accuracy":    [...],  # 2018+ 기술 (검증 1: 정확도)
            "consistency": [...],  # 전체 기술 (검증 2: 일관성)
            "sensitivity": [...],  # 2013-2017 기술 (검증 4: 민감도)
        }
    """
    accuracy = []
    consistency = []
    sensitivity = []

    for tech_num, p in proposals.items():
        year = p.get("designation_year")
        consistency.append(tech_num)

        if year and int(year) >= ACCURACY_CUTOFF_YEAR:
            accuracy.append(tech_num)

        if year and SENSITIVITY_YEAR_RANGE[0] <= int(year) <= SENSITIVITY_YEAR_RANGE[1]:
            sensitivity.append(tech_num)

    return {
        "accuracy": sorted(accuracy, key=lambda x: int(x) if x.isdigit() else 0),
        "consistency": sorted(consistency, key=lambda x: int(x) if x.isdigit() else 0),
        "sensitivity": sorted(sensitivity, key=lambda x: int(x) if x.isdigit() else 0),
    }


def _create_orchestrator(tech_numbers: list[str], max_workers: int = 5):
    """오케스트레이터 생성 (벡터 KB 포함)."""
    from src.pipeline.orchestrator import Orchestrator
    from src.vectordb.kb_vectorizer import KBVectorizer
    from src.evaluation.kb_assembler import KBAssembler

    vectorizer = None
    try:
        vectorizer = KBVectorizer()
        vectorizer.set_excluded_techs(tech_numbers)
        vectorizer.db.open_table(KBVectorizer.TABLE_NAME)
        logger.info("벡터 KB 로드 완료 (제외: %d건)", len(tech_numbers))
    except Exception:
        logger.info("벡터 KB 없음 — JSON store 폴백 모드")
        vectorizer = None

    kb_assembler = KBAssembler(vectorizer=vectorizer)
    return Orchestrator(kb_assembler=kb_assembler, max_workers=max_workers)


# ─────────────────────────────────────────────────────────────
# Phase 1: Prepare
# ─────────────────────────────────────────────────────────────

def phase_prepare(args):
    """Phase 1: 테스트 케이스 선별 + 제안기술 구축 + KB 준비."""
    proposals = load_all_proposals()
    groups = classify_proposals(proposals)

    logger.info("=== 실험 프로포절 분류 ===")
    logger.info("  전체 프로포절: %d건", len(proposals))
    logger.info("  검증 1 (정확도, 2018+): %d건", len(groups["accuracy"]))
    logger.info("  검증 2 (일관성, 전체): %d건", len(groups["consistency"]))
    logger.info("  검증 4 (민감도, 2013-2017): %d건", len(groups["sensitivity"]))

    # 실험 구성 저장
    experiment_config = {
        "groups": {k: v for k, v in groups.items()},
        "accuracy_cutoff_year": ACCURACY_CUTOFF_YEAR,
        "sensitivity_year_range": list(SENSITIVITY_YEAR_RANGE),
        "total_proposals": len(proposals),
        "seed": args.seed,
        "repetitions": args.repetitions,
    }
    config_path = settings.data_dir / "experiment_config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(experiment_config, f, ensure_ascii=False, indent=2)
    logger.info("실험 구성 저장: %s", config_path)

    # 벡터 KB 구축 (전체 테스트 케이스 제외)
    all_tech_numbers = groups["consistency"]
    if not args.skip_vectorize:
        logger.info("벡터 KB 구축 시작 (제외: %d건)", len(all_tech_numbers))
        from src.vectordb.kb_vectorizer import KBVectorizer
        vectorizer = KBVectorizer()
        vectorizer.set_excluded_techs(all_tech_numbers)
        n_docs = vectorizer.build_from_store()
        logger.info("벡터 KB 구축 완료: %d건", n_docs)


# ─────────────────────────────────────────────────────────────
# Phase 2: Evaluate (검증 1 + 2 + 3)
# ─────────────────────────────────────────────────────────────

def phase_evaluate(args):
    """Phase 2: 반복 평가 실행.

    모든 프로포절을 시간적 커트오프 적용하여 평가한다.
    - 검증 1 (정확도): 2018+ 결과만 사용
    - 검증 2 (일관성): 전체 결과의 반복 비교
    - 검증 3 (점수패턴): 전체 결과 대상
    """
    config_path = settings.data_dir / "experiment_config.json"
    if not config_path.exists():
        logger.error("실험 구성 없음. --phase prepare를 먼저 실행하세요.")
        return

    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    all_tech_numbers = config["groups"]["consistency"]
    proposals = load_all_proposals()

    # 통계적 최소 반복 횟수 확인
    from src.analysis.consistency_analyzer import compute_required_repetitions
    min_reps = compute_required_repetitions()
    if args.repetitions < min_reps:
        logger.warning(
            "반복 횟수 %d < 통계적 최소 권장 %d. "
            "일관성 분석의 통계적 유의성이 부족할 수 있습니다.",
            args.repetitions, min_reps,
        )

    orchestrator = _create_orchestrator(all_tech_numbers, args.max_workers)

    total_runs = len(all_tech_numbers) * args.repetitions
    completed = 0

    logger.info("=== 평가 시작: %d건 × %d반복 = %d회 ===", len(all_tech_numbers), args.repetitions, total_runs)

    for tech_num in all_tech_numbers:
        proposal = proposals.get(tech_num)
        if not proposal:
            logger.warning("제안기술 없음: %s", tech_num)
            continue

        for rep in range(args.repetitions):
            run_id = f"run_{tech_num}_{rep:03d}"
            seed = (args.seed or 0) + rep if args.seed is not None else None

            # 이미 완료된 결과 건너뛰기
            result_path = settings.results_dir / f"{run_id}.json"
            if result_path.exists() and not args.force:
                completed += 1
                continue

            logger.info(
                "평가 [%d/%d]: %s (반복 %d/%d)",
                completed + 1, total_runs, tech_num, rep + 1, args.repetitions,
            )

            try:
                orchestrator.evaluate(
                    proposal=proposal,
                    run_id=run_id,
                    seed=seed,
                    skip_chairman=args.skip_chairman,
                    exclude_tech_numbers=all_tech_numbers,
                )
            except Exception as e:
                logger.error("평가 실패 (%s): %s", run_id, e)

            completed += 1

    logger.info("평가 완료: %d/%d건", completed, total_runs)


# ─────────────────────────────────────────────────────────────
# Phase 3: Sensitivity (검증 4)
# ─────────────────────────────────────────────────────────────

def phase_sensitivity(args):
    """Phase 3: 민감도 분석용 평가.

    2013-2017 기술에 대해 커트오프 미적용 버전을 추가 실행.
    (커트오프 적용 버전은 Phase 2에서 이미 실행됨)
    """
    config_path = settings.data_dir / "experiment_config.json"
    if not config_path.exists():
        logger.error("실험 구성 없음. --phase prepare를 먼저 실행하세요.")
        return

    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    sensitivity_techs = config["groups"]["sensitivity"]
    all_tech_numbers = config["groups"]["consistency"]
    proposals = load_all_proposals()

    if not sensitivity_techs:
        logger.warning("민감도 분석 대상 기술 없음 (2013-2017)")
        return

    logger.info("=== 민감도 분석: %d건 (커트오프 미적용 추가 실행) ===", len(sensitivity_techs))

    orchestrator = _create_orchestrator(all_tech_numbers, args.max_workers)

    total_runs = len(sensitivity_techs) * args.repetitions
    completed = 0

    for tech_num in sensitivity_techs:
        proposal = proposals.get(tech_num)
        if not proposal:
            logger.warning("제안기술 없음: %s", tech_num)
            continue

        # 커트오프 미적용 버전: designation_year를 제거한 복사본으로 평가
        proposal_no_cutoff = dict(proposal)
        proposal_no_cutoff.pop("designation_year", None)
        proposal_no_cutoff.pop("cutoff_year", None)
        proposal_no_cutoff.pop("protection_period", None)

        for rep in range(args.repetitions):
            run_id = f"nocutoff_{tech_num}_{rep:03d}"
            seed = (args.seed or 0) + rep if args.seed is not None else None

            result_path = settings.results_dir / f"{run_id}.json"
            if result_path.exists() and not args.force:
                completed += 1
                continue

            logger.info(
                "민감도 평가 [%d/%d]: %s (반복 %d/%d, 커트오프 미적용)",
                completed + 1, total_runs, tech_num, rep + 1, args.repetitions,
            )

            try:
                orchestrator.evaluate(
                    proposal=proposal_no_cutoff,
                    run_id=run_id,
                    seed=seed,
                    skip_chairman=args.skip_chairman,
                    exclude_tech_numbers=all_tech_numbers,
                )
            except Exception as e:
                logger.error("민감도 평가 실패 (%s): %s", run_id, e)

            completed += 1

    logger.info("민감도 평가 완료: %d/%d건", completed, total_runs)


# ─────────────────────────────────────────────────────────────
# Phase 4: Analyze (검증 1 + 2 + 3 + 4)
# ─────────────────────────────────────────────────────────────

def phase_analyze(args):
    """Phase 4: 분석 실행."""
    from src.analysis.accuracy_analyzer import AccuracyAnalyzer
    from src.analysis.consistency_analyzer import ConsistencyAnalyzer
    from src.analysis.score_pattern_analyzer import ScorePatternAnalyzer
    from src.analysis.sensitivity_analyzer import SensitivityAnalyzer

    results_dir = settings.results_dir
    analysis_dir = settings.data_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    # 실험 구성 로드
    config_path = settings.data_dir / "experiment_config.json"
    config = {}
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)

    accuracy_techs = set(config.get("groups", {}).get("accuracy", []))

    # ── 8-1: 정확도 분석 (2018+ 기술만) ──
    logger.info("분석 8-1: 정확도 분석 (2018+ 기술)...")
    accuracy_analyzer = AccuracyAnalyzer()

    # 2018+ 결과만 필터링
    accuracy_results_dir = analysis_dir / "_temp_accuracy"
    accuracy_results_dir.mkdir(exist_ok=True)
    n_accuracy_files = 0
    for f in results_dir.glob("run_*.json"):
        with open(f, encoding="utf-8") as fp:
            data = json.load(fp)
        if str(data.get("tech_number", "")) in accuracy_techs:
            # 심볼릭 링크 대신 경로 기록
            import shutil
            shutil.copy2(f, accuracy_results_dir / f.name)
            n_accuracy_files += 1

    accuracy = accuracy_analyzer.analyze(accuracy_results_dir)
    accuracy["filter"] = f"designation_year >= {ACCURACY_CUTOFF_YEAR}"
    accuracy["n_filtered_files"] = n_accuracy_files

    with open(analysis_dir / "accuracy.json", "w", encoding="utf-8") as f:
        json.dump(accuracy, f, ensure_ascii=False, indent=2, default=str)

    # 임시 디렉토리 정리
    import shutil
    shutil.rmtree(accuracy_results_dir, ignore_errors=True)

    logger.info(
        "정확도: %.1f%% (%d/%d건 정확, 2018+ 필터)",
        accuracy.get("overall_accuracy", 0) * 100,
        sum(1 for c in accuracy.get("case_results", []) if c.get("is_correct")),
        accuracy.get("total_cases", 0),
    )

    # ── 8-2: 일관성 분석 (전체) ──
    logger.info("분석 8-2: 일관성 분석 (전체)...")
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

    # ── 8-3: 점수 패턴 분석 (전체) ──
    logger.info("분석 8-3: 점수 패턴 분석 (전체)...")
    patterns = ScorePatternAnalyzer().analyze(results_dir)
    with open(analysis_dir / "score_patterns.json", "w", encoding="utf-8") as f:
        json.dump(patterns, f, ensure_ascii=False, indent=2, default=str)
    logger.info("점수 패턴: %d건 투표 분석 완료", patterns.get("total_votes", 0))

    # ── 8-4: 민감도 분석 (2013-2017, 커트오프 적용 vs 미적용) ──
    logger.info("분석 8-4: 커트오프 민감도 분석...")
    sensitivity_analyzer = SensitivityAnalyzer()
    sensitivity = sensitivity_analyzer.analyze(results_dir)

    # 지정연도 매핑 추가
    if isinstance(sensitivity, dict) and "error" not in sensitivity:
        pairs = sensitivity.get("tech_numbers", [])
        # pairs 리스트가 아니라 analyze 내부에서 처리됨
        # 별도로 지정연도를 결과에 추가
        proposals = load_all_proposals()
        for tech_list_key in ["tech_numbers"]:
            if tech_list_key in sensitivity:
                enriched = []
                for tn in sensitivity[tech_list_key]:
                    p = proposals.get(str(tn), {})
                    enriched.append({
                        "tech_number": tn,
                        "designation_year": p.get("designation_year"),
                    })
                sensitivity[f"{tech_list_key}_detail"] = enriched

    with open(analysis_dir / "sensitivity.json", "w", encoding="utf-8") as f:
        json.dump(sensitivity, f, ensure_ascii=False, indent=2, default=str)

    if isinstance(sensitivity, dict) and "error" not in sensitivity:
        vc = sensitivity.get("verdict_comparison", {})
        sc = sensitivity.get("score_comparison", {})
        logger.info(
            "민감도: 의결 일치율 %.1f%%, 평균 점수차 %.1f점 (p=%.3f)",
            vc.get("verdict_match_rate", 0) * 100,
            sc.get("mean_score_diff", 0),
            sc.get("paired_p_value", 1),
        )
    else:
        logger.info("민감도: 분석 데이터 부족 (%s)", sensitivity.get("error", ""))

    # ── 종합 요약 ──
    print("\n" + "=" * 70)
    print("실험 결과 종합 요약")
    print("=" * 70)

    print(f"\n[검증 1] 정확도 (8-1) — 2018+ 기술 대상")
    print(f"  정확도: {accuracy.get('overall_accuracy', 0):.1%}")
    print(f"  대상: {accuracy.get('total_cases', 0)}건")

    print(f"\n[검증 2] 일관성 (8-2) — 전체 기술 대상")
    print(f"  의결 안정성: {consistency.get('overall_verdict_stability', 0):.1%}")
    if kappa:
        print(f"  Fleiss' kappa: {kappa.get('kappa', 0):.3f} ({kappa.get('interpretation', '')})")
    print(f"  점수 CV: {consistency.get('overall_score_cv', 0):.1f}%")

    print(f"\n[검증 3] 점수 패턴 (8-3) — 전체 투표 대상")
    print(f"  총 투표: {patterns.get('total_votes', 0)}건")

    print(f"\n[검증 4] 커트오프 민감도 (8-4) — 2013-2017 기술 대상")
    if isinstance(sensitivity, dict) and "error" not in sensitivity:
        summary = sensitivity.get("summary", {})
        print(f"  의결 안정성: {summary.get('verdict_stability', 0):.1%}")
        print(f"  평균 점수 영향: {summary.get('mean_score_impact', 0):+.1f}점")
        print(f"  통계적 유의성: {'유의미' if summary.get('score_impact_significant') else '유의미하지 않음'}")
        sensitive_fields = summary.get("sensitive_fields", [])
        if sensitive_fields:
            print(f"  민감 항목: {', '.join(sensitive_fields)}")
        print(f"  권고: {summary.get('recommendation', '')}")
    else:
        print(f"  (민감도 분석 미실행 — sensitivity phase를 먼저 실행하세요)")

    print(f"\n결과 파일: {analysis_dir}")


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="건설신기술 LLM 평가 실험 (하이브리드 설계)")
    parser.add_argument(
        "--phase",
        choices=["all", "prepare", "evaluate", "sensitivity", "analyze"],
        default="all",
        help="실행할 단계 (all=전체, prepare/evaluate/sensitivity/analyze=개별)",
    )
    parser.add_argument("--n-cases", type=int, default=10, help="테스트 케이스 수 (prepare용)")
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
    settings.results_dir.mkdir(parents=True, exist_ok=True)

    if args.phase in ("all", "prepare"):
        phase_prepare(args)

    if args.phase in ("all", "evaluate"):
        phase_evaluate(args)

    if args.phase in ("all", "sensitivity"):
        phase_sensitivity(args)

    if args.phase in ("all", "analyze"):
        phase_analyze(args)


if __name__ == "__main__":
    main()
