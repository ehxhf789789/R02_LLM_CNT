"""KCI (한국학술지인용색인) API 클라이언트.

한국연구재단 KCI Open API를 통해 국내 학술 논문을 검색한다.
data.go.kr 공공데이터포털에서 API 키 발급 (일 10만건).

API 문서: https://www.kci.go.kr/kciportal/po/openApi/openApiList.kci
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from xml.etree import ElementTree

import requests

from config.settings import settings

logger = logging.getLogger(__name__)

# KCI Open API 엔드포인트
SEARCH_URL = "https://open.kci.go.kr/po/openApi/openApiSearch.kci"


@dataclass
class KCIRecord:
    """KCI 논문 레코드."""
    article_id: str = ""
    title: str = ""
    authors: str = ""
    journal: str = ""
    publish_year: str = ""
    abstract: str = ""
    keywords: list[str] = field(default_factory=list)
    doi: str = ""
    url: str = ""
    journal_issn: str = ""
    volume: str = ""
    issue: str = ""
    pages: str = ""
    source: str = "kci"
    raw: dict = field(default_factory=dict)


class KCIClient:
    """KCI Open API 클라이언트."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or getattr(settings, "kci_api_key", "")
        self.session = requests.Session()
        self._request_interval = 0.5  # 초당 2건 이하

    def search_papers(
        self,
        query: str,
        display_count: int = 10,
        page_no: int = 1,
        sort: str = "score",
    ) -> list[KCIRecord]:
        """논문 검색.

        Args:
            query: 검색어
            display_count: 한 페이지 결과 수 (최대 100)
            page_no: 페이지 번호
            sort: 정렬 기준 (score, pub_year)
        """
        if not self.api_key:
            logger.warning("KCI API 키가 설정되지 않음. config/.env에 KCI_API_KEY를 설정하세요.")
            return []

        params = {
            "apiCode": "articleSearch",
            "key": self.api_key,
            "title": query,
            "displayCount": min(display_count, 100),
            "pageNo": page_no,
            "sort": sort,
        }

        try:
            resp = self.session.get(SEARCH_URL, params=params, timeout=30)
            resp.raise_for_status()
            return self._parse_response(resp.text)
        except requests.RequestException as e:
            logger.error("KCI API 요청 실패: %s", e)
            return []

    def search_construction_papers(
        self,
        tech_keyword: str,
        max_results: int = 50,
    ) -> list[KCIRecord]:
        """건설 분야 논문을 수집. 페이지네이션 자동 처리."""
        all_records: list[KCIRecord] = []
        page = 1
        per_page = min(max_results, 100)

        while len(all_records) < max_results:
            records = self.search_papers(
                query=tech_keyword,
                display_count=per_page,
                page_no=page,
            )
            if not records:
                break
            all_records.extend(records)
            page += 1
            time.sleep(self._request_interval)

        return all_records[:max_results]

    def _parse_response(self, xml_text: str) -> list[KCIRecord]:
        """KCI XML 응답을 파싱."""
        records: list[KCIRecord] = []

        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError:
            logger.warning("KCI XML 파싱 실패, 원문 (처음 500자): %s", xml_text[:500])
            return records

        # 에러 체크
        result_code = root.findtext(".//resultCode")
        if result_code and result_code != "success":
            error_msg = root.findtext(".//resultMessage") or ""
            logger.error("KCI API 오류: %s %s", result_code, error_msg)
            return records

        # KCI 응답 구조: <outputData><record>...</record></outputData>
        for record_el in root.iter("record"):
            raw: dict = {}
            for child in record_el:
                raw[child.tag] = child.text or ""

            # 저자 파싱 (KCI는 author 하위에 authorName이 있을 수 있음)
            authors_els = record_el.findall(".//author")
            if authors_els:
                author_names = []
                for a_el in authors_els:
                    name = a_el.findtext("authorName") or a_el.text or ""
                    if name.strip():
                        author_names.append(name.strip())
                authors_str = ", ".join(author_names) if author_names else raw.get("authors", "")
            else:
                authors_str = raw.get("authors", raw.get("author", ""))

            # 키워드 파싱
            keywords_text = raw.get("keyword", raw.get("keywords", ""))
            keywords = [k.strip() for k in keywords_text.split(";") if k.strip()]

            article_id = raw.get("articleId", raw.get("article-id", ""))
            kci_url = f"https://www.kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId={article_id}" if article_id else ""

            record = KCIRecord(
                article_id=article_id,
                title=raw.get("title", raw.get("articleTitle", "")),
                authors=authors_str,
                journal=raw.get("journalTitle", raw.get("journal-title", "")),
                publish_year=raw.get("pubYear", raw.get("pub-year", "")),
                abstract=raw.get("abstract", raw.get("abstractText", "")),
                keywords=keywords,
                doi=raw.get("doi", ""),
                url=kci_url,
                journal_issn=raw.get("issn", ""),
                volume=raw.get("volume", ""),
                issue=raw.get("issue", ""),
                pages=raw.get("pages", raw.get("fpage", "")),
                raw=raw,
            )
            records.append(record)

        logger.info("KCI: %d건 검색됨", len(records))
        return records
