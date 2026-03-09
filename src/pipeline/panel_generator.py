"""에이전트 패널 생성기.

실제 건설신기술 평가위원회 구성을 모사:
  - 무작위 10~15명 (실제 위원회 규모)
  - 70% 정합 / 30% 부분정합
  - 경력 분포: 고경력 30%, 중경력 40%, 저경력 30%
  - 전문분야 배정: classification_tree.json 기반
"""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path

from config.settings import settings
from src.models.agent_profile import AgentProfile, ExperienceLevel, MatchLevel
from src.models.cnt_classification import (
    CNTClassification,
    TechCategory,
    MAJOR_CATEGORIES,
    MIDDLE_CATEGORIES,
    parse_kaia_field,
)

logger = logging.getLogger(__name__)


# 경력 분포 가중치
EXPERIENCE_WEIGHTS = {
    ExperienceLevel.HIGH: 0.3,
    ExperienceLevel.MEDIUM: 0.4,
    ExperienceLevel.LOW: 0.3,
}

# 경력별 경력 연수 범위
EXPERIENCE_YEAR_RANGES = {
    ExperienceLevel.HIGH: (15, 30),
    ExperienceLevel.MEDIUM: (7, 14),
    ExperienceLevel.LOW: (3, 6),
}


class PanelGenerator:
    """평가 에이전트 패널 생성기."""

    def __init__(self, classification_tree_path: Path | None = None):
        tree_path = classification_tree_path or (
            settings.classifications_dir / "classification_tree.json"
        )
        self.classification_tree = self._load_classification_tree(tree_path)

    def generate(
        self,
        tech_field: str,
        min_size: int | None = None,
        max_size: int | None = None,
        exact_ratio: float | None = None,
        seed: int | None = None,
    ) -> list[AgentProfile]:
        """제안기술 분야에 맞는 에이전트 패널을 생성.

        Args:
            tech_field: 제안기술 분류 (예: "토목 > 교량 > 교량거더")
            min_size: 최소 패널 크기
            max_size: 최대 패널 크기
            exact_ratio: 정합 에이전트 비율
            seed: 랜덤 시드 (재현성)
        """
        if seed is not None:
            random.seed(seed)

        min_size = min_size or settings.min_panel_size
        max_size = max_size or settings.max_panel_size
        exact_ratio = exact_ratio or settings.exact_match_ratio

        # 패널 크기 결정
        panel_size = random.randint(min_size, max_size)
        n_exact = round(panel_size * exact_ratio)
        n_partial = panel_size - n_exact

        logger.info(
            "패널 생성: %d명 (정합 %d, 부분정합 %d)",
            panel_size, n_exact, n_partial,
        )

        # 제안기술 분류 파싱
        classification = parse_kaia_field(tech_field)
        if not classification:
            logger.warning("기술 분류 파싱 실패, 기본값 사용: %s", tech_field)
            classification = self._default_classification()

        panel: list[AgentProfile] = []

        # 정합 에이전트 생성
        for i in range(n_exact):
            experience = self._sample_experience()
            profile = self._create_exact_agent(
                idx=i + 1,
                classification=classification,
                experience=experience,
            )
            panel.append(profile)

        # 부분정합 에이전트 생성
        partial_specialties = self._find_partial_specialties(classification)
        for i in range(n_partial):
            experience = self._sample_experience()
            specialty = partial_specialties[i % len(partial_specialties)]
            profile = self._create_partial_agent(
                idx=n_exact + i + 1,
                specialty=specialty,
                experience=experience,
            )
            panel.append(profile)

        return panel

    def _sample_experience(self) -> ExperienceLevel:
        """가중치 기반 경력 수준 샘플링."""
        levels = list(EXPERIENCE_WEIGHTS.keys())
        weights = list(EXPERIENCE_WEIGHTS.values())
        return random.choices(levels, weights=weights, k=1)[0]

    def _create_exact_agent(
        self,
        idx: int,
        classification: CNTClassification,
        experience: ExperienceLevel,
    ) -> AgentProfile:
        """정합 에이전트 생성 (동일 분야)."""
        year_min, year_max = EXPERIENCE_YEAR_RANGES[experience]
        years = random.randint(year_min, year_max)

        return AgentProfile(
            agent_id=f"agent_{idx:02d}_exact_{experience.value[0]}",
            specialty=classification,
            match_level=MatchLevel.EXACT,
            experience=experience,
            experience_years=years,
        )

    def _create_partial_agent(
        self,
        idx: int,
        specialty: CNTClassification,
        experience: ExperienceLevel,
    ) -> AgentProfile:
        """부분정합 에이전트 생성 (인접 분야)."""
        year_min, year_max = EXPERIENCE_YEAR_RANGES[experience]
        years = random.randint(year_min, year_max)

        return AgentProfile(
            agent_id=f"agent_{idx:02d}_partial_{experience.value[0]}",
            specialty=specialty,
            match_level=MatchLevel.PARTIAL,
            experience=experience,
            experience_years=years,
        )

    def _find_partial_specialties(
        self,
        target: CNTClassification,
    ) -> list[CNTClassification]:
        """제안기술과 인접한 분야 목록을 생성.

        규칙:
          1. 같은 대분류, 다른 중분류
          2. 같은 중분류, 다른 소분류
          3. 다른 대분류의 관련 분야
        """
        specialties: list[CNTClassification] = []
        major_name = target.major.name
        middle_name = target.middle.name

        # 1. 같은 대분류, 다른 중분류의 소분류
        if major_name in self.classification_tree:
            for mid, minors in self.classification_tree[major_name].items():
                if mid != middle_name and minors:
                    minor_name = random.choice(minors)
                    major_cat = target.major
                    mid_code = f"{major_cat.code}_{mid[:3]}"
                    mid_cat = self._find_middle_category(major_cat.code, mid)
                    if not mid_cat:
                        mid_cat = TechCategory(code=mid_code, name=mid)
                    minor_cat = TechCategory(
                        code=f"{mid_cat.code}_{minor_name[:3]}",
                        name=minor_name,
                    )
                    specialties.append(CNTClassification(
                        major=major_cat,
                        middle=mid_cat,
                        minor=minor_cat,
                    ))

        # 2. 다른 대분류에서 선택
        for major_name_other, middles in self.classification_tree.items():
            if major_name_other == major_name:
                continue
            for mid, minors in middles.items():
                if minors:
                    minor_name = random.choice(minors)
                    major_cat = self._find_major_category(major_name_other)
                    if not major_cat:
                        continue
                    mid_cat = self._find_middle_category(major_cat.code, mid)
                    if not mid_cat:
                        mid_cat = TechCategory(
                            code=f"{major_cat.code}_{mid[:3]}",
                            name=mid,
                        )
                    minor_cat = TechCategory(
                        code=f"{mid_cat.code}_{minor_name[:3]}",
                        name=minor_name,
                    )
                    specialties.append(CNTClassification(
                        major=major_cat,
                        middle=mid_cat,
                        minor=minor_cat,
                    ))

        if not specialties:
            specialties.append(self._default_classification())

        random.shuffle(specialties)
        return specialties

    def _find_major_category(self, name: str) -> TechCategory | None:
        for cat in MAJOR_CATEGORIES:
            if cat.name == name:
                return cat
        return None

    def _find_middle_category(self, major_code: str, name: str) -> TechCategory | None:
        for cat in MIDDLE_CATEGORIES.get(major_code, []):
            if cat.name == name:
                return cat
        return None

    def _default_classification(self) -> CNTClassification:
        return CNTClassification(
            major=TechCategory(code="CIV", name="토목", name_en="Civil Engineering"),
            middle=TechCategory(code="CIV_BRG", name="교량", name_en="Bridge"),
            minor=TechCategory(code="CIV_BRG_GRD", name="교량거더"),
        )

    def _load_classification_tree(self, path: Path) -> dict:
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        logger.warning("분류 트리 파일 없음: %s", path)
        return {}
