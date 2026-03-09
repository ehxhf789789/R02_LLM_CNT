"""건설신기술 분류체계 데이터 모델.

KAIA 실제 분류체계 기반 (대분류 > 중분류 > 소분류).
대분류: 토목, 건축, 기계설비
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


class TechCategory(BaseModel):
    code: str
    name: str
    name_en: str = ""


class CNTClassification(BaseModel):
    """건설신기술 3단계 분류체계."""
    major: TechCategory       # 대분류
    middle: TechCategory      # 중분류
    minor: TechCategory       # 소분류


# KAIA 실제 분류체계 (대분류)
MAJOR_CATEGORIES: list[TechCategory] = [
    TechCategory(code="CIV", name="토목", name_en="Civil Engineering"),
    TechCategory(code="ARC", name="건축", name_en="Architecture"),
    TechCategory(code="MEC", name="기계설비", name_en="Mechanical & Equipment"),
]

# KAIA 실제 분류체계 (중분류)
MIDDLE_CATEGORIES: dict[str, list[TechCategory]] = {
    "CIV": [
        TechCategory(code="CIV_BRG", name="교량", name_en="Bridge"),
        TechCategory(code="CIV_ROD", name="도로", name_en="Road"),
        TechCategory(code="CIV_TNL", name="터널", name_en="Tunnel"),
        TechCategory(code="CIV_RLW", name="철도", name_en="Railway"),
        TechCategory(code="CIV_GEO", name="토질 및 기초", name_en="Geotechnical & Foundation"),
        TechCategory(code="CIV_RPR", name="토목구조물 보수보강(포장 보수제외)", name_en="Civil Structure Repair"),
        TechCategory(code="CIV_RVR", name="하천 및 수자원", name_en="River & Water Resources"),
        TechCategory(code="CIV_PRT", name="항만 및 해안", name_en="Port & Coastal"),
        TechCategory(code="CIV_ENV", name="환경", name_en="Environment"),
    ],
    "ARC": [
        TechCategory(code="ARC_FND", name="기초", name_en="Foundation"),
        TechCategory(code="ARC_FIN", name="마감", name_en="Finishing"),
        TechCategory(code="ARC_WPF", name="방수", name_en="Waterproofing"),
        TechCategory(code="ARC_RPR", name="보수보강", name_en="Repair & Reinforcement"),
        TechCategory(code="ARC_STL", name="철골", name_en="Steel Structure"),
        TechCategory(code="ARC_RCC", name="철근콘크리트", name_en="Reinforced Concrete"),
        TechCategory(code="ARC_SPC", name="특수 건축물", name_en="Special Structure"),
        TechCategory(code="ARC_TMP", name="가설시설물", name_en="Temporary Structure"),
    ],
    "MEC": [
        TechCategory(code="MEC_CON", name="건설기계", name_en="Construction Machinery"),
        TechCategory(code="MEC_ENV", name="환경기계설비", name_en="Environmental Mech. Equipment"),
        TechCategory(code="MEC_COM", name="통신전자 및 제어설비", name_en="Communication & Control"),
    ],
}


def parse_kaia_field(field_str: str) -> CNTClassification | None:
    """KAIA 기술분류 문자열(예: '토목 > 교량 > 교량거더')을 파싱.

    일부 행에서 두 분류가 이어붙여진 경우 첫 번째만 사용.
    """
    if not field_str:
        return None

    # 이어붙여진 분류 분리 (예: "건축 > 기초 > 기초 보강건축 > 기초 > 기타 기초")
    # 소분류 뒤에 다른 대분류명이 바로 이어붙는 패턴을 감지하여 분리
    import re
    major_names = ["토목", "건축", "기계설비"]
    # 소분류 끝에 대분류명이 붙은 경우 제거
    for mn in major_names:
        pattern = f"({mn})"
        occurrences = [m.start() for m in re.finditer(re.escape(mn), field_str)]
        if len(occurrences) > 1:
            # 첫 번째 대분류만 사용
            field_str = field_str[:occurrences[1]]
            break

    segments = [s.strip() for s in field_str.split(">")]
    if len(segments) < 3:
        return None

    major_name = segments[0]
    middle_name = segments[1]
    minor_name = segments[2]

    # 대분류 매칭
    major = None
    for cat in MAJOR_CATEGORIES:
        if cat.name == major_name:
            major = cat
            break
    if not major:
        return None

    # 중분류 매칭
    middle = None
    for cat in MIDDLE_CATEGORIES.get(major.code, []):
        if cat.name == middle_name:
            middle = cat
            break
    if not middle:
        middle = TechCategory(code=f"{major.code}_{middle_name[:3]}", name=middle_name)

    minor = TechCategory(code=f"{middle.code}_{minor_name[:3]}", name=minor_name)

    return CNTClassification(major=major, middle=middle, minor=minor)


def get_major_category(code: str) -> TechCategory | None:
    for cat in MAJOR_CATEGORIES:
        if cat.code == code:
            return cat
    return None


def get_major_by_name(name: str) -> TechCategory | None:
    for cat in MAJOR_CATEGORIES:
        if cat.name == name:
            return cat
    return None


def get_middle_categories(major_code: str) -> list[TechCategory]:
    return MIDDLE_CATEGORIES.get(major_code, [])


def build_classification_tree_from_kaia(designated_techs: list[dict]) -> dict:
    """KAIA 지정기술 데이터에서 실제 분류 트리를 동적으로 구축."""
    tree: dict[str, dict[str, set]] = {}

    for tech in designated_techs:
        field_str = tech.get("tech_field", "")
        classification = parse_kaia_field(field_str)
        if not classification:
            continue

        major = classification.major.name
        middle = classification.middle.name
        minor = classification.minor.name

        if major not in tree:
            tree[major] = {}
        if middle not in tree[major]:
            tree[major][middle] = set()
        tree[major][middle].add(minor)

    # set -> sorted list
    return {
        major: {middle: sorted(minors) for middle, minors in middles.items()}
        for major, middles in tree.items()
    }
