"""CODIL (건설기술정보시스템) 크롤러.

https://www.codil.or.kr 에서 건설기준, 시방서, 연구보고서를 크롤링한다.
목록 페이지: /viewConRpt.do?gubun=rpt&pageIndex={n}
상세 페이지: /viewDtlConRpt.do?...

페이지 구조:
  - table.tbl_type02: 목록 (10건/페이지)
  - 각 항목: th에 제목+링크, 다음 tr의 td에 저자/발행처/출판년도/분류/문서유형
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://www.codil.or.kr"
LIST_URL = BASE_URL + "/viewConRpt.do"


@dataclass
class CODILRecord:
    """CODIL 문서 레코드."""
    doc_id: str = ""
    title: str = ""
    authors: str = ""
    publisher: str = ""
    publish_year: str = ""
    doc_type: str = ""
    category: str = ""
    abstract: str = ""
    keywords: list[str] = field(default_factory=list)
    url: str = ""
    source: str = "codil"
    raw: dict = field(default_factory=dict)


class CODILCrawler:
    """CODIL 건설기술정보 크롤러."""

    def __init__(self, verify_ssl: bool = False):
        self.session = requests.Session()
        self.session.verify = verify_ssl
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ko-KR,ko;q=0.9",
        })
        self._request_interval = 2.0

    def fetch_list_page(
        self,
        page_index: int = 1,
        gubun: str = "rpt",
        search_text: str = "",
    ) -> list[CODILRecord]:
        """목록 페이지에서 문서 레코드를 추출.

        Args:
            page_index: 페이지 번호 (1부터)
            gubun: 문서 구분 (rpt=보고서)
            search_text: 검색어 (빈 문자열이면 전체 목록)
        """
        params = {
            "gubun": gubun,
            "pageIndex": page_index,
        }
        if search_text:
            params["searchText"] = search_text

        try:
            resp = self.session.get(LIST_URL, params=params, timeout=30)
            resp.raise_for_status()
            return self._parse_list_page(resp.text)
        except requests.RequestException as e:
            logger.error("CODIL 목록 요청 실패 (page %d): %s", page_index, e)
            return []

    def fetch_all_reports(
        self,
        max_pages: int = 10,
        gubun: str = "rpt",
        search_text: str = "",
    ) -> list[CODILRecord]:
        """여러 페이지에서 보고서 목록을 수집.

        Args:
            max_pages: 최대 페이지 수
            gubun: 문서 구분
            search_text: 검색어
        """
        all_records: list[CODILRecord] = []

        for page in range(1, max_pages + 1):
            records = self.fetch_list_page(page, gubun, search_text)
            if not records:
                break
            all_records.extend(records)
            logger.info("CODIL 페이지 %d: %d건 (누적 %d건)", page, len(records), len(all_records))
            time.sleep(self._request_interval)

        return all_records

    def search_construction_standards(
        self,
        tech_keyword: str,
        max_results: int = 30,
    ) -> list[CODILRecord]:
        """건설기준/시방서 관련 문서 검색."""
        max_pages = (max_results + 9) // 10
        records = self.fetch_all_reports(
            max_pages=max_pages,
            search_text=tech_keyword,
        )
        return records[:max_results]

    def fetch_full_catalog(
        self,
        gubun: str = "rpt",
        max_pages: int = 50,
    ) -> list[CODILRecord]:
        """전체 카탈로그를 페이지네이션으로 수집 (검색어 없이).

        검색 기능이 동작하지 않을 때 전체 목록을 순회하여 수집한다.
        """
        return self.fetch_all_reports(max_pages=max_pages, gubun=gubun)

    def _parse_list_page(self, html: str) -> list[CODILRecord]:
        """목록 페이지 HTML을 파싱.

        table.tbl_type02 구조:
          - 홀수 tr: th에 순번+제목(링크 포함)
          - 짝수 tr: td에 저자, 발행처, 출판년도, 분류, 문서유형
        """
        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table", class_="tbl_type02")
        if not table:
            return []

        records: list[CODILRecord] = []
        rows = table.find_all("tr")

        i = 0
        while i < len(rows):
            row = rows[i]
            th = row.find("th")

            if th:
                link = th.find("a", href=True)
                if link:
                    title = link.get_text(strip=True)
                    # 순번 제거 (예: "1.제목..." → "제목...")
                    title = re.sub(r"^\d+\.\s*", "", title)
                    href = link["href"]
                    url = href if href.startswith("http") else BASE_URL + href

                    # 다음 행에서 상세 정보 추출
                    detail = {}
                    if i + 1 < len(rows):
                        detail_row = rows[i + 1]
                        detail_td = detail_row.find("td")
                        if detail_td:
                            detail = self._parse_detail_td(detail_td)
                        i += 1  # 상세 행 건너뛰기

                    record = CODILRecord(
                        title=title,
                        authors=detail.get("저자", ""),
                        publisher=detail.get("발행처", ""),
                        publish_year=detail.get("출판년도", ""),
                        category=detail.get("분류", ""),
                        doc_type=detail.get("문서유형", ""),
                        url=url,
                        raw=detail,
                    )
                    records.append(record)
            i += 1

        return records

    def _parse_detail_td(self, td) -> dict:
        """상세 정보 td에서 필드를 추출.

        형식: "저자XXX발행처YYY출판년도ZZZ분류AAA문서유형BBB"
        """
        text = td.get_text(strip=True)
        fields = {}

        # 알려진 필드 라벨로 분할
        labels = ["저자", "발행처", "출판년도", "분류", "문서유형"]
        for i, label in enumerate(labels):
            start = text.find(label)
            if start < 0:
                continue
            value_start = start + len(label)
            # 다음 라벨까지가 값
            next_start = len(text)
            for next_label in labels[i + 1:]:
                pos = text.find(next_label, value_start)
                if pos >= 0:
                    next_start = pos
                    break
            fields[label] = text[value_start:next_start].strip()

        return fields
