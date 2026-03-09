"""공유 지식베이스 구축 스크립트.

1. KAIA 건설신기술 지정 목록 크롤링
2. 정적 KB (평가 기준 체계) 생성
3. 분류체계 데이터 저장
"""

import json
import logging
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.dynamic_kb.kb_builder import KBBuilder
from src.static_kb.evaluation_criteria import get_evaluation_summary
from config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    logger.info("=== 공유 지식베이스 구축 시작 ===")

    builder = KBBuilder()

    # 1. 공유 KB 구축 (KAIA 크롤링 + 정적 KB)
    shared_kb = builder.build_shared_kb(max_pages=10)

    # 2. 평가 기준 체계를 별도 파일로 저장
    criteria_dir = settings.static_kb_dir / "evaluation_manual"
    criteria_dir.mkdir(parents=True, exist_ok=True)

    criteria_path = criteria_dir / "evaluation_criteria.md"
    criteria_path.write_text(get_evaluation_summary(), encoding="utf-8")
    logger.info("평가 기준 체계 저장: %s", criteria_path)

    # 3. 공유 KB 메타데이터 저장
    meta_path = settings.data_dir / "shared_kb_meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(shared_kb, f, ensure_ascii=False, indent=2)
    logger.info("공유 KB 메타 저장: %s", meta_path)

    logger.info("=== 공유 지식베이스 구축 완료 ===")
    logger.info("  지정기술: %d건", shared_kb["designated_technologies_count"])
    logger.info("  대분류: %d개", len(shared_kb["classification"]["major_categories"]))


if __name__ == "__main__":
    main()
