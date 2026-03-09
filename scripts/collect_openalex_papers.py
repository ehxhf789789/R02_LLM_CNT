"""OpenAlex API를 활용한 건설 분야 논문 체계적 수집.

평가차원(6) × 분야(3) 매트릭스 기반으로 체계적 논문 수집.
무료, 키 불필요, 즉시 실행 가능.

사용법:
  py scripts/collect_openalex_papers.py                    # 전체 수집
  py scripts/collect_openalex_papers.py --category CIV     # 토목만
  py scripts/collect_openalex_papers.py --dimension safety  # 안전성만
  py scripts/collect_openalex_papers.py --oa-only          # OA 논문만
  py scripts/collect_openalex_papers.py --status           # 현황 확인
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.dynamic_kb.openalex_client import (
    EVALUATION_DIMENSION_KEYWORDS,
    OpenAlexClient,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(open(sys.stdout.fileno(), mode='w', encoding='utf-8', closefd=False))],
)
logger = logging.getLogger(__name__)

OUTPUT_BASE = Path("data/dynamic/openalex_papers")

DIMENSIONS = [
    "differentiation",
    "originality",
    "quality_improvement",
    "development_maturity",
    "safety",
    "eco_friendliness",
]

DIMENSION_LABELS = {
    "differentiation": "차별성",
    "originality": "독창성",
    "quality_improvement": "품질향상",
    "development_maturity": "개발정도",
    "safety": "안전성",
    "eco_friendliness": "친환경성",
}

CATEGORIES = ["CIV", "ARC", "MEC"]


def collect_by_dimension(
    client: OpenAlexClient,
    dimension: str,
    category: str,
    max_per_keyword: int = 30,
    from_year: int = 2018,
) -> int:
    """특정 차원/분야 조합의 논문 수집."""
    out_dir = OUTPUT_BASE / category / dimension
    out_dir.mkdir(parents=True, exist_ok=True)

    # 이미 수집된 ID 로드 (중복 방지)
    existing_ids: set[str] = set()
    for f in out_dir.glob("*.json"):
        try:
            with open(f, encoding="utf-8") as fp:
                records = json.load(fp)
            for r in records:
                oid = r.get("openalex_id", "")
                if oid:
                    existing_ids.add(oid)
        except Exception:
            pass

    keywords = EVALUATION_DIMENSION_KEYWORDS.get(dimension, {}).get(category, [])
    total_added = 0

    for kw in keywords:
        safe_kw = kw.replace(" ", "_")[:50]
        out_path = out_dir / f"{safe_kw}.json"

        # 이미 수집된 키워드 스킵
        if out_path.exists():
            logger.info("스킵 (이미 수집): [%s/%s] %s", dimension, category, kw)
            continue

        logger.info("검색: [%s/%s] %s", dimension, category, kw)

        records = client.search_construction_papers(
            query=kw,
            max_results=max_per_keyword,
            from_year=from_year,
        )

        # 초록 있는 논문만 + 중복 제거
        new_records = []
        for r in records:
            if not r.abstract or len(r.abstract) < 30:
                continue
            if r.openalex_id in existing_ids:
                continue
            existing_ids.add(r.openalex_id)
            r.eval_dimension = dimension
            rec_dict = asdict(r)
            rec_dict.pop("raw", None)
            new_records.append(rec_dict)

        if new_records:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(new_records, f, ensure_ascii=False, indent=2)
            logger.info("  → %d건 저장 (초록 보유)", len(new_records))
            total_added += len(new_records)
        else:
            logger.info("  → 새 논문 없음")

    return total_added


def collect_all(
    categories: list[str] | None = None,
    dimensions: list[str] | None = None,
    max_per_keyword: int = 30,
    from_year: int = 2018,
) -> dict:
    """전체 매트릭스 수집."""
    client = OpenAlexClient()
    cats = categories or CATEGORIES
    dims = dimensions or DIMENSIONS

    stats: dict[str, dict[str, int]] = {}

    for cat in cats:
        stats[cat] = {}
        for dim in dims:
            added = collect_by_dimension(
                client, dim, cat,
                max_per_keyword=max_per_keyword,
                from_year=from_year,
            )
            stats[cat][dim] = added
            logger.info(
                "[%s/%s] %s: %d건 추가",
                cat, DIMENSION_LABELS.get(dim, dim), dim, added,
            )

    # 요약
    logger.info("\n=== 수집 결과 요약 ===")
    grand_total = 0
    for cat in cats:
        cat_total = sum(stats[cat].values())
        grand_total += cat_total
        logger.info(
            "%s: %d건 (%s)",
            cat, cat_total,
            ", ".join(f"{DIMENSION_LABELS.get(d, d)}:{stats[cat].get(d, 0)}" for d in dims),
        )
    logger.info("총합: %d건", grand_total)

    return stats


def show_status():
    """수집 현황 표시."""
    print("\n=== OpenAlex 논문 수집 현황 ===\n")

    grand_total = 0
    grand_with_abs = 0
    grand_with_oa = 0

    for cat in CATEGORIES:
        cat_dir = OUTPUT_BASE / cat
        if not cat_dir.exists():
            print(f"{cat}: 데이터 없음")
            continue

        cat_total = 0
        cat_with_abs = 0
        cat_with_oa = 0
        dim_stats: dict[str, int] = {}

        for dim in DIMENSIONS:
            dim_dir = cat_dir / dim
            if not dim_dir.exists():
                dim_stats[dim] = 0
                continue

            count = 0
            for f in dim_dir.glob("*.json"):
                try:
                    with open(f, encoding="utf-8") as fp:
                        records = json.load(fp)
                    for r in records:
                        count += 1
                        cat_total += 1
                        if r.get("abstract") and len(r.get("abstract", "")) > 30:
                            cat_with_abs += 1
                        if r.get("oa_url"):
                            cat_with_oa += 1
                except Exception:
                    pass
            dim_stats[dim] = count

        abs_pct = cat_with_abs / max(cat_total, 1) * 100
        oa_pct = cat_with_oa / max(cat_total, 1) * 100
        print(f"{cat}: {cat_total}건 (초록 {abs_pct:.0f}%, OA {oa_pct:.0f}%)")
        for dim in DIMENSIONS:
            label = DIMENSION_LABELS.get(dim, dim)
            print(f"  {label}: {dim_stats.get(dim, 0)}건")

        grand_total += cat_total
        grand_with_abs += cat_with_abs
        grand_with_oa += cat_with_oa

    print(f"\n총합: {grand_total}건 (초록 {grand_with_abs}건, OA PDF {grand_with_oa}건)")


def main():
    parser = argparse.ArgumentParser(description="OpenAlex 건설 분야 논문 수집")
    parser.add_argument("--category", type=str, help="카테고리 (CIV, ARC, MEC)")
    parser.add_argument("--dimension", type=str, help="평가 차원")
    parser.add_argument("--max-per-keyword", type=int, default=30, help="키워드당 최대")
    parser.add_argument("--from-year", type=int, default=2018, help="시작 연도")
    parser.add_argument("--oa-only", action="store_true", help="OA 논문만")
    parser.add_argument("--status", action="store_true", help="현황 확인")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    categories = [args.category] if args.category else None
    dimensions = [args.dimension] if args.dimension else None

    collect_all(
        categories=categories,
        dimensions=dimensions,
        max_per_keyword=args.max_per_keyword,
        from_year=args.from_year,
    )


if __name__ == "__main__":
    main()
