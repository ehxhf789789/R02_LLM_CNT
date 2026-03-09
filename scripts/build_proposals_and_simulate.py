"""프로포절 구축 + End-to-End 시뮬레이션 스크립트.

지정기술 목록에서 다양한 분류의 프로포절을 구축하고,
전체 평가 파이프라인을 실행한다.

사용법:
  py scripts/build_proposals_and_simulate.py --build-proposals   # 프로포절 구축
  py scripts/build_proposals_and_simulate.py --simulate          # 시뮬레이션 실행
  py scripts/build_proposals_and_simulate.py --simulate-one 1046 # 단건 시뮬레이션
  py scripts/build_proposals_and_simulate.py --list-proposals    # 프로포절 목록
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import settings
from src.dynamic_kb.kaia_detail_crawler import KaiaDetailCrawler
from src.models.cnt_classification import parse_kaia_field

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def build_proposals(max_per_category: int = 5, max_total: int = 15) -> int:
    """지정기술 목록에서 분류별로 골고루 프로포절을 구축.

    KAIA 상세 페이지를 크롤링하여 실제 기술 내용을 수집한다.
    """
    list_path = settings.dynamic_kb_dir / "cnt_designated" / "designated_list.json"
    if not list_path.exists():
        logger.error("designated_list.json 없음")
        return 0

    with open(list_path, encoding="utf-8") as f:
        techs = json.load(f)

    proposals_dir = settings.proposals_dir
    proposals_dir.mkdir(parents=True, exist_ok=True)

    # 기존 프로포절 확인
    existing = {f.stem.replace("proposal_", "") for f in proposals_dir.glob("proposal_*.json")}
    logger.info("기존 프로포절: %d건", len(existing))

    # 분류별 그룹핑
    by_major: dict[str, list[dict]] = {}
    for t in techs:
        classification = parse_kaia_field(t.get("tech_field", ""))
        if classification:
            major = classification.major.name
            by_major.setdefault(major, []).append(t)

    logger.info("분류별 지정기술: %s",
                {k: len(v) for k, v in by_major.items()})

    # 각 대분류에서 골고루 선택 (detail_url 있는 것 우선)
    selected: list[dict] = []
    for major_name, items in by_major.items():
        # detail_url이 있는 항목 우선
        with_url = [t for t in items if t.get("detail_url") and t.get("tech_number") not in existing]
        without_url = [t for t in items if not t.get("detail_url") and t.get("tech_number") not in existing]

        candidates = with_url + without_url
        for item in candidates[:max_per_category]:
            selected.append(item)

        if len(selected) >= max_total:
            break

    selected = selected[:max_total]
    logger.info("프로포절 구축 대상: %d건", len(selected))

    crawler = KaiaDetailCrawler()
    built = 0

    for tech in selected:
        tech_number = tech.get("tech_number", "")
        detail_url = tech.get("detail_url", "")
        proposal_path = proposals_dir / f"proposal_{tech_number}.json"

        if proposal_path.exists():
            logger.debug("이미 존재: %s", tech_number)
            built += 1
            continue

        try:
            if detail_url:
                info = crawler.fetch_detail(detail_url)
                proposal = crawler.build_proposal_from_detail(info)
            else:
                # detail_url 없으면 기본 정보만으로 구성
                proposal = {
                    "tech_number": tech_number,
                    "tech_name": tech.get("tech_name", ""),
                    "tech_field": tech.get("tech_field", ""),
                    "tech_description": tech.get("tech_name", ""),
                    "tech_core_content": "",
                    "differentiation_claim": "",
                    "test_results": "",
                    "field_application": "",
                    "search_keywords": [],
                    "patents": [],
                    "pdf_content": "",
                    "source": "kaia_list",
                }

            with open(proposal_path, "w", encoding="utf-8") as f:
                json.dump(proposal, f, ensure_ascii=False, indent=2, default=str)

            built += 1
            logger.info("프로포절 구축: %s (%s)", tech_number, tech.get("tech_name", ""))
            time.sleep(2)  # rate limiting

        except Exception as e:
            logger.error("프로포절 구축 실패 %s: %s", tech_number, e)

    logger.info("프로포절 구축 완료: %d건", built)
    return built


def list_proposals() -> list[dict]:
    """사용 가능한 프로포절 목록을 출력."""
    proposals_dir = settings.proposals_dir
    if not proposals_dir.exists():
        print("프로포절 디렉토리 없음")
        return []

    proposals = []
    for f in sorted(proposals_dir.glob("proposal_*.json")):
        with open(f, encoding="utf-8") as fp:
            data = json.load(fp)
        proposals.append(data)
        tech_number = data.get("tech_number", "")
        tech_name = data.get("tech_name", "")[:50]
        tech_field = data.get("tech_field", "")
        has_content = bool(data.get("tech_core_content", ""))
        print(f"  [{tech_number}] {tech_name}")
        print(f"    분야: {tech_field} | 상세내용: {'있음' if has_content else '없음'}")

    print(f"\n  총 {len(proposals)}건")
    return proposals


def run_simulation(
    proposal_path: str | None = None,
    tech_number: str | None = None,
    seed: int = 42,
) -> None:
    """전체 평가 파이프라인 시뮬레이션을 실행.

    Args:
        proposal_path: 프로포절 JSON 경로 (지정 시 단건)
        tech_number: 기술 번호 (proposals 디렉토리에서 검색)
        seed: 랜덤 시드 (재현성)
    """
    from src.pipeline.orchestrator import Orchestrator
    from src.vectordb.kb_vectorizer import KBVectorizer
    from src.evaluation.kb_assembler import KBAssembler
    from src.evaluation.prior_art_searcher import PriorArtSearcher
    from src.llm.bedrock_client import BedrockClient

    # 프로포절 로드
    proposals_dir = settings.proposals_dir
    if proposal_path:
        with open(proposal_path, encoding="utf-8") as f:
            proposals = [json.load(f)]
    elif tech_number:
        p = proposals_dir / f"proposal_{tech_number}.json"
        if not p.exists():
            logger.error("프로포절 없음: %s", p)
            return
        with open(p, encoding="utf-8") as f:
            proposals = [json.load(f)]
    else:
        # 모든 프로포절 실행
        proposals = []
        for f in sorted(proposals_dir.glob("proposal_*.json")):
            with open(f, encoding="utf-8") as fp:
                proposals.append(json.load(fp))

    if not proposals:
        logger.error("실행할 프로포절이 없습니다.")
        return

    logger.info("시뮬레이션 대상: %d건", len(proposals))

    # 벡터 KB 초기화 (있으면 사용)
    vectorizer = None
    try:
        v = KBVectorizer()
        table = v.db.open_table(v.TABLE_NAME)
        row_count = table.count_rows()
        if row_count > 0:
            vectorizer = v
            logger.info("벡터 KB 사용: %d건", row_count)
    except Exception:
        logger.info("벡터 KB 없음, JSON store 폴백")

    # 오케스트레이터 초기화
    kb_assembler = KBAssembler(vectorizer=vectorizer)
    orchestrator = Orchestrator(
        kb_assembler=kb_assembler,
        max_workers=3,  # LLM 호출 병렬도
    )

    # 각 프로포절에 대해 평가 실행
    results = []
    for proposal in proposals:
        tech_num = proposal.get("tech_number", "unknown")
        tech_name = proposal.get("tech_name", "")

        logger.info("\n" + "=" * 60)
        logger.info("평가 시작: [%s] %s", tech_num, tech_name)
        logger.info("=" * 60)

        try:
            result = orchestrator.evaluate(
                proposal=proposal,
                seed=seed,
                exclude_tech_numbers=[tech_num],
            )
            results.append(result)

            # 앙상블 결과 출력
            er = result.ensemble_result
            print(f"\n{'='*60}")
            print(f"  [{tech_num}] {tech_name}")
            print(f"  최종 의결: {er.get('final_verdict', 'N/A')}")
            print(f"  찬성률: {er.get('approval_ratio', 0):.1%} (가중: {er.get('weighted_approval_ratio', 0):.1%})")
            print(f"  점수: 신규성 {er.get('avg_novelty_total', 0):.1f}/50, "
                  f"진보성 {er.get('avg_progressiveness_total', 0):.1f}/50, "
                  f"총점 {er.get('avg_total', 0):.1f}/100")
            print(f"  패널: {result.panel_size}명, 소요시간: {result.elapsed_seconds:.1f}초")
            print(f"{'='*60}")

        except Exception as e:
            logger.error("평가 실패 [%s]: %s", tech_num, e, exc_info=True)

    # 전체 결과 요약
    if len(results) > 1:
        print(f"\n{'='*60}")
        print(f"  전체 시뮬레이션 결과 요약 ({len(results)}건)")
        print(f"{'='*60}")
        approved = sum(1 for r in results if r.ensemble_result.get("final_verdict") == "approved")
        print(f"  승인: {approved}건, 불승인: {len(results)-approved}건")
        avg_total = sum(r.ensemble_result.get("avg_total", 0) for r in results) / len(results)
        print(f"  평균 총점: {avg_total:.1f}/100")
        total_time = sum(r.elapsed_seconds for r in results)
        print(f"  총 소요시간: {total_time:.1f}초")
        print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="프로포절 구축 + 시뮬레이션")
    parser.add_argument("--build-proposals", action="store_true",
                        help="KAIA 상세 페이지에서 프로포절 구축")
    parser.add_argument("--max-proposals", type=int, default=15,
                        help="최대 프로포절 수 (기본 15)")
    parser.add_argument("--list-proposals", action="store_true",
                        help="프로포절 목록 출력")
    parser.add_argument("--simulate", action="store_true",
                        help="전체 프로포절 시뮬레이션")
    parser.add_argument("--simulate-one", type=str, default=None,
                        help="단건 시뮬레이션 (기술번호)")
    parser.add_argument("--seed", type=int, default=42,
                        help="랜덤 시드 (기본 42)")
    args = parser.parse_args()

    if args.build_proposals:
        build_proposals(max_total=args.max_proposals)
    elif args.list_proposals:
        list_proposals()
    elif args.simulate:
        run_simulation(seed=args.seed)
    elif args.simulate_one:
        run_simulation(tech_number=args.simulate_one, seed=args.seed)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
