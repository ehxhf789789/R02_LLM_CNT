"""분석 8-3: 점수 패턴 분석.

평가 에이전트별 세부 기준 점수 패턴을 분석한다.

분석 항목:
  - 에이전트별 평균 점수 프로파일 (레이더 차트)
  - 정합 vs 부분정합 점수 분포 비교
  - 경력별 점수 경향
  - 세부 항목별 점수 분산
  - 의결과 점수 간 상관 분석
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

SCORE_FIELDS = [
    "novelty.differentiation",
    "novelty.originality",
    "progressiveness.quality_improvement",
    "progressiveness.development_degree",
    "progressiveness.safety",
    "progressiveness.eco_friendliness",
]

SCORE_LABELS = [
    "차별성",
    "독창성",
    "품질향상",
    "개발정도",
    "안전성",
    "친환경성",
]

SCORE_MAX = [25, 25, 15, 15, 10, 10]


class ScorePatternAnalyzer:
    """점수 패턴 분석기."""

    def analyze(self, results_dir: Path) -> dict:
        """결과 디렉토리의 모든 평가 결과에서 점수 패턴을 분석."""
        result_files = sorted(results_dir.glob("run_*.json"))
        if not result_files:
            return {}

        # 모든 투표 데이터 수집
        all_votes: list[dict] = []
        agent_meta: dict[str, dict] = {}  # agent_id → match_level, experience

        for f in result_files:
            with open(f, encoding="utf-8") as fp:
                data = json.load(fp)

            # 프로파일 정보 매핑
            for profile in data.get("panel_profiles", []):
                aid = profile.get("agent_id", "")
                agent_meta[aid] = {
                    "match_level": profile.get("match_level", ""),
                    "experience": profile.get("experience", ""),
                }

            for vote in data.get("votes", []):
                vote["_tech_number"] = data.get("tech_number", "")
                vote["_tech_name"] = data.get("tech_name", "")
                all_votes.append(vote)

        if not all_votes:
            return {}

        analysis = {
            "total_votes": len(all_votes),
            "score_fields": SCORE_LABELS,
            "score_max": SCORE_MAX,
            "overall_stats": self._compute_overall_stats(all_votes),
            "by_match_level": self._analyze_by_group(all_votes, agent_meta, "match_level"),
            "by_experience": self._analyze_by_group(all_votes, agent_meta, "experience"),
            "correlation": self._compute_correlation(all_votes),
            "agent_profiles": self._compute_agent_profiles(all_votes, agent_meta),
        }

        return analysis

    def _extract_scores(self, vote: dict) -> list[float]:
        """투표에서 6개 세부 점수를 추출."""
        n = vote.get("novelty", {})
        p = vote.get("progressiveness", {})
        return [
            n.get("differentiation", 0),
            n.get("originality", 0),
            p.get("quality_improvement", 0),
            p.get("development_degree", 0),
            p.get("safety", 0),
            p.get("eco_friendliness", 0),
        ]

    def _compute_overall_stats(self, votes: list[dict]) -> dict:
        """전체 점수 통계."""
        all_scores = np.array([self._extract_scores(v) for v in votes])

        return {
            "mean": [float(x) for x in np.mean(all_scores, axis=0)],
            "std": [float(x) for x in np.std(all_scores, axis=0)],
            "median": [float(x) for x in np.median(all_scores, axis=0)],
            "min": [float(x) for x in np.min(all_scores, axis=0)],
            "max": [float(x) for x in np.max(all_scores, axis=0)],
            "normalized_mean": [
                float(m / mx) if mx > 0 else 0
                for m, mx in zip(np.mean(all_scores, axis=0), SCORE_MAX)
            ],
        }

    def _analyze_by_group(
        self,
        votes: list[dict],
        agent_meta: dict[str, dict],
        group_key: str,
    ) -> dict:
        """그룹별(match_level 또는 experience) 점수 통계."""
        grouped: dict[str, list[list[float]]] = {}

        for vote in votes:
            aid = vote.get("agent_id", "")
            meta = agent_meta.get(aid, {})
            group = meta.get(group_key, "unknown")

            grouped.setdefault(group, []).append(self._extract_scores(vote))

        result = {}
        for group, scores_list in grouped.items():
            arr = np.array(scores_list)
            result[group] = {
                "count": len(scores_list),
                "mean": [float(x) for x in np.mean(arr, axis=0)],
                "std": [float(x) for x in np.std(arr, axis=0)],
                "approval_rate": sum(
                    1 for v in votes
                    if agent_meta.get(v.get("agent_id"), {}).get(group_key) == group
                    and v.get("vote") == "approved"
                ) / len(scores_list) if scores_list else 0,
            }

        return result

    def _compute_correlation(self, votes: list[dict]) -> dict:
        """점수와 의결 간 상관관계."""
        scores = np.array([self._extract_scores(v) for v in votes])
        verdicts = np.array([1 if v.get("vote") == "approved" else 0 for v in votes])
        totals = scores.sum(axis=1)
        confidences = np.array([v.get("confidence", 0.5) for v in votes])

        result = {
            "total_vs_verdict": float(np.corrcoef(totals, verdicts)[0, 1]) if len(totals) > 1 else 0,
            "confidence_vs_total": float(np.corrcoef(confidences, totals)[0, 1]) if len(totals) > 1 else 0,
        }

        # 각 세부 항목과 의결 간 상관
        per_field = {}
        for i, label in enumerate(SCORE_LABELS):
            if len(scores[:, i]) > 1:
                per_field[label] = float(np.corrcoef(scores[:, i], verdicts)[0, 1])
            else:
                per_field[label] = 0
        result["per_field_vs_verdict"] = per_field

        return result

    def _compute_agent_profiles(
        self,
        votes: list[dict],
        agent_meta: dict[str, dict],
    ) -> list[dict]:
        """개별 에이전트의 평균 점수 프로파일."""
        by_agent: dict[str, list[list[float]]] = {}
        agent_verdicts: dict[str, list[str]] = {}

        for vote in votes:
            aid = vote.get("agent_id", "")
            by_agent.setdefault(aid, []).append(self._extract_scores(vote))
            agent_verdicts.setdefault(aid, []).append(vote.get("vote", ""))

        profiles = []
        for aid, scores_list in by_agent.items():
            arr = np.array(scores_list)
            meta = agent_meta.get(aid, {})
            verdicts = agent_verdicts.get(aid, [])

            profiles.append({
                "agent_id": aid,
                "match_level": meta.get("match_level", ""),
                "experience": meta.get("experience", ""),
                "n_evaluations": len(scores_list),
                "mean_scores": [float(x) for x in np.mean(arr, axis=0)],
                "mean_total": float(np.sum(np.mean(arr, axis=0))),
                "approval_rate": verdicts.count("approved") / len(verdicts) if verdicts else 0,
                "avg_confidence": float(np.mean([
                    v.get("confidence", 0.5) for v in votes if v.get("agent_id") == aid
                ])),
            })

        profiles.sort(key=lambda x: x["mean_total"], reverse=True)
        return profiles
