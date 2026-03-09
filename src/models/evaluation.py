"""건설신기술 1차 평가 항목 구조 모델.

신규성(50점) + 진보성(50점) = 총 100점
각 항목 ≥ 35점이어야 통과.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class NoveltyScore(BaseModel):
    """신규성 평가 (50점 만점)."""
    differentiation: float = Field(ge=0, le=25, description="기존 기술과의 차별성 (25점)")
    originality: float = Field(ge=0, le=25, description="기술적 독창성·창의성 (25점)")

    @property
    def total(self) -> float:
        return self.differentiation + self.originality

    @property
    def passed(self) -> bool:
        return self.total >= 35


class ProgressivenessScore(BaseModel):
    """진보성 평가 (50점 만점)."""
    quality_improvement: float = Field(ge=0, le=15, description="품질향상 (15점)")
    development_degree: float = Field(ge=0, le=15, description="개발정도 (15점)")
    safety: float = Field(ge=0, le=10, description="안전성 (10점)")
    eco_friendliness: float = Field(ge=0, le=10, description="친환경성 (10점)")

    @property
    def total(self) -> float:
        return (
            self.quality_improvement
            + self.development_degree
            + self.safety
            + self.eco_friendliness
        )

    @property
    def passed(self) -> bool:
        return self.total >= 35


class EvaluationResult(BaseModel):
    """단일 에이전트의 평가 결과."""
    agent_id: str
    novelty: NoveltyScore
    progressiveness: ProgressivenessScore
    evidence: list[str] = Field(default_factory=list, description="판단 근거 목록")
    verdict: str = Field(description="approved 또는 rejected")

    @property
    def overall_passed(self) -> bool:
        return self.novelty.passed and self.progressiveness.passed
