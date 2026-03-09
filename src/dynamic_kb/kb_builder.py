"""동적 지식베이스 빌더.

각 전문가 에이전트의 프로파일(전문분야, 매칭수준, 경력)에 따라
KIPRIS(특허), 논문(Semantic Scholar/OpenAlex/KCI/ScienceON), KAIA(지정기술),
CODIL(건설기준), KCSC(건설기준 전문) 데이터를 수집하고 에이전트별 맞춤 KB를 구축한다.

논문 소스 우선순위:
  1. OpenAlex (무료, 키 불필요, 2억+ 학술 문헌, OA PDF URL 포함)
  2. Semantic Scholar (무료, 인증 불필요)
  3. KCI (국내 학술지 특화, data.go.kr 키 필요)
  4. ScienceON (토큰 발급 이슈 미해결, 폴백)

건설기준 소스:
  1. KCSC (KDS/KCS 전문 - 사전 수집 데이터 활용)
  2. CODIL (보고서/기준 - 크롤링)
"""

from __future__ import annotations

import logging
from dataclasses import asdict

from src.dynamic_kb.codil_crawler import CODILCrawler
from src.dynamic_kb.kaia_crawler import KaiaCrawler
from src.dynamic_kb.kci_client import KCIClient
from src.dynamic_kb.kipris_client import KiprisClient
from src.dynamic_kb.openalex_client import OpenAlexClient
from src.dynamic_kb.scienceon_client import ScienceOnClient
from src.dynamic_kb.semantic_scholar_client import SemanticScholarClient
from src.models.agent_profile import AgentProfile, MatchLevel
from src.models.cnt_classification import MAJOR_CATEGORIES, get_middle_categories
from src.static_kb.evaluation_criteria import get_evaluation_summary
from src.storage.kb_store import KBStore

logger = logging.getLogger(__name__)


