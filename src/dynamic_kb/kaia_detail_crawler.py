"""KAIA 건설신기술 상세 페이지 크롤러 + PDF 다운로드.

kaia.re.kr 상세 페이지에서:
  1. 기본 정보 (기술명, 분야, 키워드, 범위, 내용 등) - table.t_data
  2. 시공절차 이미지 - div#mediaDiv .photo_frame02
  3. 지식재산권 (특허 목록) - div#mediaDiv #knowledge
  4. 다운로드 파일 (홍보자료 PDF 등) - div#mediaDiv tbody.filelist
을 수집한다.

페이지 구조:
  - div#detail: 기본정보 (table.t_data), 개발자, 담당자
  - div#mediaDiv: 시공절차, 지식재산권, 다운로드
  - div#utiRltDiv: 활용실적
  - div#evlDiv: 사후평가
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class KaiaDetailInfo:
    """KAIA 건설신기술 상세 페이지 정보."""
    tech_number: str = ""
    tech_name: str = ""
    tech_field: str = ""
    keywords: list[str] = field(default_factory=list)
    science_classification: str = ""
    scope: str = ""
    content: str = ""
    designation_year: str = ""
    notice_number: str = ""
    protection_period: str = ""
    patents: list[dict] = field(default_factory=list)
    download_files: list[dict] = field(default_factory=list)
    procedure_images: list[str] = field(default_factory=list)
    raw_info: dict = field(default_factory=dict)


KAIA_BASE = "https://www.kaia.re.kr"


class KaiaDetailCrawler:
    """KAIA 건설신기술 상세 페이지 크롤러.

    designated_list.json의 detail_url 필드를 사용하여 상세 페이지에 접근한다.
    URL 형식: /portal/newtec/nView.do?menuNo=200076&...&apntNo={번호}&newtecId={ID}
    """

    def __init__(self, download_dir: Path | None = None):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ko-KR,ko;q=0.9",
        })
        self.download_dir = download_dir or (settings.data_dir / "proposals" / "pdfs")
        self._request_interval = 2.0

    def fetch_detail(self, detail_url: str) -> KaiaDetailInfo:
        """상세 URL로 기본 정보를 수집.

        Args:
            detail_url: 상대 경로 (/portal/newtec/nView.do?...) 또는 절대 URL
        """
        if detail_url.startswith("/"):
            url = KAIA_BASE + detail_url
        else:
            url = detail_url

        logger.info("KAIA 상세 페이지 크롤링: %s", url)

        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            return self._parse_detail(resp.text)
        except requests.RequestException as e:
            logger.error("KAIA 상세 페이지 요청 실패 (%s): %s", url, e)
            return KaiaDetailInfo()

    def fetch_by_tech_number(self, tech_number: str) -> KaiaDetailInfo:
        """designated_list.json에서 detail_url을 찾아 크롤링."""
        import json

        list_path = settings.data_dir / "dynamic" / "cnt_designated" / "designated_list.json"
        if not list_path.exists():
            logger.error("designated_list.json 없음: %s", list_path)
            return KaiaDetailInfo(tech_number=tech_number)

        with open(list_path, encoding="utf-8") as f:
            items = json.load(f)

        for item in items:
            if item.get("tech_number") == tech_number:
                detail_url = item.get("detail_url", "")
                if detail_url:
                    info = self.fetch_detail(detail_url)
                    if not info.tech_number:
                        info.tech_number = tech_number
                    return info
                break

        logger.warning("기술 번호 %s에 대한 detail_url 없음", tech_number)
        return KaiaDetailInfo(tech_number=tech_number)

    def _parse_detail(self, html: str) -> KaiaDetailInfo:
        """상세 페이지 HTML을 파싱."""
        soup = BeautifulSoup(html, "lxml")
        info = KaiaDetailInfo()

        # 1. 기본 정보: div#detail > table.t_data
        self._parse_basic_info(soup, info)

        # 2. 미디어 탭: div#mediaDiv
        self._parse_media_tab(soup, info)

        return info

    def _parse_basic_info(self, soup: BeautifulSoup, info: KaiaDetailInfo) -> None:
        """table.t_data에서 기본 정보를 추출."""
        table = soup.find("table", class_="t_data")
        if not table:
            logger.warning("t_data 테이블을 찾을 수 없음")
            return

        field_map = {
            "지정번호": "tech_number",
            "지정년도": "designation_year",
            "고시번호": "notice_number",
            "신기술명": "tech_name",
            "기술분류": "tech_field",
            "키워드": "_keywords",
            "과학기술표준분류": "science_classification",
            "범위": "scope",
            "내용": "content",
            "보호기간": "protection_period",
        }

        for row in table.find_all("tr"):
            th = row.find("th")
            td = row.find("td")
            if not th or not td:
                continue

            key = th.get_text(strip=True)
            value = td.get_text(strip=True)
            info.raw_info[key] = value

            for label, attr in field_map.items():
                if label in key:
                    if attr == "_keywords":
                        info.keywords = [k.strip() for k in value.split(",") if k.strip()]
                    else:
                        setattr(info, attr, value)
                    break

    def _parse_media_tab(self, soup: BeautifulSoup, info: KaiaDetailInfo) -> None:
        """div#mediaDiv에서 시공절차, 지식재산권, 다운로드를 추출."""
        media_div = soup.find("div", id="mediaDiv")
        if not media_div:
            return

        # 시공절차 이미지
        photo_frame = media_div.find("div", class_="photo_frame02")
        if photo_frame:
            for img in photo_frame.find_all("img", src=True):
                src = img["src"]
                if not src.startswith("http"):
                    src = KAIA_BASE + src
                info.procedure_images.append(src)

        # 지식재산권
        knowledge = media_div.find(id="knowledge")
        if knowledge:
            for dd in knowledge.find_all("dd"):
                text = dd.get_text(strip=True)
                if text:
                    info.patents.append({"description": text})

        # 다운로드 파일 (tbody.filelist)
        filelist = media_div.find("tbody", class_="filelist")
        if filelist:
            for row in filelist.find_all("tr"):
                tds = row.find_all("td")
                if len(tds) < 2:
                    continue

                file_td = tds[1] if len(tds) >= 2 else tds[0]
                link = file_td.find("a", href=True)
                if link:
                    href = link["href"]
                    name = link.get_text(strip=True)
                    if not href.startswith("http"):
                        href = KAIA_BASE + href
                    if name:
                        info.download_files.append({"name": name, "url": href})

            # onclick 기반 다운로드 링크도 체크
            for a_tag in filelist.find_all("a", attrs={"onclick": True}):
                onclick = a_tag["onclick"]
                name = a_tag.get_text(strip=True)
                if name and name not in [f["name"] for f in info.download_files]:
                    info.download_files.append({
                        "name": name,
                        "url": "",
                        "onclick": onclick,
                    })

    def download_pdf(self, file_info: dict, tech_number: str) -> Path | None:
        """PDF 파일 다운로드."""
        url = file_info.get("url", "")
        name = file_info.get("name", f"file_{tech_number}")

        if not url:
            return None

        safe_name = re.sub(r'[<>:"/\\|?*]', '_', name)
        if not safe_name.endswith(".pdf"):
            safe_name += ".pdf"

        out_dir = self.download_dir / tech_number
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / safe_name

        if out_path.exists():
            logger.info("이미 다운로드됨: %s", out_path)
            return out_path

        try:
            resp = self.session.get(url, timeout=60, stream=True)
            resp.raise_for_status()

            with open(out_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            logger.info("PDF 다운로드 완료: %s (%.1f KB)", out_path, out_path.stat().st_size / 1024)
            return out_path
        except requests.RequestException as e:
            logger.error("PDF 다운로드 실패 (%s): %s", url, e)
            return None

    def fetch_and_download(self, detail_url: str, tech_number: str = "") -> KaiaDetailInfo:
        """상세 정보 수집 + PDF 다운로드를 한번에 수행."""
        info = self.fetch_detail(detail_url)
        if not tech_number:
            tech_number = info.tech_number

        for file_info in info.download_files:
            name = file_info.get("name", "").lower()
            if ".pdf" in name or "홍보" in name or "자료" in name:
                path = self.download_pdf(file_info, tech_number)
                if path:
                    file_info["local_path"] = str(path)
                time.sleep(self._request_interval)

        return info

    def build_proposal_from_detail(
        self,
        info: KaiaDetailInfo,
        pdf_text: str = "",
    ) -> dict:
        """KaiaDetailInfo를 평가 입력용 proposal dict로 변환."""
        return {
            "tech_number": info.tech_number,
            "tech_name": info.tech_name,
            "tech_field": info.tech_field,
            "tech_description": info.scope or info.content[:500],
            "tech_core_content": info.content,
            "differentiation_claim": "",
            "test_results": "",
            "field_application": "",
            "search_keywords": info.keywords,
            "patents": info.patents,
            "pdf_content": pdf_text,
            "designation_year": info.designation_year,
            "notice_number": info.notice_number,
            "protection_period": info.protection_period,
            "science_classification": info.science_classification,
            "source": "kaia",
            "raw_info": info.raw_info,
        }
