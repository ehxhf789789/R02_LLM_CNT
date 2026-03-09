"""최근 5년(2021~) 특허 추가 수집.

KIPRIS API에 연도 필터가 없으므로, 많은 결과를 가져온 뒤
application_date 또는 register_date가 2021년 이후인 것만 필터링하여 저장한다.

기존 data/dynamic/patents/ 데이터와 별도로
data/dynamic/patents_recent/ 에 저장하여 기존 데이터를 보존한다.

사용법:
  py scripts/collect_recent_patents.py
  py scripts/collect_recent_patents.py --category CIV
  py scripts/collect_recent_patents.py --max 500
  py scripts/collect_recent_patents.py --status
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.dynamic_kb.kipris_client import KiprisClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(open(sys.stdout.fileno(), mode='w', encoding='utf-8', closefd=False))],
)
logger = logging.getLogger(__name__)

# 분야별 최신 트렌드 키워드 (2021~2026 기술 동향 반영)
RECENT_KEYWORDS = {
    "CIV": [
        "스마트 도로 시공", "디지털 트윈 교량", "3D 프린팅 콘크리트",
        "탄소중립 건설", "드론 측량 시공", "AI 구조물 점검",
        "프리캐스트 급속시공", "자율주행 건설장비", "그린 인프라",
        "스마트 터널 모니터링", "BIM 기반 시공", "건설현장 안전 IoT",
        "해상풍력 기초", "복합섬유 보강", "친환경 포장재",
        "수소연료전지 건설장비", "로봇 콘크리트 타설", "레이저 측량",
    ],
    "ARC": [
        "제로에너지 건축", "모듈러 건축 시공", "스마트 건축 자동화",
        "디지털 트윈 건물", "패시브하우스 시공", "건축물 내진보강 신기술",
        "3D 프린팅 건축", "OSC 건축", "AI 건물 에너지",
        "그린리모델링", "친환경 단열재", "스마트 방수",
        "로봇 용접 건축", "건축 BIM 자동화", "탄소저감 시멘트",
    ],
    "MEC": [
        "건설로봇 자동화", "IoT 건설안전 모니터링", "드론 건설현장",
        "자율주행 굴착기", "AI 건설관리", "스마트 건설 플랫폼",
        "건설기계 전동화", "디지털 안전관리", "지능형 CCTV 건설",
        "건설 빅데이터", "가상현실 건설교육", "웨어러블 안전장비",
    ],
}

# 기존 키워드도 최신 데이터 추가 수집용으로 활용
EXISTING_KEYWORDS = {
    "CIV": [
        "교량 보수보강", "터널 시공", "도로 포장", "말뚝 기초",
        "내진 보강", "하천 제방", "연약지반 처리",
    ],
    "ARC": [
        "건축 방수", "외단열", "철근콘크리트", "커튼월",
        "내화구조", "프리캐스트", "고강도 콘크리트",
    ],
    "MEC": [
        "건설기계", "소음방지", "환기설비", "배관시공",
        "소방설비", "지열시스템",
    ],
}

OUTPUT_DIR = PROJECT_ROOT / "data" / "dynamic" / "patents_recent"
MIN_YEAR = 2021


def extract_year(date_str: str) -> int | None:
    """날짜 문자열에서 연도 추출."""
    s = str(date_str).strip()
    if not s:
        return None
    for i in range(len(s) - 3):
        chunk = s[i:i + 4]
        if chunk.isdigit():
            y = int(chunk)
            if 1990 <= y <= 2030:
                return y
    return None


def is_recent(record: dict, min_year: int = MIN_YEAR) -> bool:
    """특허가 최근 N년 이내인지 확인."""
    for field in ["application_date", "register_date", "open_date"]:
        y = extract_year(record.get(field, ""))
        if y and y >= min_year:
            return True
    return False


def collect_recent_patents(
    category: str | None = None,
    max_per_category: int = 300,
) -> dict:
    """최근 5년 특허를 추가 수집."""
    client = KiprisClient()
    categories = [category] if category else ["CIV", "ARC", "MEC"]
    stats = {}

    for cat in categories:
        # 기존 특허 ID 수집 (중복 방지)
        existing_ids = set()
        existing_dir = PROJECT_ROOT / "data" / "dynamic" / "patents" / cat
        if existing_dir.exists():
            for f in existing_dir.glob("*.json"):
                with open(f, encoding="utf-8") as fp:
                    data = json.load(fp)
                for r in data:
                    app = r.get("application_number", "")
                    if app:
                        existing_ids.add(app)

        # 이미 수집된 최근 특허 ID도 확인
        recent_dir = OUTPUT_DIR / cat
        if recent_dir.exists():
            for f in recent_dir.glob("*.json"):
                with open(f, encoding="utf-8") as fp:
                    data = json.load(fp)
                for r in data:
                    app = r.get("application_number", "")
                    if app:
                        existing_ids.add(app)

        logger.info("=== %s 최근 특허 수집 (기존 %d건 제외) ===", cat, len(existing_ids))

        all_keywords = RECENT_KEYWORDS.get(cat, []) + EXISTING_KEYWORDS.get(cat, [])
        recent_records = []

        for kw in all_keywords:
            if len(recent_records) >= max_per_category:
                break

            logger.info("  검색: %s", kw)
            try:
                # 많이 가져와서 후처리 필터링
                results = client.search_construction_patents(kw, max_results=100)
            except Exception as e:
                logger.error("  검색 실패: %s", e)
                time.sleep(5)
                continue

            new_recent = 0
            for r in results:
                record = asdict(r)
                app_num = record.get("application_number", "")

                # 중복 체크
                if app_num in existing_ids:
                    continue

                # 최근 5년 필터
                if not is_recent(record, MIN_YEAR):
                    continue

                existing_ids.add(app_num)
                # raw 필드 제거 (용량 절약)
                record.pop("raw", None)
                recent_records.append(record)
                new_recent += 1

            if new_recent > 0:
                logger.info("    +%d건 (최근 5년)", new_recent)

            time.sleep(1)

        # 저장
        if recent_records:
            out_dir = OUTPUT_DIR / cat
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / "recent_2021_2026.json"

            # 기존 파일과 병합
            existing_recent = []
            if out_path.exists():
                with open(out_path, encoding="utf-8") as f:
                    existing_recent = json.load(f)

            merged = existing_recent + recent_records
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)

            logger.info("%s: %d건 최근 특허 저장 (누적 %d건)", cat, len(recent_records), len(merged))

        stats[cat] = len(recent_records)

    logger.info("최근 특허 수집 완료: %s", stats)
    return stats


def show_status():
    """최근 특허 수집 현황 + 기존 데이터 연도 분석."""
    patents_dir = PROJECT_ROOT / "data" / "dynamic" / "patents"
    recent_dir = OUTPUT_DIR

    for cat in ["CIV", "ARC", "MEC"]:
        total = 0
        recent = 0

        cat_dir = patents_dir / cat
        if cat_dir.exists():
            for f in cat_dir.glob("*.json"):
                with open(f, encoding="utf-8") as fp:
                    data = json.load(fp)
                for r in data:
                    total += 1
                    if is_recent(r):
                        recent += 1

        # 추가 수집분
        extra = 0
        rcat_dir = recent_dir / cat
        if rcat_dir.exists():
            for f in rcat_dir.glob("*.json"):
                with open(f, encoding="utf-8") as fp:
                    data = json.load(fp)
                extra += len(data)

        combined_recent = recent + extra
        combined_total = total + extra
        pct = combined_recent / max(combined_total, 1) * 100
        print(f"{cat}: 기존 {total}건 (최근 {recent}건) + 추가 {extra}건 = 최근 비중 {pct:.1f}%")


def main():
    parser = argparse.ArgumentParser(description="최근 5년 특허 추가 수집")
    parser.add_argument("--category", type=str, help="카테고리")
    parser.add_argument("--max", type=int, default=300, help="카테고리당 최대 건수")
    parser.add_argument("--status", action="store_true", help="현황")
    args = parser.parse_args()

    if args.status:
        show_status()
    else:
        collect_recent_patents(category=args.category, max_per_category=args.max)


if __name__ == "__main__":
    main()