class KBBuilder:
    """에이전트별 동적 지식베이스 빌더."""

    def __init__(
        self,
        kipris: KiprisClient | None = None,
        scienceon: ScienceOnClient | None = None,
        semantic_scholar: SemanticScholarClient | None = None,
        openalex: OpenAlexClient | None = None,
        kci: KCIClient | None = None,
        codil: CODILCrawler | None = None,
        kaia: KaiaCrawler | None = None,
        store: KBStore | None = None,
    ):
        self.kipris = kipris or KiprisClient()
        self.scienceon = scienceon or ScienceOnClient()
        self.semantic_scholar = semantic_scholar or SemanticScholarClient()
        self.openalex = openalex or OpenAlexClient()
        self.kci = kci or KCIClient()
        self.codil = codil or CODILCrawler()
        self.kaia = kaia or KaiaCrawler()
        self.store = store or KBStore()

    def build_agent_kb(
        self,
        profile: AgentProfile,
        max_patents: int = 30,
        max_papers: int = 30,
        max_codil: int = 10,
    ) -> dict:
        """단일 에이전트를 위한 통합 KB를 구축.

        논문은 Semantic Scholar → KCI → ScienceON 순으로 수집하여
        max_papers에 도달할 때까지 보충한다.

        Returns:
            dict: 에이전트 KB 전체 (정적 + 동적 통합)
        """
        logger.info(
            "에이전트 KB 구축 시작: %s (전문분야: %s, 매칭: %s, 경력: %s)",
            profile.agent_id,
            profile.specialty_description,
            profile.match_level.value,
            profile.experience.value,
        )

        keywords = self._generate_search_keywords(profile)

        # 1. 특허 데이터 수집 (KIPRIS)
        patents = self._collect_patents(keywords, max_patents)

        # 2. 논문 데이터 수집 (다중 소스 - 폴백 체인)
        papers_by_source = self._collect_papers_multi_source(keywords, max_papers)

        # 3. CODIL 건설기준 수집
        codil_docs = self._collect_codil(keywords, max_codil)

        # 4. 저장
        category_code = profile.specialty.major.code
        primary_keyword = keywords[0]

        if patents:
            self.store.save_patents(patents, category_code, primary_keyword)

        for source_name, records in papers_by_source.items():
            if not records:
                continue
            if source_name == "openalex":
                self.store.save_openalex_papers(records, category_code, primary_keyword)
            elif source_name == "semantic_scholar":
                self.store.save_scholar_papers(records, category_code, primary_keyword)
            elif source_name == "kci":
                self.store.save_kci_papers(records, category_code, primary_keyword)
            elif source_name == "scienceon":
                self.store.save_papers(records, category_code, primary_keyword)

        if codil_docs:
            self.store.save_codil_docs(codil_docs, category_code, primary_keyword)

        # 4-b. 사전 수집된 데이터 로드 (KCSC, CrossRef, OpenAlex 차원별)
        kcsc_standards = self.store.load_kcsc_standards(category_code)
        crossref_papers = self.store.load_crossref_papers(category_code)
        pre_openalex = self.store.load_openalex_papers(category_code)

        # 5. 통합 KB 구성
        all_papers = []
        for records in papers_by_source.values():
            all_papers.extend([asdict(p) for p in records])

        # 사전 수집 논문 추가 (중복 허용 — 벡터DB에서 dedup 처리)
        all_papers.extend(crossref_papers)
        all_papers.extend(pre_openalex)

        agent_kb = {
            "agent_profile": {
                "agent_id": profile.agent_id,
                "specialty": profile.specialty_description,
                "match_level": profile.match_level.value,
                "experience": profile.experience.value,
                "experience_years": profile.experience_years,
                "behavior": profile.behavior_description,
            },
            "static_kb": {
                "evaluation_criteria": get_evaluation_summary(),
            },
            "dynamic_kb": {
                "patents": [asdict(p) for p in patents],
                "papers": all_papers,
                "codil_docs": [asdict(d) for d in codil_docs],
                "kcsc_standards": kcsc_standards,
                "search_keywords": keywords,
                "paper_sources": {k: len(v) for k, v in papers_by_source.items()},
                "pre_collected": {
                    "kcsc": len(kcsc_standards),
                    "crossref": len(crossref_papers),
                    "openalex_pre": len(pre_openalex),
                },
            },
        }

        self.store.save_agent_kb(profile.agent_id, agent_kb)

        total_papers = sum(len(v) for v in papers_by_source.values())
        source_summary = ", ".join(f"{k}:{len(v)}" for k, v in papers_by_source.items() if v)
        logger.info(
            "에이전트 KB 구축 완료: %s (특허 %d건, 논문 %d건 [%s], CODIL %d건)",
            profile.agent_id,
            len(patents),
            total_papers,
            source_summary,
            len(codil_docs),
        )
        return agent_kb

    def _collect_patents(self, keywords: list[str], max_results: int) -> list:
        """KIPRIS에서 특허 데이터를 수집."""
        patents = []
        for kw in keywords:
            results = self.kipris.search_construction_patents(kw, max_results=max_results)
            patents.extend(results)
            if len(patents) >= max_results:
                break
        return patents[:max_results]

    def _collect_papers_multi_source(
        self,
        keywords: list[str],
        max_papers: int,
    ) -> dict:
        """다중 소스에서 논문을 수집. 폴백 체인으로 동작.

        1차: OpenAlex (무료, 키 불필요, 2억+ 학술 문헌)
        2차: Semantic Scholar (무료, 즉시 사용 가능)
        3차: KCI (국내 학술지, API 키 필요)
        4차: ScienceON (토큰 발급 성공 시에만)

        사전 수집된 데이터(openalex_papers, crossref_papers)도 함께 활용한다.
        """
        results: dict = {}
        remaining = max_papers

        # 1차: OpenAlex (가장 안정적이고 풍부한 소스)
        openalex_papers = []
        openalex_quota = min(remaining, max_papers)
        for kw in keywords:
            records = self.openalex.search_construction_papers(
                kw, max_results=openalex_quota,
            )
            openalex_papers.extend(records)
            if len(openalex_papers) >= openalex_quota:
                break
        openalex_papers = openalex_papers[:openalex_quota]
        results["openalex"] = openalex_papers
        remaining -= len(openalex_papers)

        # 2차: Semantic Scholar (부족분 보충)
        scholar_papers = []
        if remaining > 0:
            scholar_quota = min(remaining, max_papers)
            for kw in keywords:
                records = self.semantic_scholar.search_construction_papers(
                    kw, max_results=scholar_quota,
                )
                scholar_papers.extend(records)
                if len(scholar_papers) >= scholar_quota:
                    break
            scholar_papers = scholar_papers[:scholar_quota]
        results["semantic_scholar"] = scholar_papers
        remaining -= len(scholar_papers)

        # 3차: KCI (부족분 보충)
        kci_papers = []
        if remaining > 0:
            for kw in keywords:
                records = self.kci.search_construction_papers(kw, max_results=remaining)
                kci_papers.extend(records)
                if len(kci_papers) >= remaining:
                    break
            kci_papers = kci_papers[:remaining]
        results["kci"] = kci_papers
        remaining -= len(kci_papers)

        # 4차: ScienceON (여전히 부족하면)
        scienceon_papers = []
        if remaining > 0:
            for kw in keywords:
                records = self.scienceon.search_construction_papers(kw, max_results=remaining)
                scienceon_papers.extend(records)
                if len(scienceon_papers) >= remaining:
                    break
            scienceon_papers = scienceon_papers[:remaining]
        results["scienceon"] = scienceon_papers

        return results

    def _collect_codil(self, keywords: list[str], max_results: int) -> list:
        """CODIL에서 건설기준/시방서 문서를 수집."""
        docs = []
        for kw in keywords:
            records = self.codil.search_construction_standards(kw, max_results=max_results)
            docs.extend(records)
            if len(docs) >= max_results:
                break
        return docs[:max_results]

    def build_shared_kb(self, max_pages: int = 10) -> dict:
        """모든 에이전트가 공유하는 기본 KB를 구축.

        - 정적 KB: 평가 기준 체계
        - 지정 건설신기술 목록
        """
        logger.info("공유 KB 구축 시작...")

        # 지정 건설신기술 목록 수집
        designated = self.kaia.fetch_all_technologies(max_pages=max_pages)
        if designated:
            self.store.save_designated_techs(designated)

        shared_kb = {
            "evaluation_criteria": get_evaluation_summary(),
            "designated_technologies_count": len(designated),
            "classification": {
                "major_categories": [
                    {"code": c.code, "name": c.name, "name_en": c.name_en}
                    for c in MAJOR_CATEGORIES
                ],
            },
        }

        return shared_kb

    def _generate_search_keywords(self, profile: AgentProfile) -> list[str]:
        """에이전트의 전문분야에 맞는 검색 키워드를 생성."""
        major = profile.specialty.major.name
        middle = profile.specialty.middle.name
        minor = profile.specialty.minor.name

        keywords = []

        if profile.match_level == MatchLevel.EXACT:
            # 정합: 세부 키워드 중심
            keywords.append(f"{minor} 건설")
            keywords.append(f"{middle} {minor}")
            keywords.append(f"{minor} 시공")
        else:
            # 부분정합: 상위 분류 키워드 중심
            keywords.append(f"{major} 건설기술")
            keywords.append(f"{middle} 건설")

        # 공통 키워드
        keywords.append(f"{major} 신기술")

        return keywords
