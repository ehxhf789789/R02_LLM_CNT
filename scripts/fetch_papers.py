"""논문 검색 단독 실행 스크립트 (다중 소스 지원).

사용법:
    python scripts/fetch_papers.py "터널 공법" --max 10
    python scripts/fetch_papers.py "교량 거더" --source scholar --max 20
    python scripts/fetch_papers.py "건설 신기술" --source kci --max 10
    python scripts/fetch_papers.py "콘크리트" --source all --max 10

지원 소스: scholar (Semantic Scholar), kci, scienceon, all
"""

import argparse
import logging
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.dynamic_kb.semantic_scholar_client import SemanticScholarClient
from src.dynamic_kb.kci_client import KCIClient
from src.dynamic_kb.scienceon_client import ScienceOnClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def print_records(records, source_name: str):
    """검색 결과를 출력."""
    print(f"\n--- {source_name} ---")
    if not records:
        print("  (결과 없음)")
        return

    for i, r in enumerate(records, 1):
        print(f"[{i}] {r.title}")
        print(f"    저자: {r.authors} | 학술지: {r.journal}")
        print(f"    연도: {r.publish_year} | DOI: {r.doi}")
        print()


def main():
    parser = argparse.ArgumentParser(description="논문 검색 (다중 소스)")
    parser.add_argument("keyword", help="검색 키워드")
    parser.add_argument("--max", type=int, default=10, help="최대 결과 수")
    parser.add_argument(
        "--source",
        choices=["scholar", "kci", "scienceon", "all"],
        default="scholar",
        help="논문 소스 (기본: scholar)",
    )
    args = parser.parse_args()

    print(f"\n=== '{args.keyword}' 논문 검색 (소스: {args.source}, 최대: {args.max}건) ===")

    total = 0

    if args.source in ("scholar", "all"):
        client = SemanticScholarClient()
        records = client.search_construction_papers(args.keyword, max_results=args.max)
        print_records(records, "Semantic Scholar")
        total += len(records)

    if args.source in ("kci", "all"):
        client = KCIClient()
        records = client.search_construction_papers(args.keyword, max_results=args.max)
        print_records(records, "KCI (한국학술지인용색인)")
        total += len(records)

    if args.source in ("scienceon", "all"):
        client = ScienceOnClient()
        records = client.search_construction_papers(args.keyword, max_results=args.max)
        print_records(records, "ScienceON")
        total += len(records)

    print(f"\n=== 총 {total}건 검색 완료 ===")


if __name__ == "__main__":
    main()
