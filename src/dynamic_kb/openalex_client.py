"""OpenAlex API 클라이언트.

OpenAlex (https://openalex.org)는 2억+ 학술 문헌 메타데이터를 제공하는
무료 오픈 API로, 키 없이 즉시 사용 가능하다.

건설 분야 논문 수집에 최적화:
  - Concept 필터링: Civil Engineering(C22212356), Construction(C154945302) 등
  - OA(Open Access) 논문 필터링 → 전문 PDF URL 확보
  - 한국어/영문 검색 모두 지원
  - 초록, 인용수, 저널, DOI, OA PDF URL 등 풍부한 메타데이터

Rate limit: polite pool (mailto 파라미터 제공 시) 10 req/s
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import requests

logger = logging.getLogger(__name__)

# OpenAlex Concept IDs for construction/civil engineering
CONCEPT_IDS = {
    "civil_engineering": "C22212356",
    "construction_engineering": "C154945302",
    "structural_engineering": "C21199528",
    "geotechnical_engineering": "C187413196",
    "construction_management": "C106159729",
    "building_materials": "C192562407",
    "concrete": "C55493867",
    "bridge": "C2779681930",
    "waterproofing": "C2776294277",
    "earthquake_engineering": "C43249092",
    "foundation": "C2776750849",
    "tunnel": "C151730666",
    "environmental_engineering": "C39432304",
    "safety_engineering": "C2524010",
    "composite_material": "C169760540",
}

# 평가차원별 검색 키워드 매트릭스 (6차원 × 3분야)
# 각 키워드는 평가 시 해당 차원의 전문 지식 기반이 된다
EVALUATION_DIMENSION_KEYWORDS = {
    "differentiation": {  # 차별성 (25점)
        "CIV": [
            "novel bridge construction method",
            "advanced tunnel boring technology",
            "innovative foundation technique",
            "new pavement material technology",
            "improved retaining wall system",
            "next generation precast concrete",
            "advanced soil improvement method",
            "novel underwater construction",
            "smart infrastructure monitoring",
            "advanced geosynthetic application",
        ],
        "ARC": [
            "innovative building waterproofing system",
            "advanced external insulation technology",
            "novel curtain wall system",
            "high performance concrete building",
            "innovative modular construction",
            "advanced fire resistant building material",
            "new seismic isolation system building",
            "smart building envelope technology",
            "novel composite structural system",
            "advanced precast connection design",
        ],
        "MEC": [
            "construction automation robot",
            "smart construction IoT system",
            "BIM integrated construction",
            "advanced HVAC system building",
            "novel noise barrier technology",
            "innovative water treatment construction",
            "drone survey construction application",
            "3D printing construction material",
            "AI construction quality control",
            "advanced construction machinery",
        ],
    },
    "originality": {  # 독창성 (25점)
        "CIV": [
            "patent construction technology Korea",
            "breakthrough civil engineering material",
            "first application bridge Korea",
            "original pile driving method",
            "unprecedented tunnel construction",
        ],
        "ARC": [
            "patent building construction Korea",
            "breakthrough architectural technology",
            "first application building material Korea",
            "original structural connection",
            "novel facade engineering system",
        ],
        "MEC": [
            "patent construction equipment Korea",
            "breakthrough construction automation",
            "original sensor monitoring system",
            "novel construction robot design",
            "unprecedented smart construction",
        ],
    },
    "quality_improvement": {  # 품질향상 (15점)
        "CIV": [
            "construction quality assurance civil",
            "durability concrete infrastructure",
            "performance based design bridge",
            "long term monitoring structure",
            "quality control concrete placement",
        ],
        "ARC": [
            "building performance evaluation",
            "thermal insulation performance",
            "waterproofing durability test",
            "structural integrity assessment",
            "construction quality management",
        ],
        "MEC": [
            "construction equipment performance test",
            "quality assurance smart construction",
            "sensor accuracy validation",
            "BIM quality control process",
            "automation quality improvement",
        ],
    },
    "development_maturity": {  # 개발정도 (15점)
        "CIV": [
            "field application bridge construction",
            "full scale test civil engineering",
            "construction site implementation",
            "pilot project infrastructure Korea",
            "technology readiness level construction",
        ],
        "ARC": [
            "field application building technology",
            "full scale test building material",
            "prototype building system",
            "pilot project building Korea",
            "commercialization building technology",
        ],
        "MEC": [
            "field deployment construction robot",
            "prototype construction equipment",
            "pilot smart construction project",
            "commercialization construction IoT",
            "technology transfer construction",
        ],
    },
    "safety": {  # 안전성 (10점)
        "CIV": [
            "construction safety bridge tunnel",
            "seismic safety infrastructure Korea",
            "structural safety assessment",
            "construction worker safety technology",
            "disaster resilience infrastructure",
        ],
        "ARC": [
            "building fire safety technology",
            "seismic safety evaluation building",
            "structural safety monitoring building",
            "construction safety management system",
            "occupant safety building design",
        ],
        "MEC": [
            "construction robot safety standard",
            "smart safety monitoring construction",
            "equipment safety construction site",
            "IoT safety alert system construction",
            "automation safety protocol",
        ],
    },
    "eco_friendliness": {  # 친환경성 (10점)
        "CIV": [
            "sustainable construction material",
            "green infrastructure civil engineering",
            "recycled material construction",
            "low carbon concrete technology",
            "environmental impact assessment construction",
        ],
        "ARC": [
            "green building material technology",
            "energy efficient building envelope",
            "sustainable building construction Korea",
            "recycled building material",
            "zero energy building technology",
        ],
        "MEC": [
            "eco friendly construction equipment",
            "energy efficient construction method",
            "green smart construction",
            "low emission construction machinery",
            "sustainable construction automation",
        ],
    },
}


@dataclass
class OpenAlexRecord:
    """OpenAlex 논문 레코드."""
    openalex_id: str = ""
    title: str = ""
    authors: str = ""
    journal: str = ""
    publish_year: str = ""
    abstract: str = ""
    keywords: list[str] = field(default_factory=list)
    doi: str = ""
    url: str = ""
    citation_count: int = 0
    oa_url: str = ""  # Open Access PDF URL
    source: str = "openalex"
    eval_dimension: str = ""  # 매핑된 평가 차원
    raw: dict = field(default_factory=dict)


class OpenAlexClient:
    """OpenAlex API 클라이언트."""

    BASE_URL = "https://api.openalex.org"

    def __init__(self, email: str = "cnt-eval@research.kr"):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": f"CNT-Eval-Framework/1.0 (mailto:{email})",
        })
        self._email = email
        self._request_interval = 0.15  # polite pool: ~7 req/s

    def search_papers(
        self,
        query: str,
        concept_ids: list[str] | None = None,
        from_year: int | None = None,
        to_year: int | None = None,
        oa_only: bool = False,
        per_page: int = 50,
        page: int = 1,
    ) -> list[OpenAlexRecord]:
        """논문 검색.

        Args:
            query: 검색어
            concept_ids: OpenAlex concept ID 필터 (복수 가능, OR 조건)
            from_year: 시작 연도
            to_year: 종료 연도
            oa_only: OA 논문만 필터링
            per_page: 페이지당 결과 수 (최대 200)
            page: 페이지 번호
        """
        params: dict[str, Any] = {
            "search": query,
            "per_page": min(per_page, 200),
            "page": page,
            "mailto": self._email,
            "select": "id,title,authorships,primary_location,publication_year,"
                      "abstract_inverted_index,concepts,doi,open_access,"
                      "cited_by_count,keywords",
        }

        # 필터 구성
        filters = []
        if concept_ids:
            concept_filter = "|".join(concept_ids)
            filters.append(f"concepts.id:{concept_filter}")
        if from_year:
            filters.append(f"from_publication_date:{from_year}-01-01")
        if to_year:
            filters.append(f"to_publication_date:{to_year}-12-31")
        if oa_only:
            filters.append("open_access.is_oa:true")
        # 학술 논문만 (단행본, 데이터셋 등 제외)
        filters.append("type:article|review")

        if filters:
            params["filter"] = ",".join(filters)

        try:
            resp = self.session.get(
                f"{self.BASE_URL}/works", params=params, timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            time.sleep(self._request_interval)
            return self._parse_results(data.get("results", []))
        except requests.RequestException as e:
            logger.error("OpenAlex API 요청 실패: %s", e)
            return []

    def search_construction_papers(
        self,
        query: str,
        max_results: int = 100,
        from_year: int = 2015,
        oa_only: bool = False,
    ) -> list[OpenAlexRecord]:
        """건설 분야 논문을 자동 페이지네이션으로 수집."""
        concept_ids = [
            CONCEPT_IDS["civil_engineering"],
            CONCEPT_IDS["construction_engineering"],
            CONCEPT_IDS["structural_engineering"],
        ]

        all_records: list[OpenAlexRecord] = []
        page = 1
        per_page = min(max_results, 200)

        while len(all_records) < max_results:
            records = self.search_papers(
                query=query,
                concept_ids=concept_ids,
                from_year=from_year,
                oa_only=oa_only,
                per_page=per_page,
                page=page,
            )
            if not records:
                break
            all_records.extend(records)
            page += 1

        return all_records[:max_results]

    def search_by_dimension(
        self,
        dimension: str,
        category: str,
        max_per_keyword: int = 30,
        from_year: int = 2018,
    ) -> list[OpenAlexRecord]:
        """평가 차원별 논문 수집.

        Args:
            dimension: 평가 차원 키 (differentiation, originality, etc.)
            category: 분야 코드 (CIV, ARC, MEC)
            max_per_keyword: 키워드당 최대 수집 수
            from_year: 시작 연도
        """
        keywords = EVALUATION_DIMENSION_KEYWORDS.get(dimension, {}).get(category, [])
        if not keywords:
            logger.warning("키워드 없음: dimension=%s, category=%s", dimension, category)
            return []

        all_records: list[OpenAlexRecord] = []
        seen_ids: set[str] = set()

        for kw in keywords:
            records = self.search_construction_papers(
                query=kw,
                max_results=max_per_keyword,
                from_year=from_year,
            )

            for r in records:
                if r.openalex_id not in seen_ids and r.abstract:
                    r.eval_dimension = dimension
                    seen_ids.add(r.openalex_id)
                    all_records.append(r)

            logger.info(
                "OpenAlex [%s/%s] '%s': %d건 (누적 %d건)",
                dimension, category, kw, len(records), len(all_records),
            )

        return all_records

    def fetch_oa_pdf_urls(
        self,
        doi_list: list[str],
    ) -> dict[str, str]:
        """DOI 목록에 대해 OA PDF URL을 조회 (Unpaywall 대체).

        OpenAlex의 open_access 필드를 활용하여 OA URL을 확보한다.
        """
        result: dict[str, str] = {}

        for doi in doi_list:
            if not doi:
                continue
            clean_doi = doi.replace("https://doi.org/", "")
            try:
                resp = self.session.get(
                    f"{self.BASE_URL}/works/doi:{clean_doi}",
                    params={"mailto": self._email, "select": "doi,open_access"},
                    timeout=15,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    oa = data.get("open_access", {})
                    oa_url = oa.get("oa_url", "")
                    if oa_url:
                        result[doi] = oa_url
                time.sleep(self._request_interval)
            except Exception as e:
                logger.debug("OA URL 조회 실패 %s: %s", doi, e)

        return result

    def _parse_results(self, results: list[dict]) -> list[OpenAlexRecord]:
        """API 응답을 OpenAlexRecord 리스트로 변환."""
        records: list[OpenAlexRecord] = []

        for work in results:
            # 초록 복원 (inverted index → 텍스트)
            abstract = self._reconstruct_abstract(
                work.get("abstract_inverted_index"),
            )

            # 저자
            authorships = work.get("authorships", [])
            authors = ", ".join(
                a.get("author", {}).get("display_name", "")
                for a in authorships[:10]
            )

            # 저널/출처
            primary = work.get("primary_location") or {}
            source = primary.get("source") or {}
            journal = source.get("display_name", "")

            # OA URL
            oa_info = work.get("open_access", {})
            oa_url = oa_info.get("oa_url", "")

            # 키워드 (concepts)
            concepts = work.get("concepts", [])
            keywords = [
                c.get("display_name", "")
                for c in concepts[:10]
                if c.get("score", 0) > 0.3
            ]

            # OpenAlex keywords (newer API)
            kw_list = work.get("keywords", [])
            for kw_item in kw_list[:5]:
                kw_name = kw_item.get("display_name", "") if isinstance(kw_item, dict) else str(kw_item)
                if kw_name and kw_name not in keywords:
                    keywords.append(kw_name)

            doi = work.get("doi", "") or ""
            # DOI URL → 순수 DOI
            if doi.startswith("https://doi.org/"):
                doi = doi.replace("https://doi.org/", "")

            record = OpenAlexRecord(
                openalex_id=work.get("id", ""),
                title=work.get("title", "") or "",
                authors=authors,
                journal=journal,
                publish_year=str(work.get("publication_year", "")),
                abstract=abstract,
                keywords=keywords,
                doi=doi,
                url=work.get("id", ""),
                citation_count=work.get("cited_by_count", 0) or 0,
                oa_url=oa_url,
                source="openalex",
            )
            records.append(record)

        return records

    @staticmethod
    def _reconstruct_abstract(inverted_index: dict | None) -> str:
        """OpenAlex inverted index를 원문 텍스트로 복원."""
        if not inverted_index:
            return ""

        try:
            word_positions: list[tuple[int, str]] = []
            for word, positions in inverted_index.items():
                for pos in positions:
                    word_positions.append((pos, word))

            word_positions.sort(key=lambda x: x[0])
            return " ".join(w for _, w in word_positions)
        except Exception:
            return ""
