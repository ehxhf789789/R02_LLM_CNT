"""에이전트 평가 프롬프트 빌더.

계층적 KB(PIKE-RAG) + 선행기술 컨텍스트(RAG-Novelty)를 결합하여
개별 에이전트의 평가 프롬프트를 생성한다.

프롬프트 구조:
  1. 시스템 프롬프트: 역할 + 판단 기조 (Level 3)
  2. 평가 기준: 신규성/진보성 기준표 (Level 1)
  3. 선행기술 컨텍스트: 검색된 특허/논문/지정기술 (Level 2 + RAG-Novelty)
  4. 제안기술 명세: 평가 대상 기술 정보
  5. 출력 형식: 구조화된 평가 결과 JSON
"""

from __future__ import annotations

import json
import logging

from src.evaluation.kb_assembler import HierarchicalKB
from src.evaluation.prior_art_searcher import PriorArtContext

logger = logging.getLogger(__name__)


SYSTEM_PROMPT_TEMPLATE = """\
당신은 건설신기술 1차 평가위원회의 전문위원입니다.
전문분야: {specialty}
매칭수준: {match_level_desc}

{judgment_tendency}

당신의 임무는 제출된 건설신기술 신청서를 검토하고,
아래의 평가 기준에 따라 신규성과 진보성을 채점하는 것입니다.
반드시 근거를 명시하고, 선행기술과의 비교 분석을 포함하세요.
"""

EVALUATION_CRITERIA_TEMPLATE = """\
---
# 평가 기준

{evaluation_criteria}
---
"""

PRIOR_ART_TEMPLATE = """\
---
# 선행기술 조사 결과 (참고자료)

아래는 제안기술과 관련된 선행기술 검색 결과입니다.
이 자료를 참고하여 제안기술의 신규성(기존 기술과의 차별성)을 판단하세요.

주의: 선행기술 목록에 평가 대상 기술과 동일하거나 매우 유사한 이름의 기술이 포함되어 있다면,
이는 자기참조(circular reference)일 수 있으므로 해당 항목을 신규성 부정 근거로 사용하지 마세요.
대신 다른 선행기술과의 차별점 분석에 집중하세요.

{prior_art_context}
---
"""

TECH_PROPOSAL_TEMPLATE = """\
---
# 평가 대상: 건설신기술 신청서

## 기술명
{tech_name}

## 기술 분야
{tech_field}

## 기술 개요
{tech_description}

## 핵심 기술 내용
{tech_core_content}

## 기존 기술과의 차별점 (신청자 주장)
{differentiation_claim}

## 성능 시험 결과
{test_results}

## 현장 적용 실적
{field_application}

{extra_sections}---
"""

OUTPUT_FORMAT_TEMPLATE = """\
---
# 출력 형식

아래 JSON 형식으로 평가 결과를 작성하세요.
각 점수는 평가 기준표의 배점 범위 내에서 부여하세요.

```json
{{
  "agent_id": "<당신의 에이전트 ID>",
  "novelty": {{
    "differentiation": <0~25>,
    "differentiation_reasoning": "차별성 판단의 구체적 근거와 참조한 KB 소스",
    "originality": <0~25>,
    "originality_reasoning": "독창성 판단의 구체적 근거와 참조한 KB 소스"
  }},
  "progressiveness": {{
    "quality_improvement": <0~15>,
    "quality_reasoning": "품질향상 판단 근거와 참조 소스",
    "development_degree": <0~15>,
    "development_reasoning": "개발정도 판단 근거와 참조 소스",
    "safety": <0~10>,
    "safety_reasoning": "안전성 판단 근거와 참조 소스",
    "eco_friendliness": <0~10>,
    "eco_reasoning": "친환경성 판단 근거와 참조 소스"
  }},
  "evidence": [
    {{
      "claim": "판단 내용",
      "source_type": "patent|paper|designated_tech|codil|evaluation_criteria|proposal",
      "source_ref": "출처 (예: 특허번호, 논문제목, 지정기술명, 기준표 항목명 등)",
      "relevance": "해당 소스가 판단에 어떻게 기여했는지"
    }}
  ],
  "prior_art_comparison": "선행기술과의 비교 분석 요약 (구체적 특허/논문/기술명 인용)",
  "verdict": "approved 또는 rejected",
  "confidence": <0.0~1.0>
}}
```

주의사항:
- 신규성 합계 ≥ 35점이고 진보성 합계 ≥ 35점이면 "approved", 아니면 "rejected"
- confidence는 당신의 판단에 대한 확신도 (1.0이 가장 확신)
- evidence에는 최소 3개 이상의 근거를 제시하되, 반드시 KB에서 참조한 소스를 명시하세요
- 각 점수 항목의 reasoning에 반드시 근거로 활용한 자료(특허, 논문, 지정기술, 평가기준 등)의 구체적 출처를 인용하세요
- 소스 없이 판단한 항목은 confidence를 낮추세요
---
"""


