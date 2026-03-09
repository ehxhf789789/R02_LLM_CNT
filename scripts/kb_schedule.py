"""KB 수집 스케줄 관리 — 월간/주간 실행 계획.

KIPRIS 월 1,000건 제한을 고려하여 수집 일정을 관리한다.
각 실행 시 사용량을 추적하고 월간 한도를 초과하지 않도록 한다.

사용법:
  py scripts/kb_schedule.py --plan     # 월간 실행 계획 출력
  py scripts/kb_schedule.py --usage    # API 사용량 확인
  py scripts/kb_schedule.py --reset    # 월간 사용량 초기화
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

USAGE_FILE = settings.data_dir / "api_usage.json"
KIPRIS_MONTHLY_LIMIT = 1000


def load_usage() -> dict:
    if USAGE_FILE.exists():
        with open(USAGE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"months": {}}


def save_usage(usage: dict) -> None:
    USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(USAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(usage, f, ensure_ascii=False, indent=2)


def get_current_month() -> str:
    return datetime.now().strftime("%Y-%m")


def record_usage(source: str, count: int) -> None:
    """API 사용량을 기록."""
    usage = load_usage()
    month = get_current_month()

    if month not in usage["months"]:
        usage["months"][month] = {}
    if source not in usage["months"][month]:
        usage["months"][month][source] = 0

    usage["months"][month][source] += count
    save_usage(usage)


def print_usage() -> None:
    usage = load_usage()
    month = get_current_month()

    print("\n" + "=" * 50)
    print("  API 사용량 현황")
    print("=" * 50)

    month_data = usage["months"].get(month, {})
    kipris_used = month_data.get("kipris", 0)
    scholar_used = month_data.get("scholar", 0)
    codil_used = month_data.get("codil", 0)

    print(f"\n  {month} 사용량:")
    print(f"    KIPRIS: {kipris_used} / {KIPRIS_MONTHLY_LIMIT} ({kipris_used/KIPRIS_MONTHLY_LIMIT*100:.1f}%)")
    print(f"    Semantic Scholar: {scholar_used} (무제한)")
    print(f"    CODIL: {codil_used} (무제한)")
    print(f"    KIPRIS 잔여: {KIPRIS_MONTHLY_LIMIT - kipris_used}건")

    # 이전 달 히스토리
    print("\n  월별 히스토리:")
    for m in sorted(usage["months"].keys(), reverse=True)[:6]:
        data = usage["months"][m]
        total = sum(data.values())
        print(f"    {m}: {total}건 (KIPRIS:{data.get('kipris',0)}, Scholar:{data.get('scholar',0)}, CODIL:{data.get('codil',0)})")
    print("=" * 50)


def print_monthly_plan() -> None:
    """4주 수집 계획 출력."""
    usage = load_usage()
    month = get_current_month()
    month_data = usage["months"].get(month, {})
    kipris_remaining = KIPRIS_MONTHLY_LIMIT - month_data.get("kipris", 0)

    print("\n" + "=" * 60)
    print("  월간 KB 수집 실행 계획")
    print("=" * 60)

    print(f"""
  이번 달 KIPRIS 잔여: {kipris_remaining}건

  ── Phase 1 (기본 커버리지) 주간 스케줄 ──

  Week 1: 토목(CIV) 키워드 수집
    실행: py scripts/kb_accumulation.py --phase 1 --source kipris
    예상: 특허 ~180건 (9 중분류 × 2 키워드 × 10건)
    실행: py scripts/kb_accumulation.py --phase 1 --source scholar
    예상: 논문 ~180건

  Week 2: 건축(ARC) 키워드 수집
    실행: py scripts/kb_accumulation.py --phase 1 --source kipris
    예상: 특허 ~160건 (8 중분류 × 2 키워드 × 10건)
    실행: py scripts/kb_accumulation.py --phase 1 --source scholar
    예상: 논문 ~160건

  Week 3: 기계설비(MEC) + CODIL 전체
    실행: py scripts/kb_accumulation.py --phase 1 --source kipris
    예상: 특허 ~60건 (3 중분류 × 2 키워드 × 10건)
    실행: py scripts/kb_accumulation.py --phase 1 --source codil
    예상: CODIL ~200건 (20 중분류 × 10건)

  Week 4: 테스트 케이스 확장
    실행: py scripts/expand_test_cases.py --collect --max-pages 30
    실행: py scripts/expand_test_cases.py --build-proposals
    예상: 프로포절 30건+ 구축

  ── Phase 2 (심화 축적) 다음 달 ──

  KIPRIS 1,000건/월 제한으로 인해 2개월에 걸쳐 진행:
    Month 2: Phase 2 전반 (CIV + ARC, 600건)
    Month 3: Phase 2 후반 (MEC + 보충, 400건)

  ── 벡터DB 재구축 ──

  각 Phase 완료 후:
    py -c "
    from src.vectordb.kb_vectorizer import KBVectorizer
    v = KBVectorizer()
    count = v.build_from_store()
    print(f'벡터화 완료: {{count}}건')
    "

  ── 최종 목표 (3개월 후) ──

  | 소스       | 현재   | Phase 1 후 | Phase 2 후 | Phase 3 후 |
  |-----------|--------|-----------|-----------|-----------|
  | 특허       | 260건  | ~660건    | ~1,260건  | ~2,260건  |
  | 논문       | 120건  | ~640건    | ~1,240건  | ~2,040건  |
  | CODIL     | 27건   | ~227건    | ~627건    | ~1,027건  |
  | 지정기술   | 50건   | ~150건    | ~150건    | ~150건    |
  | 프로포절   | 1건    | ~30건     | ~45건     | ~45건     |
  |-----------|--------|-----------|-----------|-----------|
  | 합계       | 458건  | ~1,707건  | ~3,277건  | ~5,522건  |

  에이전트당 KB (15명 기준):
    현재: ~30건 → Phase 3 후: ~370건
""")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="KB 수집 스케줄 관리")
    parser.add_argument("--plan", action="store_true", help="월간 실행 계획 출력")
    parser.add_argument("--usage", action="store_true", help="API 사용량 확인")
    parser.add_argument("--reset", action="store_true", help="월간 사용량 초기화")
    args = parser.parse_args()

    if args.plan:
        print_monthly_plan()
    elif args.usage:
        print_usage()
    elif args.reset:
        usage = load_usage()
        month = get_current_month()
        usage["months"][month] = {}
        save_usage(usage)
        print(f"  {month} 사용량 초기화 완료")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
