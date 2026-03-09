"""KIPRIS Plus API 클라이언트.

특허/실용신안 검색을 통해 건설신기술 관련 선행기술 데이터를 수집한다.
API 문서: https://plus.kipris.or.kr/portal/data/service/DBII_000000000000001/view.do
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from xml.etree import ElementTree

import requests

from config.settings import settings

logger = logging.getLogger(__name__)

WORD_SEARCH_PATH = "/getWordSearch"
ADVANCED_SEARCH_PATH = "/getAdvancedSearch"


@dataclass
class PatentRecord:
    title: str = ""
    application_number: str = ""
    application_date: str = ""
    register_number: str = ""
    register_date: str = ""
    open_number: str = ""
    open_date: str = ""
    applicant_name: str = ""
    ipc_number: str = ""
    abstract: str = ""
    register_status: str = ""
    raw: dict = field(default_factory=dict)


class KiprisClient:
    """KIPRIS Plus REST API 클라이언트."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or settings.kipris_api_key
        self.base_url = base_url or settings.kipris_base_url
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/xml"})
        self._request_interval = 1.0  # Rate limit: 1 req/sec

    def search_by_keyword(
        self,
        keyword: str,
        num_of_rows: int = 10,
        page_no: int = 1,
        patent: bool = True,
        utility: bool = True,
    ) -> list[PatentRecord]:
        """키워드 기반 특허/실용신안 검색."""
        params = {
            "word": keyword,
            "numOfRows": num_of_rows,
            "pageNo": page_no,
            "patent": str(patent).lower(),
            "utility": str(utility).lower(),
            "ServiceKey": self.api_key,
        }
        return self._do_search(WORD_SEARCH_PATH, params)

    def search_advanced(
        self,
        invention_title: str = "",
        applicant: str = "",
        ipc_number: str = "",
        abstract_content: str = "",
        num_of_rows: int = 10,
        page_no: int = 1,
    ) -> list[PatentRecord]:
        """항목별 상세 검색."""
        params: dict = {
            "numOfRows": num_of_rows,
            "pageNo": page_no,
            "ServiceKey": self.api_key,
        }
        if invention_title:
            params["inventionTitle"] = invention_title
        if applicant:
            params["applicant"] = applicant
        if ipc_number:
            params["astrtCont"] = ipc_number
        if abstract_content:
            params["astrtCont"] = abstract_content
        return self._do_search(ADVANCED_SEARCH_PATH, params)

    def search_construction_patents(
        self,
        tech_keyword: str,
        max_results: int = 50,
    ) -> list[PatentRecord]:
        """건설신기술 관련 특허를 수집. 페이지네이션 자동 처리."""
        all_records: list[PatentRecord] = []
        page = 1
        rows_per_page = min(max_results, 50)

        while len(all_records) < max_results:
            records = self.search_by_keyword(
                keyword=tech_keyword,
                num_of_rows=rows_per_page,
                page_no=page,
            )
            if not records:
                break
            all_records.extend(records)
            page += 1
            time.sleep(self._request_interval)

        return all_records[:max_results]

    def _do_search(self, path: str, params: dict) -> list[PatentRecord]:
        url = self.base_url + path
        try:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return self._parse_response(resp.text)
        except requests.RequestException as e:
            logger.error("KIPRIS API 요청 실패: %s", e)
            return []

    def _parse_response(self, xml_text: str) -> list[PatentRecord]:
        records: list[PatentRecord] = []
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError as e:
            logger.error("XML 파싱 실패: %s", e)
            return records

        # KIPRIS XML 구조: response > body > items > item
        items = root.findall(".//item")
        for item in items:
            raw = {child.tag: (child.text or "") for child in item}
            record = PatentRecord(
                title=raw.get("inventionTitle", ""),
                application_number=raw.get("applicationNumber", ""),
                application_date=raw.get("applicationDate", ""),
                register_number=raw.get("registerNumber", ""),
                register_date=raw.get("registerDate", ""),
                open_number=raw.get("openNumber", ""),
                open_date=raw.get("openDate", ""),
                applicant_name=raw.get("applicantName", ""),
                ipc_number=raw.get("ipcNumber", ""),
                abstract=raw.get("astrtCont", ""),
                register_status=raw.get("registerStatus", ""),
                raw=raw,
            )
            records.append(record)

        logger.info("KIPRIS: %d건 검색됨", len(records))
        return records
