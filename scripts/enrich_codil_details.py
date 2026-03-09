"""CODIL 상세페이지 크롤링으로 초록/내용 보강.

기존 3,027건 CODIL 레코드는 제목만 보유. 상세 페이지를 크롤링하여
초록, 키워드, 본문 요약 등을 추가한다.

사용법:
  py scripts/enrich_codil_details.py                # 전체 보강
  py scripts/enrich_codil_details.py --category CIV # 특정 카테고리
  py scripts/enrich_codil_details.py --max 200      # 최대 200건
  py scripts/enrich_codil_details.py --status       # 현황 확인
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

CODIL_BASE = "https://www.codil.or.kr"


def create_session() -> requests.Session:
    """CODIL 크롤링용 세션."""
    session = requests.Session()
    session.verify = False
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Referer": CODIL_BASE,
    })
    return session


def fetch_detail_page(session: requests.Session, url: str) -> dict:
    """CODIL 상세 페이지에서 초록, 키워드, 내용을 추출.

    상세 페이지 구조:
      - div.view_cont: 본문 영역
      - 초록/요약: 별도 섹션 또는 본문 앞부분
      - 키워드: 별도 태그 또는 메타데이터
    """
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.debug("상세 페이지 요청 실패 %s: %s", url, e)
        return {}

    soup = BeautifulSoup(resp.text, "lxml")
    result: dict = {}

    # 1. 초록 추출 시도 (다양한 패턴)
    abstract = ""

    # 패턴 1: 초록/요약 섹션
    for label_text in ["초록", "요약", "Abstract", "Summary"]:
        label_el = soup.find(string=re.compile(label_text, re.IGNORECASE))
        if label_el:
            parent = label_el.find_parent()
            if parent:
                # 다음 형제 또는 부모의 다음 요소에서 텍스트 추출
                next_el = parent.find_next_sibling()
                if next_el:
                    abstract = next_el.get_text(strip=True)
                    if len(abstract) > 20:
                        break

    # 패턴 2: view_cont 클래스의 본문
    if not abstract or len(abstract) < 20:
        view_cont = soup.find("div", class_=re.compile(r"view_cont|cont_view|content"))
        if view_cont:
            text = view_cont.get_text(separator="\n", strip=True)
            # 앞부분 500자를 요약으로 사용
            if len(text) > 50:
                abstract = text[:2000]

    # 패턴 3: meta description
    if not abstract or len(abstract) < 20:
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            abstract = meta_desc["content"]

    # 패턴 4: table 기반 상세 정보 (CODIL 일반 패턴)
    if not abstract or len(abstract) < 20:
        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                th = row.find("th")
                td = row.find("td")
                if th and td:
                    th_text = th.get_text(strip=True)
                    if any(k in th_text for k in ["초록", "요약", "내용", "설명", "개요"]):
                        abstract = td.get_text(strip=True)
                        if len(abstract) > 20:
                            break
            if abstract and len(abstract) > 20:
                break

    if abstract:
        result["abstract"] = abstract

    # 2. 키워드 추출
    keywords = []
    for label_text in ["키워드", "Keyword", "주제어"]:
        kw_el = soup.find(string=re.compile(label_text, re.IGNORECASE))
        if kw_el:
            parent = kw_el.find_parent()
            if parent:
                next_el = parent.find_next_sibling()
                if next_el:
                    kw_text = next_el.get_text(strip=True)
                    keywords = [k.strip() for k in re.split(r'[;,|/]', kw_text) if k.strip()]
                    break

    # 키워드: meta keywords
    if not keywords:
        meta_kw = soup.find("meta", attrs={"name": "keywords"})
        if meta_kw and meta_kw.get("content"):
            keywords = [k.strip() for k in meta_kw["content"].split(",") if k.strip()]

    if keywords:
        result["keywords"] = keywords

    # 3. 목차/섹션 제목 추출
    toc = []
    for heading in soup.find_all(["h2", "h3", "h4", "strong"]):
        text = heading.get_text(strip=True)
        if text and len(text) > 2 and len(text) < 100:
            toc.append(text)
    if toc:
        result["table_of_contents"] = toc[:20]

    # 4. 전체 텍스트 길이 기록
    body_text = soup.find("body")
    if body_text:
        full_text = body_text.get_text(strip=True)
        result["content_length"] = len(full_text)

    return result


def enrich_codil_file(
    session: requests.Session,
    file_path: Path,
    max_per_file: int = 50,
) -> dict:
    """단일 CODIL JSON 파일의 레코드에 상세 정보 추가."""
    with open(file_path, encoding="utf-8") as f:
        records = json.load(f)

    stats = {"total": len(records), "enriched": 0, "skipped": 0, "failed": 0}

    for record in records:
        # 이미 상세 정보가 있으면 스킵
        if record.get("abstract") and len(record.get("abstract", "")) > 50:
            stats["skipped"] += 1
            continue

        if stats["enriched"] >= max_per_file:
            break

        url = record.get("url", "")
        if not url:
            stats["failed"] += 1
            continue

        # URL이 상대경로인 경우 절대경로로 변환
        if not url.startswith("http"):
            url = CODIL_BASE + url

        detail = fetch_detail_page(session, url)

        if detail:
            if detail.get("abstract"):
                record["abstract"] = detail["abstract"]
                record["detail_source"] = "codil_detail"
                stats["enriched"] += 1
                logger.debug("  보강: %s (%d자)", record.get("title", "")[:30], len(detail["abstract"]))
            else:
                stats["failed"] += 1

            if detail.get("keywords"):
                record["keywords"] = detail["keywords"]
            if detail.get("table_of_contents"):
                record["table_of_contents"] = detail["table_of_contents"]
            if detail.get("content_length"):
                record["content_length"] = detail["content_length"]
        else:
            stats["failed"] += 1

        time.sleep(2)  # Rate limiting

    # 저장
    if stats["enriched"] > 0:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

    return stats


def enrich_all(
    category: str | None = None,
    max_total: int = 500,
    max_per_file: int = 50,
) -> dict:
    """전체 CODIL 파일에 상세 정보 추가."""
    codil_dir = Path("data/dynamic/codil")
    categories = [category] if category else ["CIV", "ARC", "MEC"]

    session = create_session()
    total_stats = {"total": 0, "enriched": 0, "skipped": 0, "failed": 0}

    for cat in categories:
        cat_dir = codil_dir / cat
        if not cat_dir.exists():
            logger.info("%s: 디렉토리 없음", cat)
            continue

        for f in sorted(cat_dir.glob("*.json")):
            if total_stats["enriched"] >= max_total:
                break

            remaining = max_total - total_stats["enriched"]
            per_file = min(max_per_file, remaining)

            logger.info("처리: %s/%s (남은 할당: %d)", cat, f.name, remaining)

            stats = enrich_codil_file(session, f, max_per_file=per_file)

            for k in total_stats:
                total_stats[k] += stats[k]

            if stats["enriched"] > 0:
                logger.info("  → %d건 상세 추가", stats["enriched"])

    logger.info(
        "CODIL 상세 보강 완료: 총 %d건 중 %d건 추가, %d건 스킵, %d건 실패",
        total_stats["total"], total_stats["enriched"],
        total_stats["skipped"], total_stats["failed"],
    )
    return total_stats


def show_status():
    """CODIL 상세 보강 현황."""
    codil_dir = Path("data/dynamic/codil")

    print("\n=== CODIL 상세 보강 현황 ===\n")

    for cat in ["CIV", "ARC", "MEC"]:
        cat_dir = codil_dir / cat
        if not cat_dir.exists():
            print(f"{cat}: 데이터 없음")
            continue

        total = 0
        with_abstract = 0
        with_keywords = 0

        for f in cat_dir.glob("*.json"):
            with open(f, encoding="utf-8") as fp:
                records = json.load(fp)
            for r in records:
                total += 1
                if r.get("abstract") and len(r.get("abstract", "")) > 50:
                    with_abstract += 1
                if r.get("keywords") and len(r.get("keywords", [])) > 0:
                    with_keywords += 1

        abs_pct = with_abstract / max(total, 1) * 100
        kw_pct = with_keywords / max(total, 1) * 100
        print(f"{cat}: {total}건 (초록 {with_abstract}/{total} = {abs_pct:.1f}%, "
              f"키워드 {with_keywords}/{total} = {kw_pct:.1f}%)")


def main():
    parser = argparse.ArgumentParser(description="CODIL 상세페이지 보강")
    parser.add_argument("--category", type=str, help="카테고리 (CIV, ARC, MEC)")
    parser.add_argument("--max", type=int, default=500, help="최대 보강 건수")
    parser.add_argument("--max-per-file", type=int, default=50, help="파일당 최대")
    parser.add_argument("--status", action="store_true", help="현황 확인")
    args = parser.parse_args()

    if args.status:
        show_status()
    else:
        enrich_all(
            category=args.category,
            max_total=args.max,
            max_per_file=args.max_per_file,
        )


if __name__ == "__main__":
    main()
