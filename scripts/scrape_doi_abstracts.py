"""DOI 기반 출판사 페이지에서 초록 스크래핑 (방안 B).

Scholar 논문 중 DOI가 있으나 초록이 없는 118건에 대해
출판사 페이지에서 초록을 추출한다.

사용법:
  py scripts/scrape_doi_abstracts.py
  py scripts/scrape_doi_abstracts.py --category CIV
  py scripts/scrape_doi_abstracts.py --status
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(open(sys.stdout.fileno(), mode='w', encoding='utf-8', closefd=False))],
)
logger = logging.getLogger(__name__)


def extract_doi(record: dict) -> str:
    """레코드에서 DOI를 추출."""
    doi = record.get("doi", "")
    if doi:
        return doi
    raw = record.get("raw", {})
    if isinstance(raw, dict):
        ext = raw.get("externalIds", {})
        if isinstance(ext, dict):
            return ext.get("DOI", "")
    return ""


def fetch_abstract_from_doi(session: requests.Session, doi: str) -> str:
    """DOI 리다이렉트 → 출판사 페이지에서 초록 추출."""
    url = f"https://doi.org/{doi}"
    try:
        resp = session.get(url, timeout=30, allow_redirects=True)
        if resp.status_code != 200:
            return ""
    except requests.RequestException as e:
        logger.debug("DOI 요청 실패 %s: %s", doi, e)
        return ""

    soup = BeautifulSoup(resp.text, "lxml")

    # 패턴 1: meta description / citation_abstract
    for meta_name in ["citation_abstract", "DC.description", "description", "og:description"]:
        meta = soup.find("meta", attrs={"name": meta_name}) or soup.find("meta", attrs={"property": meta_name})
        if meta and meta.get("content"):
            text = meta["content"].strip()
            if len(text) > 50:
                return text

    # 패턴 2: abstract 클래스/id/itemprop
    for selector in [
        {"class_": re.compile(r"abstract", re.I)},
        {"id": re.compile(r"abstract", re.I)},
        {"itemprop": "description"},
    ]:
        el = soup.find(["div", "section", "p", "span"], selector)
        if el:
            text = el.get_text(separator=" ", strip=True)
            # "Abstract" 헤더 제거
            text = re.sub(r'^Abstract\s*', '', text, flags=re.I).strip()
            if len(text) > 50:
                return text[:3000]

    # 패턴 3: JATS abstract (Elsevier, Springer 등)
    abstract_el = soup.find("div", class_=re.compile(r"abstract|summary", re.I))
    if abstract_el:
        # 제목 태그 제거
        for h in abstract_el.find_all(["h2", "h3", "h4"]):
            h.decompose()
        text = abstract_el.get_text(separator=" ", strip=True)
        if len(text) > 50:
            return text[:3000]

    return ""


def enrich_scholar_with_doi(
    category: str | None = None,
    max_total: int = 200,
) -> dict:
    """DOI가 있는 Scholar 논문의 초록을 출판사 페이지에서 수집."""
    scholar_dir = PROJECT_ROOT / "data" / "dynamic" / "scholar_papers"
    categories = [category] if category else ["CIV", "ARC", "MEC"]

    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
    })

    stats = {"scanned": 0, "enriched": 0, "failed": 0, "no_doi": 0, "skipped": 0}
    total_enriched = 0

    for cat in categories:
        cat_dir = scholar_dir / cat
        if not cat_dir.exists():
            continue

        for f in sorted(cat_dir.glob("*.json")):
            if total_enriched >= max_total:
                break

            with open(f, encoding="utf-8") as fp:
                records = json.load(fp)

            modified = False
            for record in records:
                if total_enriched >= max_total:
                    break

                stats["scanned"] += 1

                # 이미 초록이 있으면 스킵
                if record.get("abstract") and len(record.get("abstract", "")) > 30:
                    stats["skipped"] += 1
                    continue

                doi = extract_doi(record)
                if not doi:
                    stats["no_doi"] += 1
                    continue

                abstract = fetch_abstract_from_doi(session, doi)
                if abstract and len(abstract) > 50:
                    record["abstract"] = abstract
                    record["abstract_source"] = "doi_scrape"
                    stats["enriched"] += 1
                    total_enriched += 1
                    modified = True
                    logger.info("  초록 추가: %s (%d자)", doi, len(abstract))
                else:
                    stats["failed"] += 1

                time.sleep(2)

            if modified:
                with open(f, "w", encoding="utf-8") as fp:
                    json.dump(records, fp, ensure_ascii=False, indent=2)

    logger.info("DOI 초록 스크래핑 완료: %s", stats)
    return stats


def show_status():
    """DOI 보유 현황."""
    scholar_dir = PROJECT_ROOT / "data" / "dynamic" / "scholar_papers"
    for cat in ["CIV", "ARC", "MEC"]:
        cat_dir = scholar_dir / cat
        if not cat_dir.exists():
            continue
        total = 0; no_abs = 0; no_abs_with_doi = 0
        for f in cat_dir.glob("*.json"):
            with open(f, encoding="utf-8") as fp:
                records = json.load(fp)
            for r in records:
                total += 1
                ab = r.get("abstract", "")
                if not ab or len(ab) < 30:
                    no_abs += 1
                    doi = extract_doi(r)
                    if doi:
                        no_abs_with_doi += 1
        print(f"{cat}: {total}건 (초록 미보유 {no_abs}건, DOI 있음 {no_abs_with_doi}건)")


def main():
    parser = argparse.ArgumentParser(description="DOI 기반 초록 스크래핑")
    parser.add_argument("--category", type=str, help="카테고리")
    parser.add_argument("--max", type=int, default=200, help="최대 건수")
    parser.add_argument("--status", action="store_true", help="현황")
    args = parser.parse_args()

    if args.status:
        show_status()
    else:
        enrich_scholar_with_doi(category=args.category, max_total=args.max)


if __name__ == "__main__":
    main()
