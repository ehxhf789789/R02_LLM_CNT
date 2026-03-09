"""Semantic Scholar / CrossRef API를 통해 누락된 논문 초록을 채움.

기존 수집된 논문 중 초록이 없거나 30자 미만인 건에 대해:
1) Semantic Scholar paper detail API로 초록 조회
2) 실패 시, DOI가 있으면 CrossRef API로 초록 조회
3) 결과를 원본 JSON에 in-place 업데이트

사용법:
  py scripts/fill_scholar_abstracts.py                     # 전체 실행
  py scripts/fill_scholar_abstracts.py --status            # 현황 확인만
  py scripts/fill_scholar_abstracts.py --category CIV      # 특정 카테고리만
  py scripts/fill_scholar_abstracts.py --max 100           # 최대 처리 건수 제한
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import re
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(open(sys.stdout.fileno(), mode="w", encoding="utf-8", closefd=False))],
)
logger = logging.getLogger(__name__)

SCHOLAR_DETAIL_URL = "https://api.semanticscholar.org/graph/v1/paper/{paper_id}"
CROSSREF_URL = "https://api.crossref.org/works/{doi}"

SCHOLAR_DELAY = 3.0   # Semantic Scholar rate limit 대응
CROSSREF_DELAY = 1.0  # CrossRef는 비교적 여유

PAPERS_DIR = PROJECT_ROOT / "data" / "dynamic" / "scholar_papers"
CATEGORIES = ["CIV", "ARC", "MEC"]


def _strip_html_tags(text: str) -> str:
    """CrossRef 초록에 포함된 HTML 태그 제거."""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def _has_abstract(record: dict) -> bool:
    """초록이 유효한지 확인 (30자 이상)."""
    ab = record.get("abstract", "") or ""
    return len(ab) >= 30


def _get_doi(record: dict) -> str:
    """레코드에서 DOI를 추출."""
    doi = record.get("doi", "")
    if doi:
        return doi
    raw = record.get("raw") or {}
    ext_ids = raw.get("externalIds") or {}
    return ext_ids.get("DOI", "")


def fetch_abstract_from_scholar(session: requests.Session, paper_id: str) -> str | None:
    """Semantic Scholar paper detail API에서 초록 조회."""
    url = SCHOLAR_DETAIL_URL.format(paper_id=paper_id)
    try:
        resp = session.get(url, params={"fields": "abstract,title"}, timeout=30)

        # 429 재시도 (최대 2회, 점진적 백오프)
        for wait in [10, 30]:
            if resp.status_code != 429:
                break
            logger.warning("Scholar rate limit, %d초 대기", wait)
            time.sleep(wait)
            resp = session.get(url, params={"fields": "abstract,title"}, timeout=30)

        if resp.status_code == 404:
            return None

        resp.raise_for_status()
        data = resp.json()
        abstract = data.get("abstract") or ""
        return abstract if len(abstract) >= 30 else None

    except requests.RequestException as e:
        logger.debug("Scholar API 실패 (paper_id=%s): %s", paper_id, e)
        return None


def fetch_abstract_from_crossref(session: requests.Session, doi: str) -> str | None:
    """CrossRef API에서 DOI로 초록 조회."""
    url = CROSSREF_URL.format(doi=doi)
    try:
        resp = session.get(
            url,
            timeout=30,
            headers={"Accept": "application/json"},
        )

        if resp.status_code == 404:
            return None

        resp.raise_for_status()
        data = resp.json()
        message = data.get("message", {})
        abstract = message.get("abstract", "")
        if abstract:
            abstract = _strip_html_tags(abstract)
        return abstract if len(abstract) >= 30 else None

    except requests.RequestException as e:
        logger.debug("CrossRef API 실패 (doi=%s): %s", doi, e)
        return None


def show_status():
    """논문 초록 보유 현황 출력."""
    grand_total = 0
    grand_with_abs = 0

    for cat in CATEGORIES:
        cat_dir = PAPERS_DIR / cat
        if not cat_dir.exists():
            continue
        total = 0
        with_abs = 0
        for f in cat_dir.glob("*.json"):
            try:
                with open(f, encoding="utf-8") as fp:
                    records = json.load(fp)
                for r in records:
                    total += 1
                    if _has_abstract(r):
                        with_abs += 1
            except Exception:
                pass
        pct = with_abs / max(total, 1) * 100
        print(f"  {cat}: {with_abs}/{total} ({pct:.1f}%) 초록 보유")
        grand_total += total
        grand_with_abs += with_abs

    pct = grand_with_abs / max(grand_total, 1) * 100
    print(f"  전체: {grand_with_abs}/{grand_total} ({pct:.1f}%) 초록 보유")


def fill_abstracts(categories: list[str], max_count: int = 0) -> dict:
    """누락된 초록을 Semantic Scholar / CrossRef에서 채움.

    Returns:
        통계 딕셔너리: filled_from_scholar, filled_from_crossref, still_missing, skipped
    """
    session = requests.Session()
    session.headers["User-Agent"] = "R02_LLM_CNT/1.0 (academic-research)"

    stats = {
        "filled_from_scholar": 0,
        "filled_from_crossref": 0,
        "still_missing": 0,
        "skipped": 0,
        "total_scanned": 0,
    }
    processed = 0

    for cat in categories:
        cat_dir = PAPERS_DIR / cat
        if not cat_dir.exists():
            logger.warning("카테고리 디렉토리 없음: %s", cat_dir)
            continue

        json_files = sorted(cat_dir.glob("*.json"))
        logger.info("[%s] %d개 파일 처리 시작", cat, len(json_files))

        for json_path in json_files:
            try:
                with open(json_path, encoding="utf-8") as fp:
                    records = json.load(fp)
            except Exception as e:
                logger.error("파일 읽기 실패 %s: %s", json_path, e)
                continue

            file_modified = False

            for record in records:
                stats["total_scanned"] += 1

                if _has_abstract(record):
                    stats["skipped"] += 1
                    continue

                if max_count > 0 and processed >= max_count:
                    stats["still_missing"] += 1
                    continue

                paper_id = record.get("paper_id", "")
                title = record.get("title", "")[:50]

                # 1단계: Semantic Scholar paper detail API
                abstract = None
                if paper_id:
                    abstract = fetch_abstract_from_scholar(session, paper_id)
                    time.sleep(SCHOLAR_DELAY)

                if abstract:
                    record["abstract"] = abstract
                    file_modified = True
                    stats["filled_from_scholar"] += 1
                    processed += 1
                    logger.info("  Scholar 초록 확보: %s...", title)
                    continue

                # 2단계: CrossRef (DOI가 있을 때만)
                doi = _get_doi(record)
                if doi:
                    abstract = fetch_abstract_from_crossref(session, doi)
                    time.sleep(CROSSREF_DELAY)

                    if abstract:
                        record["abstract"] = abstract
                        file_modified = True
                        stats["filled_from_crossref"] += 1
                        processed += 1
                        logger.info("  CrossRef 초록 확보: %s...", title)
                        continue

                stats["still_missing"] += 1
                processed += 1

            # 변경된 파일만 저장
            if file_modified:
                with open(json_path, "w", encoding="utf-8") as fp:
                    json.dump(records, fp, ensure_ascii=False, indent=2)
                logger.info("  파일 업데이트: %s", json_path.name)

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="누락된 논문 초록을 Semantic Scholar / CrossRef API로 채움"
    )
    parser.add_argument("--status", action="store_true", help="현황 확인만")
    parser.add_argument(
        "--category",
        type=str,
        choices=CATEGORIES,
        help="특정 카테고리만 처리 (CIV, ARC, MEC)",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=0,
        help="최대 처리 건수 (0=무제한)",
    )
    args = parser.parse_args()

    if args.status:
        print("=== 논문 초록 보유 현황 ===")
        show_status()
        return

    categories = [args.category] if args.category else CATEGORIES

    print("=== 초록 채우기 시작 ===")
    print(f"  카테고리: {', '.join(categories)}")
    print(f"  최대 처리: {'무제한' if args.max == 0 else f'{args.max}건'}")
    print()

    # 실행 전 현황
    print("[실행 전 현황]")
    show_status()
    print()

    stats = fill_abstracts(categories, max_count=args.max)

    # 결과 출력
    print()
    print("=== 결과 ===")
    print(f"  전체 스캔: {stats['total_scanned']}건")
    print(f"  이미 보유: {stats['skipped']}건")
    print(f"  Scholar에서 채움: {stats['filled_from_scholar']}건")
    print(f"  CrossRef에서 채움: {stats['filled_from_crossref']}건")
    print(f"  여전히 누락: {stats['still_missing']}건")
    print()

    # 실행 후 현황
    print("[실행 후 현황]")
    show_status()


if __name__ == "__main__":
    main()
