"""KAIA 건설신기술 목록 크롤러.

https://www.kaia.re.kr/portal/newtec/comparelist.do 에서
지정된 건설신기술 목록, 상세정보를 크롤링하여 저장한다.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

from config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class CNTDesignatedTech:
    """지정된 건설신기술 정보."""
    tech_number: str = ""          # 신기술 번호 (예: 1046)
    tech_name: str = ""            # 기술명
    applicant: str = ""            # 개발사(업체)
    tech_field: str = ""           # 기술 분야 (대분류 > 중분류 > 소분류)
    protection_period: str = ""    # 보호기간 (시작일 ~ 종료일)
    consulting: str = ""           # 컨설팅 여부
    status: str = ""               # 상태 (유효/만료 등)
    summary: str = ""              # 기술 요약 (상세페이지에서)
    detail_url: str = ""           # 상세 페이지 URL
    raw: dict = field(default_factory=dict)


class KaiaCrawler:
    """KAIA 건설신기술 목록 크롤러."""

    BASE_URL = "https://www.kaia.re.kr"
    LIST_URL = BASE_URL + "/portal/newtec/comparelist.do"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ko-KR,ko;q=0.9",
        })
        self._request_interval = 2.0  # 서버 부담 최소화

    def fetch_list_page(
        self,
        page_no: int = 1,
        menu_no: str = "200076",
        search_keyword: str = "",
    ) -> list[CNTDesignatedTech]:
        """목록 페이지에서 건설신기술 리스트를 파싱."""
        params: dict = {
            "menuNo": menu_no,
            "pageIndex": page_no,
        }
        if search_keyword:
            params["searchKeyword"] = search_keyword

        try:
            resp = self.session.get(self.LIST_URL, params=params, timeout=30)
            resp.raise_for_status()
            return self._parse_list_page(resp.text)
        except requests.RequestException as e:
            logger.error("KAIA 목록 페이지 요청 실패: %s", e)
            return []

    def fetch_all_technologies(
        self,
        max_pages: int = 50,
        search_keyword: str = "",
        fetch_details: bool = False,
    ) -> list[CNTDesignatedTech]:
        """모든 페이지를 순회하여 전체 건설신기술 목록 수집.

        Args:
            fetch_details: True이면 각 기술의 상세 페이지도 크롤링하여 summary에 저장.
        """
        all_techs: list[CNTDesignatedTech] = []

        for page in range(1, max_pages + 1):
            logger.info("KAIA 목록 페이지 %d 크롤링 중...", page)
            techs = self.fetch_list_page(page_no=page, search_keyword=search_keyword)
            if not techs:
                logger.info("페이지 %d: 결과 없음, 크롤링 종료", page)
                break
            all_techs.extend(techs)
            time.sleep(self._request_interval)

        if fetch_details:
            logger.info("상세 페이지 크롤링 시작 (%d건)...", len(all_techs))
            for tech in all_techs:
                if tech.detail_url:
                    detail = self.fetch_detail(tech.detail_url)
                    tech.summary = detail.get("내용", detail.get("범위", ""))
                    tech.raw.update(detail)
                    time.sleep(self._request_interval)

        logger.info("KAIA: 총 %d건 수집 완료", len(all_techs))
        return all_techs

    def fetch_detail(self, detail_url: str) -> dict:
        """개별 건설신기술 상세 페이지에서 추가 정보 수집."""
        if not detail_url.startswith("http"):
            detail_url = self.BASE_URL + detail_url

        try:
            resp = self.session.get(detail_url, timeout=30)
            resp.raise_for_status()
            return self._parse_detail_page(resp.text)
        except requests.RequestException as e:
            logger.error("KAIA 상세 페이지 요청 실패 (%s): %s", detail_url, e)
            return {}

    def _parse_list_page(self, html: str) -> list[CNTDesignatedTech]:
        """목록 페이지 HTML에서 건설신기술 데이터를 추출.

        KAIA 테이블 구조 (class="t_list"):
          col[0]: 체크박스(빈칸)
          col[1]: 신기술번호
          col[2]: 신기술명 (링크 포함)
          col[3]: 개발사(업체)
          col[4]: 기술분야 (대분류 > 중분류 > 소분류)
          col[5]: 보호기간 (시작일 ~ 종료일)
          col[6]: 컨설팅여부
          col[7]: 상태
        """
        soup = BeautifulSoup(html, "lxml")
        techs: list[CNTDesignatedTech] = []

        table = soup.find("table", class_="t_list")
        if not table:
            logger.warning("t_list 테이블을 찾을 수 없음")
            return techs

        rows = table.find_all("tr")[1:]  # 헤더 제외

        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 6:
                continue

            link = row.find("a", href=True)
            detail_url = link["href"] if link else ""

            tech = CNTDesignatedTech(
                tech_number=cols[1].get_text(strip=True),
                tech_name=cols[2].get_text(strip=True),
                applicant=cols[3].get_text(strip=True),
                tech_field=cols[4].get_text(strip=True),
                protection_period=cols[5].get_text(strip=True),
                consulting=cols[6].get_text(strip=True) if len(cols) > 6 else "",
                status=cols[7].get_text(strip=True) if len(cols) > 7 else "",
                detail_url=detail_url,
            )
            tech.raw = {
                f"col_{i}": col.get_text(strip=True) for i, col in enumerate(cols)
            }
            techs.append(tech)

        return techs

    def _parse_detail_page(self, html: str) -> dict:
        """상세 페이지에서 기술 요약, 분류 등 추가 정보 추출."""
        soup = BeautifulSoup(html, "lxml")
        detail: dict = {}

        # 상세 정보 테이블 파싱
        info_table = soup.find("table", class_="tbl_view") or soup.find("table")
        if info_table:
            for row in info_table.find_all("tr"):
                th = row.find("th")
                td = row.find("td")
                if th and td:
                    key = th.get_text(strip=True)
                    value = td.get_text(strip=True)
                    detail[key] = value

        # 기술 요약/설명 영역
        desc_area = soup.find("div", class_="view_content") or soup.find(
            "div", class_="cont_area"
        )
        if desc_area:
            detail["description"] = desc_area.get_text(strip=True)

        return detail
