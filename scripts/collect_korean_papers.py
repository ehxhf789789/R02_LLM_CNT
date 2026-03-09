"""국내(한국어) 건설 논문 수집 (OpenAlex 한국 학술지 기반).

KCI/ScienceON API가 제한적이므로, OpenAlex에 인덱싱된 한국 건설 학술지를
소스로 활용하여 국내 논문을 수집한다.

수집 전략:
  1) OpenAlex Sources API로 한국 건설 관련 학술지 ID 탐색
  2) 해당 학술지의 논문을 필터링하여 초록 보유 논문 수집
  3) 한국어 키워드로 OpenAlex Works 검색 (보충)

사용법:
  py scripts/collect_korean_papers.py
  py scripts/collect_korean_papers.py --max 500
  py scripts/collect_korean_papers.py --status
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(open(sys.stdout.fileno(), mode='w', encoding='utf-8', closefd=False))],
)
logger = logging.getLogger(__name__)

OPENALEX_BASE = "https://api.openalex.org"

# 한국 건설 관련 학술지 (OpenAlex source ID)
# OpenAlex Sources API 검색으로 확인된 학술지 목록
KOREAN_JOURNALS = {
    "CIV": [
        # 토목 분야
        ("S4306495324", "대한토목학회 학술대회"),
        ("S4306495378", "대한토목학회 학술발표회 논문집"),
        ("S109054653", "KSCE Journal of Civil Engineering"),
        ("S4306517851", "KSCE Journal of Civil and Environmental Engineering Research"),
        ("S2913678714", "Korean Journal of Construction Engineering and Management"),
        ("S2911319145", "Journal of Korean Society of Steel Construction"),
        ("S4210232354", "Journal of the Korean Recycled Construction Resources Institute"),
    ],
    "ARC": [
        # 건축 분야
        ("S4306496179", "한국건축시공학회 논문집"),
        ("S4306496175", "한국건축시공학회 학술.기술논문발표회 논문집"),
        ("S4210227761", "Journal of the Korea Institute of Building Construction"),
    ],
    "MEC": [
        # 기계설비/건설관리 분야
        ("S2913678714", "Korean Journal of Construction Engineering and Management"),
        ("S2911319145", "Journal of Korean Society of Steel Construction"),
    ],
}

# 한국어 건설 키워드 (OpenAlex 검색용)
KOREAN_KEYWORDS = {
    "CIV": [
        "교량 보수보강", "터널 시공 안전", "도로 포장 내구성",
        "말뚝 기초 시공", "내진 보강 공법", "하천 제방",
        "프리캐스트 콘크리트", "BIM 토목", "스마트 건설",
        "디지털 트윈 인프라", "드론 측량", "건설 자동화",
    ],
    "ARC": [
        "건축물 방수", "외단열 시스템", "건축 내진보강",
        "모듈러 건축", "제로에너지 건축", "건축 BIM",
        "고강도 콘크리트", "커튼월 시공", "건축 안전",
        "그린리모델링", "패시브하우스", "건축 로봇",
    ],
    "MEC": [
        "건설기계 자동화", "건설 안전 관리", "건설 환경",
        "소음 진동 제어", "건설 폐기물 재활용", "스마트 건설 관리",
        "건설 IoT 모니터링", "건설 빅데이터", "건설 AI",
    ],
}

# 영문 키워드 (한국 학술지 내 영문 논문 탐색)
ENGLISH_KEYWORDS_FOR_KOREAN_JOURNALS = {
    "CIV": [
        "bridge construction Korea", "tunnel construction method",
        "foundation pile design", "seismic retrofitting",
        "road pavement performance", "precast concrete bridge",
        "smart infrastructure monitoring", "construction management Korea",
    ],
    "ARC": [
        "building waterproofing system", "thermal insulation building",
        "seismic strengthening building", "modular construction Korea",
        "zero energy building Korea", "high performance concrete",
    ],
    "MEC": [
        "construction equipment automation", "construction safety management",
        "construction waste recycling", "noise control construction",
        "smart construction management Korea",
    ],
}

OUTPUT_DIR = PROJECT_ROOT / "data" / "dynamic" / "korean_papers"


def fetch_journal_papers(
    session: requests.Session,
    source_id: str,
    journal_name: str,
    category: str,
    max_papers: int = 100,
    from_year: int = 2015,
) -> list[dict]:
    """OpenAlex에서 특정 학술지의 논문을 수집."""
    records = []
    page = 1
    per_page = 50

    while len(records) < max_papers:
        params = {
            "filter": f"primary_location.source.id:{source_id},from_publication_date:{from_year}-01-01,has_abstract:true",
            "per_page": per_page,
            "page": page,
            "sort": "publication_date:desc",
        }

        try:
            resp = session.get(f"{OPENALEX_BASE}/works", params=params, timeout=30)
            if resp.status_code != 200:
                logger.warning("HTTP %d for %s", resp.status_code, journal_name)
                break
            data = resp.json()
        except Exception as e:
            logger.error("요청 실패 %s: %s", journal_name, e)
            break

        results = data.get("results", [])
        if not results:
            break

        for work in results:
            if len(records) >= max_papers:
                break

            # 초록 재구성 (inverted index → 텍스트)
            abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))
            if not abstract or len(abstract) < 30:
                continue

            title = work.get("title", "")
            year = work.get("publication_year", "")
            doi = work.get("doi", "")
            oa_id = work.get("id", "")

            # 저자 추출
            authors = ", ".join(
                a.get("author", {}).get("display_name", "")
                for a in work.get("authorships", [])[:5]
            )

            records.append({
                "title": title,
                "abstract": abstract,
                "authors": authors,
                "publish_year": str(year),
                "doi": doi.replace("https://doi.org/", "") if doi else "",
                "openalex_id": oa_id,
                "journal": journal_name,
                "source": "openalex_korean",
                "category": category,
                "language": work.get("language", ""),
            })

        page += 1
        time.sleep(0.3)

        # 더 이상 결과 없으면 종료
        total_count = data.get("meta", {}).get("count", 0)
        if page * per_page > total_count:
            break

    return records


def search_korean_keywords(
    session: requests.Session,
    category: str,
    max_papers: int = 100,
    from_year: int = 2015,
) -> list[dict]:
    """한국어/영문 키워드로 OpenAlex 검색."""
    records = []
    existing_ids = set()

    all_keywords = (
        KOREAN_KEYWORDS.get(category, []) +
        ENGLISH_KEYWORDS_FOR_KOREAN_JOURNALS.get(category, [])
    )

    for kw in all_keywords:
        if len(records) >= max_papers:
            break

        params = {
            "search": kw,
            "filter": f"from_publication_date:{from_year}-01-01,has_abstract:true",
            "per_page": 30,
            "sort": "relevance_score:desc",
        }

        try:
            resp = session.get(f"{OPENALEX_BASE}/works", params=params, timeout=30)
            if resp.status_code != 200:
                continue
            data = resp.json()
        except Exception:
            continue

        new_count = 0
        for work in data.get("results", []):
            oa_id = work.get("id", "")
            if oa_id in existing_ids:
                continue

            abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))
            if not abstract or len(abstract) < 30:
                continue

            # 한국 관련 논문인지 확인 (저자 기관, 학술지명 등)
            is_korean = _is_korean_related(work)
            if not is_korean:
                continue

            existing_ids.add(oa_id)
            title = work.get("title", "")
            year = work.get("publication_year", "")
            doi = work.get("doi", "")

            authors = ", ".join(
                a.get("author", {}).get("display_name", "")
                for a in work.get("authorships", [])[:5]
            )

            journal = ""
            loc = work.get("primary_location", {})
            if loc and loc.get("source"):
                journal = loc["source"].get("display_name", "")

            records.append({
                "title": title,
                "abstract": abstract,
                "authors": authors,
                "publish_year": str(year),
                "doi": doi.replace("https://doi.org/", "") if doi else "",
                "openalex_id": oa_id,
                "journal": journal,
                "source": "openalex_korean_search",
                "category": category,
                "language": work.get("language", ""),
                "search_keyword": kw,
            })
            new_count += 1

        if new_count > 0:
            logger.info("  %s: +%d건", kw[:40], new_count)

        time.sleep(0.3)

    return records


def _reconstruct_abstract(inverted_index: dict | None) -> str:
    """OpenAlex inverted index를 텍스트로 재구성."""
    if not inverted_index:
        return ""

    # {word: [position1, position2, ...]} → 위치순으로 정렬
    word_positions = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions.append((pos, word))

    word_positions.sort(key=lambda x: x[0])
    return " ".join(w for _, w in word_positions)


def _is_korean_related(work: dict) -> bool:
    """논문이 한국 관련인지 확인."""
    # 1. 언어가 ko인 경우
    if work.get("language") == "ko":
        return True

    # 2. 학술지가 한국 학술지인 경우
    loc = work.get("primary_location", {})
    if loc and loc.get("source"):
        source = loc["source"]
        country = source.get("country_code", "")
        if country == "KR":
            return True
        display_name = source.get("display_name", "").lower()
        korean_indicators = ["korea", "korean", "한국", "대한", "ksce", "kibc"]
        if any(k in display_name for k in korean_indicators):
            return True

    # 3. 저자 소속이 한국인 경우
    for authorship in work.get("authorships", [])[:3]:
        for inst in authorship.get("institutions", []):
            country = inst.get("country_code", "")
            if country == "KR":
                return True

    return False


def collect_korean_papers(
    category: str | None = None,
    max_per_category: int = 300,
    from_year: int = 2015,
) -> dict:
    """한국 건설 논문 수집."""
    categories = [category] if category else ["CIV", "ARC", "MEC"]
    stats = {}

    session = requests.Session()
    session.headers.update({
        "User-Agent": "R02_LLM_CNT/1.0 (mailto:research@example.com)",
    })

    # 기존 수집 ID (중복 방지)
    existing_ids = set()
    for cat in categories:
        cat_dir = OUTPUT_DIR / cat
        if cat_dir.exists():
            for f in cat_dir.glob("*.json"):
                data = json.load(open(f, encoding="utf-8"))
                for r in data:
                    oid = r.get("openalex_id", "")
                    if oid:
                        existing_ids.add(oid)

    # 기존 OpenAlex 논문 ID도 (전체 중복 방지)
    oa_dir = PROJECT_ROOT / "data" / "dynamic" / "openalex_papers"
    if oa_dir.exists():
        for f in oa_dir.rglob("*.json"):
            data = json.load(open(f, encoding="utf-8"))
            for r in data:
                oid = r.get("openalex_id", "")
                if oid:
                    existing_ids.add(oid)

    logger.info("기존 논문 %d건 중복 제외", len(existing_ids))

    for cat in categories:
        logger.info("=== %s 한국 논문 수집 ===", cat)
        all_records = []

        # 방법 1: 한국 학술지별 수집
        journals = KOREAN_JOURNALS.get(cat, [])
        for source_id, journal_name in journals:
            if len(all_records) >= max_per_category:
                break

            remaining = max_per_category - len(all_records)
            logger.info("  학술지: %s (최대 %d건)", journal_name, min(remaining, 100))

            records = fetch_journal_papers(
                session, source_id, journal_name, cat,
                max_papers=min(remaining, 100),
                from_year=from_year,
            )

            # 중복 제거
            new_records = []
            for r in records:
                if r["openalex_id"] not in existing_ids:
                    existing_ids.add(r["openalex_id"])
                    new_records.append(r)

            all_records.extend(new_records)
            logger.info("    → %d건 수집 (중복 %d건 제외)",
                       len(new_records), len(records) - len(new_records))

        # 방법 2: 키워드 검색 보충
        if len(all_records) < max_per_category:
            remaining = max_per_category - len(all_records)
            logger.info("  키워드 검색 보충 (최대 %d건)", remaining)

            kw_records = search_korean_keywords(
                session, cat,
                max_papers=remaining,
                from_year=from_year,
            )

            new_count = 0
            for r in kw_records:
                if r["openalex_id"] not in existing_ids:
                    existing_ids.add(r["openalex_id"])
                    all_records.append(r)
                    new_count += 1

            logger.info("    → 키워드 검색 %d건 추가", new_count)

        # 저장
        if all_records:
            out_dir = OUTPUT_DIR / cat
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / "korean_papers.json"

            # 기존 파일과 병합
            existing = []
            if out_path.exists():
                existing = json.load(open(out_path, encoding="utf-8"))

            merged = existing + all_records
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)

            logger.info("%s: %d건 저장 (누적 %d건)", cat, len(all_records), len(merged))

        stats[cat] = len(all_records)

    logger.info("한국 논문 수집 완료: %s", stats)
    return stats


def show_status():
    """한국 논문 수집 현황."""
    print("\n=== 한국 논문 수집 현황 ===\n")

    total_all = 0
    for cat in ["CIV", "ARC", "MEC"]:
        cat_dir = OUTPUT_DIR / cat
        if not cat_dir.exists():
            print(f"{cat}: 데이터 없음")
            continue

        total = 0
        with_abs = 0
        recent = 0
        journals = {}

        for f in cat_dir.glob("*.json"):
            data = json.load(open(f, encoding="utf-8"))
            for r in data:
                total += 1
                if r.get("abstract") and len(r["abstract"]) >= 30:
                    with_abs += 1
                try:
                    if int(r.get("publish_year", 0)) >= 2021:
                        recent += 1
                except (ValueError, TypeError):
                    pass
                j = r.get("journal", "기타")
                journals[j] = journals.get(j, 0) + 1

        total_all += total
        pct_abs = with_abs / max(total, 1) * 100
        pct_recent = recent / max(total, 1) * 100
        print(f"{cat}: {total}건 (초록 {pct_abs:.1f}%, 2021+ {pct_recent:.1f}%)")
        for j, cnt in sorted(journals.items(), key=lambda x: -x[1])[:5]:
            print(f"  - {j}: {cnt}건")

    print(f"\n총 한국 논문: {total_all}건")


def main():
    parser = argparse.ArgumentParser(description="한국 건설 논문 수집 (OpenAlex)")
    parser.add_argument("--category", type=str, help="카테고리")
    parser.add_argument("--max", type=int, default=300, help="카테고리당 최대 건수")
    parser.add_argument("--from-year", type=int, default=2015, help="시작 연도")
    parser.add_argument("--status", action="store_true", help="현황")
    args = parser.parse_args()

    if args.status:
        show_status()
    else:
        collect_korean_papers(
            category=args.category,
            max_per_category=args.max,
            from_year=args.from_year,
        )


if __name__ == "__main__":
    main()