class PromptBuilder:
    """에이전트 평가 프롬프트 빌더."""

    def build_evaluation_prompt(
        self,
        kb: HierarchicalKB,
        prior_art: PriorArtContext,
        tech_proposal: dict,
    ) -> dict[str, str]:
        """완성된 평가 프롬프트를 생성.

        Args:
            kb: 계층적 KB (PIKE-RAG)
            prior_art: 선행기술 검색 결과 (RAG-Novelty)
            tech_proposal: 제안기술 정보 dict

        Returns:
            dict with keys: "system", "user"
        """
        match_level_desc = (
            "정합 (기술 분야 직접 일치)" if kb.match_level == "exact"
            else "부분정합 (인접·관련 분야)"
        )

        # 시스템 프롬프트 (Level 3: 역할 + 판단 기조)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            specialty=kb.specialty_description,
            match_level_desc=match_level_desc,
            judgment_tendency=kb.judgment_tendency,
        )

        # 유저 프롬프트 조립
        user_parts = []

        # Level 1: 평가 기준
        user_parts.append(EVALUATION_CRITERIA_TEMPLATE.format(
            evaluation_criteria=kb.evaluation_criteria,
        ))

        # Level 2 + RAG-Novelty: 선행기술 컨텍스트
        prior_art_text = prior_art.to_context_text()
        user_parts.append(PRIOR_ART_TEMPLATE.format(
            prior_art_context=prior_art_text,
        ))

        # 제안기술 명세
        # PDF에서 추출한 추가 섹션 구성
        extra_parts = []
        if tech_proposal.get("prior_art_survey_text"):
            text = tech_proposal["prior_art_survey_text"][:3000]
            extra_parts.append(f"## 신청자 제출 선행기술조사\n{text}")
        if tech_proposal.get("tech_detail_text"):
            text = tech_proposal["tech_detail_text"][:3000]
            extra_parts.append(f"## 신기술 상세 (PDF 추출)\n{text}")
        if tech_proposal.get("intro_text"):
            text = tech_proposal["intro_text"][:2000]
            extra_parts.append(f"## 기술 소개\n{text}")
        if tech_proposal.get("procedure_text"):
            text = tech_proposal["procedure_text"][:1500]
            extra_parts.append(f"## 시공절차\n{text}")
        extra_sections = "\n\n".join(extra_parts) + "\n" if extra_parts else ""

        user_parts.append(TECH_PROPOSAL_TEMPLATE.format(
            tech_name=tech_proposal.get("tech_name", ""),
            tech_field=tech_proposal.get("tech_field", ""),
            tech_description=tech_proposal.get("tech_description", ""),
            tech_core_content=tech_proposal.get("tech_core_content", ""),
            differentiation_claim=tech_proposal.get("differentiation_claim", ""),
            test_results=tech_proposal.get("test_results", ""),
            field_application=tech_proposal.get("field_application", ""),
            extra_sections=extra_sections,
        ))

        # 출력 형식 지시
        user_parts.append(OUTPUT_FORMAT_TEMPLATE)

        user_prompt = "\n".join(user_parts)

        return {
            "system": system_prompt,
            "user": user_prompt,
        }

    def build_evaluation_messages(
        self,
        kb: HierarchicalKB,
        prior_art: PriorArtContext,
        tech_proposal: dict,
    ) -> list[dict]:
        """Claude API messages 형식으로 변환.

        Returns:
            list of {"role": ..., "content": ...}
        """
        prompts = self.build_evaluation_prompt(kb, prior_art, tech_proposal)
        return [
            {"role": "system", "content": prompts["system"]},
            {"role": "user", "content": prompts["user"]},
        ]
