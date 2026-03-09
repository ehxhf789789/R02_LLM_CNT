"""최근 5년(2021~) 논문 추가 수집 (OpenAlex + CrossRef 보강).

기존 수집의 최근 5년 비중을 높이기 위해
OpenAlex(from_year=2021)와 CrossRef(from_date=2021)로 추가 수집한다.

사용법:
  py scripts/collect_recent_papers.py
  py scripts/collect_recent_papers.py --source openalex
  py scripts/collect_recent_papers.py --source crossref
  py scripts/collect_recent_papers.py --status
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.dynamic_kb.openalex_client import OpenAlexClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(open(sys.stdout.fileno(), mode='w', encoding='utf-8', closefd=False))],
)
logger = logging.getLogger(__name__)

# 최신 트렌드 키워드 (2021~2026 기술 동향)
RECENT_KEYWORDS = {
    "CIV": [
        "digital twin bridge monitoring 2023",
        "3D printing concrete construction",
        "carbon neutral infrastructure",
        "drone inspection bridge tunnel",
        "AI structural health monitoring",
        "autonomous construction equipment",
        "smart road pavement sensor",
        "green infrastructure climate resilience",
        "prefabricated rapid bridge construction",
        "robotic concrete placement",
        "BIM construction management automation",
        "offshore wind turbine foundation",
    ],
    "ARC": [
        "zero energy building construction",
        "modular offsite construction 2023",
        "digital twin building management",
        "passive house retrofit",
        "3D printed building components",
        "AI building energy optimization",
        "green remodeling carbon reduction",
        "smart waterproofing membrane",
        "robotic welding construction",
        "mass timber construction CLT",
    ],
    "MEC": [
        "construction robot automation 2023",
        "IoT construction safety wearable",
        "autonomous excavator machine learning",
        "electric construction equipment",
        "digital safety management construction",
        "AI construction project management",
        "virtual reality construction training",
        "construction big data analytics",
        "smart construction platform cloud",
        "drone lidar construction survey",
    ],
}

CROSSREF_BASE = "https://api.crossref.org/works"
CROSSREF_KEYWORDS = {
    "CIV": [
        "smart bridge monitoring", "3D concrete printing", "carbon neutral construction",
        "autonomous construction", "BIM infrastructure", "digital twin civil",
    ],
    "ARC": [
        "zero energy building", "modular construction", "3D printing architecture",
        "green building retrofit", "smart building automation",
    ],
    "MEC": [
        "construction robot", "IoT safety construction", "electric construction equipment",
        "AI construction management", "drone construction survey",
    ],
}


def collect_openalex_recent(
    category: str | None = None,
    max_per_category: int = 300,
) -> dict:
    """OpenAlex에서 2021+ 논문 추가 수집."""
    client = OpenAlexClient()
    categories = [category] if category else ["CIV", "ARC", "MEC"]
    stats = {}

    for cat in categories:
        # 기존 OpenAlex ID 수집 (중복 방지)
        existing_ids = set()
        oa_dir = PROJECT_ROOT / "data" / "dynamic" / "openalex_papers" / cat
        if oa_dir.exists():
            for f in oa_dir.rglob("*.json"):
                with open(f, encoding="utf-8") as fp:
                    data = json.load(fp)
                for r in data:
                    oid = r.get("openalex_id", "")
                    if oid:
                        existing_ids.add(oid)

        logger.info("=== %s OpenAlex 최근 논문 수집 (기존 %d건 제외) ===", cat, len(existing_ids))

        keywords = RECENT_KEYWORDS.get(cat, [])
        recent_records = []

        for kw in keywords:
            if len(recent_records) >= max_per_category:
                break

            try:
                records = client.search_construction_papers(
                    kw, max_results=50, from_year=2021, oa_only=False,
                )
            except Exception as e:
                logger.error("  검색 실패 %s: %s", kw, e)
                continue

            new_count = 0
            for r in records:
                if not r.abstract or len(r.abstract) < 30:
                    continue
                if r.openalex_id in existing_ids:
                    continue

                # 연도 확인
                try:
                    yr = int(r.publish_year)
                    if yr < 2021:
                        continue
                except (ValueError, TypeError):
                    continue

                existing_ids.add(r.openalex_id)
                record = asdict(r)
                record.pop("raw", None)
                recent_records.append(record)
                new_count += 1

            if new_count > 0:
                logger.info("  %s: +%d건", kw[:40], new_count)

            time.sleep(0.5)

        # 저장
        if recent_records:
            out_dir = oa_dir / "recent_2021"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / "recent_collection.json"

            existing = []
            if out_path.exists():
                with open(out_path, encoding="utf-8") as f:
                    existing = json.load(f)

            merged = existing + recent_records
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)

            logger.info("%s: %d건 저장 (누적 %d건)", cat, len(recent_records), len(merged))

        stats[cat] = len(recent_records)

    return stats


def collect_crossref_recent(
    category: str | None = None,
    max_per_category: int = 200,
) -> dict:
    """CrossRef에서 2021+ 논문 추가 수집."""
    categories = [category] if category else ["CIV", "ARC", "MEC"]
    stats = {}

    session = requests.Session()
    session.headers.update({
        "User-Agent": "R02_LLM_CNT/1.0 (mailto:research@example.com)",
    })

    for cat in categories:
        # 기존 DOI 수집 (중복 방지)
        existing_dois = set()
        cr_dir = PROJECT_ROOT / "data" / "dynamic" / "crossref_papers" / cat
        if cr_dir.exists():
            for f in cr_dir.glob("*.json"):
                with open(f, encoding="utf-8") as fp:
                    data = json.load(fp)
                for r in data:
                    doi = r.get("doi", "")
                    if doi:
                        existing_dois.add(doi.lower())

        logger.info("=== %s CrossRef 최근 논문 수집 (기존 %d건 제외) ===", cat, len(existing_dois))

        keywords = CROSSREF_KEYWORDS.get(cat, [])
        recent_records = []

        for kw in keywords:
            if len(recent_records) >= max_per_category:
                break

            params = {
                "query": kw,
                "filter": "from-pub-date:2021-01-01,type:journal-article",
                "rows": 50,
                "sort": "published",
                "order": "desc",
                "select": "DOI,title,author,published-print,published-online,abstract,container-title,is-referenced-by-count",
            }

            try:
                resp = session.get(CROSSREF_BASE, params=params, timeout=30)
                if resp.status_code != 200:
                    logger.warning("  CrossRef HTTP %d: %s", resp.status_code, kw)
                    continue
                data = resp.json()
            except Exception as e:
                logger.error("  CrossRef 실패 %s: %s", kw, e)
                continue

            items = data.get("message", {}).get("items", [])
            new_count = 0

            for item in items:
                doi = item.get("DOI", "")
                if doi.lower() in existing_dois:
                    continue

                abstract = item.get("abstract", "")
                if not abstract or len(abstract) < 30:
                    continue

                # HTML 태그 제거
                import re
                abstract = re.sub(r'<[^>]+>', '', abstract).strip()

                title_parts = item.get("title", [])
                title = title_parts[0] if title_parts else ""

                # 연도 추출
                pub_date = item.get("published-print", item.get("published-online", {}))
                date_parts = pub_date.get("date-parts", [[None]])
                year = date_parts[0][0] if date_parts and date_parts[0] else None
                if not year or year < 2021:
                    continue

                # 저자
                authors = ", ".join(
                    f"{a.get('family', '')} {a.get('given', '')}"
                    for a in item.get("author", [])[:5]
                )

                journal = item.get("container-title", [""])[0] if item.get("container-title") else ""

                existing_dois.add(doi.lower())
                recent_records.append({
                    "doi": doi,
                    "title": title,
                    "authors": authors,
                    "abstract": abstract,
                    "publish_year": str(year),
                    "journal": journal,
                    "citation_count": item.get("is-referenced-by-count", 0),
                    "source": "crossref",
                })
                new_count += 1

            if new_count > 0:
                logger.info("  %s: +%d건", kw[:40], new_count)

            time.sleep(1)

        # 저장
        if recent_records:
            cr_dir.mkdir(parents=True, exist_ok=True)
            out_path = cr_dir / "recent_2021_collection.json"

            existing = []
            if out_path.exists():
                with open(out_path, encoding="utf-8") as f:
                    existing = json.load(f)

            merged = existing + recent_records
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)

            logger.info("%s: %d건 저장 (누적 %d건)", cat, len(recent_records), len(merged))

        stats[cat] = len(recent_records)

    return stats


def show_status():
    """연도별 논문 분포 현황."""
    for source, dir_name in [("OpenAlex", "openalex_papers"), ("CrossRef", "crossref_papers"), ("Scholar", "scholar_papers")]:
        base_dir = PROJECT_ROOT / "data" / "dynamic" / dir_name
        if not base_dir.exists():
            continue
        print(f"\n=== {source} ===")
        for cat in ["CIV", "ARC", "MEC"]:
            cat_dir = base_dir / cat
            if not cat_dir.exists():
                continue
            total = 0; recent = 0
            for f in cat_dir.rglob("*.json"):
                with open(f, encoding="utf-8") as fp:
                    data = json.load(fp)
                for r in data:
                    total += 1
                    yr = r.get("publish_year", r.get("year", ""))
                    try:
                        if int(yr) >= 2021:
                            recent += 1
                    except (ValueError, TypeError):
                        pass
            pct = recent / max(total, 1) * 100
            print(f"  {cat}: {total}건 (2021+: {recent}건, {pct:.1f}%)")


def main():
    parser = argparse.ArgumentParser(description="최근 5년 논문 추가 수집")
    parser.add_argument("--source", type=str, choices=["openalex", "crossref", "all"], default="all")
    parser.add_argument("--category", type=str, help="카테고리")
    parser.add_argument("--max", type=int, default=300, help="카테고리당 최대 건수")
    parser.add_argument("--status", action="store_true", help="현황")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    if args.source in ("openalex", "all"):
        logger.info("=== OpenAlex 최근 논문 수집 ===")
        stats = collect_openalex_recent(category=args.category, max_per_category=args.max)
        logger.info("OpenAlex 완료: %s", stats)

    if args.source in ("crossref", "all"):
        logger.info("=== CrossRef 최근 논문 수집 ===")
        stats = collect_crossref_recent(category=args.category, max_per_category=args.max)
        logger.info("CrossRef 완료: %s", stats)


if __name__ == "__main__":
    main()
