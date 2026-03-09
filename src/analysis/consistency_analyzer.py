"""분석 8-2: 일관성 분석.

동일 입력을 여러 번 반복 평가하여
다수결 의결이 안정적인지 검증한다.

통계 기법:
  - Fleiss' kappa: 평가자 간 일치도
  - 의결 안정성: 동일 입력의 반복 결과 일치 비율
  - 95% 신뢰구간: 부트스트랩 기반
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path

import numpy as np
from scipy import stats

logger = logging.getLogger(__name__)


class ConsistencyAnalyzer:
    """일관성 분석기."""

    def analyze(
        self,
        results_dir: Path,
        min_repetitions: int = 3,
    ) -> dict:
        """반복 실행 결과의 일관성을 분석.

        파일명 규칙: run_{tech_number}_{timestamp}.json
        동일 tech_number로 그룹핑하여 분석.
        """
        result_files = sorted(results_dir.glob("run_*.json"))
        if not result_files:
            return {}

        # tech_number별 그룹핑
        groups: dict[str, list[dict]] = {}
        for f in result_files:
            with open(f, encoding="utf-8") as fp:
                data = json.load(fp)
            tech_num = data.get("tech_number", "unknown")
            groups.setdefault(tech_num, []).append(data)

        analysis = {
            "total_cases": len(groups),
            "cases_with_repetitions": 0,
            "case_consistency": [],
            "overall_verdict_stability": 0.0,
            "overall_score_cv": 0.0,
            "fleiss_kappa": None,
        }

        all_verdicts_stable = 0
        all_score_cvs = []
        fleiss_matrix = []  # (N subjects) x (k categories)

        for tech_num, runs in groups.items():
            if len(runs) < min_repetitions:
                continue

            analysis["cases_with_repetitions"] += 1

            # 의결 안정성
            verdicts = [r.get("ensemble_result", {}).get("final_verdict", "") for r in runs]
            verdict_counter = Counter(verdicts)
            majority_verdict = verdict_counter.most_common(1)[0][0]
            stability = verdict_counter[majority_verdict] / len(verdicts)

            if stability == 1.0:
                all_verdicts_stable += 1

            # 점수 변동 계수 (CV)
            scores = [r.get("ensemble_result", {}).get("avg_total", 0) for r in runs]
            mean_score = np.mean(scores)
            std_score = np.std(scores)
            cv = (std_score / mean_score * 100) if mean_score > 0 else 0

            all_score_cvs.append(cv)

            # 개별 에이전트 투표 패턴 (Fleiss' kappa용)
            for run in runs:
                votes = run.get("votes", [])
                n_approved = sum(1 for v in votes if v.get("vote") == "approved")
                n_rejected = len(votes) - n_approved
                fleiss_matrix.append([n_approved, n_rejected])

            # 95% 신뢰구간 (부트스트랩)
            ci_lower, ci_upper = self._bootstrap_ci(scores, n_bootstrap=1000)

            case_result = {
                "tech_number": tech_num,
                "n_repetitions": len(runs),
                "majority_verdict": majority_verdict,
                "verdict_stability": stability,
                "verdict_distribution": dict(verdict_counter),
                "score_mean": float(mean_score),
                "score_std": float(std_score),
                "score_cv_percent": float(cv),
                "score_ci_95": [float(ci_lower), float(ci_upper)],
                "all_scores": [float(s) for s in scores],
            }
            analysis["case_consistency"].append(case_result)

        # 전체 통계
        n_cases = analysis["cases_with_repetitions"]
        if n_cases > 0:
            analysis["overall_verdict_stability"] = all_verdicts_stable / n_cases
            analysis["overall_score_cv"] = float(np.mean(all_score_cvs)) if all_score_cvs else 0

        # Fleiss' kappa
        if len(fleiss_matrix) >= 2:
            analysis["fleiss_kappa"] = self._compute_fleiss_kappa(fleiss_matrix)

        return analysis

    def _bootstrap_ci(
        self,
        scores: list[float],
        n_bootstrap: int = 1000,
        confidence: float = 0.95,
    ) -> tuple[float, float]:
        """부트스트랩 기반 신뢰구간."""
        if len(scores) < 2:
            return (float(np.mean(scores)), float(np.mean(scores)))

        arr = np.array(scores)
        boot_means = []

        rng = np.random.default_rng()
        for _ in range(n_bootstrap):
            sample = rng.choice(arr, size=len(arr), replace=True)
            boot_means.append(np.mean(sample))

        alpha = (1 - confidence) / 2
        lower = float(np.percentile(boot_means, alpha * 100))
        upper = float(np.percentile(boot_means, (1 - alpha) * 100))

        return (lower, upper)

    def _compute_fleiss_kappa(self, matrix: list[list[int]]) -> dict:
        """Fleiss' kappa 계산.

        Args:
            matrix: N x k 행렬 (N=평가 대상 수, k=카테고리 수)
                    각 행: [approved 수, rejected 수]
        """
        mat = np.array(matrix, dtype=float)
        N = mat.shape[0]  # 평가 대상 수
        k = mat.shape[1]  # 카테고리 수
        n = mat.sum(axis=1)  # 각 대상의 평가자 수

        if N < 2 or np.any(n == 0):
            return {"kappa": 0, "interpretation": "계산 불가"}

        # 각 카테고리의 전체 비율
        p_j = mat.sum(axis=0) / mat.sum()

        # 각 대상의 일치도
        P_i = np.zeros(N)
        for i in range(N):
            if n[i] > 1:
                P_i[i] = (np.sum(mat[i] ** 2) - n[i]) / (n[i] * (n[i] - 1))

        P_bar = np.mean(P_i)
        P_e = np.sum(p_j ** 2)

        if P_e >= 1:
            kappa = 1.0
        else:
            kappa = (P_bar - P_e) / (1 - P_e)

        interpretation = self._interpret_kappa(kappa)

        return {
            "kappa": float(kappa),
            "P_bar": float(P_bar),
            "P_e": float(P_e),
            "interpretation": interpretation,
        }

    def _interpret_kappa(self, kappa: float) -> str:
        """Fleiss' kappa 해석 (Landis & Koch, 1977)."""
        if kappa < 0:
            return "일치도 없음 (poor)"
        elif kappa < 0.20:
            return "약한 일치 (slight)"
        elif kappa < 0.40:
            return "적당한 일치 (fair)"
        elif kappa < 0.60:
            return "보통 일치 (moderate)"
        elif kappa < 0.80:
            return "상당한 일치 (substantial)"
        else:
            return "거의 완벽한 일치 (almost perfect)"


def compute_required_repetitions(
    desired_power: float = 0.80,
    alpha: float = 0.05,
    expected_kappa: float = 0.60,
    null_kappa: float = 0.40,
    n_raters: int = 12,
) -> int:
    """통계적 검정력 분석에 기반한 최소 반복 횟수.

    Donner & Rotondi (2010)의 공식 근사.
    """
    z_alpha = stats.norm.ppf(1 - alpha / 2)
    z_beta = stats.norm.ppf(desired_power)

    # 간단 근사: 대표적인 kappa 차이에 대한 필요 표본 수
    effect_size = abs(expected_kappa - null_kappa)
    if effect_size == 0:
        return 100

    # 근사 공식 (Sim & Wright, 2005)
    n = ((z_alpha + z_beta) ** 2) / (effect_size ** 2)
    n = max(int(np.ceil(n)), 5)

    return n
