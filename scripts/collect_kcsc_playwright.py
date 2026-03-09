"""KCSC (국가건설기준센터) Playwright 기반 건설기준 수집.

https://kcsc.re.kr 은 JavaScript SPA로 구현되어 있어 일반 HTTP 요청으로는
콘텐츠를 가져올 수 없다. Playwright headless Chromium을 사용하여 렌더링된
페이지에서 KDS(설계기준) / KCS(시공기준) 전문 텍스트를 수집한다.

건설기준 코드 체계:
  KDS XX XX XX: 설계기준 (구조, 지반, 내진 등)
  KCS XX XX XX: 시공기준 (콘크리트, 강구조, 도로 등)

수집 전략:
  1. Playwright로 기준 목록/검색 페이지 렌더링
  2. KDS/KCS 코드 + 제목 파싱
  3. 개별 뷰어 페이지에서 전문 텍스트 추출
  4. XHR/fetch 인터셉트로 API 엔드포인트 자동 탐지

사전 설치:
  pip install playwright
  playwright install chromium

사용법:
  py scripts/collect_kcsc_playwright.py                  # KDS 전체 수집
  py scripts/collect_kcsc_playwright.py --type KCS       # KCS만
  py scripts/collect_kcsc_playwright.py --max 50         # 최대 50건
  py scripts/collect_kcsc_playwright.py --status         # 현황 확인
  py scripts/collect_kcsc_playwright.py --no-content     # 목록만 (내용 X)
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(
        open(sys.stdout.fileno(), mode="w", encoding="utf-8", closefd=False)
    )],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
KCSC_BASE = "https://kcsc.re.kr"

OUTPUT_DIR = PROJECT_ROOT / "data" / "dynamic" / "kcsc_standards"

# KDS/KCS 앞 2자리 → 대분류 매핑
CATEGORY_MAP: dict[str, str] = {
    # 토목 (CIV)
    "11": "CIV", "14": "CIV", "21": "CIV", "24": "CIV", "27": "CIV",
    "31": "CIV", "34": "CIV", "44": "CIV", "51": "CIV", "64": "CIV",
    # 건축 (ARC)
    "41": "ARC", "42": "ARC", "43": "ARC",
    # 기계설비 (MEC)
    "57": "MEC", "61": "MEC",
}

# 코드 패턴: KDS 14 20 00 또는 KCS 44 50 05
CODE_RE = re.compile(r"(K[DC]S)\s*(\d{2})\s*(\d{2})\s*(\d{2})")

# 페이지 로드 후 대기 시간 (ms)
PAGE_WAIT_MS = 3000
# 요청 간 딜레이 (초)
REQUEST_DELAY = 2.5

# ---------------------------------------------------------------------------
# URL Candidates - KCSC SPA가 사용할 수 있는 라우트 패턴
# ---------------------------------------------------------------------------
LIST_URL_CANDIDATES = [
    "/Standards/Search",
    "/Standards/List",
    "/StandardCode/List",
    "/StandardCode/Search",
    "/standard/search",
    "/standard/list",
    "/Standard/Search",
    "/Standard/List",
    "/",
]

VIEWER_URL_PATTERNS = [
    "/Standards/Viewer",
    "/StandardCode/Viewer",
    "/Standard/Viewer",
    "/standard/viewer",
]


def classify_category(code: str) -> str:
    """KDS/KCS 코드의 앞 2자리로 대분류 판별."""
    match = CODE_RE.search(code)
    if match:
        return CATEGORY_MAP.get(match.group(2), "CIV")
    return "CIV"


def normalize_code(match: re.Match) -> str:
    """코드를 표준 형식으로 변환: KDS 14 20 00"""
    return f"{match.group(1)} {match.group(2)} {match.group(3)} {match.group(4)}"


# ---------------------------------------------------------------------------
# API Interceptor
# ---------------------------------------------------------------------------
class APIInterceptor:
    """XHR/fetch 요청을 인터셉트하여 API 엔드포인트를 자동 탐지."""

    def __init__(self):
        self.api_calls: list[dict] = []
        self.api_responses: list[dict] = []

    def on_request(self, request):
        """요청 인터셉트."""
        url = request.url
        if request.resource_type in ("xhr", "fetch"):
            self.api_calls.append({
                "url": url,
                "method": request.method,
                "post_data": request.post_data,
                "resource_type": request.resource_type,
            })
            logger.debug("API 요청 탐지: %s %s", request.method, url)

    def on_response(self, response):
        """응답 인터셉트 (JSON 응답만)."""
        content_type = response.headers.get("content-type", "")
        if "json" in content_type or "javascript" in content_type:
            url = response.url
            if response.request.resource_type in ("xhr", "fetch"):
                try:
                    body = response.json()
                    self.api_responses.append({
                        "url": url,
                        "status": response.status,
                        "body": body,
                    })
                    logger.debug("API 응답 탐지: %s (status %d)", url, response.status)
                except Exception:
                    pass

    def get_list_api(self) -> dict | None:
        """목록 API 엔드포인트를 찾아 반환."""
        for resp in self.api_responses:
            body = resp.get("body")
            if isinstance(body, dict):
                # 리스트 형태 데이터가 있는 응답 탐색
                for key in ("data", "list", "items", "result", "resultList",
                            "standardList", "codeList", "rows"):
                    if key in body and isinstance(body[key], list) and len(body[key]) > 0:
                        return resp
            elif isinstance(body, list) and len(body) > 0:
                return resp
        return None


# ---------------------------------------------------------------------------
# Playwright Crawler
# ---------------------------------------------------------------------------
class KCSCPlaywrightCrawler:
    """Playwright 기반 KCSC 크롤러."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.browser = None
        self.context = None
        self.page = None
        self.interceptor = APIInterceptor()
        self._discovered_api_url: str | None = None
        self._discovered_api_method: str | None = None
        self._discovered_api_post_data: str | None = None

    def _launch(self):
        """Playwright 브라우저 시작."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error(
                "playwright가 설치되지 않았습니다.\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            )
            raise SystemExit(1)

        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(headless=self.headless)
        self.context = self.browser.new_context(
            locale="ko-KR",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
        )
        self.page = self.context.new_page()
        # 인터셉터 등록
        self.page.on("request", self.interceptor.on_request)
        self.page.on("response", self.interceptor.on_response)
        logger.info("Playwright Chromium 브라우저 시작 (headless=%s)", self.headless)

    def _close(self):
        """브라우저 종료."""
        if self.browser:
            self.browser.close()
        if hasattr(self, "_pw") and self._pw:
            self._pw.stop()
        logger.info("브라우저 종료")

    def _wait_for_content(self, timeout_ms: int = 10000):
        """SPA 콘텐츠 로딩 대기."""
        try:
            # networkidle 대기 (모든 네트워크 요청이 완료될 때까지)
            self.page.wait_for_load_state("networkidle", timeout=timeout_ms)
        except Exception:
            pass
        # 추가 대기: SPA 렌더링 시간 확보
        self.page.wait_for_timeout(PAGE_WAIT_MS)

    def _navigate(self, url: str, wait: bool = True) -> str:
        """페이지 이동 후 콘텐츠 반환."""
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            if wait:
                self._wait_for_content()
            return self.page.content()
        except Exception as e:
            logger.warning("페이지 이동 실패 (%s): %s", url, e)
            return ""

    # ------------------------------------------------------------------
    # Phase 1: 사이트 구조 탐색
    # ------------------------------------------------------------------
    def explore_site(self) -> dict:
        """KCSC 사이트 구조를 탐색하여 목록 페이지와 API를 찾는다."""
        logger.info("=== KCSC 사이트 구조 탐색 시작 ===")
        result = {
            "list_url": None,
            "api_url": None,
            "nav_links": [],
            "found_codes": [],
        }

        # 메인 페이지 방문하여 네비게이션 링크 수집
        html = self._navigate(KCSC_BASE)
        if not html:
            logger.error("메인 페이지 로딩 실패")
            return result

        # 현재 URL (리다이렉트 확인)
        current_url = self.page.url
        logger.info("메인 페이지 URL: %s", current_url)

        # 네비게이션 링크 수집
        links = self.page.evaluate("""() => {
            const links = [];
            document.querySelectorAll('a[href]').forEach(a => {
                const href = a.getAttribute('href');
                const text = a.textContent.trim();
                if (href && text && !href.startsWith('#') && !href.startsWith('javascript')) {
                    links.push({href: href, text: text.substring(0, 100)});
                }
            });
            return links;
        }""")
        result["nav_links"] = links
        logger.info("네비게이션 링크 %d개 발견", len(links))
        for lnk in links[:20]:
            logger.debug("  링크: %s -> %s", lnk["text"][:40], lnk["href"])

        # 메뉴에서 기준 관련 링크 찾기
        standard_links = [
            lnk for lnk in links
            if any(kw in lnk["text"] for kw in ["기준", "KDS", "KCS", "설계", "시공", "표준", "검색"])
            or any(kw in lnk["href"].lower() for kw in ["standard", "code", "search", "kds", "kcs"])
        ]
        if standard_links:
            logger.info("기준 관련 링크 %d개:", len(standard_links))
            for lnk in standard_links:
                logger.info("  %s -> %s", lnk["text"][:40], lnk["href"])

        # 후보 URL 순회하며 목록 페이지 탐색
        candidate_urls = []
        # 네비게이션에서 발견된 링크 우선
        for lnk in standard_links:
            href = lnk["href"]
            if href.startswith("http"):
                candidate_urls.append(href)
            elif href.startswith("/"):
                candidate_urls.append(urljoin(KCSC_BASE, href))
        # 기본 후보
        for path in LIST_URL_CANDIDATES:
            candidate_urls.append(urljoin(KCSC_BASE, path))

        # 중복 제거
        seen = set()
        unique_candidates = []
        for u in candidate_urls:
            if u not in seen:
                seen.add(u)
                unique_candidates.append(u)

        for url in unique_candidates:
            logger.info("후보 URL 탐색: %s", url)
            self.interceptor.api_calls.clear()
            self.interceptor.api_responses.clear()

            html = self._navigate(url)
            if not html:
                continue

            # 페이지 텍스트에서 KDS/KCS 코드 검색
            page_text = self.page.evaluate("() => document.body?.innerText || ''")
            codes = CODE_RE.findall(page_text)
            if codes:
                logger.info("  KDS/KCS 코드 %d개 발견!", len(codes))
                result["list_url"] = url
                result["found_codes"] = codes[:5]

            # API 응답 확인
            api_resp = self.interceptor.get_list_api()
            if api_resp:
                result["api_url"] = api_resp["url"]
                logger.info("  API 엔드포인트 발견: %s", api_resp["url"])
                # 해당 API의 요청 정보 저장
                for call in self.interceptor.api_calls:
                    if call["url"] == api_resp["url"]:
                        self._discovered_api_url = call["url"]
                        self._discovered_api_method = call["method"]
                        self._discovered_api_post_data = call["post_data"]
                        break

            if result["list_url"] or result["api_url"]:
                break

            time.sleep(REQUEST_DELAY)

        logger.info("탐색 결과: list_url=%s, api_url=%s",
                     result["list_url"], result["api_url"])
        return result

    # ------------------------------------------------------------------
    # Phase 2: 목록 수집 - DOM 파싱
    # ------------------------------------------------------------------
    def collect_standards_from_dom(
        self,
        std_type: str,
        list_url: str,
        max_total: int,
    ) -> list[dict]:
        """렌더링된 DOM에서 기준 목록을 수집."""
        logger.info("DOM 기반 목록 수집 시작 (type=%s, url=%s)", std_type, list_url)
        all_standards: list[dict] = []
        page_num = 0

        while len(all_standards) < max_total:
            page_num += 1
            if page_num > 1:
                # 페이지네이션: 다음 페이지 버튼 또는 페이지 번호 클릭
                paged = self._try_next_page(page_num)
                if not paged:
                    logger.info("더 이상 페이지 없음 (page %d)", page_num)
                    break

            # 현재 페이지에서 기준 추출
            standards = self._extract_standards_from_page(std_type)
            if not standards:
                if page_num == 1:
                    logger.warning("첫 페이지에서 기준을 찾을 수 없음")
                break

            new_count = 0
            existing_codes = {s["code"] for s in all_standards}
            for s in standards:
                if s["code"] not in existing_codes:
                    all_standards.append(s)
                    existing_codes.add(s["code"])
                    new_count += 1

            logger.info("페이지 %d: %d건 수집 (신규 %d, 누적 %d)",
                        page_num, len(standards), new_count, len(all_standards))

            if new_count == 0:
                logger.info("신규 항목 없음, 수집 종료")
                break

            time.sleep(REQUEST_DELAY)

        return all_standards[:max_total]

    def _extract_standards_from_page(self, std_type: str) -> list[dict]:
        """현재 렌더링된 페이지에서 KDS/KCS 기준 정보를 추출."""
        standards = []

        # 방법 1: 테이블 행에서 추출
        table_data = self.page.evaluate("""(stdType) => {
            const results = [];
            const rows = document.querySelectorAll('table tr, .list-item, .standard-item, [class*="item"], [class*="row"]');
            rows.forEach(row => {
                const text = row.textContent || '';
                const codeMatch = text.match(/(K[DC]S)\\s*(\\d{2})\\s*(\\d{2})\\s*(\\d{2})/);
                if (codeMatch && codeMatch[1] === stdType) {
                    // 링크 URL 추출
                    const link = row.querySelector('a[href]');
                    const href = link ? link.getAttribute('href') : '';
                    // 제목 추출: 코드 이후 텍스트
                    const fullText = text.trim();
                    const codeStr = codeMatch[0];
                    const idx = fullText.indexOf(codeStr);
                    let title = '';
                    if (idx >= 0) {
                        title = fullText.substring(idx + codeStr.length).trim();
                        // 첫 줄만 (줄바꿈 이전)
                        const nlIdx = title.indexOf('\\n');
                        if (nlIdx > 0) title = title.substring(0, nlIdx).trim();
                        // 불필요한 앞부분 제거
                        title = title.replace(/^[:\\s:]+/, '');
                    }
                    // 제목이 없으면 코드 앞쪽 텍스트 시도
                    if (!title && idx > 0) {
                        title = fullText.substring(0, idx).trim();
                    }
                    results.push({
                        code: codeMatch[1] + ' ' + codeMatch[2] + ' ' + codeMatch[3] + ' ' + codeMatch[4],
                        title: title.substring(0, 200),
                        href: href,
                    });
                }
            });
            return results;
        }""", std_type)

        if table_data:
            for item in table_data:
                code = item["code"]
                match = CODE_RE.search(code)
                category = classify_category(code) if match else "CIV"
                viewer_url = item.get("href", "")
                if viewer_url and not viewer_url.startswith("http"):
                    viewer_url = urljoin(KCSC_BASE, viewer_url)
                standards.append({
                    "code": code,
                    "title": item.get("title", ""),
                    "std_type": std_type,
                    "category": category,
                    "viewer_url": viewer_url,
                })

        # 방법 2: 전체 텍스트에서 패턴 매칭 (테이블 추출 실패 시)
        if not standards:
            page_text = self.page.evaluate("() => document.body?.innerText || ''")
            # 라인별로 코드+제목 매칭
            for line in page_text.split("\n"):
                line = line.strip()
                match = CODE_RE.search(line)
                if match and match.group(1) == std_type:
                    code = normalize_code(match)
                    title = line[match.end():].strip(" :\t")
                    if not title:
                        title = line[:match.start()].strip(" :\t")
                    category = CATEGORY_MAP.get(match.group(2), "CIV")

                    # 중복 확인
                    if not any(s["code"] == code for s in standards):
                        standards.append({
                            "code": code,
                            "title": title[:200],
                            "std_type": std_type,
                            "category": category,
                            "viewer_url": "",
                        })

        # 방법 3: 모든 링크에서 코드 추출
        if not standards:
            link_data = self.page.evaluate("""(stdType) => {
                const results = [];
                document.querySelectorAll('a[href]').forEach(a => {
                    const text = a.textContent || '';
                    const href = a.getAttribute('href') || '';
                    const match = text.match(/(K[DC]S)\\s*(\\d{2})\\s*(\\d{2})\\s*(\\d{2})/);
                    if (match && match[1] === stdType) {
                        results.push({
                            code: match[1] + ' ' + match[2] + ' ' + match[3] + ' ' + match[4],
                            title: text.replace(match[0], '').trim().substring(0, 200),
                            href: href,
                        });
                    }
                });
                return results;
            }""", std_type)

            for item in link_data:
                code = item["code"]
                category = classify_category(code)
                viewer_url = item.get("href", "")
                if viewer_url and not viewer_url.startswith("http"):
                    viewer_url = urljoin(KCSC_BASE, viewer_url)
                if not any(s["code"] == code for s in standards):
                    standards.append({
                        "code": code,
                        "title": item.get("title", ""),
                        "std_type": std_type,
                        "category": category,
                        "viewer_url": viewer_url,
                    })

        return standards

    def _try_next_page(self, page_num: int) -> bool:
        """다음 페이지로 이동. 성공 시 True."""
        try:
            # 방법 1: 페이지 번호 버튼 클릭
            selectors = [
                f'a:text-is("{page_num}")',
                f'button:text-is("{page_num}")',
                f'[data-page="{page_num}"]',
                f'.pagination a:text-is("{page_num}")',
                f'.paging a:text-is("{page_num}")',
            ]
            for sel in selectors:
                try:
                    el = self.page.locator(sel).first
                    if el.is_visible(timeout=1000):
                        el.click()
                        self._wait_for_content()
                        return True
                except Exception:
                    continue

            # 방법 2: "다음" / ">" 버튼
            next_selectors = [
                'a:text-is("다음")',
                'button:text-is("다음")',
                'a:text-is(">")',
                'a:text-is("Next")',
                '.next a',
                '[class*="next"]',
                'a[aria-label="Next"]',
            ]
            for sel in next_selectors:
                try:
                    el = self.page.locator(sel).first
                    if el.is_visible(timeout=1000):
                        el.click()
                        self._wait_for_content()
                        return True
                except Exception:
                    continue

        except Exception as e:
            logger.debug("페이지 이동 실패: %s", e)

        return False

    # ------------------------------------------------------------------
    # Phase 2b: API 기반 목록 수집
    # ------------------------------------------------------------------
    def collect_standards_from_api(
        self,
        std_type: str,
        max_total: int,
    ) -> list[dict]:
        """인터셉트된 API를 직접 호출하여 목록 수집."""
        if not self._discovered_api_url:
            return []

        logger.info("API 기반 목록 수집 (url=%s)", self._discovered_api_url)
        all_standards: list[dict] = []

        # API 응답에서 기준 데이터 추출
        for resp in self.interceptor.api_responses:
            body = resp.get("body")
            records = self._extract_from_api_response(body, std_type)
            for r in records:
                if not any(s["code"] == r["code"] for s in all_standards):
                    all_standards.append(r)

        # 추가 페이지 요청 시도 (page 파라미터 변경)
        if self._discovered_api_url and len(all_standards) < max_total:
            for page_idx in range(2, 50):
                if len(all_standards) >= max_total:
                    break

                try:
                    # URL에 page 파라미터 추가/변경
                    api_url = self._discovered_api_url
                    if "page=" in api_url:
                        api_url = re.sub(r"page=\d+", f"page={page_idx}", api_url)
                    elif "?" in api_url:
                        api_url += f"&page={page_idx}"
                    else:
                        api_url += f"?page={page_idx}"

                    # Playwright의 page.evaluate로 fetch 호출
                    resp_data = self.page.evaluate("""async (url) => {
                        try {
                            const resp = await fetch(url, {credentials: 'include'});
                            return await resp.json();
                        } catch(e) {
                            return null;
                        }
                    }""", api_url)

                    if not resp_data:
                        break

                    records = self._extract_from_api_response(resp_data, std_type)
                    if not records:
                        break

                    new_count = 0
                    for r in records:
                        if not any(s["code"] == r["code"] for s in all_standards):
                            all_standards.append(r)
                            new_count += 1

                    logger.info("API 페이지 %d: %d건 (신규 %d, 누적 %d)",
                                page_idx, len(records), new_count, len(all_standards))

                    if new_count == 0:
                        break
                    time.sleep(REQUEST_DELAY)

                except Exception as e:
                    logger.debug("API 페이지 %d 요청 실패: %s", page_idx, e)
                    break

        return all_standards[:max_total]

    def _extract_from_api_response(
        self, body, std_type: str
    ) -> list[dict]:
        """API 응답 JSON에서 기준 레코드를 추출."""
        records: list[dict] = []
        if not body:
            return records

        # 리스트 데이터 찾기
        items: list = []
        if isinstance(body, list):
            items = body
        elif isinstance(body, dict):
            for key in ("data", "list", "items", "result", "resultList",
                        "standardList", "codeList", "rows", "content"):
                if key in body and isinstance(body[key], list):
                    items = body[key]
                    break

        for item in items:
            if not isinstance(item, dict):
                continue

            # 코드 필드 탐색
            code_str = ""
            title_str = ""

            for key in ("code", "stdCode", "standardCode", "codeNo",
                        "kdsCode", "kcsCode", "cdNm", "번호"):
                if key in item:
                    val = str(item[key])
                    match = CODE_RE.search(val)
                    if match:
                        code_str = normalize_code(match)
                        break

            if not code_str:
                # 모든 값에서 코드 탐색
                for val in item.values():
                    if isinstance(val, str):
                        match = CODE_RE.search(val)
                        if match:
                            code_str = normalize_code(match)
                            break

            if not code_str:
                continue

            # std_type 필터
            if not code_str.startswith(std_type):
                continue

            # 제목 필드 탐색
            for key in ("title", "stdTitle", "standardTitle", "name",
                        "titleNm", "제목", "기준명", "표준명", "codeName"):
                if key in item and item[key]:
                    title_str = str(item[key]).strip()
                    break

            category = classify_category(code_str)

            # 뷰어 URL 탐색
            viewer_url = ""
            for key in ("url", "viewerUrl", "detailUrl", "link", "href"):
                if key in item and item[key]:
                    viewer_url = str(item[key])
                    if not viewer_url.startswith("http"):
                        viewer_url = urljoin(KCSC_BASE, viewer_url)
                    break

            records.append({
                "code": code_str,
                "title": title_str,
                "std_type": std_type,
                "category": category,
                "viewer_url": viewer_url,
            })

        return records

    # ------------------------------------------------------------------
    # Phase 3: 개별 뷰어 페이지에서 전문 추출
    # ------------------------------------------------------------------
    def fetch_viewer_content(self, standard: dict) -> dict:
        """개별 기준 뷰어 페이지에서 전문 텍스트를 추출."""
        viewer_url = standard.get("viewer_url", "")
        code = standard.get("code", "")

        # viewer_url이 없으면 패턴으로 생성 시도
        if not viewer_url:
            code_compact = code.replace(" ", "").replace("KDS", "").replace("KCS", "")
            for pattern in VIEWER_URL_PATTERNS:
                viewer_url = urljoin(KCSC_BASE, f"{pattern}/{code_compact}")
                break

        if not viewer_url:
            return {}

        logger.debug("뷰어 페이지 접근: %s (%s)", code, viewer_url)

        html = self._navigate(viewer_url)
        if not html:
            return {}

        result: dict = {"viewer_url": self.page.url}

        # 전문 텍스트 추출
        content_data = self.page.evaluate("""() => {
            const result = {full_text: '', sections: [], toc: []};

            // 본문 컨텐츠 영역 탐색
            const contentSelectors = [
                '#viewer', '#content', '#article',
                '.viewer', '.content', '.article',
                '[class*="viewer"]', '[class*="content"]',
                '[class*="standard"]', '[class*="article"]',
                'article', 'main', '.main-content',
            ];

            let contentArea = null;
            for (const sel of contentSelectors) {
                const el = document.querySelector(sel);
                if (el && el.textContent.trim().length > 100) {
                    contentArea = el;
                    break;
                }
            }

            if (!contentArea) {
                // 가장 긴 텍스트 블록 찾기
                const divs = document.querySelectorAll('div');
                let maxLen = 0;
                divs.forEach(div => {
                    const text = div.textContent.trim();
                    if (text.length > maxLen && text.length > 200) {
                        maxLen = text.length;
                        contentArea = div;
                    }
                });
            }

            if (contentArea) {
                // 전문 텍스트 (최대 50000자)
                result.full_text = contentArea.innerText.substring(0, 50000);

                // 섹션별 추출
                const headings = contentArea.querySelectorAll('h1, h2, h3, h4, h5, .section-title, [class*="title"], [class*="heading"]');
                headings.forEach(h => {
                    const headingText = h.textContent.trim();
                    if (!headingText || headingText.length < 2) return;

                    let sectionText = '';
                    let sibling = h.nextElementSibling;
                    while (sibling) {
                        if (['H1','H2','H3','H4','H5'].includes(sibling.tagName) ||
                            sibling.classList?.contains('section-title')) break;
                        sectionText += sibling.textContent.trim() + '\\n';
                        sibling = sibling.nextElementSibling;
                    }

                    result.sections.push({
                        heading: headingText.substring(0, 200),
                        content: sectionText.substring(0, 5000),
                    });
                });

                // 목차
                const tocSelectors = [
                    '.toc', '.table-of-contents', '#toc',
                    '[class*="toc"]', '[class*="index"]',
                    'nav', '.nav', '.sidebar',
                ];
                for (const sel of tocSelectors) {
                    const tocEl = document.querySelector(sel);
                    if (tocEl) {
                        tocEl.querySelectorAll('a, li').forEach(item => {
                            const text = item.textContent.trim();
                            if (text && text.length > 2) {
                                result.toc.push(text.substring(0, 200));
                            }
                        });
                        break;
                    }
                }

                // 목차 없으면 헤딩에서 추출
                if (result.toc.length === 0) {
                    headings.forEach(h => {
                        const text = h.textContent.trim();
                        if (text && text.length > 2) {
                            result.toc.push(text.substring(0, 200));
                        }
                    });
                }
            }

            return result;
        }""")

        if content_data:
            if content_data.get("full_text"):
                result["full_text"] = content_data["full_text"]
            if content_data.get("sections"):
                result["sections"] = content_data["sections"][:50]
            if content_data.get("toc"):
                result["table_of_contents"] = content_data["toc"][:50]

        # API 응답에서도 추출 시도
        for resp in self.interceptor.api_responses:
            body = resp.get("body")
            if isinstance(body, dict):
                for key in ("content", "text", "body", "fullText",
                            "standardContent", "viewerContent"):
                    if key in body and isinstance(body[key], str) and len(body[key]) > 100:
                        if "full_text" not in result:
                            result["full_text"] = body[key][:50000]
                        break

        return result

    # ------------------------------------------------------------------
    # Main collection flow
    # ------------------------------------------------------------------
    def collect(
        self,
        std_type: str = "KDS",
        max_total: int = 200,
        fetch_content: bool = True,
    ) -> list[dict]:
        """전체 수집 파이프라인."""
        self._launch()

        try:
            # Phase 1: 사이트 구조 탐색
            exploration = self.explore_site()

            # Phase 2: 목록 수집
            all_standards: list[dict] = []

            # API 기반 수집 시도
            if exploration.get("api_url"):
                all_standards = self.collect_standards_from_api(std_type, max_total)
                logger.info("API 기반 수집: %d건", len(all_standards))

            # DOM 기반 수집 (API 수집 부족 시)
            if len(all_standards) < max_total and exploration.get("list_url"):
                self._navigate(exploration["list_url"])
                dom_standards = self.collect_standards_from_dom(
                    std_type, exploration["list_url"], max_total - len(all_standards)
                )
                existing_codes = {s["code"] for s in all_standards}
                for s in dom_standards:
                    if s["code"] not in existing_codes:
                        all_standards.append(s)
                logger.info("DOM 기반 수집 추가: 총 %d건", len(all_standards))

            # 목록이 비었으면 전체 페이지 스캔
            if not all_standards:
                logger.warning("목록 수집 실패. 전체 사이트 스캔 시도...")
                all_standards = self._fallback_full_scan(std_type, max_total)

            all_standards = all_standards[:max_total]
            logger.info("=== 총 %d건 %s 기준 목록 수집 완료 ===", len(all_standards), std_type)

            # Phase 3: 전문 내용 수집
            if fetch_content and all_standards:
                enriched = 0
                failed = 0
                for i, std in enumerate(all_standards):
                    try:
                        self.interceptor.api_responses.clear()
                        content = self.fetch_viewer_content(std)
                        if content:
                            std.update(content)
                            if content.get("full_text"):
                                enriched += 1
                            else:
                                failed += 1
                        else:
                            failed += 1
                    except Exception as e:
                        logger.warning("내용 수집 실패 (%s): %s", std["code"], e)
                        failed += 1

                    if (i + 1) % 10 == 0:
                        logger.info("내용 수집 진행: %d/%d (성공 %d, 실패 %d)",
                                    i + 1, len(all_standards), enriched, failed)
                    time.sleep(REQUEST_DELAY)

                logger.info("내용 수집 완료: %d건 성공, %d건 실패", enriched, failed)

            return all_standards

        finally:
            self._close()

    def _fallback_full_scan(self, std_type: str, max_total: int) -> list[dict]:
        """최후 수단: 사이트의 다양한 경로를 방문하며 기준 코드를 찾는다."""
        standards: list[dict] = []
        visited: set[str] = set()

        # 기본 경로 + 발견된 모든 링크를 순회
        scan_urls = [KCSC_BASE + p for p in LIST_URL_CANDIDATES]

        # 현재 페이지의 모든 내부 링크 수집
        try:
            all_links = self.page.evaluate("""() => {
                const links = new Set();
                document.querySelectorAll('a[href]').forEach(a => {
                    const href = a.getAttribute('href');
                    if (href && (href.startsWith('/') || href.startsWith('https://kcsc'))) {
                        links.add(href);
                    }
                });
                return Array.from(links);
            }""")
            for href in all_links:
                url = urljoin(KCSC_BASE, href)
                if url not in scan_urls:
                    scan_urls.append(url)
        except Exception:
            pass

        for url in scan_urls[:30]:  # 최대 30 URL
            if url in visited or len(standards) >= max_total:
                break
            visited.add(url)

            logger.debug("폴백 스캔: %s", url)
            html = self._navigate(url)
            if not html:
                continue

            found = self._extract_standards_from_page(std_type)
            existing_codes = {s["code"] for s in standards}
            for s in found:
                if s["code"] not in existing_codes:
                    standards.append(s)

            if found:
                logger.info("폴백 스캔 %s: %d건 발견", url, len(found))

            time.sleep(REQUEST_DELAY)

        return standards


# ---------------------------------------------------------------------------
# Save / Status
# ---------------------------------------------------------------------------
def save_standards(standards: list[dict], std_type: str):
    """수집된 기준을 카테고리별로 저장."""
    by_category: dict[str, list] = {}
    for std in standards:
        cat = std.get("category", "CIV")
        by_category.setdefault(cat, []).append(std)

    for cat, records in by_category.items():
        out_dir = OUTPUT_DIR / cat
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{std_type.lower()}_standards.json"

        # 기존 데이터 병합
        existing: list[dict] = []
        if out_path.exists():
            try:
                with open(out_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                logger.info("기존 데이터 로드: %s (%d건)", out_path, len(existing))
            except Exception:
                pass

        # 기존 코드 → 레코드 맵
        code_map = {r["code"]: r for r in existing}
        for r in records:
            code_map[r["code"]] = r  # 새 데이터로 덮어쓰기

        merged = list(code_map.values())
        # 코드순 정렬
        merged.sort(key=lambda x: x.get("code", ""))

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        logger.info("%s/%s: %d건 저장 (기존 %d → 병합 %d)",
                    cat, std_type, len(records), len(existing), len(merged))


def show_status():
    """수집 현황."""
    print("\n=== KCSC 건설기준 수집 현황 ===\n")

    grand_total = 0
    grand_content = 0

    for cat in ["CIV", "ARC", "MEC"]:
        cat_dir = OUTPUT_DIR / cat
        if not cat_dir.exists():
            print(f"  {cat}: 데이터 없음")
            continue

        for f in sorted(cat_dir.glob("*.json")):
            try:
                with open(f, encoding="utf-8") as fp:
                    records = json.load(fp)
            except Exception:
                continue

            total = len(records)
            with_content = sum(
                1 for r in records
                if r.get("full_text") and len(r.get("full_text", "")) > 100
            )
            pct = with_content / max(total, 1) * 100
            grand_total += total
            grand_content += with_content

            print(f"  {cat}/{f.name}: {total}건 (전문 {with_content}/{total} = {pct:.1f}%)")

    if grand_total == 0:
        print("  데이터 없음. 수집을 실행하세요.")
    else:
        pct = grand_content / max(grand_total, 1) * 100
        print(f"\n  합계: {grand_total}건 (전문 {grand_content}/{grand_total} = {pct:.1f}%)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="KCSC 건설기준 수집 (Playwright 기반)",
    )
    parser.add_argument(
        "--type", type=str, default="KDS", choices=["KDS", "KCS"],
        help="기준 유형 (기본: KDS)",
    )
    parser.add_argument(
        "--max", type=int, default=200,
        help="최대 수집 건수 (기본: 200)",
    )
    parser.add_argument(
        "--no-content", action="store_true",
        help="목록만 수집 (전문 내용 X)",
    )
    parser.add_argument(
        "--status", action="store_true",
        help="수집 현황 확인",
    )
    parser.add_argument(
        "--headed", action="store_true",
        help="브라우저 창 표시 (디버깅용)",
    )
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    crawler = KCSCPlaywrightCrawler(headless=not args.headed)
    standards = crawler.collect(
        std_type=args.type,
        max_total=args.max,
        fetch_content=not args.no_content,
    )

    if standards:
        save_standards(standards, args.type)
        logger.info("=== 수집 완료: %d건 %s 기준 저장 ===", len(standards), args.type)
    else:
        logger.warning("수집된 기준이 없습니다. 사이트 구조가 변경되었을 수 있습니다.")
        logger.info("--headed 옵션으로 브라우저를 표시하여 확인해 보세요.")


if __name__ == "__main__":
    main()
