"""Semantic Scholar API 클라이언트.

ScienceON 대안으로, 무료 API를 통해 건설 분야 학술 논문을 검색한다.
인증 불필요 (API 키 선택적), Rate limit: 키 없이 100 req/5분, 키 있으면 1 req/sec.

API 문서: https://api.semanticscholar.org/api-docs/graph
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import requests

from config.settings import settings

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
PAPER_FIELDS = "title,authors,year,abstract,externalIds,journal,citationCount,fieldsOfStudy,publicationTypes,url"


@dataclass
class SemanticScholarRecord:
    """Semantic Scholar 논문 레코드."""
    paper_id: str = ""
    title: str = ""
    authors: str = ""
    journal: str = ""
    publish_year: str = ""
    abstract: str = ""
    keywords: list[str] = field(default_factory=list)
    doi: str = ""
    url: str = ""
    citation_count: int = 0
    source: str = "semantic_scholar"
    raw: dict = field(default_factory=dict)


class SemanticScholarClient:
    """Semantic Scholar API 클라이언트."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or getattr(settings, "semantic_scholar_api_key", "")
        self.session = requests.Session()
        if self.api_key:
            self.session.headers["x-api-key"] = self.api_key
        self._request_interval = 1.0 if self.api_key else 5.0  # rate limit 준수 (100 req/5분)

    def search_papers(
        self,
        query: str,
        limit: int = 10,
        offset: int = 0,
        year: str = "",
        fields_of_study: str = "",
    ) -> list[SemanticScholarRecord]:
        """논문 검색.

        Args:
            query: 검색어
            limit: 결과 수 (최대 100)
            offset: 시작 위치
            year: 연도 필터 (예: "2020-", "2018-2023")
            fields_of_study: 분야 필터 (예: "Engineering")
        """
        params: dict = {
            "query": query,
            "limit": min(limit, 100),
            "offset": offset,
            "fields": PAPER_FIELDS,
        }
        if year:
            params["year"] = year
        if fields_of_study:
            params["fieldsOfStudy"] = fields_of_study

        try:
            resp = self.session.get(SEARCH_URL, params=params, timeout=30)
            # 429 재시도 (최대 3회, 점진적 백오프)
            for retry_wait in [10, 30, 60]:
                if resp.status_code != 429:
                    break
                logger.warning("Rate limit 초과, %d초 대기 후 재시도", retry_wait)
                time.sleep(retry_wait)
                resp = self.session.get(SEARCH_URL, params=params, timeout=30)
            resp.raise_for_status()
            return self._parse_response(resp.json())
        except requests.RequestException as e:
            logger.error("Semantic Scholar API 요청 실패: %s", e)
            return []

    def search_construction_papers(
        self,
        tech_keyword: str,
        max_results: int = 50,
    ) -> list[SemanticScholarRecord]:
        """건설 분야 논문을 수집. 페이지네이션 자동 처리.

        건설 키워드를 영문으로 보강하여 검색 범위를 넓힌다.
        """
        all_records: list[SemanticScholarRecord] = []
        offset = 0
        per_page = min(max_results, 100)

        while len(all_records) < max_results:
            records = self.search_papers(
                query=tech_keyword,
                limit=per_page,
                offset=offset,
            )
            if not records:
                break
            all_records.extend(records)
            offset += per_page
            time.sleep(self._request_interval)

        return all_records[:max_results]

    def _parse_response(self, data: dict) -> list[SemanticScholarRecord]:
        """API JSON 응답을 SemanticScholarRecord 리스트로 변환."""
        records: list[SemanticScholarRecord] = []

        for paper in data.get("data", []):
            authors_list = paper.get("authors") or []
            authors_str = ", ".join(a.get("name", "") for a in authors_list)

            journal_info = paper.get("journal") or {}
            journal_name = journal_info.get("name", "") if isinstance(journal_info, dict) else ""

            external_ids = paper.get("externalIds") or {}
            doi = external_ids.get("DOI", "")

            fields = paper.get("fieldsOfStudy") or []

            record = SemanticScholarRecord(
                paper_id=paper.get("paperId", ""),
                title=paper.get("title", ""),
                authors=authors_str,
                journal=journal_name,
                publish_year=str(paper.get("year", "")),
                abstract=paper.get("abstract") or "",
                keywords=fields,
                doi=doi,
                url=paper.get("url", ""),
                citation_count=paper.get("citationCount", 0),
                raw=paper,
            )
            records.append(record)

        logger.info("Semantic Scholar: %d건 검색됨", len(records))
        return records
