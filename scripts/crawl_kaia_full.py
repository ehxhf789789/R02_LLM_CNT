"""KAIA 건설신기술 전체 크롤링 + 홍보자료 보유 건 필터링 + PDF enrichment.

전체 흐름:
  1. KAIA 목록 페이지에서 전체 건설신기술 크롤링 (~1042건)
  2. 각 기술의 AJAX 엔드포인트로 홍보자료(다운로드 파일) 존재 여부 확인
  3. 홍보자료가 있는 기술만 designated_list.json에 저장
  4. PDF 다운로드 + 텍스트 추출 → enriched 파일 생성
  5. 벡터DB 재구축

사용법:
  py scripts/crawl_kaia_full.py                    # 전체 실행
  py scripts/crawl_kaia_full.py --phase list       # 1단계: 목록만 크롤링
  py scripts/crawl_kaia_full.py --phase check      # 2단계: 홍보자료 존재 확인
  py scripts/crawl_kaia_full.py --phase enrich     # 3단계: PDF 다운로드 + enrichment
  py scripts/crawl_kaia_full.py --phase rebuild    # 4단계: 벡터DB 재구축
  py scripts/crawl_kaia_full.py --resume           # 중단된 곳부터 재개
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
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(open(sys.stdout.fileno(), mode='w', encoding='utf-8', closefd=False))],
)
logger = logging.getLogger(__name__)

KAIA_BASE = "https://www.kaia.re.kr"
NTECH_BASE = "https://ntech.kaia.re.kr"
LIST_URL = KAIA_BASE + "/portal/newtec/comparelist.do"
MEDIA_AJAX_URL = KAIA_BASE + "/portal/newtec/selectMediaAjax2.do"

# 출력 경로
DESIGNATED_DIR = settings.dynamic_kb_dir / "cnt_designated"
DESIGNATED_LIST_PATH = DESIGNATED_DIR / "designated_list.json"
ENRICHED_DIR = DESIGNATED_DIR / "enriched"
PDF_DIR = settings.proposals_dir / "pdfs"

# 홍보자료 체크 중간 결과 저장
PROGRESS_PATH = DESIGNATED_DIR / "_crawl_progress.json"

# PDF 필드 매핑
PDF_PRIORITY = [
    {"pattern": "홍보용 책자(내용)", "field": "pdf_content", "priority": 1},
    {"pattern": "홍보용 책자", "field": "pdf_content", "priority": 2},
    {"pattern": "신기술 상세", "field": "tech_detail", "priority": 3},
    {"pattern": "선행기술조사", "field": "prior_art_survey", "priority": 4},
    {"pattern": "홍보용 요약자료", "field": "summary", "priority": 5},
    {"pattern": "건설신기술 소개자료", "field": "intro", "priority": 6},
    {"pattern": "시공절차", "field": "procedure", "priority": 7},
    {"pattern": "원가계산서", "field": "cost", "priority": 8},
]


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Referer": f"{KAIA_BASE}/portal/newtec/comparelist.do",
    })
    return session


# =============================================================================
# Phase 1: 전체 목록 크롤링
# =============================================================================

def crawl_full_list(session: requests.Session, max_pages: int = 120) -> list[dict]:
    """KAIA 목록 페이지에서 전체 건설신기술 목록을 크롤링."""
    all_techs = []

    for page in range(1, max_pages + 1):
        logger.info("목록 페이지 %d 크롤링 중...", page)
        try:
            resp = session.get(LIST_URL, params={
                "menuNo": "200076",
                "pageIndex": page,
            }, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            logger.error("페이지 %d 요청 실패: %s", page, e)
            break

        soup = BeautifulSoup(resp.text, "lxml")
        table = soup.find("table", class_="t_list")
        if not table:
            logger.info("페이지 %d: 테이블 없음, 크롤링 종료", page)
            break

        rows = table.find_all("tr")[1:]  # 헤더 제외
        if not rows:
            logger.info("페이지 %d: 결과 없음, 크롤링 종료", page)
            break

        page_count = 0
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 6:
                continue

            link = row.find("a", href=True)
            detail_url = link["href"] if link else ""

            tech = {
                "tech_number": cols[1].get_text(strip=True),
                "tech_name": cols[2].get_text(strip=True),
                "applicant": cols[3].get_text(strip=True),
                "tech_field": cols[4].get_text(strip=True),
                "protection_period": cols[5].get_text(strip=True),
                "consulting": cols[6].get_text(strip=True) if len(cols) > 6 else "",
                "status": cols[7].get_text(strip=True) if len(cols) > 7 else "",
                "detail_url": detail_url,
            }
            all_techs.append(tech)
            page_count += 1

        logger.info("페이지 %d: %d건 수집 (누적 %d건)", page, page_count, len(all_techs))

        if page_count == 0:
            break

        time.sleep(2)

    logger.info("전체 목록 크롤링 완료: %d건", len(all_techs))
    return all_techs


# =============================================================================
# Phase 2: 홍보자료 존재 여부 확인
# =============================================================================

def extract_newtec_id(detail_url: str) -> str:
    parsed = urlparse(detail_url)
    params = parse_qs(parsed.query)
    ids = params.get("newtecId", [])
    return ids[0] if ids else ""


def check_files_for_tech(session: requests.Session, tech: dict) -> dict | None:
    """기술의 홍보자료 존재 여부를 AJAX로 확인. 파일이 있으면 파일 목록 반환."""
    detail_url = tech.get("detail_url", "")
    newtec_id = extract_newtec_id(detail_url)
    if not newtec_id:
        return None

    try:
        # 상세 페이지 방문 (세션/쿠키)
        full_url = KAIA_BASE + detail_url if detail_url.startswith("/") else detail_url
        session.get(full_url, timeout=30)
        time.sleep(1)

        # AJAX 파일 목록 조회
        resp = session.post(
            MEDIA_AJAX_URL,
            data={"manNum": newtec_id, "exeNo": newtec_id},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        files = data.get("resultatch", [])
        patents = data.get("resultList", [])

        if not files:
            return None

        file_list = []
        for f in files:
            name = f.get("multipartname", "")
            url = f.get("multiparturl", "")
            size = int(f.get("multipartsize", 0))
            full_url = NTECH_BASE + url if url else ""
            file_list.append({"name": name, "url": full_url, "size": size})

        patent_list = []
        for p in patents:
            patent_list.append({
                "title": p.get("documenttitle", ""),
                "type": p.get("documentregistertype", ""),
                "register_number": p.get("documentregister", ""),
                "owner": p.get("documentowner", ""),
            })

        return {"files": file_list, "patents": patent_list, "newtec_id": newtec_id}

    except Exception as e:
        logger.error("파일 확인 실패 (기술 %s): %s", tech.get("tech_number"), e)
        return None


def check_all_files(
    session: requests.Session,
    techs: list[dict],
    progress: dict,
) -> dict:
    """전체 기술의 홍보자료 존재 여부를 확인하고 progress에 저장."""
    checked = progress.get("checked", {})
    has_files = progress.get("has_files", {})

    total = len(techs)
    for i, tech in enumerate(techs):
        tech_num = tech.get("tech_number", "")
        if not tech_num:
            continue

        # 이미 확인된 건 스킵
        if tech_num in checked:
            continue

        logger.info("[%d/%d] 홍보자료 확인: %s (%s)", i + 1, total, tech_num, tech.get("tech_name", "")[:30])

        result = check_files_for_tech(session, tech)
        checked[tech_num] = True

        if result and result["files"]:
            has_files[tech_num] = result
            logger.info("  → 파일 %d개 발견", len(result["files"]))
        else:
            logger.info("  → 홍보자료 없음")

        # 주기적 저장 (10건마다)
        if (i + 1) % 10 == 0:
            progress["checked"] = checked
            progress["has_files"] = has_files
            _save_progress(progress)
            logger.info("  진행 상황 저장: %d/%d 확인, %d건 홍보자료 보유",
                       len(checked), total, len(has_files))

        time.sleep(2)

    progress["checked"] = checked
    progress["has_files"] = has_files
    _save_progress(progress)

    logger.info("홍보자료 확인 완료: %d/%d건 보유", len(has_files), len(checked))
    return progress


# =============================================================================
# Phase 3: PDF 다운로드 + enrichment
# =============================================================================

def classify_file(name: str) -> dict | None:
    for entry in PDF_PRIORITY:
        if entry["pattern"] in name:
            return entry
    return None


def download_pdf(session: requests.Session, url: str, out_path: Path,
                 max_size_mb: float = 30.0) -> bool:
    if out_path.exists() and out_path.stat().st_size > 0:
        return True

    try:
        resp = session.get(url, timeout=120, stream=True)
        resp.raise_for_status()

        content_length = int(resp.headers.get("Content-Length", 0))
        if content_length > max_size_mb * 1024 * 1024:
            logger.info("  크기 초과 스킵 (%.1f MB): %s", content_length / 1024 / 1024, out_path.name)
            return False

        out_path.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        with open(out_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
                total += len(chunk)
                if total > max_size_mb * 1024 * 1024:
                    break

        logger.info("  다운로드: %s (%.1f KB)", out_path.name, total / 1024)
        return True
    except Exception as e:
        logger.error("  다운로드 실패: %s", e)
        if out_path.exists():
            out_path.unlink()
        return False


def extract_text_from_pdf(pdf_path: Path, max_pages: int = 80) -> str:
    best_text = ""

    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        pages_to_read = min(len(doc), max_pages)
        text = ""
        for i in range(pages_to_read):
            page_text = doc[i].get_text()
            if page_text and len(page_text.strip()) > 5:
                text += page_text + "\n\n"
        doc.close()
        if len(text.strip()) > len(best_text):
            best_text = text.strip()
    except Exception:
        pass

    if len(best_text) < 100:
        try:
            import pdfplumber
            with pdfplumber.open(str(pdf_path)) as pdf:
                pages_to_read = min(len(pdf.pages), max_pages)
                text = ""
                for i in range(pages_to_read):
                    page_text = pdf.pages[i].extract_text()
                    if page_text:
                        text += page_text + "\n\n"
                if len(text.strip()) > len(best_text):
                    best_text = text.strip()
        except Exception:
            pass

    return best_text


def enrich_tech(
    session: requests.Session,
    tech: dict,
    file_info: dict,
) -> bool:
    """기술의 PDF를 다운로드하고 enriched 파일을 생성."""
    tech_num = tech.get("tech_number", "")
    enriched_path = ENRICHED_DIR / f"designated_{tech_num}.json"

    # 이미 enriched 파일이 있으면 스킵
    if enriched_path.exists():
        return True

    files = file_info.get("files", [])
    patents = file_info.get("patents", [])

    # 다운로드 대상 선별
    download_targets = []
    for f in files:
        name = f["name"]
        classification = classify_file(name)
        if not classification:
            continue
        if "부록" in name:
            continue
        download_targets.append({**f, **classification})

    download_targets.sort(key=lambda x: x["priority"])

    # PDF 다운로드 + 텍스트 추출
    tech_pdf_dir = PDF_DIR / tech_num
    extracted_texts = {}

    for target in download_targets:
        safe_name = re.sub(r'[<>:"/\\|?*]', '_', target["name"])
        if not safe_name.endswith(".pdf"):
            safe_name += ".pdf"

        out_path = tech_pdf_dir / safe_name

        if download_pdf(session, target["url"], out_path):
            text = extract_text_from_pdf(out_path)
            if text:
                field = target["field"]
                if field in extracted_texts:
                    extracted_texts[field] += "\n\n" + text
                else:
                    extracted_texts[field] = text

        time.sleep(1)

    if not extracted_texts:
        logger.warning("  텍스트 추출 실패: %s", tech_num)
        return False

    # enriched 파일 저장
    ENRICHED_DIR.mkdir(parents=True, exist_ok=True)
    enriched_data = {
        "tech_number": tech_num,
        "tech_name": tech.get("tech_name", ""),
        "tech_field": tech.get("tech_field", ""),
        "detail_url": tech.get("detail_url", ""),
        "patents": patents,
        "extracted_texts": extracted_texts,
        "file_count": len(download_targets),
    }

    with open(enriched_path, "w", encoding="utf-8") as f:
        json.dump(enriched_data, f, ensure_ascii=False, indent=2)

    logger.info("  enriched 저장: %s (%d 필드)", enriched_path.name, len(extracted_texts))
    return True


def enrich_all(
    session: requests.Session,
    techs: list[dict],
    progress: dict,
) -> None:
    """홍보자료가 있는 모든 기술의 PDF를 다운로드하고 enriched 파일을 생성."""
    has_files = progress.get("has_files", {})
    enriched_set = progress.get("enriched", set())
    if isinstance(enriched_set, list):
        enriched_set = set(enriched_set)

    # tech_number → tech 매핑
    tech_map = {t["tech_number"]: t for t in techs if t.get("tech_number")}

    total = len(has_files)
    for i, (tech_num, file_info) in enumerate(has_files.items()):
        if tech_num in enriched_set:
            continue

        tech = tech_map.get(tech_num)
        if not tech:
            continue

        logger.info("[%d/%d] enrichment: %s (%s)",
                   i + 1, total, tech_num, tech.get("tech_name", "")[:30])

        success = enrich_tech(session, tech, file_info)
        if success:
            enriched_set.add(tech_num)

        # 주기적 저장
        if (i + 1) % 5 == 0:
            progress["enriched"] = list(enriched_set)
            _save_progress(progress)

        time.sleep(2)

    progress["enriched"] = list(enriched_set)
    _save_progress(progress)
    logger.info("enrichment 완료: %d/%d건", len(enriched_set), total)


# =============================================================================
# Progress 관리
# =============================================================================

def _load_progress() -> dict:
    if PROGRESS_PATH.exists():
        with open(PROGRESS_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"checked": {}, "has_files": {}, "enriched": [], "all_techs": []}


def _save_progress(progress: dict) -> None:
    DESIGNATED_DIR.mkdir(parents=True, exist_ok=True)
    with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2, default=str)


# =============================================================================
# Phase 4: designated_list.json 업데이트 + 벡터DB 재구축
# =============================================================================

def update_designated_list(techs: list[dict]) -> int:
    """designated_list.json을 전체 기술 목록으로 업데이트."""
    DESIGNATED_DIR.mkdir(parents=True, exist_ok=True)

    # 기존 파일 백업
    if DESIGNATED_LIST_PATH.exists():
        backup = DESIGNATED_DIR / "designated_list_backup.json"
        import shutil
        shutil.copy2(DESIGNATED_LIST_PATH, backup)
        logger.info("기존 목록 백업: %s", backup)

    with open(DESIGNATED_LIST_PATH, "w", encoding="utf-8") as f:
        json.dump(techs, f, ensure_ascii=False, indent=2)

    logger.info("designated_list.json 업데이트: %d건", len(techs))
    return len(techs)


def rebuild_vector_db() -> int:
    """벡터DB 재구축."""
    from src.vectordb.kb_vectorizer import KBVectorizer
    vectorizer = KBVectorizer()
    count = vectorizer.build_from_store()
    logger.info("벡터DB 재구축 완료: %d건", count)
    return count


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="KAIA 전체 크롤링 + 홍보자료 필터링")
    parser.add_argument("--phase", choices=["list", "check", "enrich", "rebuild", "all"],
                       default="all", help="실행 단계")
    parser.add_argument("--resume", action="store_true", help="중단된 곳부터 재개")
    parser.add_argument("--max-pages", type=int, default=120, help="최대 크롤링 페이지 수")
    args = parser.parse_args()

    session = create_session()
    progress = _load_progress() if args.resume else {"checked": {}, "has_files": {}, "enriched": [], "all_techs": []}

    phases = [args.phase] if args.phase != "all" else ["list", "check", "enrich", "rebuild"]

    for phase in phases:
        if phase == "list":
            print("\n" + "=" * 60)
            print("Phase 1: KAIA 전체 목록 크롤링")
            print("=" * 60)

            if args.resume and progress.get("all_techs"):
                techs = progress["all_techs"]
                logger.info("기존 목록 사용: %d건", len(techs))
            else:
                techs = crawl_full_list(session, max_pages=args.max_pages)
                progress["all_techs"] = techs
                _save_progress(progress)

            # designated_list.json 업데이트 (전체 목록)
            update_designated_list(techs)

            print(f"\n전체 건설신기술: {len(techs)}건")

        elif phase == "check":
            print("\n" + "=" * 60)
            print("Phase 2: 홍보자료 존재 여부 확인")
            print("=" * 60)

            techs = progress.get("all_techs", [])
            if not techs:
                # designated_list.json에서 로드
                if DESIGNATED_LIST_PATH.exists():
                    with open(DESIGNATED_LIST_PATH, encoding="utf-8") as f:
                        techs = json.load(f)
                    progress["all_techs"] = techs
                else:
                    logger.error("목록 없음. --phase list를 먼저 실행하세요.")
                    return

            progress = check_all_files(session, techs, progress)

            has_count = len(progress.get("has_files", {}))
            total = len(progress.get("checked", {}))
            print(f"\n홍보자료 보유: {has_count}/{total}건")

        elif phase == "enrich":
            print("\n" + "=" * 60)
            print("Phase 3: PDF 다운로드 + enrichment")
            print("=" * 60)

            techs = progress.get("all_techs", [])
            if not techs and DESIGNATED_LIST_PATH.exists():
                with open(DESIGNATED_LIST_PATH, encoding="utf-8") as f:
                    techs = json.load(f)

            if not progress.get("has_files"):
                logger.error("홍보자료 확인 결과 없음. --phase check를 먼저 실행하세요.")
                return

            enrich_all(session, techs, progress)

            # enriched 파일 수 확인
            enriched_count = len(list(ENRICHED_DIR.glob("designated_*.json")))
            print(f"\nenriched 파일: {enriched_count}건")

        elif phase == "rebuild":
            print("\n" + "=" * 60)
            print("Phase 4: 벡터DB 재구축")
            print("=" * 60)

            count = rebuild_vector_db()
            print(f"\n벡터DB 적재: {count:,}건")

    # 최종 요약
    enriched_count = len(list(ENRICHED_DIR.glob("designated_*.json"))) if ENRICHED_DIR.exists() else 0
    total_techs = len(progress.get("all_techs", []))
    has_files_count = len(progress.get("has_files", {}))

    print("\n" + "=" * 60)
    print("최종 요약")
    print("=" * 60)
    print(f"  전체 건설신기술: {total_techs}건")
    print(f"  홍보자료 보유: {has_files_count}건")
    print(f"  enriched 파일: {enriched_count}건")
    print(f"  KB/입력데이터에는 enriched 보유 건만 포함")


if __name__ == "__main__":
    main()
