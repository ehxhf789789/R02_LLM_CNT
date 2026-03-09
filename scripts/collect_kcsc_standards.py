"""KCSC (국가건설기준센터) 건설기준 전문 수집.

https://kcsc.re.kr 의 KDS(설계기준) / KCS(시공기준) 뷰어 페이지에서
건설기준 전문 텍스트를 수집한다.

건설기준 코드 체계:
  KDS XX XX XX: 설계기준 (구조, 지반, 내진 등)
  KCS XX XX XX: 시공기준 (콘크리트, 강구조, 도로 등)

수집 전략:
  1. 기준 목록 페이지에서 KDS/KCS 코드 + 제목 수집
  2. 뷰어 페이지에서 전문 텍스트 추출

주의: kcsc.re.kr은 JavaScript SPA로 구현되어 있어 일반 HTTP 요청으로는
콘텐츠를 가져올 수 없음. Playwright 같은 headless browser가 필요.
현재 버전은 기본 HTTP 수집을 시도하지만, SPA 제약으로 실패할 수 있음.

사용법:
  py scripts/collect_kcsc_standards.py                  # 전체 수집
  py scripts/collect_kcsc_standards.py --type KDS       # KDS만
  py scripts/collect_kcsc_standards.py --max 100        # 최대 100건
  py scripts/collect_kcsc_standards.py --status         # 현황 확인
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

KCSC_BASE = "https://kcsc.re.kr"

OUTPUT_DIR = Path("data/dynamic/kcsc_standards")

# KDS/KCS 분류 → CIV/ARC/MEC 매핑
# 앞 2자리 코드로 대분류 판별
CATEGORY_MAP = {
    # 토목 (CIV)
    "11": "CIV",  # 총칙
    "14": "CIV",  # 지반
    "21": "CIV",  # 도로
    "24": "CIV",  # 교량
    "27": "CIV",  # 터널
    "31": "CIV",  # 하천
    "34": "CIV",  # 항만
    "44": "CIV",  # 수자원
    "51": "CIV",  # 상하수도
    "64": "CIV",  # 철도
    # 건축 (ARC)
    "41": "ARC",  # 건축구조
    "42": "ARC",  # 건축
    "43": "ARC",  # 건축시설
    # 기계설비 (MEC)
    "57": "MEC",  # 기계설비
    "61": "MEC",  # 소방
}


def create_session() -> requests.Session:
    """KCSC 크롤링용 세션."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Referer": KCSC_BASE,
    })
    return session


