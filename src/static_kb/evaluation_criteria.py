"""건설신기술 1차 평가 기준 정적 지식베이스.

건설기술진흥법 시행규칙 및 건설신기술 평가 매뉴얼에 근거한
신규성·진보성 평가 기준을 구조화한 정적 KB.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SubCriterion:
    name: str
    max_score: float
    description: str
    scoring_guide: list[str]


@dataclass
class EvaluationCriterion:
    name: str
    name_en: str
    max_score: float
    pass_threshold: float
    sub_criteria: list[SubCriterion]


# 신규성 평가 기준 (50점 만점, ≥35점 통과)
NOVELTY_CRITERION = EvaluationCriterion(
    name="신규성",
    name_en="Novelty",
    max_score=50.0,
    pass_threshold=35.0,
    sub_criteria=[
        SubCriterion(
            name="기존 기술과의 차별성",
            max_score=25.0,
            description="국내에서 최초로 개발되었거나 외국에서 도입하여 개선한 기술로서 "
            "기존 기술과의 차별성이 인정되는 정도",
            scoring_guide=[
                "25~21점: 기존 기술 대비 명확하고 현저한 차별성 입증. "
                "선행기술 조사 결과 동일·유사 기술 부재.",
                "20~16점: 기존 기술 대비 상당한 차별성 존재. "
                "유사 기술 존재하나 핵심 원리/방법에서 차이 명확.",
                "15~11점: 부분적 차별성 존재. 기존 기술의 개선 수준이나 "
                "일부 구성에서 새로운 요소 포함.",
                "10~6점: 차별성 미약. 기존 기술과 유사한 구성이 대부분이며 "
                "미미한 변경에 그침.",
                "5~0점: 차별성 불인정. 기존 기술과 실질적으로 동일하거나 "
                "공지된 기술의 단순 조합.",
            ],
        ),
        SubCriterion(
            name="기술적 독창성·창의성",
            max_score=25.0,
            description="기술의 핵심 원리, 방법, 구조 등에서 독창적이고 "
            "창의적인 요소가 인정되는 정도",
            scoring_guide=[
                "25~21점: 핵심 원리/방법에서 독창적 창의성 뚜렷. "
                "특허 등 지식재산권 확보.",
                "20~16점: 기술적 접근 방식에서 창의성 인정. "
                "기존 원리의 새로운 적용 또는 조합.",
                "15~11점: 일부 구성요소에서 창의적 요소 존재. "
                "전체적으로는 기존 방식의 개선 수준.",
                "10~6점: 창의성 미약. 통상의 기술 수준에서의 "
                "설계 변경 정도.",
                "5~0점: 독창성 불인정. 공지 기술의 통상적 적용.",
            ],
        ),
    ],
)

# 진보성 평가 기준 (50점 만점, ≥35점 통과)
PROGRESSIVENESS_CRITERION = EvaluationCriterion(
    name="진보성",
    name_en="Progressiveness",
    max_score=50.0,
    pass_threshold=35.0,
    sub_criteria=[
        SubCriterion(
            name="품질향상",
            max_score=15.0,
            description="기존 기술 대비 시공 품질, 구조적 성능, "
            "내구성 등의 향상 정도",
            scoring_guide=[
                "15~13점: 정량적 시험 데이터로 현저한 품질향상 입증.",
                "12~10점: 품질향상이 객관적으로 확인되나 향상폭이 보통 수준.",
                "9~7점: 일부 항목에서 품질향상 확인되나 전체적 효과 제한적.",
                "6~4점: 품질향상 미미하거나 입증 자료 불충분.",
                "3~0점: 품질향상 불인정 또는 기존 대비 저하 가능성.",
            ],
        ),
        SubCriterion(
            name="개발정도",
            max_score=15.0,
            description="기술의 완성도, 실용화 단계, "
            "현장 적용 가능성의 정도",
            scoring_guide=[
                "15~13점: 현장 실증 완료, 실용화 준비 완료 단계. "
                "시공 매뉴얼·품질 기준 구비.",
                "12~10점: 시험 시공 완료, 주요 성능 검증됨. "
                "일부 보완 후 현장 적용 가능.",
                "9~7점: 실험실 수준 검증 완료, 현장 적용을 위한 "
                "추가 검증 필요.",
                "6~4점: 개발 초기 단계, 핵심 기술 검증 미완료.",
                "3~0점: 개념 단계, 실용화까지 상당한 추가 개발 필요.",
            ],
        ),
        SubCriterion(
            name="안전성",
            max_score=10.0,
            description="시공 중 및 사용 중 안전성 확보 정도, "
            "기존 기술 대비 안전성 향상",
            scoring_guide=[
                "10~9점: 안전성 관련 인증/시험 성적서 확보, "
                "기존 대비 현저한 안전성 향상.",
                "8~7점: 안전성 시험 결과 양호, 관련 기준 충족.",
                "6~5점: 기본적 안전성 확보, 기존 기술과 동등 수준.",
                "4~3점: 안전성 검증 자료 부족.",
                "2~0점: 안전성 우려 사항 존재.",
            ],
        ),
        SubCriterion(
            name="친환경성",
            max_score=10.0,
            description="환경 부하 저감, 자원 절약, 에너지 효율 등 "
            "친환경적 요소의 정도",
            scoring_guide=[
                "10~9점: 정량적 환경 성능 데이터로 현저한 "
                "환경 개선 효과 입증.",
                "8~7점: 친환경적 요소가 명확하게 확인됨.",
                "6~5점: 일부 친환경적 요소 존재, 효과 보통 수준.",
                "4~3점: 친환경성 미미하거나 입증 불충분.",
                "2~0점: 환경적 우려 사항 존재 가능.",
            ],
        ),
    ],
)

# 전체 1차 평가 체계
FIRST_STAGE_EVALUATION = {
    "novelty": NOVELTY_CRITERION,
    "progressiveness": PROGRESSIVENESS_CRITERION,
}

# 의결 기준
QUORUM_THRESHOLD = 2 / 3  # 위원 2/3 이상 찬성


def get_evaluation_summary() -> str:
    """평가 체계 요약 텍스트 생성 (에이전트 프롬프트 삽입용)."""
    lines = [
        "## 건설신기술 1차 평가 체계",
        "",
        "### 통과 기준",
        "- 신규성: 50점 만점, 35점 이상",
        "- 진보성: 50점 만점, 35점 이상",
        "- 의결: 위원 2/3 이상 찬성",
        "",
    ]

    for key, criterion in FIRST_STAGE_EVALUATION.items():
        lines.append(f"### {criterion.name} ({criterion.max_score}점)")
        for sub in criterion.sub_criteria:
            lines.append(f"\n#### {sub.name} ({sub.max_score}점)")
            lines.append(sub.description)
            for guide in sub.scoring_guide:
                lines.append(f"  - {guide}")
        lines.append("")

    return "\n".join(lines)
