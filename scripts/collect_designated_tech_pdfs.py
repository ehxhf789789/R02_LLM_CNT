"""전체 지정기술 PDF 수집 + KB 강화 스크립트.

designated_list.json의 모든 지정기술에 대해:
1. KAIA 상세 페이지에서 다운로드 가능한 PDF 목록 조회
2. 선행기술조사, 신기술상세, 소개자료, 홍보용요약 등 핵심 PDF 다운로드
3. 텍스트 추출 후 지정기술 KB 데이터에 통합
4. 프로포절용 데이터도 함께 구축

사용법:
  py scripts/collect_designated_tech_pdfs.py                     # 전체 수집
  py scripts/collect_designated_tech_pdfs.py --start 546 --end 700  # 범위 지정
  py scripts/collect_designated_tech_pdfs.py --status              # 수집 현황
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
MEDIA_AJAX_URL = f"{KAIA_BASE}/portal/newtec/selectMediaAjax2.do"

# KB에 유용한 PDF 타입 (우선순위순)
USEFUL_PDF_TYPES = [
    {"pattern": "선행기술조사", "field": "prior_art_survey"},
    {"pattern": "신기술 상세", "field": "tech_detail"},
    {"pattern": "건설신기술 소개자료", "field": "intro"},
    {"pattern": "홍보용 요약자료", "field": "summary"},
    {"pattern": "시공절차", "field": "procedure"},
    {"pattern": "지식재산권", "field": "ip_info"},
]

MAX_PDF_SIZE = 15 * 1024 * 1024  # 15MB limit per file


def extract_newtec_id(detail_url: str) -> str:
    parsed = urlparse(detail_url)
    params = parse_qs(parsed.query)
    ids = params.get("newtecId", [])
    return ids[0] if ids else ""


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Referer": f"{KAIA_BASE}/portal/newtec/nView.do",
    })
    return session


def extract_text_from_pdf(pdf_path: Path, max_pages: int = 80) -> str:
    """PDF에서 텍스트 추출."""
    best_text = ""
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        pages = min(len(doc), max_pages)
        text = ""
        for i in range(pages):
            t = doc[i].get_text()
            if t and len(t.strip()) > 5:
                text += t + "\n\n"
        doc.close()
        if len(text.strip()) > len(best_text):
            best_text = text.strip()
    except Exception:
        pass

    if len(best_text) < 100:
        try:
            import pdfplumber
            with pdfplumber.open(str(pdf_path)) as pdf:
                text = ""
                for i in range(min(len(pdf.pages), max_pages)):
                    t = pdf.pages[i].extract_text()
                    if t:
                        text += t + "\n\n"
                if len(text.strip()) > len(best_text):
                    best_text = text.strip()
        except Exception:
            pass

    return best_text


def collect_single_tech(
    session: requests.Session,
    tech: dict,
    pdf_base_dir: Path,
    kb_output_dir: Path,
) -> dict | None:
    """단일 지정기술의 PDF를 수집하고 KB 데이터를 구축."""
    tech_number = tech.get("tech_number", "")
    detail_url = tech.get("detail_url", "")
    if not detail_url:
        return None

    newtec_id = extract_newtec_id(detail_url)
    if not newtec_id:
        return None

    # 이미 수집한 KB 데이터가 있으면 스킵
    kb_path = kb_output_dir / f"designated_{tech_number}.json"
    if kb_path.exists():
        return None

    # 메인 페이지 방문 (세션)
    full_url = KAIA_BASE + detail_url
    try:
        session.get(full_url, timeout=15)
    except Exception:
        return None
    time.sleep(0.5)

    # AJAX로 파일 목록 + 특허 목록 가져오기
    try:
        resp = session.post(
            MEDIA_AJAX_URL,
            data={"manNum": newtec_id, "exeNo": newtec_id},
            timeout=15,
        )
        data = resp.json()
    except Exception as e:
        logger.debug("AJAX 실패 %s: %s", tech_number, e)
        return None

    files = data.get("resultatch", [])
    patents_raw = data.get("resultList", [])

    if not files:
        return None

    # 특허 정보
    patents = []
    for p in patents_raw:
        patents.append({
            "title": p.get("documenttitle", ""),
            "type": p.get("documentregistertype", ""),
            "register_number": p.get("documentregister", ""),
        })

    # 유용한 PDF 다운로드 + 텍스트 추출
    pdf_dir = pdf_base_dir / tech_number
    extracted = {}

    for pdf_type in USEFUL_PDF_TYPES:
        matching_files = [f for f in files if pdf_type["pattern"] in f.get("multipartname", "")]
        if not matching_files:
            continue

        file_info = matching_files[0]
        name = file_info["multipartname"]
        size = int(file_info.get("multipartsize", 0))
        url = NTECH_BASE + file_info.get("multiparturl", "")

        if size > MAX_PDF_SIZE:
            continue

        safe_name = re.sub(r'[<>:"/\\|?*]', '_', name)
        out_path = pdf_dir / safe_name

        # 다운로드
        if not out_path.exists():
            try:
                r = session.get(url, timeout=60, stream=True)
                r.raise_for_status()
                pdf_dir.mkdir(parents=True, exist_ok=True)
                total = 0
                with open(out_path, "wb") as f:
                    for chunk in r.iter_content(8192):
                        f.write(chunk)
                        total += len(chunk)
                        if total > MAX_PDF_SIZE:
                            break
            except Exception:
                if out_path.exists():
                    out_path.unlink()
                continue
            time.sleep(1)

        # 텍스트 추출
        if out_path.exists():
            text = extract_text_from_pdf(out_path)
            if text and len(text) > 50:
                extracted[pdf_type["field"]] = text

    if not extracted and not patents:
        return None

    # KB 데이터 구축
    kb_data = {
        "tech_number": tech_number,
        "tech_name": tech.get("tech_name", ""),
        "tech_field": tech.get("tech_field", ""),
        "detail_url": detail_url,
        "patents": patents,
        "extracted_texts": extracted,
        "file_count": len(files),
    }

    # 저장
    kb_output_dir.mkdir(parents=True, exist_ok=True)
    with open(kb_path, "w", encoding="utf-8") as f:
        json.dump(kb_data, f, ensure_ascii=False, indent=2)

    return kb_data


def run_collection(start: int = 546, end: int = 1046) -> dict:
    """범위 내 지정기술 PDF 수집."""
    list_path = settings.dynamic_kb_dir / "cnt_designated" / "designated_list.json"
    with open(list_path, encoding="utf-8") as f:
        techs = json.load(f)

    # 범위 필터
    def safe_int(val):
        try:
            return int(re.sub(r'[^0-9]', '', str(val)) or '0')
        except ValueError:
            return 0

    target_techs = [
        t for t in techs
        if start <= safe_int(t.get("tech_number", "0")) <= end
    ]
    logger.info("수집 대상: %d건 (범위 %d~%d)", len(target_techs), start, end)

    pdf_dir = settings.data_dir / "proposals" / "pdfs"
    kb_dir = settings.dynamic_kb_dir / "cnt_designated" / "enriched"

    session = create_session()
    stats = {"total": 0, "collected": 0, "skipped": 0, "no_files": 0, "error": 0}

    for i, tech in enumerate(target_techs):
        tn = tech.get("tech_number", "")
        stats["total"] += 1

        # 이미 수집된 건 스킵
        kb_path = kb_dir / f"designated_{tn}.json"
        if kb_path.exists():
            stats["skipped"] += 1
            continue

        try:
            result = collect_single_tech(session, tech, pdf_dir, kb_dir)
            if result:
                n_texts = len(result.get("extracted_texts", {}))
                n_patents = len(result.get("patents", []))
                logger.info(
                    "[%d/%d] %s: %d texts, %d patents",
                    i + 1, len(target_techs), tn, n_texts, n_patents,
                )
                stats["collected"] += 1
            else:
                stats["no_files"] += 1
        except Exception as e:
            logger.error("[%s] 오류: %s", tn, e)
            stats["error"] += 1

        # Rate limiting
        time.sleep(2)

        # Progress every 50 items
        if (i + 1) % 50 == 0:
            logger.info("진행: %d/%d (수집 %d, 스킵 %d)", i + 1, len(target_techs),
                        stats["collected"], stats["skipped"])

    logger.info(
        "수집 완료: 총 %d, 수집 %d, 스킵 %d, 파일없음 %d, 에러 %d",
        stats["total"], stats["collected"], stats["skipped"], stats["no_files"], stats["error"],
    )
    return stats


def show_status():
    """수집 현황 출력."""
    kb_dir = settings.dynamic_kb_dir / "cnt_designated" / "enriched"
    if not kb_dir.exists():
        print("수집된 데이터 없음")
        return

    files = sorted(kb_dir.glob("designated_*.json"))
    total_texts = 0
    total_patents = 0
    text_lengths = []

    for f in files:
        with open(f, encoding="utf-8") as fp:
            data = json.load(fp)
        texts = data.get("extracted_texts", {})
        patents = data.get("patents", [])
        total_texts += len(texts)
        total_patents += len(patents)
        total_len = sum(len(v) for v in texts.values())
        text_lengths.append(total_len)

    print(f"수집된 지정기술: {len(files)}건")
    print(f"  추출 텍스트: {total_texts}건 (평균 {sum(text_lengths)/max(1,len(files)):.0f}자)")
    print(f"  특허 정보: {total_patents}건")
    if text_lengths:
        print(f"  텍스트 최소/최대: {min(text_lengths):,}자 / {max(text_lengths):,}자")


def main():
    parser = argparse.ArgumentParser(description="지정기술 PDF 수집 + KB 강화")
    parser.add_argument("--start", type=int, default=546, help="시작 기술번호 (기본 546)")
    parser.add_argument("--end", type=int, default=1046, help="종료 기술번호 (기본 1046)")
    parser.add_argument("--status", action="store_true", help="수집 현황")
    args = parser.parse_args()

    if args.status:
        show_status()
    else:
        run_collection(start=args.start, end=args.end)


if __name__ == "__main__":
    main()
