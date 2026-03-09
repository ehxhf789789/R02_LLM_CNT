"""CrossRef API를 활용한 건설 분야 OA 논문 수집.

CrossRef (https://api.crossref.org)는 1.65억+ 메타데이터를 보유한 무료 API.
키 없이 즉시 사용 가능. MDPI(Buildings, CivilEng 등) OA 논문 특화 수집.

수집 전략:
  1. MDPI OA 저널 필터: Buildings(ISSN 2075-5309), Materials(1996-1944) 등
  2. 건설 키워드 검색 + 전문 PDF URL 확보
  3. DOI 기반 중복 제거

사용법:
  py scripts/collect_crossref_papers.py                    # 전체 수집
  py scripts/collect_crossref_papers.py --journal buildings # 특정 저널
  py scripts/collect_crossref_papers.py --keyword "waterproofing"
  py scripts/collect_crossref_papers.py --status           # 현황 확인
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(open(sys.stdout.fileno(), mode='w', encoding='utf-8', closefd=False))],
)
logger = logging.getLogger(__name__)

CROSSREF_BASE = "https://api.crossref.org"
OUTPUT_DIR = Path("data/dynamic/crossref_papers")

# MDPI 건설 관련 OA 저널 ISSN
MDPI_JOURNALS = {
    "buildings": {"issn": "2075-5309", "name": "Buildings", "category": "ARC"},
    "materials": {"issn": "1996-1944", "name": "Materials", "category": "ARC"},
    "sustainability": {"issn": "2071-1050", "name": "Sustainability", "category": "CIV"},
    "applsci": {"issn": "2076-3417", "name": "Applied Sciences", "category": "MEC"},
    "infrastructures": {"issn": "2412-3811", "name": "Infrastructures", "category": "CIV"},
    "civileng": {"issn": "2673-4109", "name": "CivilEng", "category": "CIV"},
    "constrmater": {"issn": "2673-7108", "name": "Construction Materials", "category": "ARC"},
    "jmse": {"issn": "2077-1312", "name": "J. Marine Sci. & Eng.", "category": "CIV"},
    "sensors": {"issn": "1424-8220", "name": "Sensors", "category": "MEC"},
    "remotesensing": {"issn": "2072-4292", "name": "Remote Sensing", "category": "MEC"},
}

# 건설 분야 검색 키워드 (저널별 필터 없이 사용)
CONSTRUCTION_KEYWORDS = {
    "CIV": [
        "bridge construction",
        "tunnel engineering",
        "foundation reinforcement",
        "road pavement technology",
        "seismic retrofit",
        "geotechnical improvement",
        "precast concrete segment",
        "waterway infrastructure",
    ],
    "ARC": [
        "building waterproofing",
        "external insulation system",
        "fire resistant building",
        "modular construction",
        "high strength concrete",
        "seismic isolation building",
        "curtain wall system",
        "composite structural system",
    ],
    "MEC": [
        "construction automation",
        "BIM construction",
        "smart construction monitoring",
        "construction safety IoT",
        "3D printing construction",
        "construction robot",
        "noise barrier construction",
        "HVAC building system",
    ],
}


def create_session() -> requests.Session:
    """CrossRef API 세션."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "CNT-Eval-Framework/1.0 (mailto:cnt-eval@research.kr)",
    })
    return session


