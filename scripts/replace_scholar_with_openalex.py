"""초록 없는 Scholar 논문을 OpenAlex 논문으로 대체 (방안 C).

Scholar에서 초록이 없는 논문을 제거하고,
동일 분야의 OpenAlex 논문(100% 초록 보유)으로 대체한다.

사용법:
  py scripts/replace_scholar_with_openalex.py
  py scripts/replace_scholar_with_openalex.py --status
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.dynamic_kb.openalex_client import OpenAlexClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(open(sys.stdout.fileno(), mode='w', encoding='utf-8', closefd=False))],
)
logger = logging.getLogger(__name__)

# 카테고리별 보충 검색 키워드
SUPPLEMENT_KEYWORDS = {
    "CIV": [
        "construction technology innovation civil",
        "bridge reinforcement new method",
        "tunnel construction safety improvement",
        "road pavement durability enhancement",
        "geotechnical engineering foundation Korea",
        "seismic design infrastructure resilience",
        "waterway dam construction management",
    ],
    "ARC": [
        "building construction innovation method",
        "structural retrofit seismic performance",
        "energy efficient building envelope",
        "prefabricated modular construction",
        "fire resistant building material",
        "smart building construction automation",
    ],
    "MEC": [
        "construction equipment automation robot",
        "HVAC system energy efficiency building",
        "smart construction IoT monitoring",
        "noise vibration control construction",
        "green construction environmental technology",
        "3D printing construction material",
    ],
}


def replace_and_supplement() -> dict:
    """초록 없는 Scholar 논문 제거 + OpenAlex로 대체."""
    scholar_dir = PROJECT_ROOT / "data" / "dynamic" / "scholar_papers"
    openalex_dir = PROJECT_ROOT / "data" / "dynamic" / "openalex_papers"

    client = OpenAlexClient()
    stats = {"removed": 0, "added": 0}

    for cat in ["CIV", "ARC", "MEC"]:
        cat_dir = scholar_dir / cat
        if not cat_dir.exists():
            continue

        # 1단계: 초록 없는 논문 제거
        removed_in_cat = 0
        for f in sorted(cat_dir.glob("*.json")):
            with open(f, encoding="utf-8") as fp:
                records = json.load(fp)

            original_count = len(records)
            filtered = [r for r in records if r.get("abstract") and len(r.get("abstract", "")) > 30]
            removed = original_count - len(filtered)

            if removed > 0:
                with open(f, "w", encoding="utf-8") as fp:
                    json.dump(filtered, fp, ensure_ascii=False, indent=2)
                logger.info("  %s/%s: %d건 제거 (%d → %d)", cat, f.name, removed, original_count, len(filtered))
                removed_in_cat += removed

        stats["removed"] += removed_in_cat
        logger.info("%s: %d건 초록 없는 논문 제거", cat, removed_in_cat)

        # 2단계: OpenAlex에서 보충 수집 (제거된 수만큼)
        if removed_in_cat <= 0:
            continue

        target = removed_in_cat
        keywords = SUPPLEMENT_KEYWORDS.get(cat, [])
        added = 0

        # 기존 OpenAlex 논문 ID 수집 (중복 방지)
        existing_ids = set()
        oa_cat_dir = openalex_dir / cat
        if oa_cat_dir.exists():
            for f in oa_cat_dir.rglob("*.json"):
                with open(f, encoding="utf-8") as fp:
                    data = json.load(fp)
                for r in data:
                    oid = r.get("openalex_id", r.get("id", ""))
                    if oid:
                        existing_ids.add(oid)

        # 보충용 디렉토리
        supplement_dir = oa_cat_dir / "supplement"
        supplement_dir.mkdir(parents=True, exist_ok=True)

        for kw in keywords:
            if added >= target:
                break

            remaining = target - added
            try:
                records = client.search_construction_papers(
                    kw, max_results=min(remaining + 10, 50), from_year=2015,
                )
            except Exception as e:
                logger.error("OpenAlex 검색 실패 %s: %s", kw, e)
                continue

            # 필터: 초록 있는 것만 + 중복 제거
            new_records = []
            for r in records:
                if not r.abstract or len(r.abstract) < 30:
                    continue
                if r.openalex_id in existing_ids:
                    continue
                existing_ids.add(r.openalex_id)
                new_records.append(asdict(r))

            if new_records:
                safe_kw = kw.replace(" ", "_")[:40]
                out_path = supplement_dir / f"supplement_{safe_kw}.json"
                # raw 필드 제거
                for nr in new_records:
                    nr.pop("raw", None)
                with open(out_path, "w", encoding="utf-8") as fp:
                    json.dump(new_records, fp, ensure_ascii=False, indent=2)
                added += len(new_records)
                logger.info("  OpenAlex 보충: %s → %d건", kw, len(new_records))

        stats["added"] += added
        logger.info("%s: %d건 OpenAlex 보충 완료", cat, added)

    logger.info("대체 완료: %d건 제거, %d건 보충", stats["removed"], stats["added"])
    return stats


def show_status():
    """현황."""
    scholar_dir = PROJECT_ROOT / "data" / "dynamic" / "scholar_papers"
    for cat in ["CIV", "ARC", "MEC"]:
        cat_dir = scholar_dir / cat
        if not cat_dir.exists():
            continue
        total = 0; no_abs = 0
        for f in cat_dir.glob("*.json"):
            with open(f, encoding="utf-8") as fp:
                records = json.load(fp)
            for r in records:
                total += 1
                ab = r.get("abstract", "")
                if not ab or len(ab) < 30:
                    no_abs += 1
        print(f"{cat}: {total}건 (초록 미보유 {no_abs}건 → 제거 대상)")


def main():
    parser = argparse.ArgumentParser(description="Scholar 초록 없는 논문 → OpenAlex 대체")
    parser.add_argument("--status", action="store_true", help="현황")
    args = parser.parse_args()

    if args.status:
        show_status()
    else:
        replace_and_supplement()


if __name__ == "__main__":
    main()
