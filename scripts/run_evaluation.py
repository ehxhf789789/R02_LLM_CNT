"""건설신기술 1차 평가 실행 스크립트.

전체 파이프라인 오케스트레이션:
  1. 제안기술 정보 로드
  2. 에이전트 패널 구성
  3. 선행기술 검색 (RAG-Novelty)
  4. 에이전트별 KB 조립 (PIKE-RAG)
  5. 평가 프롬프트 생성
  6. 앙상블 집계 (PoLL)

사용법:
    python scripts/run_evaluation.py --proposal data/proposals/sample.json
    python scripts/run_evaluation.py --proposal data/proposals/sample.json --dry-run
"""

import argparse
import json
import logging
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.evaluation.kb_assembler import KBAssembler
from src.evaluation.prior_art_searcher import PriorArtSearcher
from src.evaluation.prompt_builder import PromptBuilder
from src.evaluation.ensemble_evaluator import EnsembleEvaluator, AgentVote
from src.models.agent_profile import AgentProfile, ExperienceLevel, MatchLevel
from src.models.cnt_classification import (
    CNTClassification,
    TechCategory,
    parse_kaia_field,
)
from src.models.evaluation import EvaluationResult, NoveltyScore, ProgressivenessScore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_default_panel(tech_field: str) -> list[AgentProfile]:
    """제안기술 분야에 맞는 기본 에이전트 패널을 생성.

    실제 건설신기술 평가위원회 구성을 모사:
    - 정합 고경력 2명
    - 정합 중경력 2명
    - 정합 저경력 1명
    - 부분정합 고경력 1명
    - 부분정합 중경력 1명
    """
    classification = parse_kaia_field(tech_field)
    if not classification:
        # 기본 분류 사용
        classification = CNTClassification(
            major=TechCategory(code="CIV", name="토목", name_en="Civil Engineering"),
            middle=TechCategory(code="CIV_BRG", name="교량", name_en="Bridge"),
            minor=TechCategory(code="CIV_BRG_GRD", name="교량거더", name_en="Bridge Girder"),
        )

    panel_config = [
        ("exact", "high", 20), ("exact", "high", 18),
        ("exact", "medium", 12), ("exact", "medium", 10),
        ("exact", "low", 5),
        ("partial", "high", 17),
        ("partial", "medium", 11),
    ]

    panel = []
    for i, (match, exp, years) in enumerate(panel_config, 1):
        profile = AgentProfile(
            agent_id=f"agent_{i:02d}_{match[0]}_{exp[0]}",
            specialty=classification,
            match_level=MatchLevel(match),
            experience=ExperienceLevel(exp),
            experience_years=years,
        )
        panel.append(profile)

    return panel


def load_proposal(path: Path) -> dict:
    """제안기술 JSON 파일을 로드."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="건설신기술 1차 평가 실행")
    parser.add_argument(
        "--proposal",
        type=Path,
        help="제안기술 JSON 파일 경로",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="프롬프트만 생성하고 실제 LLM 호출은 하지 않음",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/evaluation_results"),
        help="결과 출력 디렉토리",
    )
    args = parser.parse_args()

    # 1. 제안기술 로드 (없으면 샘플 사용)
    if args.proposal and args.proposal.exists():
        proposal = load_proposal(args.proposal)
    else:
        proposal = create_sample_proposal()
        logger.info("샘플 제안기술을 사용합니다.")

    tech_name = proposal.get("tech_name", "미지정 기술")
    tech_field = proposal.get("tech_field", "토목 > 교량 > 교량거더")
    logger.info("평가 대상: %s (%s)", tech_name, tech_field)

    # 2. 에이전트 패널 구성
    panel = create_default_panel(tech_field)
    logger.info("평가 패널: %d명 구성", len(panel))

    # 3. 선행기술 검색 (RAG-Novelty)
    searcher = PriorArtSearcher()
    prior_art = searcher.search(
        tech_name=tech_name,
        tech_description=proposal.get("tech_description", ""),
        tech_keywords=proposal.get("search_keywords"),
    )
    logger.info("선행기술 검색 완료: 총 %d건", prior_art.total_count)

    # 4. 에이전트별 KB 조립 + 프롬프트 생성
    assembler = KBAssembler()
    builder = PromptBuilder()

    prompts_by_agent: dict[str, dict] = {}
    for profile in panel:
        kb = assembler.assemble(profile)
        prompt = builder.build_evaluation_prompt(kb, prior_art, proposal)
        prompts_by_agent[profile.agent_id] = prompt

    # 5. 결과 저장
    args.output.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        # 프롬프트만 저장
        for agent_id, prompt in prompts_by_agent.items():
            out_path = args.output / f"prompt_{agent_id}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(prompt, f, ensure_ascii=False, indent=2)

        logger.info(
            "DRY-RUN 완료: %d개 에이전트 프롬프트가 %s에 저장되었습니다.",
            len(prompts_by_agent),
            args.output,
        )
        print(f"\n프롬프트 파일 {len(prompts_by_agent)}개 생성됨: {args.output}")
        print("실제 LLM 호출을 위해서는 --dry-run 플래그를 제거하세요.")
        print("\n--- 프롬프트 미리보기 (첫 번째 에이전트) ---")
        first_prompt = next(iter(prompts_by_agent.values()))
        print(f"[SYSTEM]\n{first_prompt['system'][:500]}...")
        print(f"\n[USER]\n{first_prompt['user'][:1000]}...")
        return

    # 실제 평가 실행 (향후 Claude API 연동)
    print("\n현재는 LLM 호출이 구현되지 않았습니다.")
    print("--dry-run 모드로 프롬프트를 먼저 확인하세요.")
    print("향후 Claude API 연동 시 실제 평가가 실행됩니다.")


def create_sample_proposal() -> dict:
    """테스트용 샘플 제안기술."""
    return {
        "tech_name": "고강도 UHPC를 활용한 프리캐스트 교량 바닥판 급속시공 공법",
        "tech_field": "토목 > 교량 > 교량거더",
        "tech_description": (
            "초고성능 콘크리트(UHPC)를 이용하여 프리캐스트 교량 바닥판을 "
            "제작하고, 현장에서 UHPC 접합부를 통해 급속시공하는 공법. "
            "기존 현장타설 방식 대비 공기 단축 및 품질 향상을 목표로 한다."
        ),
        "tech_core_content": (
            "1. UHPC 배합 설계: 압축강도 180MPa 이상, 인장강도 8MPa 이상\n"
            "2. 프리캐스트 세그먼트 설계: 표준 모듈화, 접합부 상세\n"
            "3. UHPC 접합부: 루프 철근 이음 + UHPC 충전, 양생 24시간\n"
            "4. 급속시공 프로세스: 거치 → 접합 → UHPC 충전 → 양생 → 연결"
        ),
        "differentiation_claim": (
            "기존 현장타설 방식 대비: 공기 70% 단축, 교통 통제 최소화. "
            "기존 프리캐스트 공법 대비: UHPC 접합부로 일체식 거동 확보, "
            "접합부 내구성 현저히 향상."
        ),
        "test_results": (
            "접합부 휨 시험: 일체식 대비 95% 이상 성능 확인\n"
            "피로 시험: 200만 회 반복하중 하 균열 미발생\n"
            "내구성 시험: 동결융해 300사이클 후 질량감소 0.1% 미만"
        ),
        "field_application": (
            "OO고속도로 IC 램프교 (2024.6 시공, 연장 120m)\n"
            "기존 공법 대비 공기 65% 단축, 품질 검사 전항목 합격"
        ),
    }


if __name__ == "__main__":
    main()