def fetch_standard_list(
    session: requests.Session,
    std_type: str = "KDS",
    page: int = 1,
) -> list[dict]:
    """건설기준 목록 페이지에서 기준 코드와 제목을 수집.

    Args:
        std_type: KDS (설계기준) 또는 KCS (시공기준)
        page: 페이지 번호
    """
    # KCSC 기준 목록 API/페이지
    url = f"{KCSC_BASE}/StandardCode/List"
    params = {
        "codeType": std_type,
        "page": page,
        "pageSize": 50,
    }

    try:
        resp = session.get(url, params=params, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error("KCSC 목록 요청 실패 (page %d): %s", page, e)
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    standards = []

    # table 또는 list 형태의 기준 목록 파싱
    # 패턴 1: table
    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue

        # 기준 코드 (KDS XX XX XX 형식)
        code_text = cells[0].get_text(strip=True)
        code_match = re.match(r'(K[DC]S)\s*(\d{2})\s*(\d{2})\s*(\d{2})', code_text)
        if not code_match:
            continue

        code = f"{code_match.group(1)} {code_match.group(2)} {code_match.group(3)} {code_match.group(4)}"
        code_num = code_match.group(2)

        title = cells[1].get_text(strip=True) if len(cells) > 1 else ""

        # 뷰어 URL
        link = row.find("a", href=True)
        viewer_url = ""
        if link:
            href = link["href"]
            viewer_url = href if href.startswith("http") else KCSC_BASE + href

        category = CATEGORY_MAP.get(code_num, "CIV")

        standards.append({
            "code": code,
            "title": title,
            "viewer_url": viewer_url,
            "std_type": std_type,
            "category": category,
        })

    # 패턴 2: div/li 기반 목록
    if not standards:
        for item in soup.find_all("a", href=re.compile(r"Viewer|Detail|View")):
            text = item.get_text(strip=True)
            code_match = re.match(r'(K[DC]S)\s*(\d{2})\s*(\d{2})\s*(\d{2})', text)
            if code_match:
                code = f"{code_match.group(1)} {code_match.group(2)} {code_match.group(3)} {code_match.group(4)}"
                code_num = code_match.group(2)
                # 제목은 코드 뒤 텍스트
                title = text[code_match.end():].strip(" :：-")
                href = item["href"]
                viewer_url = href if href.startswith("http") else KCSC_BASE + href
                category = CATEGORY_MAP.get(code_num, "CIV")
                standards.append({
                    "code": code,
                    "title": title,
                    "viewer_url": viewer_url,
                    "std_type": std_type,
                    "category": category,
                })

    return standards


def fetch_standard_content(session: requests.Session, viewer_url: str) -> dict:
    """건설기준 뷰어 페이지에서 전문 텍스트를 추출."""
    if not viewer_url:
        return {}

    try:
        resp = session.get(viewer_url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.debug("뷰어 페이지 요청 실패: %s", e)
        return {}

    soup = BeautifulSoup(resp.text, "lxml")
    result: dict = {}

    # 본문 컨텐츠 추출 (다양한 패턴 시도)
    content_areas = [
        soup.find("div", class_=re.compile(r"viewer|content|article|standard")),
        soup.find("div", id=re.compile(r"viewer|content|article")),
        soup.find("article"),
        soup.find("main"),
    ]

    for area in content_areas:
        if area:
            text = area.get_text(separator="\n", strip=True)
            if len(text) > 100:
                result["full_text"] = text[:10000]  # 최대 10000자
                break

    # 섹션별 추출
    sections = []
    for heading in soup.find_all(["h1", "h2", "h3", "h4"]):
        heading_text = heading.get_text(strip=True)
        if not heading_text or len(heading_text) < 2:
            continue

        # 다음 형제 요소들에서 본문 텍스트 수집
        section_text = []
        for sibling in heading.find_next_siblings():
            if sibling.name in ["h1", "h2", "h3", "h4"]:
                break
            text = sibling.get_text(strip=True)
            if text:
                section_text.append(text)

        sections.append({
            "heading": heading_text,
            "content": "\n".join(section_text)[:3000],
        })

    if sections:
        result["sections"] = sections[:30]

    # 목차
    toc = []
    for heading in soup.find_all(["h2", "h3"]):
        text = heading.get_text(strip=True)
        if text and len(text) > 2:
            toc.append(text)
    if toc:
        result["table_of_contents"] = toc

    return result


def collect_standards(
    std_type: str = "KDS",
    max_total: int = 200,
    max_pages: int = 20,
    fetch_content: bool = True,
) -> dict:
    """건설기준 수집."""
    session = create_session()

    # 1. 목록 수집
    all_standards = []
    for page in range(1, max_pages + 1):
        standards = fetch_standard_list(session, std_type, page)
        if not standards:
            break
        all_standards.extend(standards)
        logger.info("KCSC 목록 페이지 %d: %d건 (누적 %d건)", page, len(standards), len(all_standards))
        time.sleep(1)

        if len(all_standards) >= max_total:
            break

    all_standards = all_standards[:max_total]
    logger.info("총 %d건 기준 목록 수집", len(all_standards))

    # 2. 상세 내용 수집
    stats = {"total": len(all_standards), "enriched": 0, "failed": 0}

    if fetch_content:
        for i, std in enumerate(all_standards):
            viewer_url = std.get("viewer_url", "")
            if not viewer_url:
                stats["failed"] += 1
                continue

            content = fetch_standard_content(session, viewer_url)
            if content:
                std.update(content)
                stats["enriched"] += 1
                logger.debug("  내용 수집: %s %s", std["code"], std["title"][:30])
            else:
                stats["failed"] += 1

            if (i + 1) % 10 == 0:
                logger.info("진행: %d/%d", i + 1, len(all_standards))
            time.sleep(2)

    # 3. 카테고리별 저장
    by_category: dict[str, list] = {}
    for std in all_standards:
        cat = std.get("category", "CIV")
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(std)

    for cat, records in by_category.items():
        out_dir = OUTPUT_DIR / cat
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{std_type.lower()}_standards.json"

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        logger.info("%s/%s: %d건 저장", cat, std_type, len(records))

    logger.info(
        "KCSC 수집 완료: %d건 목록, %d건 내용 수집, %d건 실패",
        stats["total"], stats["enriched"], stats["failed"],
    )
    return stats


def show_status():
    """수집 현황."""
    print("\n=== KCSC 건설기준 수집 현황 ===\n")

    for cat in ["CIV", "ARC", "MEC"]:
        cat_dir = OUTPUT_DIR / cat
        if not cat_dir.exists():
            print(f"{cat}: 데이터 없음")
            continue

        total = 0
        with_content = 0

        for f in cat_dir.glob("*.json"):
            with open(f, encoding="utf-8") as fp:
                records = json.load(fp)
            for r in records:
                total += 1
                if r.get("full_text") and len(r.get("full_text", "")) > 100:
                    with_content += 1

        pct = with_content / max(total, 1) * 100
        print(f"{cat}: {total}건 (전문 {with_content}/{total} = {pct:.1f}%)")


def main():
    parser = argparse.ArgumentParser(description="KCSC 건설기준 수집")
    parser.add_argument("--type", type=str, default="KDS", choices=["KDS", "KCS"], help="기준 유형")
    parser.add_argument("--max", type=int, default=200, help="최대 수집 건수")
    parser.add_argument("--max-pages", type=int, default=20, help="최대 페이지")
    parser.add_argument("--no-content", action="store_true", help="목록만 수집 (내용 X)")
    parser.add_argument("--status", action="store_true", help="현황 확인")
    args = parser.parse_args()

    if args.status:
        show_status()
    else:
        collect_standards(
            std_type=args.type,
            max_total=args.max,
            max_pages=args.max_pages,
            fetch_content=not args.no_content,
        )


if __name__ == "__main__":
    main()
