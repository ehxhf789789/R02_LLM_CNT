"""KIPRIS 특허 검색 단독 실행 스크립트.

특정 키워드로 특허를 검색하여 결과를 확인한다.

사용법:
    python scripts/fetch_patents.py "연약지반 처리" --max 10
"""

import argparse
import json
import logging
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.dynamic_kb.kipris_client import KiprisClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main():
    parser = argparse.ArgumentParser(description="KIPRIS 특허 검색")
    parser.add_argument("keyword", help="검색 키워드")
    parser.add_argument("--max", type=int, default=10, help="최대 결과 수")
    args = parser.parse_args()

    client = KiprisClient()
    records = client.search_construction_patents(args.keyword, max_results=args.max)

    print(f"\n=== '{args.keyword}' 검색 결과: {len(records)}건 ===\n")
    for i, r in enumerate(records, 1):
        print(f"[{i}] {r.title}")
        print(f"    출원번호: {r.application_number} | 출원일: {r.application_date}")
        print(f"    출원인: {r.applicant_name} | IPC: {r.ipc_number}")
        print()


if __name__ == "__main__":
    main()