def search_crossref(
    session: requests.Session,
    query: str,
    issn: str | None = None,
    from_year: int = 2018,
    rows: int = 50,
    offset: int = 0,
) -> list[dict]:
    """CrossRef API 검색."""
    params: dict = {
        "query": query,
        "rows": min(rows, 100),
        "offset": offset,
        "filter": f"from-pub-date:{from_year}-01-01",
        "select": "DOI,title,author,container-title,published,abstract,"
                  "is-referenced-by-count,subject,URL,link,license",
    }

    if issn:
        params["filter"] += f",issn:{issn}"

    try:
        resp = session.get(f"{CROSSREF_BASE}/works", params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("message", {}).get("items", [])
        time.sleep(1)  # polite rate limiting
        return items
    except requests.RequestException as e:
        logger.error("CrossRef API 요청 실패: %s", e)
        return []


def parse_crossref_item(item: dict) -> dict:
    """CrossRef API 응답 항목을 표준 레코드로 변환."""
    # 제목
    titles = item.get("title", [])
    title = titles[0] if titles else ""

    # 저자
    authors_list = item.get("author", [])
    authors = ", ".join(
        f"{a.get('given', '')} {a.get('family', '')}".strip()
        for a in authors_list[:10]
    )

    # 저널명
    containers = item.get("container-title", [])
    journal = containers[0] if containers else ""

    # 출판 연도
    published = item.get("published", {})
    date_parts = published.get("date-parts", [[]])
    year = str(date_parts[0][0]) if date_parts and date_parts[0] else ""

    # 초록 (HTML 태그 제거)
    abstract = item.get("abstract", "")
    if abstract:
        import re
        abstract = re.sub(r'<[^>]+>', '', abstract).strip()

    # DOI
    doi = item.get("DOI", "")

    # PDF URL (OA 링크)
    pdf_url = ""
    for link in item.get("link", []):
        if link.get("content-type", "") == "application/pdf":
            pdf_url = link.get("URL", "")
            break

    # OA 라이선스 확인
    is_oa = False
    for lic in item.get("license", []):
        url = lic.get("URL", "")
        if "creativecommons" in url:
            is_oa = True
            break

    return {
        "doi": doi,
        "title": title,
        "authors": authors,
        "journal": journal,
        "publish_year": year,
        "abstract": abstract,
        "keywords": item.get("subject", []),
        "citation_count": item.get("is-referenced-by-count", 0),
        "url": item.get("URL", ""),
        "pdf_url": pdf_url,
        "is_oa": is_oa,
        "source": "crossref",
    }


def collect_journal_papers(
    session: requests.Session,
    journal_key: str,
    keywords: list[str],
    max_per_keyword: int = 30,
) -> list[dict]:
    """특정 저널에서 건설 관련 논문 수집."""
    journal_info = MDPI_JOURNALS.get(journal_key)
    if not journal_info:
        return []

    issn = journal_info["issn"]
    all_records = []
    seen_dois: set[str] = set()

    for kw in keywords:
        items = search_crossref(session, kw, issn=issn, rows=max_per_keyword)

        for item in items:
            record = parse_crossref_item(item)
            if record["doi"] in seen_dois:
                continue
            if not record["abstract"] or len(record["abstract"]) < 30:
                continue
            seen_dois.add(record["doi"])
            all_records.append(record)

        logger.info(
            "[%s] '%s': %d건 (누적 %d건)",
            journal_info["name"], kw, len(items), len(all_records),
        )

    return all_records


def collect_all(
    journals: list[str] | None = None,
    categories: list[str] | None = None,
    max_per_keyword: int = 30,
) -> dict:
    """전체 수집."""
    session = create_session()
    target_journals = journals or list(MDPI_JOURNALS.keys())
    target_cats = categories or ["CIV", "ARC", "MEC"]

    stats: dict[str, int] = {}

    for journal_key in target_journals:
        journal_info = MDPI_JOURNALS.get(journal_key)
        if not journal_info:
            continue

        cat = journal_info["category"]
        if cat not in target_cats:
            continue

        # 해당 카테고리 키워드 사용
        keywords = CONSTRUCTION_KEYWORDS.get(cat, [])

        records = collect_journal_papers(
            session, journal_key, keywords, max_per_keyword,
        )

        if records:
            out_dir = OUTPUT_DIR / cat
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{journal_key}.json"

            # 기존 데이터와 병합
            existing = []
            existing_dois: set[str] = set()
            if out_path.exists():
                with open(out_path, encoding="utf-8") as f:
                    existing = json.load(f)
                    existing_dois = {r.get("doi", "") for r in existing}

            new_records = [r for r in records if r["doi"] not in existing_dois]
            merged = existing + new_records

            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)

            stats[journal_key] = len(new_records)
            logger.info(
                "%s/%s: %d건 신규 (총 %d건)",
                cat, journal_info["name"], len(new_records), len(merged),
            )
        else:
            stats[journal_key] = 0

    return stats


