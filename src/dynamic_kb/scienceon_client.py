"""ScienceON API 클라이언트.

KISTI ScienceON API Gateway를 통해 건설 분야 학술 논문 및 보고서를 수집한다.
엔드포인트: https://apigateway.kisti.re.kr/openapicall.do
인증: MAC주소+시간을 AES256 암호화 → 토큰 발급 → API 호출

searchQuery 형식: {"BI":"검색어"} (URI 인코딩 필수)
  - BI: 기본 검색 (제목+초록+키워드)
  - TI: 제목 검색
  - AB: 초록 검색
  - AU: 저자 검색
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import quote
from xml.etree import ElementTree

import requests

from config.settings import settings

logger = logging.getLogger(__name__)

TOKEN_CACHE_FILE = "data/.scienceon_token.json"


def _aes256_encrypt(plaintext: str, key: str) -> str:
    """AES256 CBC 암호화 (PKCS7 패딩).

    ScienceON API Gateway 토큰 발급에 필요한 accounts 파라미터 암호화.
    key는 32자리 인증키, IV는 key의 앞 16바이트.
    """
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding as sym_padding
    except ImportError:
        logger.error("cryptography 패키지 필요: pip install cryptography")
        raise

    key_bytes = key.encode("utf-8")[:32]
    iv = key_bytes[:16]

    padder = sym_padding.PKCS7(128).padder()
    padded = padder.update(plaintext.encode("utf-8")) + padder.finalize()

    cipher = Cipher(algorithms.AES(key_bytes), modes.CBC(iv))
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()

    return base64.b64encode(encrypted).decode("utf-8")


class ScienceOnTokenManager:
    """ScienceON API Gateway 토큰 관리."""

    def __init__(
        self,
        auth_key: str,
        client_id: str,
        mac_address: str,
        token_url: str,
    ):
        self.auth_key = auth_key
        self.client_id = client_id
        self.mac_address = mac_address
        self.token_url = token_url
        self._access_token: str = ""
        self._refresh_token: str = ""
        self._token_expires: str = ""
        self._load_cached_token()

    def get_token(self) -> str:
        """유효한 access token을 반환. 만료 시 자동 갱신."""
        if self._is_token_valid():
            return self._access_token

        # refresh token으로 갱신 시도
        if self._refresh_token:
            if self._refresh_access_token():
                return self._access_token

        # 새 토큰 발급
        if self._request_new_token():
            return self._access_token

        logger.error("ScienceON 토큰 발급 실패")
        return ""

    def _is_token_valid(self) -> bool:
        if not self._access_token or not self._token_expires:
            return False
        try:
            expires = datetime.strptime(self._token_expires[:19], "%Y-%m-%d %H:%M:%S")
            return datetime.now() < expires
        except ValueError:
            return False

    def _request_new_token(self) -> bool:
        """MAC 주소 + 현재시간을 AES256 암호화하여 새 토큰 발급."""
        now_str = datetime.now().strftime("%Y%m%d%H%M%S")
        payload = json.dumps(
            {"mac_address": self.mac_address, "datetime": now_str},
            ensure_ascii=False,
        )

        try:
            encrypted = _aes256_encrypt(payload, self.auth_key)
            encoded = quote(encrypted)
        except Exception as e:
            logger.error("AES256 암호화 실패: %s", e)
            return False

        params = {"accounts": encoded, "client_id": self.client_id}
        try:
            resp = requests.get(self.token_url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return self._save_token(data)
        except Exception as e:
            logger.error("토큰 발급 요청 실패: %s (응답: %s)", e, resp.text[:300] if 'resp' in dir() else '')
            return False

    def _refresh_access_token(self) -> bool:
        """refresh token으로 access token 갱신."""
        params = {
            "refresh_token": self._refresh_token,
            "client_id": self.client_id,
        }
        try:
            resp = requests.get(self.token_url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return self._save_token(data)
        except Exception as e:
            logger.warning("토큰 갱신 실패: %s", e)
            return False

    def _save_token(self, data: dict) -> bool:
        if "access_token" not in data:
            logger.error("토큰 응답에 access_token 없음: %s", data)
            return False

        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token", "")
        self._token_expires = data.get("access_token_expire", "")

        # 파일 캐시
        try:
            from pathlib import Path
            cache = Path(TOKEN_CACHE_FILE)
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

        logger.info("ScienceON 토큰 발급 완료 (만료: %s)", self._token_expires)
        return True

    def _load_cached_token(self) -> None:
        try:
            from pathlib import Path
            cache = Path(TOKEN_CACHE_FILE)
            if cache.exists():
                data = json.loads(cache.read_text(encoding="utf-8"))
                self._access_token = data.get("access_token", "")
                self._refresh_token = data.get("refresh_token", "")
                self._token_expires = data.get("access_token_expire", "")
        except Exception:
            pass


@dataclass
class PaperRecord:
    title: str = ""
    authors: str = ""
    journal: str = ""
    publish_year: str = ""
    abstract: str = ""
    keywords: list[str] = field(default_factory=list)
    doi: str = ""
    url: str = ""
    document_type: str = ""
    raw: dict = field(default_factory=dict)


class ScienceOnClient:
    """ScienceON 논문/보고서 검색 API 클라이언트."""

    def __init__(
        self,
        auth_key: str | None = None,
        client_id: str | None = None,
        mac_address: str | None = None,
        base_url: str | None = None,
    ):
        self.client_id = client_id or settings.scienceon_client_id
        self.base_url = base_url or settings.scienceon_base_url
        self.session = requests.Session()
        self._request_interval = 1.0

        self._token_manager = ScienceOnTokenManager(
            auth_key=auth_key or settings.scienceon_auth_key,
            client_id=self.client_id,
            mac_address=mac_address or settings.scienceon_mac_address,
            token_url=settings.scienceon_token_url,
        )

    def search_papers(
        self,
        query: str,
        row_count: int = 10,
        cur_page: int = 1,
        search_field: str = "BI",
        target: str = "ARTI",
    ) -> list[PaperRecord]:
        """논문 검색.

        Args:
            query: 검색어
            row_count: 한 페이지 결과 수 (최대 100)
            cur_page: 페이지 번호
            search_field: BI(기본), TI(제목), AB(초록), AU(저자)
            target: ARTI(논문), REPO(보고서)
        """
        token = self._token_manager.get_token()
        if not token:
            logger.error("유효한 토큰 없음 - API 호출 불가")
            return []

        search_query = json.dumps({search_field: query}, ensure_ascii=False)
        params = {
            "client_id": self.client_id,
            "token": token,
            "version": "1.0",
            "action": "search",
            "target": target,
            "searchQuery": search_query,
            "curPage": cur_page,
            "rowCount": min(row_count, 100),
        }
        return self._do_search(params)

    def search_construction_papers(
        self,
        tech_keyword: str,
        max_results: int = 50,
    ) -> list[PaperRecord]:
        """건설 분야 논문을 수집. 페이지네이션 자동 처리."""
        all_records: list[PaperRecord] = []
        page = 1
        rows_per_page = min(max_results, 100)

        while len(all_records) < max_results:
            records = self.search_papers(
                query=tech_keyword,
                row_count=rows_per_page,
                cur_page=page,
            )
            if not records:
                break
            all_records.extend(records)
            page += 1
            time.sleep(self._request_interval)

        return all_records[:max_results]

    def _do_search(self, params: dict) -> list[PaperRecord]:
        try:
            resp = self.session.get(self.base_url, params=params, timeout=30)
            resp.raise_for_status()
            return self._parse_response(resp.text)
        except requests.RequestException as e:
            logger.error("ScienceON API 요청 실패: %s", e)
            return []

    def _parse_response(self, xml_text: str) -> list[PaperRecord]:
        records: list[PaperRecord] = []

        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError:
            logger.warning("XML 파싱 실패, 원문 (처음 500자): %s", xml_text[:500])
            return records

        # 에러 응답 체크
        status_code = root.findtext(".//statusCode")
        if status_code and status_code != "200":
            error_msg = root.findtext(".//errorMessage") or ""
            logger.error("ScienceON API 오류: %s %s", status_code, error_msg)
            return records

        # ScienceON 응답: <MetaData> + <ParameterData> + <RecordData><record>...</record>
        for record_el in root.iter("record"):
            raw = {}
            for child in record_el:
                raw[child.tag] = child.text or ""

            keywords_text = raw.get("keyword", raw.get("keywords", ""))
            keywords = [k.strip() for k in keywords_text.split(";") if k.strip()]

            record = PaperRecord(
                title=raw.get("title", raw.get("articleTitle", "")),
                authors=raw.get("author", raw.get("authors", "")),
                journal=raw.get("journalTitle", raw.get("journal", "")),
                publish_year=raw.get("pubyear", raw.get("publishYear", "")),
                abstract=raw.get("abstract", ""),
                keywords=keywords,
                doi=raw.get("doi", ""),
                url=raw.get("url", raw.get("articleUrl", "")),
                document_type=raw.get("docType", ""),
                raw=raw,
            )
            records.append(record)

        logger.info("ScienceON: %d건 검색됨", len(records))
        return records
