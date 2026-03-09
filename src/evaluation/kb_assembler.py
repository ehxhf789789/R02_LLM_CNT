"""계층적 지식베이스 어셈블러 (PIKE-RAG 패턴).

에이전트 프로파일에 따라 3단계 계층 구조로 KB를 조립한다:
  Level 1 (공통): 평가 매뉴얼 + 평가기준표 → 모든 에이전트 공유
  Level 2 (분야별): 해당 분야 특허 + 논문 + 지정기술 + CODIL → 정합/부분정합 에이전트
  Level 3 (경력별): 평가 행동 특성 + 판단 기조 → 고/중/저 경력 차별화
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.models.agent_profile import AgentProfile, ExperienceLevel, MatchLevel
from src.static_kb.evaluation_criteria import get_evaluation_summary
from src.storage.kb_store import KBStore

logger = logging.getLogger(__name__)


@dataclass
class HierarchicalKB:
    """3단계 계층적 지식베이스."""

    # Level 1: 공통 지식 (모든 에이전트 공유)
    evaluation_criteria: str = ""
    manual_sections: dict = field(default_factory=dict)

    # Level 2: 분야별 지식 (전문분야에 따라 다름)
    prior_patents: list[dict] = field(default_factory=list)
    prior_papers: list[dict] = field(default_factory=list)
    designated_techs: list[dict] = field(default_factory=list)
    codil_docs: list[dict] = field(default_factory=list)

    # Level 3: 경력별 행동 특성
    behavior_profile: str = ""
    judgment_tendency: str = ""
    scoring_bias: dict = field(default_factory=dict)

    # 메타
    agent_id: str = ""
    specialty_description: str = ""
    match_level: str = ""
    experience_level: str = ""


# 경력별 판단 기조 (Level 3)
JUDGMENT_TENDENCIES: dict[ExperienceLevel, str] = {
    ExperienceLevel.HIGH: (
        "당신은 15년 이상의 건설신기술 심사 경험을 보유한 고경력 전문위원입니다.\n"
        "판단 기조:\n"
        "- 형식적 완결성보다 기술의 본질적 차별성에 집중합니다.\n"
        "- 선행기술과의 실질적 차이를 깊이 분석하며, 표면적 유사성에 현혹되지 않습니다.\n"
        "- 핵심 기술 원리의 부실에는 엄격하지만, 보조적 구성의 미비에는 관대합니다.\n"
        "- 현장 경험을 바탕으로 기술의 실용성과 파급 효과를 종합적으로 판단합니다.\n"
        "- 불확실한 경우에도 경험에 기반한 정성적 판단을 내릴 수 있습니다."
    ),
    ExperienceLevel.MEDIUM: (
        "당신은 7~14년의 건설신기술 심사 경험을 보유한 중경력 전문위원입니다.\n"
        "판단 기조:\n"
        "- 기술 내용과 형식적 완결성의 균형을 추구합니다.\n"
        "- 평가 기준표의 서술에 충실하게 평가하되, 현장 적용성도 고려합니다.\n"
        "- 정량적 데이터와 정성적 판단을 균형있게 활용합니다.\n"
        "- 선행기술 조사 결과를 체계적으로 비교 분석합니다.\n"
        "- 판단 근거를 명확히 제시하려 노력합니다."
    ),
    ExperienceLevel.LOW: (
        "당신은 3~6년의 건설신기술 심사 경험을 보유한 저경력 전문위원입니다.\n"
        "판단 기조:\n"
        "- 평가 기준표의 문언에 엄격히 의거하여 판단합니다.\n"
        "- 형식적 완결성(시험성적서, 인증서 등)에 민감합니다.\n"
        "- 불확실한 경우 보수적으로 판정하는 경향이 있습니다.\n"
        "- 정량적 증거를 중시하며, 정성적 판단에는 신중합니다.\n"
        "- 기준에 명시되지 않은 사항에 대해서는 감점하는 경향이 있습니다."
    ),
}

# 경력별 채점 편향 (Level 3)
SCORING_BIASES: dict[ExperienceLevel, dict] = {
    ExperienceLevel.HIGH: {
        "novelty_weight": 1.1,       # 신규성을 약간 더 중시
        "evidence_strictness": 0.8,  # 증빙에 다소 관대
        "risk_tolerance": 0.9,       # 불확실성에 관대
    },
    ExperienceLevel.MEDIUM: {
        "novelty_weight": 1.0,       # 균형
        "evidence_strictness": 1.0,  # 균형
        "risk_tolerance": 1.0,       # 균형
    },
    ExperienceLevel.LOW: {
        "novelty_weight": 0.9,       # 진보성을 약간 더 중시
        "evidence_strictness": 1.2,  # 증빙에 엄격
        "risk_tolerance": 1.1,       # 불확실성에 보수적
    },
}


class KBAssembler:
    """계층적 KB 어셈블러.

    에이전트 프로파일에 따라 Level 1/2/3 지식을 조합하여
    HierarchicalKB를 생성한다.

    벡터 KB(LanceDB)가 사용 가능하면 RAG 기반 검색을 우선 사용하고,
    없으면 JSON store에서 직접 로드한다.
    """

    def __init__(self, store: KBStore | None = None, vectorizer=None):
        self.store = store or KBStore()
        self.vectorizer = vectorizer  # KBVectorizer instance (optional)

    def assemble(
        self,
        profile: AgentProfile,
        tech_query: str = "",
        exclude_tech_numbers: list[str] | None = None,
    ) -> HierarchicalKB:
        """에이전트 프로파일에 맞는 계층적 KB를 조립.

        Args:
            profile: 에이전트 프로파일
            tech_query: 벡터 검색용 쿼리 (제안기술명 등)
            exclude_tech_numbers: KB에서 제외할 기술 번호
        """
        category_code = profile.specialty.major.code

        # Level 1: 공통 지식
        evaluation_criteria = get_evaluation_summary()
        manual_sections = self._load_manual()

        # Level 2: 분야별 지식
        if self.vectorizer and tech_query:
            # 벡터 KB 기반 RAG 검색
            # category_major 필터: 특허/논문/CODIL은 코드(ARC/CIV/MEC),
            # 지정기술은 한글명(건축/토목/기계설비)으로 저장됨
            major_code = category_code  # ARC, CIV, MEC
            major_name = profile.specialty.major.name  # 건축, 토목, 기계설비
            prior_patents = self.vectorizer.search(
                query=tech_query,
                top_k=30 if profile.match_level == MatchLevel.EXACT else 50,
                source_type="patent",
                category_major=major_code,
                exclude_tech_numbers=exclude_tech_numbers,
            )
            prior_papers = self.vectorizer.search(
                query=tech_query,
                top_k=30 if profile.match_level == MatchLevel.EXACT else 50,
                source_type="paper",
                category_major=major_code,
                exclude_tech_numbers=exclude_tech_numbers,
            )
            designated_techs = self.vectorizer.search(
                query=tech_query,
                top_k=10,
                source_type="designated_tech",
                category_major=major_name,
                exclude_tech_numbers=exclude_tech_numbers,
            )
            codil_docs = self.vectorizer.search(
                query=tech_query,
                top_k=10,
                source_type="codil",
                category_major=major_code,
            )
        else:
            # JSON store 기반 (폴백)
            prior_patents = self.store.load_patents(category_code)
            prior_papers = (
                self.store.load_scholar_papers(category_code)
                + self.store.load_kci_papers(category_code)
                + self.store.load_papers(category_code)
            )
            designated_techs = self._filter_designated_techs(profile, exclude_tech_numbers)
            codil_docs = self.store.load_codil_docs(category_code)

            # 매칭수준에 따른 필터링
            if profile.match_level == MatchLevel.EXACT:
                prior_patents = self._filter_by_relevance(prior_patents, profile, top_k=30)
                prior_papers = self._filter_by_relevance(prior_papers, profile, top_k=30)
            else:
                prior_patents = prior_patents[:50]
                prior_papers = prior_papers[:50]

        # Level 3: 경력별 행동 특성
        behavior_profile = profile.behavior_description
        judgment_tendency = JUDGMENT_TENDENCIES[profile.experience]
        scoring_bias = SCORING_BIASES[profile.experience]

        kb = HierarchicalKB(
            evaluation_criteria=evaluation_criteria,
            manual_sections=manual_sections,
            prior_patents=prior_patents,
            prior_papers=prior_papers,
            designated_techs=designated_techs,
            codil_docs=codil_docs,
            behavior_profile=behavior_profile,
            judgment_tendency=judgment_tendency,
            scoring_bias=scoring_bias,
            agent_id=profile.agent_id,
            specialty_description=profile.specialty_description,
            match_level=profile.match_level.value,
            experience_level=profile.experience.value,
        )

        logger.info(
            "KB 조립 완료: %s (특허 %d, 논문 %d, 지정기술 %d, CODIL %d)",
            profile.agent_id,
            len(kb.prior_patents),
            len(kb.prior_papers),
            len(kb.designated_techs),
            len(kb.codil_docs),
        )
        return kb

    def _load_manual(self) -> dict:
        """파싱된 매뉴얼 데이터를 로드."""
        from src.static_kb.manual_parser import load_parsed_manual
        return load_parsed_manual()

    def _filter_designated_techs(
        self,
        profile: AgentProfile,
        exclude_tech_numbers: list[str] | None = None,
    ) -> list[dict]:
        """에이전트 전문분야에 해당하는 지정기술만 필터링.

        통제 실험을 위해 exclude_tech_numbers에 포함된 기술은 제외한다.
        """
        all_techs = self.store.load_designated_techs()
        exclude_set = set(exclude_tech_numbers or [])
        major_name = profile.specialty.major.name
        middle_name = profile.specialty.middle.name

        filtered = []
        for tech in all_techs:
            tech_num = tech.get("tech_number", "")
            if tech_num and tech_num in exclude_set:
                continue

            field_str = tech.get("tech_field", "")
            if major_name in field_str:
                if profile.match_level == MatchLevel.EXACT:
                    if middle_name in field_str:
                        filtered.append(tech)
                else:
                    filtered.append(tech)

        return filtered

    def _filter_by_relevance(
        self,
        records: list[dict],
        profile: AgentProfile,
        top_k: int = 30,
    ) -> list[dict]:
        """에이전트 전문분야 키워드와의 관련성으로 필터링.

        간단한 키워드 매칭 기반 (향후 임베딩 기반으로 확장 가능).
        """
        minor_name = profile.specialty.minor.name
        middle_name = profile.specialty.middle.name

        scored = []
        for record in records:
            score = 0
            searchable = (
                record.get("title", "")
                + record.get("abstract", "")
                + record.get("tech_name", "")
            ).lower()

            if minor_name.lower() in searchable:
                score += 3
            if middle_name.lower() in searchable:
                score += 1
            scored.append((score, record))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:top_k]]