def collect_keyword_search(
    category: str,
    max_per_keyword: int = 30,
) -> int:
    """저널 필터 없이 키워드 검색으로 OA 논문 수집."""
    session = create_session()
    keywords = CONSTRUCTION_KEYWORDS.get(category, [])
    if not keywords:
        return 0

    out_dir = OUTPUT_DIR / category
    out_dir.mkdir(parents=True, exist_ok=True)

    # 기존 DOI 수집
    existing_dois: set[str] = set()
    for f in out_dir.glob("*.json"):
        try:
            with open(f, encoding="utf-8") as fp:
                for r in json.load(fp):
                    doi = r.get("doi", "")
                    if doi:
                        existing_dois.add(doi)
        except Exception:
            pass

    total_added = 0

    for kw in keywords:
        safe_kw = kw.replace(" ", "_")[:40]
        out_path = out_dir / f"kw_{safe_kw}.json"

        if out_path.exists():
            logger.info("스킵 (이미 수집): %s", kw)
            continue

        items = search_crossref(session, kw, rows=max_per_keyword)

        new_records = []
        for item in items:
            record = parse_crossref_item(item)
            if record["doi"] in existing_dois:
                continue
            if not record["abstract"] or len(record["abstract"]) < 30:
                continue
            existing_dois.add(record["doi"])
            new_records.append(record)

        if new_records:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(new_records, f, ensure_ascii=False, indent=2)
            logger.info("[%s] '%s': %d건 저장", category, kw, len(new_records))
            total_added += len(new_records)
        else:
            logger.info("[%s] '%s': 새 논문 없음", category, kw)

    return total_added


def show_status():
    """수집 현황."""
    print("\n=== CrossRef 논문 수집 현황 ===\n")

    for cat in ["CIV", "ARC", "MEC"]:
        cat_dir = OUTPUT_DIR / cat
        if not cat_dir.exists():
            print(f"{cat}: 데이터 없음")
            continue

        total = 0
        with_abs = 0
        with_pdf = 0
        oa_count = 0

        for f in cat_dir.glob("*.json"):
            with open(f, encoding="utf-8") as fp:
                records = json.load(fp)
            for r in records:
                total += 1
                if r.get("abstract") and len(r.get("abstract", "")) > 30:
                    with_abs += 1
                if r.get("pdf_url"):
                    with_pdf += 1
                if r.get("is_oa"):
                    oa_count += 1

        print(f"{cat}: {total}건 (초록 {with_abs}, PDF URL {with_pdf}, OA {oa_count})")


def main():
    parser = argparse.ArgumentParser(description="CrossRef/MDPI OA 논문 수집")
    parser.add_argument("--journal", type=str, help="특정 저널 (buildings, materials 등)")
    parser.add_argument("--category", type=str, help="카테고리 (CIV, ARC, MEC)")
    parser.add_argument("--keyword", type=str, help="특정 키워드 검색")
    parser.add_argument("--max-per-keyword", type=int, default=30, help="키워드당 최대")
    parser.add_argument("--keyword-search", action="store_true", help="저널 필터 없이 키워드 검색")
    parser.add_argument("--status", action="store_true", help="현황 확인")
    args = parser.parse_args()

    if args.status:
        show_status()
    elif args.keyword_search:
        cats = [args.category] if args.category else ["CIV", "ARC", "MEC"]
        for cat in cats:
            added = collect_keyword_search(cat, args.max_per_keyword)
            logger.info("%s: %d건 추가", cat, added)
    else:
        journals = [args.journal] if args.journal else None
        categories = [args.category] if args.category else None
        collect_all(
            journals=journals,
            categories=categories,
            max_per_keyword=args.max_per_keyword,
        )


if __name__ == "__main__":
    main()
