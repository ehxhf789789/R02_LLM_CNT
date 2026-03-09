"""전문가 에이전트 프로파일 모델.

각 에이전트는 전문 분야 매칭 수준(정합/부분정합)과
심사 경력(고/중/저)을 기반으로 페르소나가 결정된다.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from .cnt_classification import CNTClassification


class MatchLevel(str, Enum):
    EXACT = "exact"          # 정합: 기술 분야 직접 일치
    PARTIAL = "partial"      # 부분정합: 인접·관련 분야


class ExperienceLevel(str, Enum):
    HIGH = "high"            # 고경력 (15년+)
    MEDIUM = "medium"        # 중경력 (7~14년)
    LOW = "low"              # 저경력 (3~6년)


EXPERIENCE_BEHAVIORS: dict[ExperienceLevel, str] = {
    ExperienceLevel.HIGH: (
        "본질적 차별성에 집중하며, 형식적 완결성에는 관대하나 "
        "핵심 기술 부실에는 엄격합니다. 선행기술과의 실질적 차이를 "
        "깊이 분석합니다."
    ),
    ExperienceLevel.MEDIUM: (
        "기술 내용과 형식적 완결성의 균형을 추구하며, "
        "평가 기준표 서술에 충실하게 평가합니다."
    ),
    ExperienceLevel.LOW: (
        "형식적 완결성에 민감하며, 불확실한 경우 보수적으로 "
        "판정합니다. 기준표의 문언에 엄격히 의거합니다."
    ),
}


class AgentProfile(BaseModel):
    """위원 에이전트의 페르소나 정의."""
    agent_id: str
    specialty: CNTClassification
    match_level: MatchLevel
    experience: ExperienceLevel
    experience_years: int

    @property
    def behavior_description(self) -> str:
        return EXPERIENCE_BEHAVIORS[self.experience]

    @property
    def specialty_description(self) -> str:
        parts = [
            f"대분류: {self.specialty.major.name}",
            f"중분류: {self.specialty.middle.name}",
            f"소분류: {self.specialty.minor.name}",
        ]
        return " > ".join(parts)
