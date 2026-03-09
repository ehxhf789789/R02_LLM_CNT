"""CODIL 콘텐츠 다중 전략 보강.

기존 3,027건 CODIL 레코드 중 ~90%가 내비게이션 텍스트만 보유.
4단계 전략으로 실제 콘텐츠를 확보한다:

  전략 1: 상세페이지 재크롤링 (메타태그, JSON-LD, 대안 URL 패턴)
  전략 2: CODIL 검색 API로 제목 검색 → 결과 스니펫 수집
  전략 3: 메타데이터 구조화 요약 생성 (기존 필드 재조합)
  전략 4: 가비지 초록 감지 및 제거

사용법:
  py scripts/enrich_codil_content.py --status              # 현황 확인
  py scripts/enrich_codil_content.py                       # 전체 보강 (전략 1→2→3→4)
  py scripts/enrich_codil_content.py --category CIV        # 특정 카테고리
  py scripts/enrich_codil_content.py --max 200             # 최대 200건
  py scripts/enrich_codil_content.py --strategy 2          # 특정 전략만
  py scripts/enrich_codil_content.py --strategy 4          # 가비지 정리만
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
import urllib.parse
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
CODIL_DIR = PROJECT_ROOT / "data" / "dynamic" / "codil"

# ── 가비지 패턴: 내비게이션/UI 텍스트 감지 ─────────────────────────────
GARBAGE_PATTERNS = [
    r"건설신기술[/\s]*추가자료",
    r"포인트\s*충전",
    r"서비스\s*메뉴",
    r"사이트\s*정보",
    r"상세정보보기",
    r"건설보고서/발간자료",
    r"연구개발정보\n건설보고서",
    r"원문보기\s*\n?\s*PDF\s*\n?\s*원문저장\s*\n?\s*다운로드",
    r"^\s*제목\s*\n\[국문\]",
    r"작성언어\s*\n?\s*한국어\s*\n?\s*분류코드",
    r"제어번호\s*\n?\s*OTK",
]
GARBAGE_RE = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in GARBAGE_PATTERNS]

# 최소 유효 초록 길이
MIN_ABSTRACT_LEN = 30


# ── 유틸리티 ─────────────────────────────────────────────────────────────

def is_garbage_abstract(text: str | None) -> bool:
    """초록이 내비게이션/UI 텍스트인지 감지."""
    if not text:
        return True
    if len(text.strip()) < MIN_ABSTRACT_LEN:
        return True
    # 가비지 패턴이 3개 이상 매칭되면 가비지로 판단
    matches = sum(1 for pat in GARBAGE_RE if pat.search(text))
    if matches >= 3:
        return True
    # 텍스트 대부분이 메타데이터 라벨로 구성된 경우
    label_keywords = ["제목", "저자", "발행처", "출판년도", "제어번호",
                      "작성언어", "분류코드", "문서유형", "원문보기"]
    label_count = sum(1 for kw in label_keywords if kw in text)
    if label_count >= 5:
        return True
    return False


def has_valid_abstract(record: dict) -> bool:
    """레코드에 유효한 초록이 있는지 확인."""
    abstract = record.get("abstract", "")
    if not abstract or len(abstract.strip()) < MIN_ABSTRACT_LEN:
        return False
    return not is_garbage_abstract(abstract)


def extract_meta_code(url: str) -> str:
    """URL에서 pMetaCode 추출."""
    match = re.search(r"pMetaCode=(\w+)", url)
    return match.group(1) if match else ""


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
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": CODIL_BASE,
    })
    return session


def load_codil_files(category: str | None = None) -> list[Path]:
    """CODIL JSON 파일 목록 반환."""
    categories = [category] if category else ["CIV", "ARC", "MEC"]
    files: list[Path] = []
    for cat in categories:
        cat_dir = CODIL_DIR / cat
        if cat_dir.exists():
            files.extend(sorted(cat_dir.glob("*.json")))
    return files


def load_all_records(category: str | None = None) -> list[tuple[Path, list[dict]]]:
    """모든 CODIL 레코드를 (파일경로, 레코드목록) 형태로 로드."""
    result = []
    for fp in load_codil_files(category):
        with open(fp, encoding="utf-8") as f:
            records = json.load(f)
        result.append((fp, records))
    return result


def save_records(file_path: Path, records: list[dict]) -> None:
    """레코드를 JSON 파일로 저장."""
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


# ── 전략 1: 상세페이지 재크롤링 ─────────────────────────────────────────

def strategy1_recrawl_detail(
    session: requests.Session,
    record: dict,
) -> str | None:
    """상세 페이지를 개선된 방식으로 재크롤링.

    시도 순서:
      1. JSON-LD 구조화 데이터
      2. meta description / og:description
      3. 본문 영역 (iframe 참조 확인)
      4. 대안 URL 패턴 (viewDtlConRptFile.do 등)
    """
    url = record.get("url", "")
    if not url:
        return None
    if not url.startswith("http"):
        url = CODIL_BASE + url

    meta_code = extract_meta_code(url)

    # 기본 상세 페이지 시도
    abstract = _try_detail_page(session, url)
    if abstract:
        return abstract

    # 대안 URL 패턴들 시도
    if meta_code:
        alt_urls = [
            f"{CODIL_BASE}/viewDtlConRptFile.do?pMetaCode={meta_code}&gubun=rpt",
            f"{CODIL_BASE}/viewPdf.do?pMetaCode={meta_code}",
            f"{CODIL_BASE}/viewDtlConRpt.do?pMetaCode={meta_code}&gubun=rpt&viewType=full",
        ]
        for alt_url in alt_urls:
            time.sleep(1)  # 대안 URL 간 짧은 대기
            abstract = _try_detail_page(session, alt_url)
            if abstract:
                return abstract

    return None


def _try_detail_page(session: requests.Session, url: str) -> str | None:
    """단일 URL에서 콘텐츠 추출 시도."""
    try:
        resp = session.get(url, timeout=30)
        if resp.status_code != 200:
            return None
    except requests.RequestException:
        return None

    soup = BeautifulSoup(resp.text, "lxml")

    # 1. JSON-LD 구조화 데이터
    for script_tag in soup.find_all("script", type="application/ld+json"):
        try:
            ld_data = json.loads(script_tag.string)
            if isinstance(ld_data, dict):
                for key in ["description", "abstract", "text", "articleBody"]:
                    val = ld_data.get(key, "")
                    if val and len(val) > MIN_ABSTRACT_LEN and not is_garbage_abstract(val):
                        return val.strip()
            elif isinstance(ld_data, list):
                for item in ld_data:
                    if isinstance(item, dict):
                        for key in ["description", "abstract", "text", "articleBody"]:
                            val = item.get(key, "")
                            if val and len(val) > MIN_ABSTRACT_LEN and not is_garbage_abstract(val):
                                return val.strip()
        except (json.JSONDecodeError, TypeError):
            continue

    # 2. meta 태그 (description, og:description, DC.description)
    meta_selectors = [
        {"name": "description"},
        {"property": "og:description"},
        {"name": "DC.description"},
        {"name": "DC.Description"},
        {"name": "dcterms.abstract"},
        {"name": "citation_abstract"},
    ]
    for attrs in meta_selectors:
        meta = soup.find("meta", attrs=attrs)
        if meta and meta.get("content"):
            content = meta["content"].strip()
            if len(content) > MIN_ABSTRACT_LEN and not is_garbage_abstract(content):
                return content

    # 3. microdata (itemprop="description" 또는 "abstract")
    for prop_name in ["description", "abstract", "articleBody"]:
        el = soup.find(attrs={"itemprop": prop_name})
        if el:
            text = el.get_text(strip=True)
            if len(text) > MIN_ABSTRACT_LEN and not is_garbage_abstract(text):
                return text

    # 4. 테이블 기반: 초록/요약/내용 라벨이 있는 행
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            th = row.find("th")
            td = row.find("td")
            if th and td:
                th_text = th.get_text(strip=True)
                if any(k in th_text for k in ["초록", "요약", "내용", "설명", "개요", "목적"]):
                    text = td.get_text(strip=True)
                    if len(text) > MIN_ABSTRACT_LEN and not is_garbage_abstract(text):
                        return text

    # 5. iframe 참조 확인 (본문이 iframe에 있을 수 있음)
    iframe = soup.find("iframe", src=True)
    if iframe:
        iframe_src = iframe["src"]
        if not iframe_src.startswith("http"):
            iframe_src = CODIL_BASE + iframe_src
        try:
            iframe_resp = session.get(iframe_src, timeout=30)
            if iframe_resp.status_code == 200:
                iframe_soup = BeautifulSoup(iframe_resp.text, "lxml")
                body = iframe_soup.find("body")
                if body:
                    text = body.get_text(separator=" ", strip=True)
                    # 앞부분 2000자를 초록으로 사용
                    if len(text) > MIN_ABSTRACT_LEN and not is_garbage_abstract(text):
                        return text[:2000].strip()
        except requests.RequestException:
            pass

    # 6. 본문 영역 (가비지 필터링 적용)
    content_selectors = [
        ("div", {"class": re.compile(r"view_cont|cont_view|content_view|report_cont")}),
        ("div", {"id": re.compile(r"content|cont_area|viewArea")}),
        ("article", {}),
    ]
    for tag, attrs in content_selectors:
        el = soup.find(tag, attrs)
        if el:
            text = el.get_text(separator="\n", strip=True)
            if len(text) > MIN_ABSTRACT_LEN and not is_garbage_abstract(text):
                return text[:2000].strip()

    return None


# ── 전략 2: CODIL 검색 API로 스니펫 수집 ────────────────────────────────

CODIL_SEARCH_URL = CODIL_BASE + "/search/search.do"
CODIL_LIST_URL = CODIL_BASE + "/viewConRpt.do"


def strategy2_search_snippet(
    session: requests.Session,
    record: dict,
) -> str | None:
    """CODIL 검색을 통해 제목으로 검색하고 결과 스니펫을 수집.

    두 가지 검색 방식 시도:
      1. /search/search.do (통합검색)
      2. /viewConRpt.do?searchText=... (목록검색)
    """
    title = record.get("title", "").strip()
    if not title:
        return None

    # 긴 제목은 앞부분만 사용 (검색 정확도 향상)
    search_query = title[:60].strip()

    # 시도 1: 통합검색 페이지
    snippet = _search_via_unified(session, search_query, title)
    if snippet:
        return snippet

    # 시도 2: 목록 페이지 검색
    snippet = _search_via_list(session, search_query, title)
    if snippet:
        return snippet

    return None


def _search_via_unified(
    session: requests.Session,
    query: str,
    original_title: str,
) -> str | None:
    """통합검색 페이지에서 스니펫 추출."""
    params = {
        "searchText": query,
        "collection": "all",
    }
    try:
        resp = session.get(CODIL_SEARCH_URL, params=params, timeout=30)
        if resp.status_code != 200:
            return None
    except requests.RequestException:
        return None

    soup = BeautifulSoup(resp.text, "lxml")

    # 검색 결과에서 제목이 매칭되는 항목의 스니펫 추출
    # 일반적인 검색 결과 구조: 제목 + 스니펫/요약
    result_items = soup.find_all(["li", "div"], class_=re.compile(
        r"search_result|result_item|sch_result|list_item", re.IGNORECASE
    ))

    for item in result_items:
        # 제목 매칭 확인
        item_title_el = item.find(["a", "strong", "h3", "h4"])
        if not item_title_el:
            continue
        item_title = item_title_el.get_text(strip=True)

        # 제목 유사도 간단 체크 (앞 20자 비교)
        if not _titles_match(original_title, item_title):
            continue

        # 스니펫 추출 (제목 이후 텍스트)
        snippet_el = item.find(["p", "dd", "span", "div"], class_=re.compile(
            r"snippet|desc|summary|abstract|txt|cont", re.IGNORECASE
        ))
        if snippet_el:
            text = snippet_el.get_text(strip=True)
            if len(text) > MIN_ABSTRACT_LEN and not is_garbage_abstract(text):
                return text

    # 결과 목록이 아닌 경우, 테이블 기반 검색 결과
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            for cell in cells:
                link = cell.find("a")
                if link:
                    link_text = link.get_text(strip=True)
                    if _titles_match(original_title, link_text):
                        # 같은 행 또는 다음 행에서 스니펫 찾기
                        next_row = row.find_next_sibling("tr")
                        if next_row:
                            td = next_row.find("td")
                            if td:
                                text = td.get_text(strip=True)
                                if len(text) > MIN_ABSTRACT_LEN and not is_garbage_abstract(text):
                                    return text

    return None


def _search_via_list(
    session: requests.Session,
    query: str,
    original_title: str,
) -> str | None:
    """목록 페이지 검색으로 스니펫 추출."""
    params = {
        "gubun": "rpt",
        "searchText": query,
        "pageIndex": 1,
    }
    try:
        resp = session.get(CODIL_LIST_URL, params=params, timeout=30)
        if resp.status_code != 200:
            return None
    except requests.RequestException:
        return None

    soup = BeautifulSoup(resp.text, "lxml")
    table = soup.find("table", class_="tbl_type02")
    if not table:
        return None

    rows = table.find_all("tr")
    for i, row in enumerate(rows):
        th = row.find("th")
        if not th:
            continue
        link = th.find("a")
        if not link:
            continue
        link_text = re.sub(r"^\d+\.\s*", "", link.get_text(strip=True))

        if not _titles_match(original_title, link_text):
            continue

        # 매칭된 항목의 다음 행에서 추가 정보 확인
        if i + 1 < len(rows):
            detail_row = rows[i + 1]
            td = detail_row.find("td")
            if td:
                # 상세 텍스트에서 초록/요약 부분 추출
                full_text = td.get_text(strip=True)
                # 목록 상세에 요약이 있는 경우 추출
                for marker in ["요약", "초록", "내용"]:
                    idx = full_text.find(marker)
                    if idx >= 0:
                        after = full_text[idx + len(marker):].strip()
                        # 다음 라벨까지 추출
                        labels = ["저자", "발행처", "출판년도", "분류", "문서유형"]
                        end = len(after)
                        for label in labels:
                            pos = after.find(label)
                            if 0 < pos < end:
                                end = pos
                        snippet = after[:end].strip()
                        if len(snippet) > MIN_ABSTRACT_LEN and not is_garbage_abstract(snippet):
                            return snippet

    return None


def _titles_match(title1: str, title2: str) -> bool:
    """두 제목이 같은 문서를 가리키는지 간단히 비교."""
    t1 = re.sub(r"\s+", "", title1)[:20]
    t2 = re.sub(r"\s+", "", title2)[:20]
    if not t1 or not t2:
        return False
    # 앞 20자 기준 80% 이상 일치
    common = sum(1 for a, b in zip(t1, t2) if a == b)
    return common >= min(len(t1), len(t2)) * 0.8


# ── 전략 3: 메타데이터 구조화 요약 ──────────────────────────────────────

def strategy3_metadata_summary(record: dict) -> str | None:
    """기존 메타데이터 필드를 구조화된 요약 텍스트로 재조합.

    형식: "[{doc_type}] {title} | 저자: {authors} | 발행: {publisher} ({year}) | 분류: {category}"
    """
    title = record.get("title", "").strip()
    if not title:
        return None

    parts: list[str] = []

    doc_type = record.get("doc_type", "").strip()
    if doc_type:
        parts.append(f"[{doc_type}]")

    parts.append(title)

    authors = record.get("authors", "").strip()
    if authors:
        parts.append(f"| 저자: {authors}")

    publisher = record.get("publisher", "").strip()
    publish_year = record.get("publish_year", "").strip()
    if publisher and publish_year:
        parts.append(f"| 발행: {publisher} ({publish_year})")
    elif publisher:
        parts.append(f"| 발행: {publisher}")
    elif publish_year:
        parts.append(f"| 발행년도: {publish_year}")

    category = record.get("category", "").strip()
    if category:
        parts.append(f"| 분류: {category}")

    # 키워드가 있으면 추가
    keywords = record.get("keywords", [])
    if keywords:
        parts.append(f"| 키워드: {', '.join(keywords)}")

    summary = " ".join(parts)

    # 최소 길이 체크 (제목만 있는 경우에도 유효)
    if len(summary) < 10:
        return None

    return summary


# ── 전략 4: 가비지 초록 정리 ────────────────────────────────────────────

def strategy4_clean_garbage(record: dict) -> bool:
    """가비지 초록을 감지하고 제거. 제거되었으면 True 반환."""
    abstract = record.get("abstract", "")
    if not abstract:
        return False

    if is_garbage_abstract(abstract):
        record["abstract_garbage"] = abstract  # 백업
        record["abstract"] = ""
        record.pop("detail_source", None)
        return True

    return False


# ── 메인 보강 로직 ───────────────────────────────────────────────────────

def run_strategy(
    strategy: int,
    category: str | None = None,
    max_total: int = 500,
) -> dict:
    """단일 전략 실행."""
    file_data = load_all_records(category)
    session = create_session() if strategy in (1, 2) else None

    stats = {
        "strategy": strategy,
        "total_checked": 0,
        "enriched": 0,
        "skipped": 0,
        "failed": 0,
    }

    strategy_name = {
        1: "상세페이지 재크롤링",
        2: "검색 스니펫 수집",
        3: "메타데이터 구조화",
        4: "가비지 초록 정리",
    }.get(strategy, f"전략 {strategy}")

    logger.info("=== 전략 %d: %s 시작 ===", strategy, strategy_name)

    for file_path, records in file_data:
        if stats["enriched"] >= max_total:
            break

        file_changed = False
        file_enriched = 0

        for record in records:
            if stats["enriched"] >= max_total:
                break

            stats["total_checked"] += 1

            if strategy == 4:
                # 전략 4는 가비지 초록이 있는 레코드만 처리
                if strategy4_clean_garbage(record):
                    stats["enriched"] += 1
                    file_changed = True
                    file_enriched += 1
                else:
                    stats["skipped"] += 1
                continue

            if strategy == 3:
                # 전략 3은 유효한 초록이 없는 레코드만 처리
                if has_valid_abstract(record):
                    stats["skipped"] += 1
                    continue
                # 이미 메타데이터 구조화된 경우 스킵
                if record.get("content_source") == "metadata_structured":
                    stats["skipped"] += 1
                    continue

                summary = strategy3_metadata_summary(record)
                if summary:
                    record["abstract"] = summary
                    record["content_source"] = "metadata_structured"
                    stats["enriched"] += 1
                    file_changed = True
                    file_enriched += 1
                else:
                    stats["failed"] += 1
                continue

            # 전략 1, 2: 유효한 초록이 있으면 스킵
            if has_valid_abstract(record):
                stats["skipped"] += 1
                continue

            if strategy == 1:
                result = strategy1_recrawl_detail(session, record)
                source_label = "codil_detail_v2"
            elif strategy == 2:
                result = strategy2_search_snippet(session, record)
                source_label = "codil_search_snippet"
            else:
                result = None
                source_label = ""

            if result and not is_garbage_abstract(result):
                record["abstract"] = result
                record["content_source"] = source_label
                # 이전 가비지 백업이 있으면 제거
                record.pop("abstract_garbage", None)
                stats["enriched"] += 1
                file_changed = True
                file_enriched += 1
                logger.debug("  보강: %s (%d자)", record.get("title", "")[:30], len(result))
            else:
                stats["failed"] += 1

            # 전략 1, 2는 HTTP 요청 포함 → rate limit
            time.sleep(2)

        # 파일 변경 시 증분 저장
        if file_changed:
            save_records(file_path, records)
            logger.info("  저장: %s (+%d건)", file_path.name, file_enriched)

    logger.info(
        "전략 %d 완료: 확인 %d건, 보강 %d건, 스킵 %d건, 실패 %d건",
        strategy, stats["total_checked"], stats["enriched"],
        stats["skipped"], stats["failed"],
    )
    return stats


def run_all_strategies(
    category: str | None = None,
    max_total: int = 500,
) -> list[dict]:
    """전략 1→2→3→4 순서로 실행."""
    all_stats: list[dict] = []

    # 전략 4를 먼저 실행 (가비지 정리 → 이후 전략에서 재보강)
    logger.info(">>> 먼저 가비지 초록 정리 (전략 4) <<<")
    stats4 = run_strategy(4, category=category, max_total=999999)
    all_stats.append(stats4)

    # 전략 1→2→3 순서로 실행
    remaining = max_total
    for strat in [1, 2, 3]:
        if remaining <= 0:
            break
        stats = run_strategy(strat, category=category, max_total=remaining)
        all_stats.append(stats)
        remaining -= stats["enriched"]

    # 최종 요약
    logger.info("\n=== 최종 보강 요약 ===")
    total_enriched = 0
    for s in all_stats:
        name = {1: "상세페이지 재크롤링", 2: "검색 스니펫", 3: "메타데이터 구조화",
                4: "가비지 정리"}.get(s["strategy"], f"전략{s['strategy']}")
        logger.info("  전략 %d (%s): %d건 보강", s["strategy"], name, s["enriched"])
        total_enriched += s["enriched"]
    logger.info("  총 보강: %d건", total_enriched)

    return all_stats


# ── 현황 표시 ────────────────────────────────────────────────────────────

def show_status():
    """CODIL 콘텐츠 보강 현황 (가비지 감지 포함)."""
    print("\n=== CODIL 콘텐츠 보강 현황 ===\n")

    grand_total = 0
    grand_valid = 0
    grand_garbage = 0
    grand_empty = 0
    grand_metadata = 0
    grand_snippet = 0
    grand_detail = 0

    for cat in ["CIV", "ARC", "MEC"]:
        cat_dir = CODIL_DIR / cat
        if not cat_dir.exists():
            print(f"{cat}: 데이터 없음")
            continue

        total = 0
        valid_abstract = 0
        garbage_abstract = 0
        empty_abstract = 0
        by_source: dict[str, int] = {}

        for fp in cat_dir.glob("*.json"):
            with open(fp, encoding="utf-8") as f:
                records = json.load(f)
            for r in records:
                total += 1
                abstract = r.get("abstract", "")
                source = r.get("content_source", r.get("detail_source", ""))

                if not abstract or len(abstract.strip()) < MIN_ABSTRACT_LEN:
                    empty_abstract += 1
                elif is_garbage_abstract(abstract):
                    garbage_abstract += 1
                else:
                    valid_abstract += 1
                    by_source[source] = by_source.get(source, 0) + 1

        valid_pct = valid_abstract / max(total, 1) * 100
        garbage_pct = garbage_abstract / max(total, 1) * 100
        empty_pct = empty_abstract / max(total, 1) * 100

        print(f"{cat}: {total}건")
        print(f"  유효 초록: {valid_abstract}건 ({valid_pct:.1f}%)")
        print(f"  가비지:    {garbage_abstract}건 ({garbage_pct:.1f}%)")
        print(f"  빈 초록:   {empty_abstract}건 ({empty_pct:.1f}%)")
        if by_source:
            print(f"  출처별:")
            for src, cnt in sorted(by_source.items(), key=lambda x: -x[1]):
                label = src if src else "(미표시)"
                print(f"    {label}: {cnt}건")
        print()

        grand_total += total
        grand_valid += valid_abstract
        grand_garbage += garbage_abstract
        grand_empty += empty_abstract
        grand_metadata += by_source.get("metadata_structured", 0)
        grand_snippet += by_source.get("codil_search_snippet", 0)
        grand_detail += by_source.get("codil_detail_v2", 0)

    print(f"전체: {grand_total}건")
    print(f"  유효: {grand_valid}건 ({grand_valid / max(grand_total, 1) * 100:.1f}%)")
    print(f"  가비지: {grand_garbage}건 ({grand_garbage / max(grand_total, 1) * 100:.1f}%)")
    print(f"  빈 초록: {grand_empty}건 ({grand_empty / max(grand_total, 1) * 100:.1f}%)")
    if grand_detail or grand_snippet or grand_metadata:
        print(f"  보강 출처: 상세페이지={grand_detail}, 검색스니펫={grand_snippet}, 메타데이터={grand_metadata}")


# ── CLI ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="CODIL 콘텐츠 다중 전략 보강",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
전략 설명:
  1  상세페이지 재크롤링 (JSON-LD, meta, iframe, 대안URL)
  2  CODIL 검색 API 스니펫 수집
  3  메타데이터 구조화 요약 생성
  4  가비지 초록 감지 및 제거
""",
    )
    parser.add_argument("--category", type=str, help="카테고리 (CIV, ARC, MEC)")
    parser.add_argument("--max", type=int, default=500, help="최대 보강 건수 (기본: 500)")
    parser.add_argument("--strategy", type=int, choices=[1, 2, 3, 4],
                        help="특정 전략만 실행 (미지정 시 전체 순서대로)")
    parser.add_argument("--status", action="store_true", help="현황 확인")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    if args.strategy:
        run_strategy(args.strategy, category=args.category, max_total=args.max)
    else:
        run_all_strategies(category=args.category, max_total=args.max)


if __name__ == "__main__":
    main()
