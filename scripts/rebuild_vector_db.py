"""벡터DB 재구축 스크립트.

모든 KB 데이터 (특허, 논문, CODIL, 지정기술, enriched 지정기술)를
LanceDB에 재구축한다.

사용법:
  py scripts/rebuild_vector_db.py
  py scripts/rebuild_vector_db.py --dry-run  # 문서 수만 확인
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(open(sys.stdout.fileno(), mode='w', encoding='utf-8', closefd=False))],
)
logger = logging.getLogger(__name__)


def count_documents():
    """벡터화 대상 문서 수를 집계."""
    base_dir = settings.dynamic_kb_dir
    counts = {}

    # 특허 (기존 + 최근 추가 수집분)
    total = 0
    for patent_dir_name in ["patents", "patents_recent"]:
        patents_dir = base_dir / patent_dir_name
        if not patents_dir.exists():
            continue
        for cat_dir in patents_dir.iterdir():
            if cat_dir.is_dir():
                cat_count = 0
                for f in cat_dir.glob("*.json"):
                    with open(f, encoding="utf-8") as fp:
                        data = json.load(fp)
                    cat_count += len(data) if isinstance(data, list) else 1
                counts[f"{patent_dir_name}/{cat_dir.name}"] = cat_count
                total += cat_count
    counts["patents_total"] = total

    # 논문 (기존 + 새 소스)
    total = 0
    for dir_name in ["scholar_papers", "kci_papers", "papers", "openalex_papers", "crossref_papers", "korean_papers"]:
        d = base_dir / dir_name
        if d.exists():
            for cat_dir in d.iterdir():
                if cat_dir.is_dir():
                    cat_count = 0
                    for f in cat_dir.glob("*.json"):
                        with open(f, encoding="utf-8") as fp:
                            data = json.load(fp)
                        cat_count += len(data) if isinstance(data, list) else 1
                    counts[f"{dir_name}/{cat_dir.name}"] = cat_count
                    total += cat_count
                    # OpenAlex 차원별 하위 디렉토리
                    for sub_dir in cat_dir.iterdir():
                        if sub_dir.is_dir():
                            sub_count = 0
                            for f in sub_dir.glob("*.json"):
                                with open(f, encoding="utf-8") as fp:
                                    data = json.load(fp)
                                sub_count += len(data) if isinstance(data, list) else 1
                            if sub_count > 0:
                                counts[f"{dir_name}/{cat_dir.name}/{sub_dir.name}"] = sub_count
                                total += sub_count
    counts["papers_total"] = total

    # CODIL
    total = 0
    codil_dir = base_dir / "codil"
    if codil_dir.exists():
        for cat_dir in codil_dir.iterdir():
            if cat_dir.is_dir():
                cat_count = 0
                for f in cat_dir.glob("*.json"):
                    with open(f, encoding="utf-8") as fp:
                        data = json.load(fp)
                    cat_count += len(data) if isinstance(data, list) else 1
                counts[f"codil/{cat_dir.name}"] = cat_count
                total += cat_count
    counts["codil_total"] = total

    # KCSC 건설기준
    total = 0
    kcsc_dir = base_dir / "kcsc_standards"
    if kcsc_dir.exists():
        for cat_dir in kcsc_dir.iterdir():
            if cat_dir.is_dir():
                cat_count = 0
                for f in cat_dir.glob("*.json"):
                    with open(f, encoding="utf-8") as fp:
                        data = json.load(fp)
                    cat_count += len(data) if isinstance(data, list) else 1
                counts[f"kcsc/{cat_dir.name}"] = cat_count
                total += cat_count
    counts["kcsc_total"] = total

    # 지정기술
    designated_path = base_dir / "cnt_designated" / "designated_list.json"
    if designated_path.exists():
        with open(designated_path, encoding="utf-8") as f:
            data = json.load(f)
        counts["designated_techs"] = len(data)

    # enriched 지정기술
    enriched_dir = base_dir / "cnt_designated" / "enriched"
    if enriched_dir.exists():
        total_chunks = 0
        for f in enriched_dir.glob("designated_*.json"):
            with open(f, encoding="utf-8") as fp:
                d = json.load(fp)
            texts = d.get("extracted_texts", {})
            for v in texts.values():
                if len(v) >= 100:
                    # Count chunks (2000 chars each, max 8000 total)
                    chunks = min(len(v), 8000) // 2000 + 1
                    total_chunks += chunks
        counts["enriched_tech_chunks"] = total_chunks

    return counts


def main():
    parser = argparse.ArgumentParser(description="벡터DB 재구축")
    parser.add_argument("--dry-run", action="store_true", help="문서 수만 확인")
    args = parser.parse_args()

    counts = count_documents()

    print("벡터DB 재구축 대상 문서 수:")
    print("=" * 60)
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v:,}")

    grand_total = (
        counts.get("patents_total", 0) +
        counts.get("papers_total", 0) +
        counts.get("codil_total", 0) +
        counts.get("kcsc_total", 0) +
        counts.get("designated_techs", 0) +
        counts.get("enriched_tech_chunks", 0)
    )
    print(f"\n  총 문서 수: {grand_total:,}")
    print(f"  예상 임베딩 배치: {(grand_total + 49) // 50}배치 ({grand_total * 0.5 / 60:.0f}분 예상)")

    if args.dry_run:
        return

    print("\n벡터DB 구축 시작...")
    from src.vectordb.kb_vectorizer import KBVectorizer

    vectorizer = KBVectorizer()
    count = vectorizer.build_from_store()
    print(f"\n벡터DB 구축 완료: {count:,}건")


if __name__ == "__main__":
    main()
