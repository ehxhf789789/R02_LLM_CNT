"""분석 8-1: 건별 정확도 분석.

각 테스트 케이스(이미 승인된 기술)에 대해
에이전트 의결과 실제 결과(approved)를 비교한다.

분석 항목:
  - 건별 승인율 (실제: 모두 approved이므로, approved 비율이 높을수록 정확)
  - 개별 에이전트 정확도
  - 분야별/경력별 정확도 패턴
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


class AccuracyAnalyzer:
    """건별 정확도 분석기."""

    def analyze(self, results_dir: Path) -> dict:
        """결과 디렉토리의 모든 평가 결과를 분석.

        모든 테스트 케이스는 실제 approved이므로,
        에이전트 의결이 approved인 비율이 정확도가 된다.
        """
        result_files = sorted(results_dir.glob("run_*.json"))
        if not result_files:
            logger.warning("분석할 결과 파일 없음: %s", results_dir)
            return {}

        runs = []
        for f in result_files:
            with open(f, encoding="utf-8") as fp:
                runs.append(json.load(fp))

        analysis = {
            "total_cases": len(runs),
            "case_results": [],
            "overall_accuracy": 0.0,
            "per_agent_accuracy": {},
            "by_match_level": {"exact": [], "partial": []},
            "by_experience": {"high": [], "medium": [], "low": []},
        }

        correct_count = 0

        for run in runs:
            final_verdict = run.get("ensemble_result", {}).get("final_verdict", "")
            is_correct = final_verdict == "approved"  # 실제 모두 approved

            case_result = {
                "tech_number": run.get("tech_number", ""),
                "tech_name": run.get("tech_name", ""),
                "final_verdict": final_verdict,
                "is_correct": is_correct,
                "approval_ratio": run.get("ensemble_result", {}).get("approval_ratio", 0),
                "weighted_approval_ratio": run.get("ensemble_result", {}).get("weighted_approval_ratio", 0),
                "avg_total": run.get("ensemble_result", {}).get("avg_total", 0),
                "panel_size": run.get("panel_size", 0),
            }

            if is_correct:
                correct_count += 1

            # 개별 에이전트 정확도 누적
            for vote in run.get("votes", []):
                agent_id = vote.get("agent_id", "")
                is_agent_correct = vote.get("vote") == "approved"

                if agent_id not in analysis["per_agent_accuracy"]:
                    analysis["per_agent_accuracy"][agent_id] = {
                        "correct": 0, "total": 0, "scores": []
                    }

                analysis["per_agent_accuracy"][agent_id]["total"] += 1
                if is_agent_correct:
                    analysis["per_agent_accuracy"][agent_id]["correct"] += 1
                analysis["per_agent_accuracy"][agent_id]["scores"].append(
                    vote.get("total", 0)
                )

            # 매칭 수준별 분류
            for profile in run.get("panel_profiles", []):
                match = profile.get("match_level", "")
                exp = profile.get("experience", "")
                aid = profile.get("agent_id", "")

                # 해당 에이전트의 투표 찾기
                vote_data = next(
                    (v for v in run.get("votes", []) if v.get("agent_id") == aid),
                    None
                )

                if vote_data:
                    is_v_correct = vote_data.get("vote") == "approved"
                    score = vote_data.get("total", 0)

                    if match in analysis["by_match_level"]:
                        analysis["by_match_level"][match].append({
                            "correct": is_v_correct, "score": score
                        })
                    if exp in analysis["by_experience"]:
                        analysis["by_experience"][exp].append({
                            "correct": is_v_correct, "score": score
                        })

            analysis["case_results"].append(case_result)

        analysis["overall_accuracy"] = correct_count / len(runs) if runs else 0

        # 매칭 수준별 통계
        for key in analysis["by_match_level"]:
            items = analysis["by_match_level"][key]
            if items:
                acc = sum(1 for i in items if i["correct"]) / len(items)
                avg_score = np.mean([i["score"] for i in items])
                analysis["by_match_level"][key] = {
                    "count": len(items),
                    "accuracy": acc,
                    "avg_score": float(avg_score),
                }
            else:
                analysis["by_match_level"][key] = {"count": 0, "accuracy": 0, "avg_score": 0}

        # 경력별 통계
        for key in analysis["by_experience"]:
            items = analysis["by_experience"][key]
            if items:
                acc = sum(1 for i in items if i["correct"]) / len(items)
                avg_score = np.mean([i["score"] for i in items])
                analysis["by_experience"][key] = {
                    "count": len(items),
                    "accuracy": acc,
                    "avg_score": float(avg_score),
                }
            else:
                analysis["by_experience"][key] = {"count": 0, "accuracy": 0, "avg_score": 0}

        # 에이전트별 정확도 비율 계산
        for aid, data in analysis["per_agent_accuracy"].items():
            data["accuracy"] = data["correct"] / data["total"] if data["total"] > 0 else 0
            data["avg_score"] = float(np.mean(data["scores"])) if data["scores"] else 0

        return analysis
