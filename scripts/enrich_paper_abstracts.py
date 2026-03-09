"""Semantic Scholar 영문 키워드 검색으로 논문 초록 보강.

기존 논문 데이터에서 초록이 없는 건을 보완하기 위해,
영문 키워드로 추가 검색하여 초록이 있는 논문을 수집한다.

사용법:
  py scripts/enrich_paper_abstracts.py              # 전체 카테고리
  py scripts/enrich_paper_abstracts.py --category CIV
  py scripts/enrich_paper_abstracts.py --status
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

from src.dynamic_kb.semantic_scholar_client import SemanticScholarClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(open(sys.stdout.fileno(), mode='w', encoding='utf-8', closefd=False))],
)
logger = logging.getLogger(__name__)

# 영문 키워드 매핑 (카테고리별)
ENGLISH_KEYWORDS = {
    "CIV": [
        "bridge construction technology Korea",
        "tunnel construction method",
        "road pavement engineering",
        "PHC pile foundation construction",
        "FRP reinforcement concrete bridge",
        "river levee embankment Korea",
        "port caisson construction",
        "retaining wall earth pressure",
        "underground structure waterproofing",
        "precast concrete segment tunnel",
        "steel bridge deck plate",
        "soil improvement ground reinforcement",
        "seismic retrofit bridge Korea",
        "prestressed concrete girder",
        "geosynthetic reinforced earth",
    ],
    "ARC": [
        "building waterproofing membrane Korea",
        "reinforced concrete construction method",
        "temporary scaffolding formwork",
        "steel structure connection joint",
        "external insulation system building",
        "precast concrete building Korea",
        "seismic retrofitting building",
        "curtain wall facade engineering",
        "fire resistant structure Korea",
        "modular construction prefabricated",
        "high strength concrete building",
        "composite slab deck plate",
    ],
    "MEC": [
        "construction IoT sensor monitoring",
        "construction robot automation",
        "BIM building information modeling",
        "construction machinery equipment",
        "noise reduction barrier construction",
        "water treatment facility Korea",
        "HVAC mechanical engineering building",
        "smart construction technology",
        "drone construction survey",
        "3D printing construction",
    ],
}


def collect_english_papers(category: str, max_per_keyword: int = 20) -> int:
    """영문 키워드로 논문 검색하여 저장."""
    client = SemanticScholarClient()
    output_dir = Path("data/dynamic/scholar_papers") / category
    output_dir.mkdir(parents=True, exist_ok=True)

    # 기존 paper_id 수집 (중복 방지)
    existing_ids = set()
    for f in output_dir.glob("*.json"):
        try:
            with open(f, encoding="utf-8") as fp:
                records = json.load(fp)
            for r in records:
                pid = r.get("paper_id", r.get("paperId", ""))
                if pid:
                    existing_ids.add(pid)
        except Exception:
            pass

    keywords = ENGLISH_KEYWORDS.get(category, [])
    total_added = 0

    for kw in keywords:
        safe_kw = kw.replace(" ", "_")[:40]
        out_path = output_dir / f"en_{safe_kw}.json"

        # 이미 수집된 키워드 스킵
        if out_path.exists():
            logger.info("스킵 (이미 수집): %s", kw)
            continue

        logger.info("검색: %s", kw)
        try:
            records = client.search_construction_papers(kw, max_results=max_per_keyword)
        except Exception as e:
            logger.error("검색 실패 %s: %s", kw, e)
            time.sleep(30)
            continue

        # 초록이 있는 논문만 필터 + 중복 제거
        new_records = []
        for r in records:
            if not r.abstract or len(r.abstract) < 30:
                continue
            if r.paper_id in existing_ids:
                continue
            existing_ids.add(r.paper_id)
            new_records.append(asdict(r))

        if new_records:
            # raw 필드 제거 (저장 공간)
            for nr in new_records:
                nr.pop("raw", None)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(new_records, f, ensure_ascii=False, indent=2)
            logger.info("  → %d건 저장 (초록 있는 논문)", len(new_records))
            total_added += len(new_records)
        else:
            logger.info("  → 새로운 초록 있는 논문 없음")

        time.sleep(5)  # Rate limiting

    return total_added


def show_status():
    """논문 초록 보유 현황."""
    papers_dir = Path("data/dynamic/scholar_papers")
    for cat in ["CIV", "ARC", "MEC"]:
        cat_dir = papers_dir / cat
        if not cat_dir.exists():
            continue
        total = 0
        with_abs = 0
        for f in cat_dir.glob("*.json"):
            with open(f, encoding="utf-8") as fp:
                records = json.load(fp)
            for r in records:
                total += 1
                ab = r.get("abstract", "")
                if ab and len(ab) > 30:
                    with_abs += 1
        pct = with_abs / max(total, 1) * 100
        print(f"{cat}: {with_abs}/{total} ({pct:.1f}%) 초록 보유")


def main():
    parser = argparse.ArgumentParser(description="논문 초록 보강 (영문 키워드)")
    parser.add_argument("--category", type=str, help="카테고리 (CIV, ARC, MEC)")
    parser.add_argument("--max-per-keyword", type=int, default=20, help="키워드당 최대")
    parser.add_argument("--status", action="store_true", help="현황 확인")
    args = parser.parse_args()

    if args.status:
        show_status()
    else:
        categories = [args.category] if args.category else ["CIV", "ARC", "MEC"]
        total = 0
        for cat in categories:
            added = collect_english_papers(cat, max_per_keyword=args.max_per_keyword)
            total += added
            logger.info("%s: %d건 추가", cat, added)
        logger.info("전체 추가: %d건", total)


if __name__ == "__main__":
    main()
