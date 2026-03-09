"""KAIA 건설신기술 목록 크롤링 단독 실행 스크립트.

사용법:
    python scripts/crawl_kaia.py --pages 5
    python scripts/crawl_kaia.py --search "터널"
"""

import argparse
import logging
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.dynamic_kb.kaia_crawler import KaiaCrawler
from src.storage.kb_store import KBStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main():
    parser = argparse.ArgumentParser(description="KAIA 건설신기술 목록 크롤링")
    parser.add_argument("--pages", type=int, default=5, help="크롤링할 최대 페이지 수")
    parser.add_argument("--search", default="", help="검색 키워드 (선택)")
    parser.add_argument("--save", action="store_true", help="결과를 JSON으로 저장")
    args = parser.parse_args()

    crawler = KaiaCrawler()
    techs = crawler.fetch_all_technologies(
        max_pages=args.pages,
        search_keyword=args.search,
    )

    print(f"\n=== 건설신기술 목록: {len(techs)}건 ===\n")
    for i, t in enumerate(techs, 1):
        print(f"[{i}] {t.tech_number} | {t.tech_name}")
        print(f"    신청인: {t.applicant} | 지정일: {t.designation_date}")
        print()

    if args.save and techs:
        store = KBStore()
        path = store.save_designated_techs(techs)
        print(f"저장 완료: {path}")


if __name__ == "__main__":
    main()
