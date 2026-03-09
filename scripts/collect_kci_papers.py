"""KCI (한국학술지인용색인) 건설 분야 논문 수집.

KCI Open API를 활용하여 건설 분야 국문 논문을 체계적으로 수집한다.
분야(3) × 키워드 매트릭스 기반 수집.

사용법:
  py scripts/collect_kci_papers.py                    # 전체 수집
  py scripts/collect_kci_papers.py --category CIV     # 토목만
  py scripts/collect_kci_papers.py --status           # 현황 확인
  py scripts/collect_kci_papers.py --from-year 2020   # 2020년 이후만
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from xml.etree import ElementTree

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(open(sys.stdout.fileno(), mode='w', encoding='utf-8', closefd=False))],
)
logger = logging.getLogger(__name__)

KCI_API_URL = "https://open.kci.go.kr/po/openapi/openApiSearch.kci"
OUTPUT_BASE = PROJECT_ROOT / "data" / "dynamic" / "kci_papers"

CATEGORIES = ["CIV", "ARC", "MEC"]

# 건설 분야 KCI 검색 키워드 매트릭스
# 건설신기술 평가에 필요한 신규성/진보성 판단 관련 국내 연구 동향 포괄
KCI_KEYWORDS = {
    "CIV": [
        # 토목 핵심 키워드
        "교량 보수보강", "교량 내구성", "교량 안전진단",
        "터널 시공", "터널 굴착 공법", "NATM 터널",
        "도로 포장", "아스팔트 포장", "콘크리트 포장",
        "말뚝 기초", "지반개량", "흙막이 공법",
        "내진 보강", "내진 설계", "지진 대응",
        "하천 제방", "수자원 관리", "홍수 방재",
        "프리캐스트 콘크리트", "PSC 거더", "프리스트레스",
        "콘크리트 균열 보수", "콘크리트 내구성", "고성능 콘크리트",
        "건설 자동화", "스마트 건설", "BIM 토목",
        "디지털 트윈 인프라", "드론 측량", "건설 IoT",
        "비파괴 검사", "구조물 모니터링", "안전 점검",
        "친환경 건설", "탄소 저감", "건설 폐기물 재활용",
    ],
    "ARC": [
        # 건축 핵심 키워드
        "건축물 방수", "방수 공법", "옥상 방수",
        "외단열 시스템", "단열 공법", "건축 단열재",
        "건축 내진보강", "내진 구조", "면진 장치",
        "모듈러 건축", "조립식 건축", "OSC 건축",
        "제로에너지 건축", "패시브하우스", "건축 에너지",
        "건축 BIM", "건축 설계 자동화", "건축 시공관리",
        "고강도 콘크리트", "고성능 콘크리트", "UHPC",
        "커튼월 시스템", "외벽 마감", "건축 파사드",
        "건축 안전", "화재 안전", "피난 설계",
        "그린리모델링", "건축 리모델링", "건축물 유지관리",
        "건축 로봇", "3D 프린팅 건축", "건축 자동화",
        "건축 소음", "바닥충격음", "차음 성능",
    ],
    "MEC": [
        # 기계설비/건설관리 핵심 키워드
        "건설기계 자동화", "건설장비", "굴삭기 자동화",
        "건설 안전관리", "건설현장 안전", "중대재해",
        "건설 환경관리", "건설 소음 진동", "미세먼지 저감",
        "건설 폐기물", "건축폐기물 재활용", "순환골재",
        "스마트 건설관리", "건설 품질관리", "건설 공정관리",
        "건설 IoT", "건설 빅데이터", "건설 AI",
        "지열 시스템", "히트펌프", "건물 에너지 설비",
        "상하수도", "배관 시공", "설비 시공",
    ],
}

# 영문 키워드 (KCI에 영문 제목/초록이 있는 논문 탐색)
KCI_ENGLISH_KEYWORDS = {
    "CIV": [
        "bridge reinforcement", "tunnel construction",
        "concrete durability", "seismic retrofitting",
        "smart construction", "digital twin infrastructure",
        "non-destructive testing", "structural health monitoring",
    ],
    "ARC": [
        "building waterproofing", "thermal insulation",
        "modular construction", "zero energy building",
        "high performance concrete", "curtain wall",
        "fire safety building", "green remodeling",
    ],
    "MEC": [
        "construction safety management", "construction automation",
        "construction waste recycling", "smart construction management",
        "geothermal heat pump", "construction IoT",
    ],
}


def parse_kci_xml(xml_text: str) -> tuple[int, list[dict]]:
    """KCI XML 응답을 파싱하여 (total, records) 반환."""
    records = []

    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        logger.warning("XML 파싱 실패")
        return 0, records

    total = 0
    total_el = root.find(".//total")
    if total_el is not None and total_el.text:
        total = int(total_el.text)

    for record_el in root.iter("record"):
        # journalInfo
        journal_info = record_el.find("journalInfo")
        journal_name = ""
        publisher = ""
        pub_year = ""
        pub_mon = ""
        volume = ""
        issue = ""
        if journal_info is not None:
            journal_name = journal_info.findtext("journal-name", "")
            publisher = journal_info.findtext("publisher-name", "")
            pub_year = journal_info.findtext("pub-year", "")
            pub_mon = journal_info.findtext("pub-mon", "")
            volume = journal_info.findtext("volume", "")
            issue = journal_info.findtext("issue", "")

        # articleInfo
        article_info = record_el.find("articleInfo")
        if article_info is None:
            continue

        article_id = article_info.get("article-id", "")
        category = article_info.findtext("article-categories", "")

        # 제목 (한국어 + 영문)
        title_ko = ""
        title_en = ""
        title_group = article_info.find("title-group")
        if title_group is not None:
            for title_el in title_group.findall("article-title"):
                lang = title_el.get("lang", "")
                text = title_el.text or ""
                if lang == "original":
                    title_ko = text
                elif lang in ("english", "foreign"):
                    title_en = text

        # 저자
        authors = []
        author_group = article_info.find("author-group")
        if author_group is not None:
            for author_el in author_group.findall("author"):
                name = author_el.text or ""
                en_name = author_el.get("english", "")
                if name.strip():
                    authors.append(name.strip())
                elif en_name.strip():
                    authors.append(en_name.strip())

        # 초록 (한국어 + 영문)
        abstract_ko = ""
        abstract_en = ""
        abstract_group = article_info.find("abstract-group")
        if abstract_group is not None:
            for abs_el in abstract_group.findall("abstract"):
                lang = abs_el.get("lang", "")
                text = abs_el.text or ""
                if lang == "original":
                    abstract_ko = text
                elif lang == "english":
                    abstract_en = text

        # 기타 필드
        fpage = article_info.findtext("fpage", "")
        lpage = article_info.findtext("lpage", "")
        doi = article_info.findtext("doi", "")
        url = article_info.findtext("url", "")
        citation_count_el = article_info.find("citation-count")
        citation_count = citation_count_el.text if citation_count_el is not None else "0"

        # 초록: 한국어 우선, 없으면 영문
        abstract = abstract_ko if abstract_ko else abstract_en
        title = title_ko if title_ko else title_en

        record = {
            "article_id": article_id,
            "title": title,
            "title_ko": title_ko,
            "title_en": title_en,
            "authors": ", ".join(authors),
            "journal": journal_name,
            "publisher": publisher,
            "publish_year": pub_year,
            "publish_month": pub_mon,
            "volume": volume,
            "issue": issue,
            "abstract": abstract,
            "abstract_ko": abstract_ko,
            "abstract_en": abstract_en,
            "fpage": fpage,
            "lpage": lpage,
            "doi": doi,
            "url": url,
            "citation_count": citation_count,
            "article_category": category,
            "source": "kci",
        }
        records.append(record)

    return total, records


def search_kci(
    api_key: str,
    keyword: str,
    page: int = 1,
    display_count: int = 100,
    date_from: str = "",
    date_to: str = "",
    search_field: str = "title",
) -> tuple[int, list[dict]]:
    """KCI API 검색 호출."""
    params: dict = {
        "apiCode": "articleSearch",
        "key": api_key,
        "displayCount": min(display_count, 100),
        "page": page,
    }

    # 검색 필드 지정
    if search_field == "keyword":
        params["keyword"] = keyword
    else:
        params["title"] = keyword

    if date_from:
        params["dateFrom"] = date_from
    if date_to:
        params["dateTo"] = date_to

    try:
        resp = requests.get(KCI_API_URL, params=params, timeout=30)
        resp.encoding = "utf-8"
        if resp.status_code != 200:
            logger.warning("KCI HTTP %d for '%s'", resp.status_code, keyword)
            return 0, []
        return parse_kci_xml(resp.text)
    except requests.RequestException as e:
        logger.error("KCI 요청 실패 '%s': %s", keyword, e)
        return 0, []


def collect_for_category(
    api_key: str,
    category: str,
    max_per_keyword: int = 100,
    from_year: int = 2015,
) -> int:
    """단일 카테고리의 KCI 논문 수집."""
    out_dir = OUTPUT_BASE / category
    out_dir.mkdir(parents=True, exist_ok=True)

    # 기존 수집된 article_id (중복 방지)
    existing_ids: set[str] = set()
    for f in out_dir.glob("*.json"):
        try:
            with open(f, encoding="utf-8") as fp:
                records = json.load(fp)
            for r in records:
                aid = r.get("article_id", "")
                if aid:
                    existing_ids.add(aid)
        except Exception:
            pass

    logger.info("[%s] 기존 %d건 로드 (중복 방지)", category, len(existing_ids))

    date_from = f"{from_year}01"  # YYYYMM 형식

    # 한국어 + 영문 키워드 합치기
    all_keywords = KCI_KEYWORDS.get(category, []) + KCI_ENGLISH_KEYWORDS.get(category, [])
    total_added = 0

    for kw in all_keywords:
        safe_kw = kw.replace(" ", "_").replace("/", "_")[:50]
        out_path = out_dir / f"{safe_kw}.json"

        # 이미 수집된 키워드 스킵
        if out_path.exists():
            logger.info("  스킵 (이미 수집): [%s] %s", category, kw)
            continue

        logger.info("  검색: [%s] %s", category, kw)

        # 페이지네이션으로 최대 max_per_keyword건 수집
        new_records = []
        page = 1
        while len(new_records) < max_per_keyword:
            total, records = search_kci(
                api_key=api_key,
                keyword=kw,
                page=page,
                display_count=100,
                date_from=date_from,
            )

            if not records:
                break

            for r in records:
                aid = r.get("article_id", "")
                if not aid or aid in existing_ids:
                    continue
                # 초록 있는 논문만
                abstract = r.get("abstract", "")
                if not abstract or len(abstract) < 30:
                    continue
                existing_ids.add(aid)
                r["search_keyword"] = kw
                r["category"] = category
                new_records.append(r)

            page += 1
            time.sleep(0.5)

            # 전체 결과보다 많이 가져왔으면 종료
            if page * 100 > total:
                break

        if new_records:
            new_records = new_records[:max_per_keyword]
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(new_records, f, ensure_ascii=False, indent=2)
            logger.info("    → %d건 저장 (초록 보유, 총 %d건 검색)", len(new_records), total)
            total_added += len(new_records)
        else:
            logger.info("    → 새 논문 없음 (총 %d건)", 0)

        time.sleep(0.5)

    return total_added


def collect_all(
    categories: list[str] | None = None,
    max_per_keyword: int = 100,
    from_year: int = 2015,
) -> dict:
    """전체 카테고리 수집."""
    api_key = settings.kci_api_key
    if not api_key or api_key == "your_kci_api_key_here":
        logger.error("KCI API 키가 설정되지 않음. .env 파일에 KCI_API_KEY를 설정하세요.")
        return {}

    cats = categories or CATEGORIES
    stats: dict[str, int] = {}

    for cat in cats:
        logger.info("=== %s KCI 논문 수집 시작 ===", cat)
        added = collect_for_category(
            api_key=api_key,
            category=cat,
            max_per_keyword=max_per_keyword,
            from_year=from_year,
        )
        stats[cat] = added
        logger.info("[%s] %d건 추가", cat, added)

    # 요약
    logger.info("\n=== KCI 논문 수집 결과 ===")
    grand_total = sum(stats.values())
    for cat in cats:
        logger.info("  %s: %d건 추가", cat, stats.get(cat, 0))
    logger.info("  총합: %d건", grand_total)

    return stats


def show_status():
    """KCI 논문 수집 현황."""
    print("\n=== KCI 논문 수집 현황 ===\n")

    grand_total = 0
    grand_with_abs_ko = 0
    grand_with_abs_en = 0
    grand_recent = 0

    for cat in CATEGORIES:
        cat_dir = OUTPUT_BASE / cat
        if not cat_dir.exists():
            print(f"  {cat}: 데이터 없음")
            continue

        total = 0
        with_abs_ko = 0
        with_abs_en = 0
        recent = 0
        journals: dict[str, int] = {}

        for f in cat_dir.glob("*.json"):
            try:
                with open(f, encoding="utf-8") as fp:
                    records = json.load(fp)
                for r in records:
                    total += 1
                    if r.get("abstract_ko") and len(r["abstract_ko"]) >= 30:
                        with_abs_ko += 1
                    if r.get("abstract_en") and len(r["abstract_en"]) >= 30:
                        with_abs_en += 1
                    try:
                        if int(r.get("publish_year", 0)) >= 2021:
                            recent += 1
                    except (ValueError, TypeError):
                        pass
                    j = r.get("journal", "기타")
                    journals[j] = journals.get(j, 0) + 1
            except Exception:
                pass

        grand_total += total
        grand_with_abs_ko += with_abs_ko
        grand_with_abs_en += with_abs_en
        grand_recent += recent

        pct_ko = with_abs_ko / max(total, 1) * 100
        pct_en = with_abs_en / max(total, 1) * 100
        pct_recent = recent / max(total, 1) * 100
        print(f"  {cat}: {total}건 (한국어초록 {pct_ko:.0f}%, 영문초록 {pct_en:.0f}%, 2021+ {pct_recent:.0f}%)")

        # 상위 학술지
        for j, cnt in sorted(journals.items(), key=lambda x: -x[1])[:5]:
            print(f"    - {j}: {cnt}건")

    print(f"\n  총합: {grand_total}건")
    print(f"  한국어 초록: {grand_with_abs_ko}건, 영문 초록: {grand_with_abs_en}건")
    print(f"  최근 5년(2021+): {grand_recent}건")


def main():
    parser = argparse.ArgumentParser(description="KCI 건설 분야 논문 수집")
    parser.add_argument("--category", type=str, help="카테고리 (CIV, ARC, MEC)")
    parser.add_argument("--max-per-keyword", type=int, default=100, help="키워드당 최대 수집 건수")
    parser.add_argument("--from-year", type=int, default=2015, help="수집 시작 연도")
    parser.add_argument("--status", action="store_true", help="수집 현황 확인")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    categories = [args.category] if args.category else None
    collect_all(
        categories=categories,
        max_per_keyword=args.max_per_keyword,
        from_year=args.from_year,
    )


if __name__ == "__main__":
    main()
