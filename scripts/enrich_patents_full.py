"""Google Patents에서 특허 청구항/설명 수집 → KB 완전성 보강.

기존 enrich_patent_claims.py의 확장판.
등록번호 B1 실패 시 A1(공개) 시도, 출원번호 fallback,
설명(description) fallback, content_status 태깅을 지원한다.

사용법:
  py scripts/enrich_patents_full.py                  # 전체 특허 보강
  py scripts/enrich_patents_full.py --category MEC   # 특정 카테고리만
  py scripts/enrich_patents_full.py --max 100        # 최대 100건만
  py scripts/enrich_patents_full.py --status          # 보강 현황
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(open(sys.stdout.fileno(), mode='w', encoding='utf-8', closefd=False))],
)
logger = logging.getLogger(__name__)

GOOGLE_PATENTS_BASE = "https://patents.google.com/patent"
RATE_LIMIT_SECONDS = 2


# ---------------------------------------------------------------------------
# Google Patents ID 생성
# ---------------------------------------------------------------------------

def make_register_patent_ids(register_number: str) -> list[str]:
    """등록번호를 Google Patents ID 후보 목록으로 변환.

    KIPRIS 등록번호 "1026433360000" (13자리, 뒤 4자리 0) →
      1) KR102643336B1  (등록특허)
      2) KR102643336A1  (공개특허, fallback)

    반환: 시도할 patent_id 목록 (우선순위 순)
    """
    if not register_number:
        return []

    num = re.sub(r'[^0-9]', '', str(register_number))
    if not num or len(num) < 7:
        return []

    # 뒤에 0000이 붙어있으면 제거 (KIPRIS 형식)
    if len(num) == 13 and num.endswith("0000"):
        num = num[:-4]

    ids = []
    if num.startswith("10"):
        ids.append(f"KR{num}B1")
        ids.append(f"KR{num}A1")
    elif num.startswith("20"):
        ids.append(f"KR{num}U1")
        ids.append(f"KR{num}B1")
    else:
        ids.append(f"KR{num}B1")
        ids.append(f"KR{num}A1")

    return ids


def make_application_patent_ids(application_number: str) -> list[str]:
    """출원번호를 Google Patents ID 후보 목록으로 변환.

    KIPRIS 출원번호 "1020230174988" →
      1) KR1020230174988A   (전체 출원번호)
      2) KR20230174988A1    ("10" 접두사 제거)
      3) KR1020230174988A1  (A1 suffix)

    반환: 시도할 patent_id 목록 (우선순위 순)
    """
    if not application_number:
        return []

    num = re.sub(r'[^0-9]', '', str(application_number))
    if not num or len(num) < 7:
        return []

    ids = []

    # 전체 출원번호 + A suffix
    ids.append(f"KR{num}A")

    # "10" 접두사 제거 + A1
    if num.startswith("10") and len(num) >= 12:
        short_num = num[2:]
        ids.append(f"KR{short_num}A1")

    # 전체 출원번호 + A1 suffix
    ids.append(f"KR{num}A1")

    return ids


def make_open_patent_ids(open_number: str) -> list[str]:
    """공개번호를 Google Patents ID 후보 목록으로 변환.

    KIPRIS 공개번호 "1020140034276" →
      1) KR1020140034276A   (전체 공개번호 + A)
      2) KR20140034276A1    ("10" 접두사 제거 + A1)

    반환: 시도할 patent_id 목록 (우선순위 순)
    """
    if not open_number:
        return []

    num = re.sub(r'[^0-9]', '', str(open_number))
    if not num or len(num) < 7:
        return []

    ids = []
    ids.append(f"KR{num}A")

    if num.startswith("10") and len(num) >= 12:
        short_num = num[2:]
        ids.append(f"KR{short_num}A1")

    ids.append(f"KR{num}A1")
    return ids


# ---------------------------------------------------------------------------
# Google Patents 크롤링
# ---------------------------------------------------------------------------

def _fetch_page(session: requests.Session, patent_id: str) -> BeautifulSoup | None:
    """Google Patents 페이지를 가져와서 파싱."""
    url = f"{GOOGLE_PATENTS_BASE}/{patent_id}/ko"
    try:
        resp = session.get(url, timeout=30)
        if resp.status_code != 200:
            logger.debug("HTTP %d: %s", resp.status_code, patent_id)
            return None
        return BeautifulSoup(resp.text, 'lxml')
    except Exception as e:
        logger.debug("페이지 가져오기 실패 %s: %s", patent_id, e)
        return None


def _extract_claims(soup: BeautifulSoup) -> str:
    """BeautifulSoup에서 청구항 텍스트 추출."""
    claims_section = soup.find('section', {'itemprop': 'claims'})
    if not claims_section:
        return ""

    claims_text = claims_section.get_text(separator='\n', strip=True)
    # "Claims (N)" 헤더 제거
    claims_text = re.sub(r'^Claims?\s*\(\d+\)\s*', '', claims_text)
    return claims_text.strip()


def _extract_description(soup: BeautifulSoup, max_chars: int = 5000) -> str:
    """BeautifulSoup에서 발명의 상세한 설명 추출."""
    desc_section = soup.find('section', {'itemprop': 'description'})
    if not desc_section:
        return ""

    desc_text = desc_section.get_text(separator='\n', strip=True)
    return desc_text[:max_chars].strip()


def fetch_patent_content(
    session: requests.Session,
    patent_id: str,
) -> dict:
    """Google Patents에서 청구항과 설명을 모두 가져온다.

    반환: {"claims": str, "description": str, "patent_id": str}
    """
    result = {"claims": "", "description": "", "patent_id": patent_id}

    soup = _fetch_page(session, patent_id)
    if soup is None:
        return result

    result["claims"] = _extract_claims(soup)
    result["description"] = _extract_description(soup)
    return result


def try_fetch_with_ids(
    session: requests.Session,
    patent_ids: list[str],
) -> dict:
    """여러 patent_id를 순서대로 시도하여 첫 성공 결과를 반환.

    각 시도 사이에 rate limiting을 적용한다.
    청구항이 있으면 즉시 반환, 없으면 설명이라도 있는 결과를 기억해둔다.

    반환: {"claims": str, "description": str, "patent_id": str, "suffix_used": str}
    """
    best_result = {"claims": "", "description": "", "patent_id": "", "suffix_used": ""}
    best_has_description = False

    for i, pid in enumerate(patent_ids):
        if i > 0:
            time.sleep(RATE_LIMIT_SECONDS)

        content = fetch_patent_content(session, pid)

        has_claims = len(content["claims"]) > 50
        has_description = len(content["description"]) > 50

        if has_claims:
            # 청구항 발견 → 즉시 반환
            suffix = pid.split("KR", 1)[-1] if "KR" in pid else pid
            # 마지막 알파벳+숫자 suffix 추출 (B1, A1, U1, A 등)
            suffix_match = re.search(r'[A-Z]\d?$', pid)
            suffix_used = suffix_match.group(0) if suffix_match else "unknown"

            return {
                "claims": content["claims"],
                "description": content["description"],
                "patent_id": pid,
                "suffix_used": suffix_used,
            }

        if has_description and not best_has_description:
            # 설명만 있는 경우 기억 (나중 fallback)
            suffix_match = re.search(r'[A-Z]\d?$', pid)
            suffix_used = suffix_match.group(0) if suffix_match else "unknown"
            best_result = {
                "claims": "",
                "description": content["description"],
                "patent_id": pid,
                "suffix_used": suffix_used,
            }
            best_has_description = True

    return best_result


# ---------------------------------------------------------------------------
# content_status 결정
# ---------------------------------------------------------------------------

def determine_content_status(record: dict) -> str:
    """레코드의 콘텐츠 상태를 결정.

    - "claims": 청구항 보유 (가장 풍부)
    - "full": 청구항 + 설명 모두 보유
    - "description": 설명만 보유 (청구항 없음)
    - "abstract_only": 초록만 보유
    """
    has_claims = bool(record.get("claims") and len(record.get("claims", "")) > 50)
    has_description = bool(record.get("description") and len(record.get("description", "")) > 50)
    has_abstract = bool(record.get("abstract") and len(record.get("abstract", "")) > 20)

    if has_claims and has_description:
        return "full"
    elif has_claims:
        return "claims"
    elif has_description:
        return "description"
    elif has_abstract:
        return "abstract_only"
    else:
        return "no_content"


# ---------------------------------------------------------------------------
# 단일 파일 보강
# ---------------------------------------------------------------------------

def enrich_patent_file(
    session: requests.Session,
    file_path: str,
    max_per_file: int = 0,
) -> dict:
    """단일 특허 JSON 파일의 특허들에 청구항/설명을 추가.

    max_per_file=0이면 무제한.
    """
    with open(file_path, encoding='utf-8') as f:
        records = json.load(f)

    stats = {
        "total": len(records),
        "enriched_claims": 0,
        "enriched_description": 0,
        "already_has_claims": 0,
        "no_id": 0,
        "failed": 0,
        "suffix_counter": Counter(),  # 어떤 suffix가 성공했는지
    }
    modified = False
    processed = 0

    for record in records:
        # 이미 청구항이 있으면 스킵 (content_status만 업데이트)
        if record.get("claims") and len(record.get("claims", "")) > 50:
            stats["already_has_claims"] += 1
            if "content_status" not in record:
                record["content_status"] = determine_content_status(record)
                modified = True
            continue

        # max_per_file 제한 (0이면 무제한)
        if max_per_file > 0 and processed >= max_per_file:
            continue

        # patent_id 후보 생성
        register_number = record.get("register_number", "")
        application_number = record.get("application_number", "")
        open_number = record.get("open_number", "")

        candidate_ids: list[str] = []

        # 1순위: 등록번호 기반 (B1 → A1)
        if register_number:
            candidate_ids.extend(make_register_patent_ids(register_number))

        # 2순위: 공개번호 기반 (A)
        if open_number:
            candidate_ids.extend(make_open_patent_ids(open_number))

        # 3순위: 출원번호 기반
        if application_number:
            candidate_ids.extend(make_application_patent_ids(application_number))

        if not candidate_ids:
            stats["no_id"] += 1
            # ID가 없어도 content_status는 태깅
            record["content_status"] = determine_content_status(record)
            modified = True
            continue

        # 중복 제거 (순서 유지)
        seen = set()
        unique_ids = []
        for pid in candidate_ids:
            if pid not in seen:
                seen.add(pid)
                unique_ids.append(pid)

        # Google Patents에서 가져오기
        result = try_fetch_with_ids(session, unique_ids)

        if result["claims"] and len(result["claims"]) > 50:
            record["claims"] = result["claims"]
            record["claims_source"] = "google_patents"
            record["claims_patent_id"] = result["patent_id"]
            stats["enriched_claims"] += 1
            stats["suffix_counter"][result["suffix_used"]] += 1
            logger.debug(
                "  청구항 추가: %s (%d자, %s)",
                result["patent_id"], len(result["claims"]), result["suffix_used"],
            )
            modified = True

            if result["description"] and len(result["description"]) > 50:
                record["description"] = result["description"]

        elif result["description"] and len(result["description"]) > 50:
            record["description"] = result["description"]
            record["description_source"] = "google_patents"
            record["description_patent_id"] = result["patent_id"]
            stats["enriched_description"] += 1
            stats["suffix_counter"][result["suffix_used"]] += 1
            logger.debug(
                "  설명 추가 (청구항 없음): %s (%d자, %s)",
                result["patent_id"], len(result["description"]), result["suffix_used"],
            )
            modified = True
        else:
            stats["failed"] += 1

        # content_status 태깅
        record["content_status"] = determine_content_status(record)
        processed += 1

        # Rate limiting (try_fetch_with_ids 내부에서도 적용하지만, 레코드 간에도)
        time.sleep(RATE_LIMIT_SECONDS)

    # 저장 (변경사항이 있을 때만)
    if modified:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

    return stats


# ---------------------------------------------------------------------------
# 전체 보강
# ---------------------------------------------------------------------------

def enrich_all(
    category: str | None = None,
    max_total: int = 500,
    max_per_file: int = 0,
    patent_dirs: list[str] | None = None,
) -> dict:
    """전체 특허 파일에 청구항/설명을 추가.

    patent_dirs: 탐색할 디렉토리 목록. None이면 ["patents", "patents_recent"] 모두 탐색.
    """
    if patent_dirs is None:
        patent_dirs = ["patents", "patents_recent"]

    categories = [category] if category else ["CIV", "ARC", "MEC"]

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9",
    })

    total_stats = {
        "total": 0,
        "enriched_claims": 0,
        "enriched_description": 0,
        "already_has_claims": 0,
        "no_id": 0,
        "failed": 0,
        "suffix_counter": Counter(),
    }

    total_enriched = 0  # claims + description

    for dir_name in patent_dirs:
        patents_dir = PROJECT_ROOT / "data" / "dynamic" / dir_name
        if not patents_dir.exists():
            continue

        for cat in categories:
            cat_dir = patents_dir / cat
            if not cat_dir.exists():
                logger.warning("카테고리 디렉토리 없음: %s", cat_dir)
                continue

            for f in sorted(cat_dir.glob("*.json")):
                if total_enriched >= max_total:
                    break

                remaining = max_total - total_enriched
                per_file = min(max_per_file, remaining) if max_per_file > 0 else remaining

                logger.info("처리: %s/%s/%s (남은 할당: %d)", dir_name, cat, f.name, remaining)

                stats = enrich_patent_file(session, str(f), max_per_file=per_file)

                # 통계 합산
                total_stats["total"] += stats["total"]
                total_stats["enriched_claims"] += stats["enriched_claims"]
                total_stats["enriched_description"] += stats["enriched_description"]
                total_stats["already_has_claims"] += stats["already_has_claims"]
                total_stats["no_id"] += stats["no_id"]
                total_stats["failed"] += stats["failed"]
                total_stats["suffix_counter"] += stats["suffix_counter"]

                file_enriched = stats["enriched_claims"] + stats["enriched_description"]
                total_enriched += file_enriched

                if file_enriched > 0:
                    logger.info(
                        "  -> 청구항 +%d, 설명 +%d (이미 보유: %d)",
                        stats["enriched_claims"],
                        stats["enriched_description"],
                        stats["already_has_claims"],
                    )

            if total_enriched >= max_total:
                logger.info("최대 건수(%d) 도달. 중단.", max_total)
                break

        if total_enriched >= max_total:
            break

    # 최종 요약
    logger.info("=" * 60)
    logger.info("특허 콘텐츠 보강 완료")
    logger.info("  총 레코드: %d", total_stats["total"])
    logger.info("  청구항 추가: %d", total_stats["enriched_claims"])
    logger.info("  설명 추가 (fallback): %d", total_stats["enriched_description"])
    logger.info("  이미 청구항 보유: %d", total_stats["already_has_claims"])
    logger.info("  ID 없음 (스킵): %d", total_stats["no_id"])
    logger.info("  실패 (콘텐츠 없음): %d", total_stats["failed"])

    if total_stats["suffix_counter"]:
        logger.info("  성공 suffix 패턴:")
        for suffix, count in total_stats["suffix_counter"].most_common():
            logger.info("    %s: %d건", suffix, count)

    logger.info("=" * 60)
    return total_stats


# ---------------------------------------------------------------------------
# 현황 표시
# ---------------------------------------------------------------------------

def show_status():
    """특허 콘텐츠 보강 현황을 상세 출력."""
    print("=" * 70)
    print("특허 콘텐츠 보강 현황")
    print("=" * 70)

    grand_total = 0
    grand_status = Counter()

    for dir_name in ["patents", "patents_recent"]:
        patents_dir = PROJECT_ROOT / "data" / "dynamic" / dir_name
        if not patents_dir.exists():
            continue
        print(f"\n--- {dir_name} ---")

        for cat in ["CIV", "ARC", "MEC"]:
            cat_dir = patents_dir / cat
            if not cat_dir.exists():
                continue

        total = 0
        with_claims = 0
        with_description = 0
        with_abstract = 0
        no_register = 0
        no_content = 0
        status_counter = Counter()
        claims_lengths: list[int] = []
        desc_lengths: list[int] = []

        for f in sorted(cat_dir.glob("*.json")):
            with open(f, encoding='utf-8') as fp:
                records = json.load(fp)
            for r in records:
                total += 1

                # 콘텐츠 상태
                claims = r.get("claims", "")
                description = r.get("description", "")
                abstract = r.get("abstract", "")
                register_number = r.get("register_number", "")
                content_status = r.get("content_status", "")

                if claims and len(claims) > 50:
                    with_claims += 1
                    claims_lengths.append(len(claims))
                if description and len(description) > 50:
                    with_description += 1
                    desc_lengths.append(len(description))
                if abstract and len(abstract) > 20:
                    with_abstract += 1
                if not register_number:
                    no_register += 1

                # content_status 집계
                if content_status:
                    status_counter[content_status] += 1
                else:
                    # 태깅 안 된 경우 자동 계산
                    auto_status = determine_content_status(r)
                    status_counter[auto_status] += 1

        grand_total += total
        grand_status += status_counter

        pct_claims = with_claims / max(total, 1) * 100
        pct_desc = with_description / max(total, 1) * 100
        avg_claims = sum(claims_lengths) / max(len(claims_lengths), 1)
        avg_desc = sum(desc_lengths) / max(len(desc_lengths), 1)

        print(f"\n[{cat}] 총 {total}건")
        print(f"  청구항 보유: {with_claims} ({pct_claims:.1f}%), 평균 {avg_claims:.0f}자")
        print(f"  설명 보유:   {with_description} ({pct_desc:.1f}%), 평균 {avg_desc:.0f}자")
        print(f"  초록 보유:   {with_abstract} ({with_abstract / max(total, 1) * 100:.1f}%)")
        print(f"  등록번호 없음: {no_register}")

        if status_counter:
            print(f"  콘텐츠 상태:")
            for status in ["full", "claims", "description", "abstract_only", "no_content"]:
                count = status_counter.get(status, 0)
                if count > 0:
                    print(f"    {status}: {count} ({count / max(total, 1) * 100:.1f}%)")

    # 전체 요약
    print(f"\n{'=' * 70}")
    print(f"전체: {grand_total}건")
    if grand_status:
        for status in ["full", "claims", "description", "abstract_only", "no_content"]:
            count = grand_status.get(status, 0)
            if count > 0:
                pct = count / max(grand_total, 1) * 100
                print(f"  {status}: {count} ({pct:.1f}%)")
    print("=" * 70)


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Google Patents 특허 콘텐츠 보강 (청구항 + 설명 + content_status)"
    )
    parser.add_argument("--category", type=str, help="카테고리 (CIV, ARC, MEC)")
    parser.add_argument("--max", type=int, default=500, help="최대 보강 건수 (기본: 500)")
    parser.add_argument(
        "--max-per-file", type=int, default=0,
        help="파일당 최대 보강 건수 (기본: 0=무제한)",
    )
    parser.add_argument("--status", action="store_true", help="보강 현황 확인")
    args = parser.parse_args()

    if args.status:
        show_status()
    else:
        enrich_all(
            category=args.category,
            max_total=args.max,
            max_per_file=args.max_per_file,
        )


if __name__ == "__main__":
    main()
