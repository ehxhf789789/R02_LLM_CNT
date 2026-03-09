"""의장 에이전트 (Chairman Agent).

전체 평가위원의 결과를 검토하여:
  1. 일관성 검증: 유사 판단 근거가 일관적인지
  2. 환각 탐지: 존재하지 않는 데이터를 인용하지 않았는지
  3. 오류 확인: 계산 오류, 기준 적용 오류 등
  4. 최종 의견 종합
"""

from __future__ import annotations

import json
import logging

from src.evaluation.ensemble_evaluator import AgentVote, EnsembleResult
from src.llm.bedrock_client import BedrockClient, LLMResponse

logger = logging.getLogger(__name__)


CHAIRMAN_SYSTEM_PROMPT = """\
당신은 건설신기술 1차 평가위원회의 위원장입니다.

당신의 역할은 개별 평가위원들의 평가 결과를 종합적으로 검토하여:
1. **일관성 검증**: 위원들의 판단 근거가 논리적으로 일관적인지 확인
2. **환각 탐지**: 위원들이 존재하지 않는 데이터나 사실을 인용하지 않았는지 확인
3. **오류 확인**: 점수 계산 오류, 평가 기준 적용 오류 등을 확인
4. **극단값 검토**: 다수 의견과 크게 다른 평가의 타당성을 검토

최종적으로 평가 결과의 신뢰도를 판정하고, 문제가 있는 경우 구체적으로 지적하세요.
"""

CHAIRMAN_USER_TEMPLATE = """\
## 평가 대상 기술
- 기술명: {tech_name}
- 기술 분야: {tech_field}

## 평가위원회 결과 요약
- 참여 위원: {n_agents}명
- 찬성률: {approval_ratio:.1%} (가중: {weighted_approval_ratio:.1%})
- 최종 의결: {final_verdict}

## 개별 위원 평가 상세

{individual_evaluations}

## 검토 요청

위의 개별 평가 결과를 검토하고 아래 JSON 형식으로 의장 검토 의견을 제출하세요:

```json
{{
  "review_verdict": "valid 또는 requires_revision",
  "consistency_score": <1~10>,
  "hallucination_flags": [
    "발견된 환각/오류 사항 (없으면 빈 리스트)"
  ],
  "outlier_analysis": [
    "극단값 위원에 대한 분석"
  ],
  "final_opinion": "종합 의견",
  "confidence": <0.0~1.0>
}}
```
"""


class ChairmanAgent:
    """의장 에이전트."""

    def __init__(self, llm_client: BedrockClient | None = None):
        self.llm_client = llm_client

    def review(
        self,
        ensemble_result: EnsembleResult,
        tech_proposal: dict,
    ) -> dict:
        """앙상블 결과를 검토.

        Args:
            ensemble_result: 앙상블 평가 결과
            tech_proposal: 제안기술 정보

        Returns:
            의장 검토 결과 dict
        """
        if not self.llm_client:
            self.llm_client = BedrockClient()

        # 개별 평가 상세 텍스트 생성
        individual_text = self._format_individual_evaluations(ensemble_result)

        user_prompt = CHAIRMAN_USER_TEMPLATE.format(
            tech_name=tech_proposal.get("tech_name", ""),
            tech_field=tech_proposal.get("tech_field", ""),
            n_agents=len(ensemble_result.votes),
            approval_ratio=ensemble_result.approval_ratio,
            weighted_approval_ratio=ensemble_result.weighted_approval_ratio,
            final_verdict=ensemble_result.final_verdict,
            individual_evaluations=individual_text,
        )

        response = self.llm_client.invoke(
            system_prompt=CHAIRMAN_SYSTEM_PROMPT,
            user_message=user_prompt,
            max_tokens=2048,
            temperature=0.2,
        )

        return self._parse_review(response)

    def _format_individual_evaluations(self, result: EnsembleResult) -> str:
        """개별 평가 결과를 텍스트로 포맷."""
        parts = []

        for v in result.votes:
            e = v.evaluation
            lines = [
                f"### {v.agent_id} (확신도: {v.confidence:.2f})",
                f"- 의결: {v.vote}",
                f"- 신규성: {e.novelty.total:.0f}/50 "
                f"(차별성 {e.novelty.differentiation:.0f}, 독창성 {e.novelty.originality:.0f})",
                f"- 진보성: {e.progressiveness.total:.0f}/50 "
                f"(품질 {e.progressiveness.quality_improvement:.0f}, "
                f"개발 {e.progressiveness.development_degree:.0f}, "
                f"안전 {e.progressiveness.safety:.0f}, "
                f"친환경 {e.progressiveness.eco_friendliness:.0f})",
                f"- 총점: {e.novelty.total + e.progressiveness.total:.0f}/100",
                "- 판단 근거:",
            ]
            for ev in e.evidence[:3]:
                lines.append(f"  * {ev}")

            if v.prior_art_comparison:
                lines.append(f"- 선행기술 비교: {v.prior_art_comparison[:200]}")

            parts.append("\n".join(lines))

        return "\n\n".join(parts)

    def _parse_review(self, response: LLMResponse) -> dict:
        """의장 응답을 파싱."""
        try:
            text = response.content
            json_start = text.find("{")
            json_end = text.rfind("}") + 1

            if json_start >= 0 and json_end > json_start:
                review = json.loads(text[json_start:json_end])
                review["raw_response"] = text
                review["usage"] = {
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                    "latency_ms": response.latency_ms,
                }
                return review

        except (json.JSONDecodeError, KeyError) as e:
            logger.error("의장 응답 파싱 실패: %s", e)

        return {
            "review_verdict": "parse_error",
            "raw_response": response.content,
            "error": "JSON 파싱 실패",
        }
