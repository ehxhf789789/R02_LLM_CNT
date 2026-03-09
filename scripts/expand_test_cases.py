"""테스트 케이스 확장 스크립트.

KAIA에서 더 많은 지정기술을 수집하고,
상세 정보 기반으로 프로포절 데이터셋을 생성한다.

사용법:
  py scripts/expand_test_cases.py --collect      # 지정기술 추가 수집
  py scripts/expand_test_cases.py --build-proposals  # 프로포절 생성
  py scripts/expand_test_cases.py --status        # 현황 출력
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import settings
from src.dynamic_kb.kaia_crawler import KaiaCrawler
from src.dynamic_kb.kaia_detail_crawler import KaiaDetailCrawler
from src.storage.kb_store import KBStore
from src.models.cnt_classification import parse_kaia_field

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def collect_more_technologies(max_pages: int = 20) -> None:
    """KAIA에서 지정기술 목록을 더 많이 수집."""
    store = KBStore()
    crawler = KaiaCrawler()

    existing = store.load_designated_techs()
    existing_numbers = {t["tech_number"] for t in existing}
    logger.info("기존 지정기술: %d건", len(existing))

    new_techs = crawler.fetch_all_technologies(max_pages=max_pages)
    logger.info("KAIA 수집: %d건", len(new_techs))

    # 기존 목록과 병합 (중복 제거)
    from dataclasses import asdict
    merged = list(existing)
    added = 0
    for tech in new_techs:
        tech_dict = asdict(tech)
        if tech_dict["tech_number"] not in existing_numbers:
            merged.append(tech_dict)
            existing_numbers.add(tech_dict["tech_number"])
            added += 1

    logger.info("신규 추가: %d건, 총: %d건", added, len(merged))

    # 저장 (KBStore는 CNTDesignatedTech 타입을 기대하므로 직접 JSON 저장)
    out_path = store.dynamic_dir / "cnt_designated" / "designated_list.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2, default=str)
    logger.info("저장 완료: %s", out_path)


def build_proposals_from_details() -> None:
    """상세 정보가 있는 지정기술로부터 프로포절 데이터셋 생성."""
    store = KBStore()
    techs = store.load_designated_techs()

    # 분류 분포 확인
    field_dist: dict[str, list] = {}
    for t in techs:
        classification = parse_kaia_field(t.get("tech_field", ""))
        if classification:
            major = classification.major.name
            field_dist.setdefault(major, []).append(t)

    print("\n지정기술 분류 분포:")
    for major, items in field_dist.items():
        print(f"  {major}: {len(items)}건")

    # 상세 페이지에서 프로포절 데이터 구축
    detail_crawler = KaiaDetailCrawler()
    proposals_dir = settings.proposals_dir
    proposals_dir.mkdir(parents=True, exist_ok=True)

    # 각 대분류에서 골고루 선택 (최소 10건씩)
    selected = []
    for major, items in field_dist.items():
        for item in items[:15]:
            selected.append(item)

    logger.info("프로포절 대상: %d건", len(selected))

    built = 0
    for tech in selected:
        tech_number = tech.get("tech_number", "")
        detail_url = tech.get("detail_url", "")

        if not detail_url:
            continue

        proposal_path = proposals_dir / f"{tech_number}.json"
        if proposal_path.exists():
            logger.debug("이미 존재: %s", tech_number)
            built += 1
            continue

        try:
            detail = detail_crawler.fetch_detail(detail_url)
            if not detail:
                continue

            proposal = {
                "tech_number": tech_number,
                "tech_name": tech.get("tech_name", ""),
                "tech_field": tech.get("tech_field", ""),
                "applicant": tech.get("applicant", ""),
                "designated_date": tech.get("designated_date", ""),
                "detail": detail,
                "source": "kaia_detail",
            }

            with open(proposal_path, "w", encoding="utf-8") as f:
                json.dump(proposal, f, ensure_ascii=False, indent=2, default=str)

            built += 1
            logger.info("프로포절 생성: %s (%s)", tech_number, tech.get("tech_name", ""))

        except Exception as e:
            logger.error("프로포절 생성 실패 %s: %s", tech_number, e)

    logger.info("프로포절 생성 완료: %d건 (대상 %d건)", built, len(selected))


def print_test_case_status() -> None:
    """테스트 케이스 현황 출력."""
    store = KBStore()
    techs = store.load_designated_techs()
    proposals_dir = settings.proposals_dir

    # 지정기술 분류 분포
    field_dist: dict[str, int] = {}
    for t in techs:
        classification = parse_kaia_field(t.get("tech_field", ""))
        if classification:
            major = classification.major.name
            field_dist[major] = field_dist.get(major, 0) + 1

    # 프로포절 현황
    proposal_count = 0
    if proposals_dir.exists():
        proposal_count = len(list(proposals_dir.glob("*.json")))

    print("\n" + "=" * 50)
    print("  테스트 케이스 현황")
    print("=" * 50)
    print(f"\n  지정기술 총: {len(techs)}건")
    for major, cnt in sorted(field_dist.items()):
        print(f"    {major}: {cnt}건")
    print(f"\n  프로포절 (입력 데이터셋): {proposal_count}건")
    print(f"  목표: 30건 이상 (통계적 유의성)")

    if proposal_count < 30:
        print(f"  부족: {30 - proposal_count}건 추가 필요")
    print("=" * 50)


def main():
    parser = argparse.ArgumentParser(description="테스트 케이스 확장")
    parser.add_argument("--collect", action="store_true",
                        help="지정기술 추가 수집")
    parser.add_argument("--build-proposals", action="store_true",
                        help="프로포절 데이터셋 생성")
    parser.add_argument("--status", action="store_true",
                        help="현황 출력")
    parser.add_argument("--max-pages", type=int, default=20,
                        help="KAIA 최대 수집 페이지 (기본 20)")
    args = parser.parse_args()

    if args.status:
        print_test_case_status()
    elif args.collect:
        collect_more_technologies(args.max_pages)
    elif args.build_proposals:
        build_proposals_from_details()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
