"""KB 데이터 축적 스크립트 — 실제 연구용 체계적 수집.

분류체계(대/중/소분류) × 키워드 매트릭스에 따라
KIPRIS(특허), Semantic Scholar(논문), CODIL(건설기준)을
단계적으로 수집한다.

사용법:
  py scripts/kb_accumulation.py --phase 1           # Phase 1만 실행
  py scripts/kb_accumulation.py --phase 1 --dry-run # 수집 계획만 출력
  py scripts/kb_accumulation.py --status             # 현재 축적 현황 출력
  py scripts/kb_accumulation.py --source kipris      # 특정 소스만 수집

API 제약:
  - KIPRIS: 월 1,000건 무료 (초당 1건). 1회 실행 = ~200건 소비
  - Semantic Scholar: 분당 100건 (인증 없음)
  - CODIL: rate limit 없음 (2초 간격 크롤링)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import settings
from src.dynamic_kb.kipris_client import KiprisClient
from src.dynamic_kb.semantic_scholar_client import SemanticScholarClient
from src.dynamic_kb.codil_crawler import CODILCrawler
from src.storage.kb_store import KBStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            settings.data_dir / "kb_accumulation.log",
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 검색 키워드 매트릭스
# 중분류별로 건설신기술 평가에 관련된 핵심 키워드를 정의
# ──────────────────────────────────────────────

KEYWORD_MATRIX: dict[str, dict[str, list[str]]] = {
    # ── 토목(CIV) ──
    "CIV": {
        "교량": [
            "교량 건설기술", "교량 유지보수", "교량거더 시공",
            "프리스트레스 교량", "교량 내진보강", "강교량 용접",
            "교량받침 면진", "교량 상판 방수",
        ],
        "도로": [
            "도로 포장 기술", "아스팔트 콘크리트 포장", "도로 배수시설",
            "도로 절토 사면", "도로 노면 보수", "투수성 포장",
        ],
        "터널": [
            "터널 건설 시공", "터널 방수공법", "터널 굴착 지보",
            "NATM 터널", "쉴드TBM 터널", "터널 환기설비",
        ],
        "철도": [
            "철도 궤도 건설", "철도 노반 보강", "고속철도 시공",
            "철도 교량 시공", "지하철 터널",
        ],
        "토질 및 기초": [
            "토질 기초 건설", "연약지반 처리", "흙막이 공법",
            "말뚝 기초 시공", "지반보강 그라우팅", "사면 안정화",
        ],
        "토목구조물 보수보강(포장 보수제외)": [
            "콘크리트 보수보강", "구조물 내진보강", "교량 보수보강",
            "FRP 보강공법", "콘크리트 균열보수", "탄소섬유 보강",
        ],
        "하천 및 수자원": [
            "하천 제방 시공", "수자원 관리 기술", "하천 호안공법",
            "친환경 하천정비", "홍수 방재 기술",
        ],
        "항만 및 해안": [
            "항만 구조물 시공", "해안 침식 방지", "방파제 건설",
            "해양 콘크리트", "항만 준설 매립",
        ],
        "환경": [
            "건설 환경기술", "건설 폐기물 재활용", "소음 진동 저감",
            "토양 오염 정화", "수처리 건설기술",
        ],
    },
    # ── 건축(ARC) ──
    "ARC": {
        "기초": [
            "건축 기초 보강", "기초 말뚝 시공", "매트 기초 시공",
            "기초 내진 보강", "지하구조물 기초",
        ],
        "마감": [
            "마감재 건설", "외벽 마감 시스템", "커튼월 시공",
            "건축 단열재 시공", "건축 미장 마감",
        ],
        "방수": [
            "방수 건설기술", "복합방수 시공", "지하방수 공법",
            "옥상 방수 시스템", "도막방수 시트방수", "누수 보수공법",
        ],
        "보수보강": [
            "건축 보수보강", "구조물 내진보강", "콘크리트 보수",
            "건축물 리모델링 보강", "외벽 보수보강",
        ],
        "철골": [
            "철골 구조 시공", "강구조 접합부", "철골 내화피복",
            "대공간 철골 건축", "철골 모듈러 건축",
        ],
        "철근콘크리트": [
            "철근콘크리트 보강", "RC 구조 시공", "고강도 콘크리트",
            "프리캐스트 콘크리트", "콘크리트 타설 기술",
        ],
        "특수 건축물": [
            "특수 건축물 시공", "초고층 건축 기술", "대공간 구조물",
            "면진 제진 건축", "방폭 건축물",
        ],
        "가설시설물": [
            "가설 시설물 시공", "비계 안전장치", "거푸집 시스템",
            "가설 동바리", "임시 구조물 안전",
        ],
    },
    # ── 기계설비(MEC) ──
    "MEC": {
        "건설기계": [
            "건설기계 기술", "굴착기 안전장치", "타워크레인 시공",
            "건설 자동화 로봇", "스마트 건설기계",
        ],
        "환경기계설비": [
            "건설 환경설비", "건설현장 분진저감", "건설 수처리 설비",
            "친환경 건설장비", "건설현장 소음저감",
        ],
        "통신전자 및 제어설비": [
            "건설 IoT 센서", "구조물 모니터링 시스템", "건설 안전관리 시스템",
            "스마트 건설 제어", "건설 BIM 기술",
        ],
    },
}


@dataclass
class CollectionPlan:
    """단일 수집 작업 계획."""
    major_code: str
    middle_name: str
    keyword: str
    source: str  # kipris, scholar, codil
    target_count: int
    existing_count: int = 0

    @property
    def needed(self) -> int:
        return max(0, self.target_count - self.existing_count)


# ──────────────────────────────────────────────
# Phase 정의
# ──────────────────────────────────────────────

PHASE_TARGETS = {
    1: {
        "description": "기본 커버리지 확보 — 모든 중분류에 최소 데이터 확보",
        "kipris_per_keyword": 20,
        "scholar_per_keyword": 10,
        "codil_per_category": 10,
        "max_keywords_per_middle": 2,  # 중분류당 최대 2개 키워드
        "kipris_budget": 400,   # 이번 Phase에서 KIPRIS 최대 사용량
    },
    2: {
        "description": "심화 축적 — 주요 중분류 키워드 확장",
        "kipris_per_keyword": 30,
        "scholar_per_keyword": 20,
        "codil_per_category": 20,
        "max_keywords_per_middle": 4,
        "kipris_budget": 600,
    },
    3: {
        "description": "전면 확장 — 전체 키워드 수집",
        "kipris_per_keyword": 50,
        "scholar_per_keyword": 30,
        "codil_per_category": 30,
        "max_keywords_per_middle": 8,  # 모든 키워드
        "kipris_budget": 1000,
    },
}


def count_existing(store: KBStore) -> dict[str, dict[str, int]]:
    """현재 저장된 데이터 건수를 소스×카테고리로 집계."""
    counts: dict[str, dict[str, int]] = {
        "patents": {},
        "scholar_papers": {},
        "codil": {},
    }

    dynamic_dir = store.dynamic_dir
    for source_key in counts:
        source_dir = dynamic_dir / source_key
        if not source_dir.exists():
            continue
        for cat_dir in source_dir.iterdir():
            if cat_dir.is_dir():
                total = 0
                for f in cat_dir.glob("*.json"):
                    with open(f, encoding="utf-8") as fh:
                        data = json.load(fh)
                    total += len(data) if isinstance(data, list) else 1
                counts[source_key][cat_dir.name] = total

    return counts


def get_existing_keywords(store: KBStore) -> dict[str, set[str]]:
    """소스별로 이미 수집된 키워드(파일명 기반)를 반환."""
    existing_kws: dict[str, set[str]] = {
        "patents": set(),
        "scholar_papers": set(),
        "codil": set(),
    }
    dynamic_dir = store.dynamic_dir
    for source_key in existing_kws:
        source_dir = dynamic_dir / source_key
        if not source_dir.exists():
            continue
        for cat_dir in source_dir.iterdir():
            if cat_dir.is_dir():
                for f in cat_dir.glob("*.json"):
                    # 파일명 = keyword.json
                    kw = f.stem.replace("_", " ")
                    existing_kws[source_key].add(f"{cat_dir.name}/{kw}")
    return existing_kws


def print_status(store: KBStore) -> None:
    """현재 KB 축적 현황을 출력."""
    counts = count_existing(store)

    print("\n" + "=" * 70)
    print("  KB 데이터 축적 현황")
    print("=" * 70)

    # 지정기술
    designated_path = store.dynamic_dir / "cnt_designated" / "designated_list.json"
    designated_count = 0
    if designated_path.exists():
        with open(designated_path, encoding="utf-8") as f:
            designated_count = len(json.load(f))
    print(f"\n  지정기술: {designated_count}건")

    for source_name, source_counts in counts.items():
        total = sum(source_counts.values())
        print(f"\n  {source_name}: {total}건")
        for cat, cnt in sorted(source_counts.items()):
            print(f"    {cat}: {cnt}건")

    grand_total = sum(sum(sc.values()) for sc in counts.values()) + designated_count
    print(f"\n  총합: {grand_total}건")

    # 중분류 커버리지 분석
    all_middles = set()
    for major_code, middles in KEYWORD_MATRIX.items():
        for middle_name in middles:
            all_middles.add(f"{major_code}/{middle_name}")

    covered_middles = set()
    for source_counts in counts.values():
        for cat in source_counts:
            covered_middles.add(cat)

    # 키워드 매트릭스 기준 커버 상태는 major_code 단위로만 체크
    print(f"\n  대분류 커버리지: {len(counts['patents'])}개 카테고리")
    print(f"  중분류 전체: {len(all_middles)}개")
    print("=" * 70)


def build_plan(
    store: KBStore,
    phase: int,
    source_filter: str | None = None,
) -> list[CollectionPlan]:
    """Phase별 수집 계획을 생성.

    키워드 단위로 중복 체크하여 이미 수집된 키워드는 건너뛴다.
    """
    config = PHASE_TARGETS[phase]
    existing_kws = get_existing_keywords(store)
    existing_counts = count_existing(store)
    plans: list[CollectionPlan] = []

    source_map = {"kipris": "patents", "scholar": "scholar_papers", "codil": "codil"}

    for major_code, middles in KEYWORD_MATRIX.items():
        for middle_name, keywords in middles.items():
            selected_keywords = keywords[:config["max_keywords_per_middle"]]

            for kw in selected_keywords:
                safe_kw = kw.replace(" ", "_").replace("/", "_")[:50]
                kw_key = f"{major_code}/{safe_kw.replace('_', ' ')}"

                # 특허
                if source_filter in (None, "kipris"):
                    already = kw_key in existing_kws["patents"]
                    plans.append(CollectionPlan(
                        major_code=major_code,
                        middle_name=middle_name,
                        keyword=kw,
                        source="kipris",
                        target_count=config["kipris_per_keyword"],
                        existing_count=config["kipris_per_keyword"] if already else 0,
                    ))

                # 논문
                if source_filter in (None, "scholar"):
                    already = kw_key in existing_kws["scholar_papers"]
                    plans.append(CollectionPlan(
                        major_code=major_code,
                        middle_name=middle_name,
                        keyword=kw,
                        source="scholar",
                        target_count=config["scholar_per_keyword"],
                        existing_count=config["scholar_per_keyword"] if already else 0,
                    ))

            # CODIL은 카테고리 단위로 수집
            if source_filter in (None, "codil"):
                existing_codil = existing_counts["codil"].get(major_code, 0)
                codil_per_middle = existing_codil // max(len(middles), 1)
                plans.append(CollectionPlan(
                    major_code=major_code,
                    middle_name=middle_name,
                    keyword=f"{middle_name} 건설기준",
                    source="codil",
                    target_count=config["codil_per_category"],
                    existing_count=codil_per_middle,
                ))

    # 실제 필요한 것만 필터
    plans = [p for p in plans if p.needed > 0]
    return plans


def execute_plan(
    plans: list[CollectionPlan],
    store: KBStore,
    dry_run: bool = False,
    kipris_budget: int = 1000,
) -> dict[str, int]:
    """수집 계획을 실행."""
    stats = {"kipris": 0, "scholar": 0, "codil": 0}
    kipris_used = 0

    kipris = None
    scholar = None
    codil = None

    for i, plan in enumerate(plans):
        if plan.needed <= 0:
            continue

        logger.info(
            "[%d/%d] %s | %s > %s | '%s' | 목표 %d건 (기존 %d건)",
            i + 1, len(plans), plan.source,
            plan.major_code, plan.middle_name,
            plan.keyword, plan.needed, plan.existing_count,
        )

        if dry_run:
            stats[plan.source] += plan.needed
            if plan.source == "kipris":
                kipris_used += plan.needed
            continue

        try:
            if plan.source == "kipris":
                if kipris_used >= kipris_budget:
                    logger.warning("KIPRIS 예산 소진 (%d건). 스킵.", kipris_budget)
                    continue
                if kipris is None:
                    kipris = KiprisClient()
                allowed = min(plan.needed, kipris_budget - kipris_used)
                records = kipris.search_construction_patents(
                    plan.keyword, max_results=allowed,
                )
                if records:
                    store.save_patents(records, plan.major_code, plan.keyword)
                    stats["kipris"] += len(records)
                    kipris_used += len(records)
                time.sleep(1)

            elif plan.source == "scholar":
                if scholar is None:
                    scholar = SemanticScholarClient()
                records = scholar.search_construction_papers(
                    plan.keyword, max_results=plan.needed,
                )
                if records:
                    store.save_scholar_papers(records, plan.major_code, plan.keyword)
                    stats["scholar"] += len(records)
                time.sleep(2)

            elif plan.source == "codil":
                if codil is None:
                    codil = CODILCrawler()
                records = codil.search_construction_standards(
                    plan.keyword, max_results=plan.needed,
                )
                if records:
                    store.save_codil_docs(records, plan.major_code, plan.keyword)
                    stats["codil"] += len(records)

        except Exception as e:
            logger.error("수집 실패 [%s/%s]: %s", plan.source, plan.keyword, e)
            continue

    return stats


def main():
    parser = argparse.ArgumentParser(description="KB 데이터 축적 스크립트")
    parser.add_argument("--phase", type=int, choices=[1, 2, 3], default=1,
                        help="수집 단계 (1=기본, 2=심화, 3=전면)")
    parser.add_argument("--dry-run", action="store_true",
                        help="실제 수집 없이 계획만 출력")
    parser.add_argument("--status", action="store_true",
                        help="현재 축적 현황 출력")
    parser.add_argument("--source", choices=["kipris", "scholar", "codil"],
                        help="특정 소스만 수집")
    args = parser.parse_args()

    store = KBStore()

    if args.status:
        print_status(store)
        return

    phase_config = PHASE_TARGETS[args.phase]
    print(f"\n Phase {args.phase}: {phase_config['description']}")
    print(f"  KIPRIS 예산: {phase_config['kipris_budget']}건")

    plans = build_plan(store, args.phase, args.source)

    # 수집 요약
    source_summary = {}
    for p in plans:
        source_summary.setdefault(p.source, 0)
        source_summary[p.source] += p.needed

    print(f"\n  수집 계획:")
    for src, cnt in source_summary.items():
        print(f"    {src}: {cnt}건")
    print(f"    합계: {sum(source_summary.values())}건")

    if args.dry_run:
        print("\n  [DRY RUN] 실제 수집을 수행하지 않습니다.")
        for p in plans[:20]:
            print(f"    {p.source} | {p.major_code}/{p.middle_name} | '{p.keyword}' | {p.needed}건")
        if len(plans) > 20:
            print(f"    ... 외 {len(plans) - 20}건")
        return

    print(f"\n  수집을 시작합니다... ({len(plans)}건 작업)")
    stats = execute_plan(
        plans, store,
        kipris_budget=phase_config["kipris_budget"],
    )

    print(f"\n  수집 완료:")
    for src, cnt in stats.items():
        if cnt > 0:
            print(f"    {src}: {cnt}건")
    print(f"    합계: {sum(stats.values())}건")

    # 최종 현황
    print_status(store)


if __name__ == "__main__":
    main()
