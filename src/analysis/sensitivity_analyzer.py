"""분석 8-4: 시간적 커트오프 민감도 분석.

소수 샘플(2013-2017 지정 기술)에 대해
커트오프 적용 vs 미적용 양쪽 평가 결과를 비교하여
KB 풍부도가 평가 결과에 미치는 영향을 측정한다.

분석 항목:
  - 동일 기술의 커트오프 적용/미적용 간 의결 일치율
  - 점수 차이 (paired t-test)
  - KB 풍부도(커트오프 연도)와 점수 변동 간 상관관계
  - 세부 항목별 민감도 (어떤 항목이 KB 부족에 취약한지)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
from scipy import stats

logger = logging.getLogger(__name__)

SCORE_LABELS = ["차별성", "독창성", "품질향상", "개발정도", "안전성", "친환경성"]

# 커트오프 연도별 예상 KB 잔여율 (시뮬레이션 기반)
# run_experiment에서 실제 값으로 갱신 가능
KB_COVERAGE_ESTIMATES = {
    2013: {"patent_pct": 41.5, "paper_pct": 0.3},
    2014: {"patent_pct": 46.0, "paper_pct": 0.4},
    2015: {"patent_pct": 50.3, "paper_pct": 5.9},
    2016: {"patent_pct": 54.6, "paper_pct": 12.8},
    2017: {"patent_pct": 59.2, "paper_pct": 19.0},
}


class SensitivityAnalyzer:
    """시간적 커트오프 민감도 분석기."""

    def analyze(
        self,
        results_dir: Path,
        cutoff_prefix: str = "run_",
        nocutoff_prefix: str = "nocutoff_",
    ) -> dict:
        """커트오프 적용/미적용 결과를 쌍으로 비교 분석.

        파일명 규칙:
          - 커트오프 적용: run_{tech_number}_{rep}.json
          - 커트오프 미적용: nocutoff_{tech_number}_{rep}.json

        Args:
            results_dir: 결과 디렉토리
            cutoff_prefix: 커트오프 적용 결과 파일 접두어
            nocutoff_prefix: 커트오프 미적용 결과 파일 접두어
        """
        # 결과 로드
        cutoff_runs = self._load_runs(results_dir, cutoff_prefix)
        nocutoff_runs = self._load_runs(results_dir, nocutoff_prefix)

        if not cutoff_runs or not nocutoff_runs:
            logger.warning(
                "민감도 분석 불가: cutoff %d건, nocutoff %d건",
                len(cutoff_runs), len(nocutoff_runs),
            )
            return {"error": "insufficient_data"}

        # 쌍(pair) 구성: 동일 tech_number끼리 매칭
        pairs = self._build_pairs(cutoff_runs, nocutoff_runs)

        if not pairs:
            logger.warning("매칭 가능한 쌍이 없음")
            return {"error": "no_matching_pairs"}

        analysis = {
            "n_pairs": len(pairs),
            "tech_numbers": list(set(p["tech_number"] for p in pairs)),
            "verdict_comparison": self._compare_verdicts(pairs),
            "score_comparison": self._compare_scores(pairs),
            "per_field_sensitivity": self._per_field_sensitivity(pairs),
            "kb_coverage_correlation": self._kb_coverage_correlation(pairs),
            "summary": {},
        }

        # 요약 판정
        analysis["summary"] = self._build_summary(analysis)

        return analysis

    def _load_runs(self, results_dir: Path, prefix: str) -> dict[str, list[dict]]:
        """접두어로 결과를 로드하여 tech_number별 그룹핑."""
        groups: dict[str, list[dict]] = {}
        for f in sorted(results_dir.glob(f"{prefix}*.json")):
            with open(f, encoding="utf-8") as fp:
                data = json.load(fp)
            tech_num = data.get("tech_number", "")
            if tech_num:
                groups.setdefault(tech_num, []).append(data)
        return groups

    def _build_pairs(
        self,
        cutoff_runs: dict[str, list[dict]],
        nocutoff_runs: dict[str, list[dict]],
    ) -> list[dict]:
        """동일 tech_number의 커트오프/미적용 결과를 쌍으로 구성."""
        pairs = []
        common_techs = set(cutoff_runs.keys()) & set(nocutoff_runs.keys())

        for tech_num in sorted(common_techs):
            c_runs = cutoff_runs[tech_num]
            nc_runs = nocutoff_runs[tech_num]

            # 각 그룹의 평균으로 비교 (반복이 여러 번인 경우)
            c_avg = self._average_runs(c_runs)
            nc_avg = self._average_runs(nc_runs)

            # 지정연도 추출
            designation_year = None
            sample = c_runs[0] if c_runs else nc_runs[0]
            # run 결과에는 직접 designation_year가 없으므로 tech_number로 추정
            # 또는 proposal에서 가져와야 함 — 여기서는 KB coverage 추정치 활용
            for yr, _ in KB_COVERAGE_ESTIMATES.items():
                # tech_number 기반으로는 추정 불가 → proposals에서 매핑 필요
                pass

            pairs.append({
                "tech_number": tech_num,
                "cutoff": c_avg,
                "nocutoff": nc_avg,
                "n_cutoff_runs": len(c_runs),
                "n_nocutoff_runs": len(nc_runs),
            })

        return pairs

    def set_designation_years(self, pairs: list[dict], proposals_dir: Path) -> None:
        """프로포절에서 지정연도를 읽어 pairs에 추가."""
        for pair in pairs:
            tech_num = pair["tech_number"]
            proposal_path = proposals_dir / f"proposal_{tech_num}.json"
            if proposal_path.exists():
                with open(proposal_path, encoding="utf-8") as f:
                    proposal = json.load(f)
                pair["designation_year"] = proposal.get("designation_year")

    def _average_runs(self, runs: list[dict]) -> dict:
        """여러 반복 실행의 평균 통계."""
        verdicts = [r.get("ensemble_result", {}).get("final_verdict", "") for r in runs]
        approval_ratios = [r.get("ensemble_result", {}).get("approval_ratio", 0) for r in runs]
        avg_totals = [r.get("ensemble_result", {}).get("avg_total", 0) for r in runs]
        avg_novelties = [r.get("ensemble_result", {}).get("avg_novelty_total", 0) for r in runs]
        avg_progs = [r.get("ensemble_result", {}).get("avg_progressiveness_total", 0) for r in runs]

        # 개별 세부점수 평균
        all_scores = []
        for run in runs:
            for vote in run.get("votes", []):
                n = vote.get("novelty", {})
                p = vote.get("progressiveness", {})
                all_scores.append([
                    n.get("differentiation", 0),
                    n.get("originality", 0),
                    p.get("quality_improvement", 0),
                    p.get("development_degree", 0),
                    p.get("safety", 0),
                    p.get("eco_friendliness", 0),
                ])

        from collections import Counter
        verdict_counter = Counter(verdicts)
        majority_verdict = verdict_counter.most_common(1)[0][0] if verdict_counter else ""

        return {
            "majority_verdict": majority_verdict,
            "approval_ratio": float(np.mean(approval_ratios)) if approval_ratios else 0,
            "avg_total": float(np.mean(avg_totals)) if avg_totals else 0,
            "avg_novelty": float(np.mean(avg_novelties)) if avg_novelties else 0,
            "avg_progressiveness": float(np.mean(avg_progs)) if avg_progs else 0,
            "detail_scores": [float(x) for x in np.mean(all_scores, axis=0)] if all_scores else [0]*6,
        }

    def _compare_verdicts(self, pairs: list[dict]) -> dict:
        """의결 일치/변동 비교."""
        same = 0
        changed_to_approved = 0  # cutoff=rejected → nocutoff=approved
        changed_to_rejected = 0  # cutoff=approved → nocutoff=rejected
        total = len(pairs)

        for p in pairs:
            cv = p["cutoff"]["majority_verdict"]
            nv = p["nocutoff"]["majority_verdict"]
            if cv == nv:
                same += 1
            elif cv == "rejected" and nv == "approved":
                changed_to_approved += 1
            elif cv == "approved" and nv == "rejected":
                changed_to_rejected += 1

        return {
            "total_pairs": total,
            "verdict_match": same,
            "verdict_match_rate": same / total if total else 0,
            "cutoff_rejected_to_nocutoff_approved": changed_to_approved,
            "cutoff_approved_to_nocutoff_rejected": changed_to_rejected,
            "interpretation": self._interpret_verdict_stability(same / total if total else 0),
        }

    def _compare_scores(self, pairs: list[dict]) -> dict:
        """점수 차이 통계 (paired t-test)."""
        cutoff_totals = [p["cutoff"]["avg_total"] for p in pairs]
        nocutoff_totals = [p["nocutoff"]["avg_total"] for p in pairs]

        diffs = [nc - c for c, nc in zip(cutoff_totals, nocutoff_totals)]
        mean_diff = float(np.mean(diffs))
        std_diff = float(np.std(diffs, ddof=1)) if len(diffs) > 1 else 0

        # Paired t-test
        if len(diffs) >= 2 and std_diff > 0:
            t_stat, p_value = stats.ttest_rel(nocutoff_totals, cutoff_totals)
        else:
            t_stat, p_value = 0, 1.0

        # 승인율 비교
        cutoff_approval = [p["cutoff"]["approval_ratio"] for p in pairs]
        nocutoff_approval = [p["nocutoff"]["approval_ratio"] for p in pairs]

        return {
            "cutoff_mean_total": float(np.mean(cutoff_totals)),
            "nocutoff_mean_total": float(np.mean(nocutoff_totals)),
            "mean_score_diff": mean_diff,
            "std_score_diff": std_diff,
            "paired_t_stat": float(t_stat),
            "paired_p_value": float(p_value),
            "significant_at_005": p_value < 0.05,
            "cutoff_mean_approval": float(np.mean(cutoff_approval)),
            "nocutoff_mean_approval": float(np.mean(nocutoff_approval)),
            "per_tech_diffs": [
                {
                    "tech_number": p["tech_number"],
                    "cutoff_total": p["cutoff"]["avg_total"],
                    "nocutoff_total": p["nocutoff"]["avg_total"],
                    "diff": p["nocutoff"]["avg_total"] - p["cutoff"]["avg_total"],
                }
                for p in pairs
            ],
        }

    def _per_field_sensitivity(self, pairs: list[dict]) -> dict:
        """세부 항목별 민감도 — 어떤 평가 항목이 KB 부족에 취약한지."""
        field_diffs = {label: [] for label in SCORE_LABELS}

        for p in pairs:
            c_scores = p["cutoff"]["detail_scores"]
            nc_scores = p["nocutoff"]["detail_scores"]
            for i, label in enumerate(SCORE_LABELS):
                if i < len(c_scores) and i < len(nc_scores):
                    field_diffs[label].append(nc_scores[i] - c_scores[i])

        result = {}
        for label, diffs in field_diffs.items():
            if not diffs:
                result[label] = {"mean_diff": 0, "sensitive": False}
                continue

            mean_d = float(np.mean(diffs))
            std_d = float(np.std(diffs, ddof=1)) if len(diffs) > 1 else 0

            if len(diffs) >= 2 and std_d > 0:
                t_stat, p_val = stats.ttest_1samp(diffs, 0)
            else:
                t_stat, p_val = 0, 1.0

            result[label] = {
                "mean_diff": mean_d,
                "std_diff": std_d,
                "t_stat": float(t_stat),
                "p_value": float(p_val),
                "sensitive": p_val < 0.05,
            }

        # 민감도 순위
        ranked = sorted(result.items(), key=lambda x: abs(x[1]["mean_diff"]), reverse=True)
        result["sensitivity_ranking"] = [
            {"field": label, "abs_mean_diff": abs(data["mean_diff"])}
            for label, data in ranked
            if isinstance(data, dict) and "mean_diff" in data
        ]

        return result

    def _kb_coverage_correlation(self, pairs: list[dict]) -> dict:
        """KB 풍부도(지정연도 → 커버리지)와 점수 변동 간 상관관계.

        지정연도가 오래될수록(커버리지 낮을수록) 점수 차이가 커지는지.
        """
        years = []
        diffs = []

        for p in pairs:
            year = p.get("designation_year")
            if year:
                years.append(int(year))
                diffs.append(p["nocutoff"]["avg_total"] - p["cutoff"]["avg_total"])

        if len(years) < 3:
            return {
                "n_data_points": len(years),
                "message": "상관분석에 필요한 데이터 부족 (최소 3건)",
            }

        # 연도와 점수차이 간 상관계수
        r, p_value = stats.pearsonr(years, diffs)

        return {
            "n_data_points": len(years),
            "pearson_r": float(r),
            "p_value": float(p_value),
            "significant_at_005": p_value < 0.05,
            "interpretation": (
                "지정연도가 오래될수록 커트오프 영향이 커짐 (유의미)"
                if p_value < 0.05 and r < -0.3
                else "지정연도가 최근일수록 커트오프 영향이 커짐 (유의미)"
                if p_value < 0.05 and r > 0.3
                else "지정연도와 커트오프 영향 간 유의미한 관계 없음"
            ),
            "data_points": [
                {"year": y, "score_diff": d} for y, d in zip(years, diffs)
            ],
        }

    @staticmethod
    def _interpret_verdict_stability(match_rate: float) -> str:
        if match_rate >= 0.9:
            return "커트오프가 의결에 거의 영향 없음 — KB 풍부도에 강건"
        elif match_rate >= 0.7:
            return "커트오프가 일부 의결을 변동시킴 — 중간 수준 민감도"
        else:
            return "커트오프가 의결을 크게 변동시킴 — KB 풍부도에 취약"

    @staticmethod
    def _build_summary(analysis: dict) -> dict:
        """분석 결과 종합 요약."""
        vc = analysis.get("verdict_comparison", {})
        sc = analysis.get("score_comparison", {})
        pfs = analysis.get("per_field_sensitivity", {})
        kbc = analysis.get("kb_coverage_correlation", {})

        sensitive_fields = [
            label for label, data in pfs.items()
            if isinstance(data, dict) and data.get("sensitive")
        ]

        return {
            "verdict_stability": vc.get("verdict_match_rate", 0),
            "mean_score_impact": sc.get("mean_score_diff", 0),
            "score_impact_significant": sc.get("significant_at_005", False),
            "sensitive_fields": sensitive_fields,
            "kb_coverage_effect": kbc.get("interpretation", ""),
            "recommendation": _generate_recommendation(
                vc.get("verdict_match_rate", 0),
                sc.get("significant_at_005", False),
                len(sensitive_fields),
            ),
        }


def _generate_recommendation(
    verdict_stability: float,
    score_significant: bool,
    n_sensitive_fields: int,
) -> str:
    """실험 설계 권고사항 생성."""
    if verdict_stability >= 0.9 and not score_significant:
        return (
            "커트오프가 평가 결과에 유의미한 영향을 미치지 않음. "
            "전 기간 프로포절에 대해 시간적 커트오프를 안전하게 적용 가능."
        )
    elif verdict_stability >= 0.7:
        return (
            "커트오프가 일부 영향을 미치나 의결 변동은 제한적. "
            "정확도 분석(8-1)은 2018년 이후 기술 위주로 보고하되, "
            "이전 기술은 KB 풍부도 제한을 명시하여 별도 보고 권장."
        )
    else:
        return (
            "커트오프에 따른 평가 변동이 크므로, "
            "정확도 분석(8-1)에서 2018년 이전 기술은 제외하고, "
            f"민감 항목({n_sensitive_fields}개)에 대한 KB 보강 또는 "
            "프롬프트 보완을 권장."
        )
