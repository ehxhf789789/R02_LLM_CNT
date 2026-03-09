"""평가 오케스트레이터.

전체 평가 파이프라인을 통합 관리:
  1. 제안기술 로드
  2. 에이전트 패널 생성
  3. KB 조립 + 선행기술 검색
  4. LLM 호출 (병렬)
  5. 앙상블 집계
  6. 의장 검토
  7. 결과 저장
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from config.settings import settings
from src.evaluation.kb_assembler import KBAssembler
from src.evaluation.prior_art_searcher import PriorArtSearcher
from src.evaluation.prompt_builder import PromptBuilder
from src.evaluation.ensemble_evaluator import (
    EnsembleEvaluator,
    AgentVote,
    EnsembleResult,
)
from src.evaluation.chairman_agent import ChairmanAgent
from src.llm.bedrock_client import BedrockClient, LLMResponse
from src.models.agent_profile import AgentProfile
from src.pipeline.panel_generator import PanelGenerator

logger = logging.getLogger(__name__)


@dataclass
class EvaluationRun:
    """단일 평가 실행 결과."""
    run_id: str = ""
    tech_number: str = ""
    tech_name: str = ""
    tech_field: str = ""
    panel_size: int = 0
    panel_profiles: list[dict] = field(default_factory=list)
    votes: list[dict] = field(default_factory=list)
    ensemble_result: dict = field(default_factory=dict)
    chairman_review: dict = field(default_factory=dict)
    llm_usage: dict = field(default_factory=dict)
    elapsed_seconds: float = 0.0


class Orchestrator:
    """평가 파이프라인 오케스트레이터."""

    def __init__(
        self,
        llm_client: BedrockClient | None = None,
        panel_generator: PanelGenerator | None = None,
        kb_assembler: KBAssembler | None = None,
        prior_art_searcher: PriorArtSearcher | None = None,
        prompt_builder: PromptBuilder | None = None,
        ensemble_evaluator: EnsembleEvaluator | None = None,
        chairman: ChairmanAgent | None = None,
        output_dir: Path | None = None,
        max_workers: int = 5,
    ):
        self.llm_client = llm_client
        self.panel_gen = panel_generator or PanelGenerator()
        self.kb_assembler = kb_assembler or KBAssembler()
        self.prior_art = prior_art_searcher or PriorArtSearcher()
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.ensemble = ensemble_evaluator or EnsembleEvaluator()
        self.chairman = chairman or ChairmanAgent()
        self.output_dir = output_dir or settings.results_dir
        self.max_workers = max_workers

    def evaluate(
        self,
        proposal: dict,
        run_id: str | None = None,
        seed: int | None = None,
        skip_chairman: bool = False,
        exclude_tech_numbers: list[str] | None = None,
    ) -> EvaluationRun:
        """단일 제안기술에 대한 전체 평가 파이프라인 실행.

        Args:
            proposal: 제안기술 dict
            run_id: 실행 ID (재현성)
            seed: 랜덤 시드 (패널 재현)
            skip_chairman: 의장 검토 생략
            exclude_tech_numbers: KB에서 제외할 기술 번호 (통제 실험)
        """
        start_time = time.time()

        tech_name = proposal.get("tech_name", "")
        tech_field = proposal.get("tech_field", "")
        tech_number = proposal.get("tech_number", "")

        # 시간적 커트오프: 지정연도 추출 (통제 실험에서 미래 정보 유입 방지)
        cutoff_year = self._extract_cutoff_year(proposal)

        if not run_id:
            run_id = f"run_{tech_number}_{int(time.time())}"

        logger.info(
            "평가 시작: %s (%s) - %s [커트오프: %s]",
            tech_name, tech_field, run_id,
            f"{cutoff_year}년" if cutoff_year else "없음",
        )

        result = EvaluationRun(
            run_id=run_id,
            tech_number=tech_number,
            tech_name=tech_name,
            tech_field=tech_field,
        )

        # 1. 에이전트 패널 생성
        panel = self.panel_gen.generate(tech_field, seed=seed)
        result.panel_size = len(panel)
        result.panel_profiles = [
            {
                "agent_id": p.agent_id,
                "match_level": p.match_level.value,
                "experience": p.experience.value,
                "experience_years": p.experience_years,
                "specialty": p.specialty_description,
            }
            for p in panel
        ]

        # 2. 선행기술 검색 (자기참조 방지: 평가 대상 기술 자체를 선행기술에서 제외)
        prior_art_exclude = list(set(exclude_tech_numbers or []))
        if tech_number and tech_number not in prior_art_exclude:
            prior_art_exclude.append(tech_number)

        prior_art_ctx = self.prior_art.search(
            tech_name=tech_name,
            tech_description=proposal.get("tech_description", ""),
            tech_keywords=proposal.get("search_keywords"),
            exclude_tech_numbers=prior_art_exclude,
            cutoff_year=cutoff_year,
        )

        # 3. 에이전트별 KB 조립 + 프롬프트 생성
        # 제외 목록: 현재 평가 대상 기술 + 외부 지정 제외 목록
        exclude_list = list(set(exclude_tech_numbers or []))
        if tech_number and tech_number not in exclude_list:
            exclude_list.append(tech_number)

        agent_prompts: dict[str, dict] = {}
        for profile in panel:
            kb = self.kb_assembler.assemble(
                profile,
                tech_query=tech_name,
                exclude_tech_numbers=exclude_list,
                cutoff_year=cutoff_year,
            )
            prompt = self.prompt_builder.build_evaluation_prompt(kb, prior_art_ctx, proposal)
            agent_prompts[profile.agent_id] = prompt

        # 4. LLM 호출
        if not self.llm_client:
            self.llm_client = BedrockClient()

        votes = self._invoke_agents(agent_prompts)
        result.votes = [self._vote_to_dict(v) for v in votes]

        # 5. 앙상블 집계
        ensemble_result = self.ensemble.aggregate(votes)
        result.ensemble_result = {
            "final_verdict": ensemble_result.final_verdict,
            "approval_ratio": ensemble_result.approval_ratio,
            "weighted_approval_ratio": ensemble_result.weighted_approval_ratio,
            "avg_novelty_total": ensemble_result.avg_novelty_total,
            "avg_progressiveness_total": ensemble_result.avg_progressiveness_total,
            "avg_total": ensemble_result.avg_total,
            "dissenting_opinions": ensemble_result.dissenting_opinions,
            "consensus_evidence": ensemble_result.consensus_evidence,
        }

        # 6. 의장 검토
        if not skip_chairman and votes:
            try:
                chairman_result = self.chairman.review(ensemble_result, proposal)
                result.chairman_review = chairman_result
            except Exception as e:
                logger.error("의장 검토 실패: %s", e)
                result.chairman_review = {"error": str(e)}

        result.elapsed_seconds = time.time() - start_time

        # 7. 결과 저장
        self._save_result(result)

        logger.info(
            "평가 완료: %s → %s (%.1f초, %d명)",
            tech_name,
            ensemble_result.final_verdict,
            result.elapsed_seconds,
            len(votes),
        )

        return result

    def _invoke_agents(
        self,
        agent_prompts: dict[str, dict],
    ) -> list[AgentVote]:
        """에이전트별 LLM 호출 (ThreadPool 기반 병렬)."""
        votes: list[AgentVote] = []
        total_usage = {"input_tokens": 0, "output_tokens": 0, "total_latency_ms": 0}

        def _call_agent(agent_id: str, prompt: dict) -> AgentVote | None:
            try:
                response = self.llm_client.invoke(
                    system_prompt=prompt["system"],
                    user_message=prompt["user"],
                    max_tokens=8192,
                    temperature=0.3,
                )
                total_usage["input_tokens"] += response.input_tokens
                total_usage["output_tokens"] += response.output_tokens
                total_usage["total_latency_ms"] += response.latency_ms

                return EnsembleEvaluator.parse_agent_response(agent_id, response.content)
            except Exception as e:
                logger.error("에이전트 %s 호출 실패: %s", agent_id, e)
                return None

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(_call_agent, aid, prompt): aid
                for aid, prompt in agent_prompts.items()
            }

            for future in as_completed(futures):
                agent_id = futures[future]
                try:
                    vote = future.result()
                    if vote:
                        votes.append(vote)
                    else:
                        logger.warning("에이전트 %s: 응답 파싱 실패", agent_id)
                except Exception as e:
                    logger.error("에이전트 %s 실행 오류: %s", agent_id, e)

        logger.info(
            "LLM 호출 완료: %d/%d 에이전트 (입력 %d, 출력 %d 토큰)",
            len(votes), len(agent_prompts),
            total_usage["input_tokens"], total_usage["output_tokens"],
        )

        return votes

    def _vote_to_dict(self, vote: AgentVote) -> dict:
        """AgentVote를 직렬화 가능한 dict로 변환."""
        e = vote.evaluation
        return {
            "agent_id": vote.agent_id,
            "vote": vote.vote,
            "confidence": vote.confidence,
            "novelty": {
                "differentiation": e.novelty.differentiation,
                "originality": e.novelty.originality,
                "total": e.novelty.total,
            },
            "progressiveness": {
                "quality_improvement": e.progressiveness.quality_improvement,
                "development_degree": e.progressiveness.development_degree,
                "safety": e.progressiveness.safety,
                "eco_friendliness": e.progressiveness.eco_friendliness,
                "total": e.progressiveness.total,
            },
            "total": e.novelty.total + e.progressiveness.total,
            "evidence": e.evidence,
            "evidence_details": vote.evidence_details,
            "reasoning": vote.reasoning,
            "prior_art_comparison": vote.prior_art_comparison,
        }

    @staticmethod
    def _extract_cutoff_year(proposal: dict) -> int | None:
        """제안기술의 지정연도를 추출하여 시간적 커트오프로 사용.

        통제 실험에서 미래 정보 유입을 방지한다.
        예: 2020년 지정 기술이면 2020년 이후 발행 자료를 KB에서 제외.

        Returns:
            지정연도 (int) 또는 None (실시간 평가 / 연도 정보 없는 경우)
        """
        # 1. 직접 지정된 cutoff_year 우선
        if proposal.get("cutoff_year"):
            try:
                return int(proposal["cutoff_year"])
            except (ValueError, TypeError):
                pass

        # 2. designation_year 필드
        if proposal.get("designation_year"):
            try:
                return int(proposal["designation_year"])
            except (ValueError, TypeError):
                pass

        # 3. protection_period에서 시작연도 추출 (e.g., "2020-09-30 ~ 2027-09-30")
        period = proposal.get("protection_period", "")
        if period:
            match = re.match(r"(\d{4})", str(period))
            if match:
                return int(match.group(1))

        return None

    def _save_result(self, result: EvaluationRun) -> Path:
        """평가 결과를 JSON으로 저장."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        out_path = self.output_dir / f"{result.run_id}.json"

        data = {
            "run_id": result.run_id,
            "tech_number": result.tech_number,
            "tech_name": result.tech_name,
            "tech_field": result.tech_field,
            "panel_size": result.panel_size,
            "panel_profiles": result.panel_profiles,
            "votes": result.votes,
            "ensemble_result": result.ensemble_result,
            "chairman_review": result.chairman_review,
            "elapsed_seconds": result.elapsed_seconds,
        }

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)

        logger.info("결과 저장: %s", out_path)
        return out_path
