"""에이전트별 동적 지식베이스 구축 스크립트.

지정된 에이전트 프로파일에 대해 KIPRIS(특허) + ScienceON(논문) 데이터를
수집하여 맞춤 KB를 생성한다.

사용법:
    python scripts/build_agent_kb.py --major A --middle A03 --minor A03_01 \
        --match exact --experience high --years 20
"""

import argparse
import logging
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.dynamic_kb.kb_builder import KBBuilder
from src.models.agent_profile import AgentProfile, ExperienceLevel, MatchLevel
from src.models.cnt_classification import (
    CNTClassification,
    TechCategory,
    get_major_category,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="에이전트별 동적 KB 구축")
    parser.add_argument("--agent-id", default=None, help="에이전트 ID (자동 생성 가능)")
    parser.add_argument("--major", required=True, help="대분류 코드 (예: A)")
    parser.add_argument("--middle", required=True, help="중분류 코드 (예: A03)")
    parser.add_argument("--minor", required=True, help="소분류 코드 (예: A03_01)")
    parser.add_argument("--minor-name", default="", help="소분류 이름")
    parser.add_argument(
        "--match",
        choices=["exact", "partial"],
        default="exact",
        help="전문 분야 매칭 수준",
    )
    parser.add_argument(
        "--experience",
        choices=["high", "medium", "low"],
        default="medium",
        help="심사 경력 수준",
    )
    parser.add_argument("--years", type=int, default=10, help="경력 연수")
    parser.add_argument("--max-patents", type=int, default=30, help="최대 특허 수집 수")
    parser.add_argument("--max-papers", type=int, default=30, help="최대 논문 수집 수")
    return parser.parse_args()


def main():
    args = parse_args()

    # 대분류 카테고리 조회
    major = get_major_category(args.major)
    if not major:
        logger.error("존재하지 않는 대분류 코드: %s", args.major)
        sys.exit(1)

    # 프로파일 구성
    classification = CNTClassification(
        major=major,
        middle=TechCategory(code=args.middle, name=args.middle),
        minor=TechCategory(code=args.minor, name=args.minor_name or args.minor),
    )

    agent_id = args.agent_id or f"agent_{args.major}_{args.match}_{args.experience}"

    profile = AgentProfile(
        agent_id=agent_id,
        specialty=classification,
        match_level=MatchLevel(args.match),
        experience=ExperienceLevel(args.experience),
        experience_years=args.years,
    )

    logger.info("=== 에이전트 KB 구축 시작 ===")
    logger.info("  에이전트: %s", agent_id)
    logger.info("  전문분야: %s", profile.specialty_description)
    logger.info("  매칭수준: %s", profile.match_level.value)
    logger.info("  경력: %s (%d년)", profile.experience.value, profile.experience_years)

    builder = KBBuilder()
    kb = builder.build_agent_kb(
        profile=profile,
        max_patents=args.max_patents,
        max_papers=args.max_papers,
    )

    logger.info("=== 에이전트 KB 구축 완료 ===")
    logger.info("  특허: %d건", len(kb["dynamic_kb"]["patents"]))
    logger.info("  논문: %d건", len(kb["dynamic_kb"]["papers"]))


if __name__ == "__main__":
    main()
