"""앙상블 평가기 (PoLL 스타일 신뢰도 가중 투표).

다수의 에이전트가 독립적으로 평가한 결과를 통합하여
최종 의결 결과를 도출한다.

의결 기준:
  - 위원 2/3 이상 찬성 시 "approved"
  - 각 에이전트의 confidence를 가중치로 사용하여 가중 투표
  - 최종 점수는 가중 평균으로 산출
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from src.models.evaluation import EvaluationResult, NoveltyScore, ProgressivenessScore
from src.static_kb.evaluation_criteria import QUORUM_THRESHOLD

logger = logging.getLogger(__name__)


@dataclass
class AgentVote:
    """개별 에이전트의 투표."""
    agent_id: str
    evaluation: EvaluationResult
    confidence: float = 1.0
    prior_art_comparison: str = ""
    evidence_details: list[dict] = field(default_factory=list)
    reasoning: dict = field(default_factory=dict)

    @property
    def vote(self) -> str:
        """approved 또는 rejected."""
        return self.evaluation.verdict


@dataclass
class EnsembleResult:
    """앙상블 평가 최종 결과."""
    votes: list[AgentVote] = field(default_factory=list)
    final_verdict: str = ""
    approval_ratio: float = 0.0
    weighted_approval_ratio: float = 0.0

    # 가중 평균 점수
    avg_novelty_differentiation: float = 0.0
    avg_novelty_originality: float = 0.0
    avg_progressiveness_quality: float = 0.0
    avg_progressiveness_development: float = 0.0
    avg_progressiveness_safety: float = 0.0
    avg_progressiveness_eco: float = 0.0

    avg_novelty_total: float = 0.0
    avg_progressiveness_total: float = 0.0
    avg_total: float = 0.0

    dissenting_opinions: list[str] = field(default_factory=list)
    consensus_evidence: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """결과 요약 텍스트."""
        lines = [
            "=" * 60,
            "건설신기술 1차 평가 앙상블 결과",
            "=" * 60,
            "",
            f"최종 의결: {self.final_verdict.upper()}",
            f"찬성률: {self.approval_ratio:.1%} (가중: {self.weighted_approval_ratio:.1%})",
            f"참여 위원: {len(self.votes)}명",
            "",
            "--- 가중 평균 점수 ---",
            f"신규성: {self.avg_novelty_total:.1f}/50",
            f"  - 기존 기술과의 차별성: {self.avg_novelty_differentiation:.1f}/25",
            f"  - 기술적 독창성·창의성: {self.avg_novelty_originality:.1f}/25",
            f"진보성: {self.avg_progressiveness_total:.1f}/50",
            f"  - 품질향상: {self.avg_progressiveness_quality:.1f}/15",
            f"  - 개발정도: {self.avg_progressiveness_development:.1f}/15",
            f"  - 안전성: {self.avg_progressiveness_safety:.1f}/10",
            f"  - 친환경성: {self.avg_progressiveness_eco:.1f}/10",
            f"총점: {self.avg_total:.1f}/100",
            "",
        ]

        if self.consensus_evidence:
            lines.append("--- 공통 판단 근거 ---")
            for e in self.consensus_evidence[:5]:
                lines.append(f"  * {e}")
            lines.append("")

        if self.dissenting_opinions:
            lines.append("--- 소수 의견 ---")
            for d in self.dissenting_opinions:
                lines.append(f"  * {d}")
            lines.append("")

        # 개별 투표 상세
        lines.append("--- 개별 위원 투표 ---")
        for v in self.votes:
            n_total = v.evaluation.novelty.total
            p_total = v.evaluation.progressiveness.total
            lines.append(
                f"  {v.agent_id}: {v.vote} "
                f"(신규성 {n_total:.0f}, 진보성 {p_total:.0f}, "
                f"확신도 {v.confidence:.2f})"
            )

        return "\n".join(lines)


class EnsembleEvaluator:
    """PoLL 스타일 앙상블 평가기."""

    def aggregate(self, votes: list[AgentVote]) -> EnsembleResult:
        """개별 에이전트 투표를 집계하여 최종 결과를 도출.

        가중 투표: 각 에이전트의 confidence를 가중치로 사용.
        의결 기준: 위원 2/3 이상 찬성 시 approved.
        """
        if not votes:
            return EnsembleResult(final_verdict="rejected")

        result = EnsembleResult(votes=votes)

        # 단순 찬성률
        approved_count = sum(1 for v in votes if v.vote == "approved")
        result.approval_ratio = approved_count / len(votes)

        # 가중 찬성률
        total_weight = sum(v.confidence for v in votes)
        if total_weight > 0:
            weighted_approved = sum(
                v.confidence for v in votes if v.vote == "approved"
            )
            result.weighted_approval_ratio = weighted_approved / total_weight
        else:
            result.weighted_approval_ratio = result.approval_ratio

        # 의결 판정 (가중 찬성률 기준)
        result.final_verdict = (
            "approved" if result.weighted_approval_ratio >= QUORUM_THRESHOLD
            else "rejected"
        )

        # 가중 평균 점수 계산
        self._compute_weighted_scores(result, votes)

        # 공통 근거 및 소수 의견 추출
        self._extract_consensus_and_dissent(result, votes)

        logger.info(
            "앙상블 결과: %s (찬성률 %.1f%%, 가중 %.1f%%)",
            result.final_verdict,
            result.approval_ratio * 100,
            result.weighted_approval_ratio * 100,
        )
        return result

    def _compute_weighted_scores(
        self,
        result: EnsembleResult,
        votes: list[AgentVote],
    ) -> None:
        """신뢰도 가중 평균 점수를 계산."""
        total_weight = sum(v.confidence for v in votes)
        if total_weight == 0:
            total_weight = len(votes)  # fallback

        w_diff = w_orig = 0.0
        w_qual = w_dev = w_safe = w_eco = 0.0

        for v in votes:
            w = v.confidence / total_weight
            n = v.evaluation.novelty
            p = v.evaluation.progressiveness

            w_diff += n.differentiation * w
            w_orig += n.originality * w
            w_qual += p.quality_improvement * w
            w_dev += p.development_degree * w
            w_safe += p.safety * w
            w_eco += p.eco_friendliness * w

        result.avg_novelty_differentiation = w_diff
        result.avg_novelty_originality = w_orig
        result.avg_progressiveness_quality = w_qual
        result.avg_progressiveness_development = w_dev
        result.avg_progressiveness_safety = w_safe
        result.avg_progressiveness_eco = w_eco

        result.avg_novelty_total = w_diff + w_orig
        result.avg_progressiveness_total = w_qual + w_dev + w_safe + w_eco
        result.avg_total = result.avg_novelty_total + result.avg_progressiveness_total

    def _extract_consensus_and_dissent(
        self,
        result: EnsembleResult,
        votes: list[AgentVote],
    ) -> None:
        """공통 판단 근거와 소수 의견을 추출."""
        # 공통 근거: 과반수 에이전트가 언급한 근거 키워드
        all_evidence: list[str] = []
        for v in votes:
            all_evidence.extend(v.evaluation.evidence)

        # 간단한 빈도 기반 공통 근거 추출
        if all_evidence:
            evidence_freq: dict[str, int] = {}
            for e in all_evidence:
                # 비슷한 근거를 그룹핑 (첫 20자 기준)
                key = e[:20] if len(e) > 20 else e
                evidence_freq[key] = evidence_freq.get(key, 0) + 1

            threshold = len(votes) / 2
            consensus = [e for e in all_evidence if evidence_freq.get(e[:20], 0) >= threshold]
            result.consensus_evidence = list(dict.fromkeys(consensus))[:5]

        # 소수 의견: 최종 결과와 다른 투표를 한 에이전트의 근거
        for v in votes:
            if v.vote != result.final_verdict:
                result.dissenting_opinions.append(
                    f"[{v.agent_id}] {v.vote}: "
                    + "; ".join(v.evaluation.evidence[:2])
                )

    @staticmethod
    def parse_agent_response(agent_id: str, response_text: str) -> AgentVote | None:
        """에이전트의 JSON 응답을 파싱하여 AgentVote로 변환."""
        try:
            # JSON 블록 추출
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            if json_start < 0 or json_end <= json_start:
                logger.error("에이전트 %s 응답에서 JSON을 찾을 수 없음", agent_id)
                return None

            data = json.loads(response_text[json_start:json_end])

            novelty = NoveltyScore(
                differentiation=float(data["novelty"]["differentiation"]),
                originality=float(data["novelty"]["originality"]),
            )
            progressiveness = ProgressivenessScore(
                quality_improvement=float(data["progressiveness"]["quality_improvement"]),
                development_degree=float(data["progressiveness"]["development_degree"]),
                safety=float(data["progressiveness"]["safety"]),
                eco_friendliness=float(data["progressiveness"]["eco_friendliness"]),
            )
            # evidence: 새 형식(dict 리스트) 또는 이전 형식(str 리스트) 모두 처리
            raw_evidence = data.get("evidence", [])
            evidence_strs = []
            evidence_details = []
            for e in raw_evidence:
                if isinstance(e, dict):
                    claim = e.get("claim", "")
                    src_type = e.get("source_type", "")
                    src_ref = e.get("source_ref", "")
                    relevance = e.get("relevance", "")
                    evidence_strs.append(
                        f"[{src_type}:{src_ref}] {claim}" if src_ref else claim
                    )
                    evidence_details.append(e)
                else:
                    evidence_strs.append(str(e))
                    evidence_details.append({"claim": str(e), "source_type": "", "source_ref": ""})

            # 항목별 reasoning 수집
            reasoning = {}
            for key in ["differentiation_reasoning", "originality_reasoning"]:
                if key in data.get("novelty", {}):
                    reasoning[key] = data["novelty"][key]
            for key in ["quality_reasoning", "development_reasoning", "safety_reasoning", "eco_reasoning"]:
                if key in data.get("progressiveness", {}):
                    reasoning[key] = data["progressiveness"][key]

            evaluation = EvaluationResult(
                agent_id=data.get("agent_id", agent_id),
                novelty=novelty,
                progressiveness=progressiveness,
                evidence=evidence_strs,
                verdict=data.get("verdict", "rejected"),
            )

            return AgentVote(
                agent_id=agent_id,
                evaluation=evaluation,
                confidence=float(data.get("confidence", 0.5)),
                prior_art_comparison=data.get("prior_art_comparison", ""),
                evidence_details=evidence_details,
                reasoning=reasoning,
            )

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error("에이전트 %s 응답 파싱 실패: %s", agent_id, e)
            return None
