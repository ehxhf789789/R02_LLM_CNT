"""선행기술 검색기 (RAG-Novelty 방식).

제안기술의 키워드로 선행 특허/논문/지정기술을 검색하여
에이전트에게 "현재 기술 동향"으로 제공한다.
에이전트는 이 선행기술과 제안기술을 비교하여 차별성을 판단한다.

흐름:
  1. 제안기술 명세서에서 핵심 키워드 추출
  2. 키워드로 KIPRIS(특허) + Semantic Scholar/KCI(논문) + KAIA(지정기술) 검색
  3. 검색 결과를 관련도 순으로 정렬
  4. 상위 N건을 "선행기술 컨텍스트"로 에이전트에게 전달
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from src.dynamic_kb.kipris_client import KiprisClient
from src.dynamic_kb.semantic_scholar_client import SemanticScholarClient
from src.dynamic_kb.kci_client import KCIClient
from src.storage.kb_store import KBStore

logger = logging.getLogger(__name__)


@dataclass
class PriorArtContext:
    """선행기술 검색 결과 컨텍스트."""
    query_keywords: list[str] = field(default_factory=list)
    patents: list[dict] = field(default_factory=list)
    papers: list[dict] = field(default_factory=list)
    designated_techs: list[dict] = field(default_factory=list)
    total_count: int = 0

    def to_context_text(self, max_patents: int = 10, max_papers: int = 10) -> str:
        """에이전트 프롬프트에 삽입할 선행기술 컨텍스트 텍스트 생성."""
        lines = [
            "## 선행기술 조사 결과",
            f"검색 키워드: {', '.join(self.query_keywords)}",
            "",
        ]

        # 특허
        if self.patents:
            lines.append(f"### 관련 특허 ({len(self.patents)}건 중 상위 {min(len(self.patents), max_patents)}건)")
            for i, p in enumerate(self.patents[:max_patents], 1):
                title = p.get("title", "")
                applicant = p.get("applicant_name", "")
                app_date = p.get("application_date", "")
                abstract = p.get("abstract", "")[:200]
                lines.append(f"[특허{i}] {title}")
                lines.append(f"  출원인: {applicant} | 출원일: {app_date}")
                if abstract:
                    lines.append(f"  요약: {abstract}...")
                lines.append("")

        # 논문
        if self.papers:
            lines.append(f"### 관련 논문 ({len(self.papers)}건 중 상위 {min(len(self.papers), max_papers)}건)")
            for i, p in enumerate(self.papers[:max_papers], 1):
                title = p.get("title", "")
                authors = p.get("authors", "")
                year = p.get("publish_year", "")
                abstract = p.get("abstract", "")[:200]
                lines.append(f"[논문{i}] {title}")
                lines.append(f"  저자: {authors} | 연도: {year}")
                if abstract:
                    lines.append(f"  요약: {abstract}...")
                lines.append("")

        # 지정기술
        if self.designated_techs:
            lines.append(f"### 유사 지정 건설신기술 ({len(self.designated_techs)}건)")
            for i, t in enumerate(self.designated_techs[:5], 1):
                name = t.get("tech_name", "")
                field_str = t.get("tech_field", "")
                applicant = t.get("applicant", "")
                lines.append(f"[지정기술{i}] {name}")
                lines.append(f"  분야: {field_str} | 개발사: {applicant}")
                lines.append("")

        if not self.patents and not self.papers and not self.designated_techs:
            lines.append("(선행기술 검색 결과 없음)")

        return "\n".join(lines)


class PriorArtSearcher:
    """제안기술에 대한 선행기술 검색기."""

    def __init__(
        self,
        kipris: KiprisClient | None = None,
        scholar: SemanticScholarClient | None = None,
        kci: KCIClient | None = None,
        store: KBStore | None = None,
    ):
        self.kipris = kipris or KiprisClient()
        self.scholar = scholar or SemanticScholarClient()
        self.kci = kci or KCIClient()
        self.store = store or KBStore()

    def search(
        self,
        tech_name: str,
        tech_description: str = "",
        tech_keywords: list[str] | None = None,
        max_patents: int = 15,
        max_papers: int = 15,
        exclude_tech_numbers: list[str] | None = None,
    ) -> PriorArtContext:
        """제안기술에 대한 선행기술을 종합 검색.

        Args:
            tech_name: 제안기술명
            tech_description: 기술 설명 (키워드 추출용)
            tech_keywords: 직접 지정한 검색 키워드 (없으면 자동 추출)
            max_patents: 최대 특허 수집 수
            max_papers: 최대 논문 수집 수
            exclude_tech_numbers: 자기참조 방지를 위해 제외할 기술 번호
        """
        # 1. 키워드 추출
        if tech_keywords:
            keywords = tech_keywords
        else:
            keywords = self.extract_keywords(tech_name, tech_description)

        logger.info("선행기술 검색 시작: 키워드 %s", keywords)

        # 2. 특허 검색 (KIPRIS)
        patents = self._search_patents(keywords, max_patents)

        # 3. 논문 검색 (Semantic Scholar + KCI)
        papers = self._search_papers(keywords, max_papers)

        # 4. 지정기술 매칭 (로컬 DB) — 자기참조 제외
        designated = self._search_designated_techs(keywords, exclude_tech_numbers)

        context = PriorArtContext(
            query_keywords=keywords,
            patents=patents,
            papers=papers,
            designated_techs=designated,
            total_count=len(patents) + len(papers) + len(designated),
        )

        logger.info(
            "선행기술 검색 완료: 특허 %d건, 논문 %d건, 지정기술 %d건",
            len(patents), len(papers), len(designated),
        )
        return context

    def extract_keywords(self, tech_name: str, description: str = "") -> list[str]:
        """제안기술명과 설명에서 검색 키워드를 추출.

        간단한 규칙 기반 추출 (향후 LLM 기반으로 확장 가능).
        """
        combined = f"{tech_name} {description}"

        # 불용어 제거
        stopwords = {
            "건설", "신기술", "기술", "공법", "시스템", "장치", "방법", "구조",
            "개선", "향상", "적용", "이용", "활용", "대한", "위한", "통한",
            "및", "의", "을", "를", "에", "와", "과", "는", "은",
        }

        # 핵심 명사 추출 (한국어 + 영어)
        tokens = re.findall(r'[가-힣]{2,}|[a-zA-Z]{3,}', combined)
        keywords = [t for t in tokens if t not in stopwords]

        # 기술명 자체를 첫 번째 키워드로
        result = [tech_name]

        # 2-gram 조합 추가
        if len(keywords) >= 2:
            for i in range(min(len(keywords) - 1, 3)):
                bigram = f"{keywords[i]} {keywords[i+1]}"
                if bigram != tech_name:
                    result.append(bigram)

        # 개별 키워드 추가
        for kw in keywords[:5]:
            if kw not in result and len(kw) >= 2:
                result.append(kw)

        return result[:5]  # 최대 5개

    def _search_patents(self, keywords: list[str], max_results: int) -> list[dict]:
        """키워드로 특허 검색."""
        from dataclasses import asdict
        patents = []
        for kw in keywords[:3]:
            results = self.kipris.search_construction_patents(kw, max_results=max_results)
            patents.extend([asdict(r) for r in results])
            if len(patents) >= max_results:
                break
        return patents[:max_results]

    def _search_papers(self, keywords: list[str], max_results: int) -> list[dict]:
        """키워드로 논문 검색 (Semantic Scholar + KCI)."""
        from dataclasses import asdict
        papers = []

        # Semantic Scholar
        for kw in keywords[:2]:
            results = self.scholar.search_construction_papers(kw, max_results=max_results)
            papers.extend([asdict(r) for r in results])
            if len(papers) >= max_results:
                break

        remaining = max_results - len(papers)
        if remaining > 0:
            # KCI 보충
            for kw in keywords[:2]:
                results = self.kci.search_construction_papers(kw, max_results=remaining)
                papers.extend([asdict(r) for r in results])
                if len(papers) >= max_results:
                    break

        return papers[:max_results]

    def _search_designated_techs(
        self, keywords: list[str], exclude_tech_numbers: list[str] | None = None,
    ) -> list[dict]:
        """저장된 지정기술 중 키워드와 매칭되는 것을 찾음.

        Args:
            keywords: 검색 키워드
            exclude_tech_numbers: 자기참조 방지를 위해 제외할 기술 번호
        """
        all_techs = self.store.load_designated_techs()
        if not all_techs:
            return []

        exclude_set = set(exclude_tech_numbers or [])

        matched = []
        for tech in all_techs:
            # 자기참조 제외: 평가 대상 기술 자체가 선행기술로 검색되지 않도록
            tech_num = str(tech.get("tech_number", ""))
            if tech_num and tech_num in exclude_set:
                continue

            searchable = (
                tech.get("tech_name", "") + tech.get("tech_field", "")
            ).lower()

            for kw in keywords:
                if kw.lower() in searchable:
                    matched.append(tech)
                    break

        return matched[:10]
