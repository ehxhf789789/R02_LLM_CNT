"""Google Patents에서 특허 청구항(Claims) 수집 → KB 보강.

기존 특허 데이터에 청구항 정보를 추가하여 KB의 깊이를 보강한다.
Google Patents (patents.google.com)에서 한국 특허의 청구항을 크롤링한다.

사용법:
  py scripts/enrich_patent_claims.py                  # 전체 특허 청구항 보강
  py scripts/enrich_patent_claims.py --category MEC   # 특정 카테고리만
  py scripts/enrich_patent_claims.py --max 100        # 최대 100건만
  py scripts/enrich_patent_claims.py --status         # 보강 현황
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
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


def make_google_patent_id(register_number: str) -> str | None:
    """등록번호를 Google Patents ID로 변환.

    KIPRIS 등록번호 형식: "1026433360000" (13자리, 뒤 4자리 0)
    Google Patents 형식: "KR102643336B1" (뒤 4자리 0 제거)
    """
    if not register_number:
        return None

    # 숫자만 추출
    num = re.sub(r'[^0-9]', '', str(register_number))
    if not num or len(num) < 7:
        return None

    # 뒤에 0000이 붙어있으면 제거 (KIPRIS 형식)
    if len(num) == 13 and num.endswith("0000"):
        num = num[:-4]

    # 10으로 시작하면 등록특허 (B1), 20으로 시작하면 실용신안 (U1)
    if num.startswith("10"):
        return f"KR{num}B1"
    elif num.startswith("20"):
        return f"KR{num}U1"
    else:
        return f"KR{num}B1"


def fetch_claims(session: requests.Session, patent_id: str) -> str:
    """Google Patents에서 청구항을 가져온다."""
    url = f"{GOOGLE_PATENTS_BASE}/{patent_id}/ko"

    try:
        resp = session.get(url, timeout=30)
        if resp.status_code != 200:
            return ""

        soup = BeautifulSoup(resp.text, 'lxml')

        # 청구항 섹션 찾기
        claims_section = soup.find('section', {'itemprop': 'claims'})
        if claims_section:
            # 불필요한 태그 제거
            for tag in claims_section.find_all(['span', 'div'], class_='notranslate'):
                pass  # keep

            claims_text = claims_section.get_text(separator='\n', strip=True)

            # "Claims (N)" 헤더 제거
            claims_text = re.sub(r'^Claims?\s*\(\d+\)\s*', '', claims_text)

            return claims_text.strip()

        return ""
    except Exception as e:
        logger.debug("청구항 가져오기 실패 %s: %s", patent_id, e)
        return ""


def fetch_description(session: requests.Session, patent_id: str) -> str:
    """Google Patents에서 발명의 상세한 설명을 가져온다."""
    url = f"{GOOGLE_PATENTS_BASE}/{patent_id}/ko"

    try:
        resp = session.get(url, timeout=30)
        if resp.status_code != 200:
            return ""

        soup = BeautifulSoup(resp.text, 'lxml')

        desc_section = soup.find('section', {'itemprop': 'description'})
        if desc_section:
            desc_text = desc_section.get_text(separator='\n', strip=True)
            # 너무 긴 경우 요약 부분만 (처음 5000자)
            return desc_text[:5000].strip()

        return ""
    except Exception:
        return ""


def enrich_patent_file(
    session: requests.Session,
    file_path: str,
    max_per_file: int = 10,
) -> dict:
    """단일 특허 JSON 파일의 특허들에 청구항을 추가."""
    with open(file_path, encoding='utf-8') as f:
        records = json.load(f)

    stats = {"total": len(records), "enriched": 0, "skipped": 0, "failed": 0}

    for record in records:
        # 이미 청구항이 있으면 스킵
        if record.get("claims") and len(record.get("claims", "")) > 100:
            stats["skipped"] += 1
            continue

        if stats["enriched"] >= max_per_file:
            break

        register_number = record.get("register_number", "")
        patent_id = make_google_patent_id(register_number)

        if not patent_id:
            stats["failed"] += 1
            continue

        claims = fetch_claims(session, patent_id)

        if claims and len(claims) > 50:
            record["claims"] = claims
            record["claims_source"] = "google_patents"
            stats["enriched"] += 1
            logger.debug("  청구항 추가: %s (%d자)", patent_id, len(claims))
        else:
            stats["failed"] += 1

        time.sleep(2)  # Rate limiting

    # 저장
    if stats["enriched"] > 0:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

    return stats


def enrich_all(
    category: str | None = None,
    max_total: int = 500,
    max_per_file: int = 10,
) -> dict:
    """전체 특허 파일에 청구항을 추가."""
    patents_dir = Path("data/dynamic/patents")

    categories = [category] if category else ["CIV", "ARC", "MEC"]

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9",
    })

    total_stats = {"total": 0, "enriched": 0, "skipped": 0, "failed": 0}

    for cat in categories:
        cat_dir = patents_dir / cat
        if not cat_dir.exists():
            continue

        for f in sorted(cat_dir.glob("*.json")):
            if total_stats["enriched"] >= max_total:
                break

            remaining = max_total - total_stats["enriched"]
            per_file = min(max_per_file, remaining)

            logger.info("처리: %s/%s (남은 할당: %d)", cat, f.name, remaining)

            stats = enrich_patent_file(session, str(f), max_per_file=per_file)

            for k in total_stats:
                total_stats[k] += stats[k]

            if stats["enriched"] > 0:
                logger.info("  → %d건 청구항 추가", stats["enriched"])

    logger.info(
        "청구항 보강 완료: 총 %d건 중 %d건 추가, %d건 스킵, %d건 실패",
        total_stats["total"], total_stats["enriched"],
        total_stats["skipped"], total_stats["failed"],
    )
    return total_stats


def show_status():
    """청구항 보강 현황."""
    patents_dir = Path("data/dynamic/patents")

    for cat in ["CIV", "ARC", "MEC"]:
        cat_dir = patents_dir / cat
        if not cat_dir.exists():
            continue

        total = 0
        with_claims = 0
        claims_lengths = []

        for f in cat_dir.glob("*.json"):
            with open(f, encoding='utf-8') as fp:
                records = json.load(fp)
            for r in records:
                total += 1
                claims = r.get("claims", "")
                if claims and len(claims) > 50:
                    with_claims += 1
                    claims_lengths.append(len(claims))

        pct = with_claims / max(total, 1) * 100
        avg_len = sum(claims_lengths) / max(len(claims_lengths), 1)
        print(f"{cat}: {with_claims}/{total} ({pct:.1f}%) 청구항 보유, 평균 {avg_len:.0f}자")


def main():
    parser = argparse.ArgumentParser(description="Google Patents 청구항 보강")
    parser.add_argument("--category", type=str, help="카테고리 (CIV, ARC, MEC)")
    parser.add_argument("--max", type=int, default=500, help="최대 수집 건수")
    parser.add_argument("--max-per-file", type=int, default=10, help="파일당 최대")
    parser.add_argument("--status", action="store_true", help="현황 확인")
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
