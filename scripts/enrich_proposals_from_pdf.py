"""KAIA 상세페이지 PDF 다운로드 + 텍스트 추출 → 프로포절 강화.

KAIA 상세페이지의 AJAX 엔드포인트에서 PDF 다운로드 링크를 수집하고,
홍보용 책자, 신기술 상세, 선행기술조사 등의 PDF를 다운로드한 후
텍스트를 추출하여 프로포절 JSON을 실제 데이터로 강화한다.

사용법:
  py scripts/enrich_proposals_from_pdf.py                    # 전체 프로포절 강화
  py scripts/enrich_proposals_from_pdf.py --tech-number 1037  # 단건
  py scripts/enrich_proposals_from_pdf.py --list-files 1037   # 파일 목록만 확인
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

# PDF 파일 우선순위 (프로포절 강화에 유용한 순서)
# 파일명 패턴 → proposal 필드 매핑
PDF_PRIORITY = [
    {"pattern": "홍보용 책자(내용)", "field": "pdf_content", "priority": 1},
    {"pattern": "홍보용 책자", "field": "pdf_content", "priority": 2},
    {"pattern": "신기술 상세", "field": "tech_detail_text", "priority": 3},
    {"pattern": "선행기술조사", "field": "prior_art_survey_text", "priority": 4},
    {"pattern": "홍보용 요약자료", "field": "summary_text", "priority": 5},
    {"pattern": "건설신기술 소개자료", "field": "intro_text", "priority": 6},
    {"pattern": "시공절차", "field": "procedure_text", "priority": 7},
    {"pattern": "원가계산서", "field": "cost_text", "priority": 8},
]

# 최대 다운로드 크기 제한 (100MB, 부록은 매우 클 수 있음)
MAX_DOWNLOAD_SIZE = 100 * 1024 * 1024


def extract_newtec_id(detail_url: str) -> str:
    """detail_url에서 newtecId 파라미터를 추출."""
    parsed = urlparse(detail_url)
    params = parse_qs(parsed.query)
    ids = params.get("newtecId", [])
    return ids[0] if ids else ""


def get_file_list(session: requests.Session, newtec_id: str) -> list[dict]:
    """KAIA AJAX 엔드포인트에서 다운로드 파일 목록을 가져온다."""
    try:
        resp = session.post(
            MEDIA_AJAX_URL,
            data={"manNum": newtec_id, "exeNo": newtec_id},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        files = data.get("resultatch", [])

        result = []
        for f in files:
            name = f.get("multipartname", "")
            url = f.get("multiparturl", "")
            size = int(f.get("multipartsize", 0))
            full_url = NTECH_BASE + url if url else ""
            result.append({
                "name": name,
                "url": full_url,
                "size": size,
            })
        return result
    except Exception as e:
        logger.error("파일 목록 조회 실패 (newtecId=%s): %s", newtec_id, e)
        return []


def get_patent_list(session: requests.Session, newtec_id: str) -> list[dict]:
    """KAIA AJAX 엔드포인트에서 지식재산권 목록을 가져온다."""
    try:
        resp = session.post(
            MEDIA_AJAX_URL,
            data={"manNum": newtec_id, "exeNo": newtec_id},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        patents = []
        for item in data.get("resultList", []):
            patents.append({
                "title": item.get("documenttitle", ""),
                "type": item.get("documentregistertype", ""),
                "register_number": item.get("documentregister", ""),
                "owner": item.get("documentowner", ""),
            })
        return patents
    except Exception:
        return []


def classify_file(name: str) -> dict | None:
    """파일명을 분석하여 PDF_PRIORITY에서 매칭되는 항목을 반환."""
    for entry in PDF_PRIORITY:
        if entry["pattern"] in name:
            return entry
    return None


def download_pdf(session: requests.Session, url: str, out_path: Path) -> bool:
    """PDF 파일을 다운로드."""
    if out_path.exists():
        logger.info("  이미 다운로드됨: %s (%.1f KB)", out_path.name, out_path.stat().st_size / 1024)
        return True

    try:
        resp = session.get(url, timeout=120, stream=True)
        resp.raise_for_status()

        content_length = int(resp.headers.get("Content-Length", 0))
        if content_length > MAX_DOWNLOAD_SIZE:
            logger.warning("  파일 크기 초과 (%.1f MB), 스킵: %s", content_length / 1024 / 1024, out_path.name)
            return False

        out_path.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        with open(out_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
                total += len(chunk)
                if total > MAX_DOWNLOAD_SIZE:
                    logger.warning("  다운로드 중 크기 초과, 중단")
                    break

        logger.info("  다운로드 완료: %s (%.1f KB)", out_path.name, total / 1024)
        return True
    except Exception as e:
        logger.error("  다운로드 실패: %s", e)
        if out_path.exists():
            out_path.unlink()
        return False


def extract_text_from_pdf(pdf_path: Path, max_pages: int = 80) -> str:
    """PDF에서 텍스트를 추출. PyMuPDF → pdfplumber → PyPDF2 순서로 시도."""
    best_text = ""

    # PyMuPDF (fitz) 시도 - 일반적으로 가장 좋은 결과
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
            logger.info("  PyMuPDF 추출: %d페이지, %d자", pages_to_read, len(best_text))
    except Exception as e:
        logger.debug("  PyMuPDF 실패: %s", e)

    # pdfplumber 시도
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
                    logger.info("  pdfplumber 추출: %d페이지, %d자", pages_to_read, len(best_text))
        except Exception as e:
            logger.debug("  pdfplumber 실패: %s", e)

    # PyPDF2 폴백
    if len(best_text) < 100:
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(str(pdf_path))
            pages_to_read = min(len(reader.pages), max_pages)
            text = ""
            for i in range(pages_to_read):
                page_text = reader.pages[i].extract_text()
                if page_text:
                    text += page_text + "\n\n"
            if len(text.strip()) > len(best_text):
                best_text = text.strip()
                logger.info("  PyPDF2 추출: %d페이지, %d자", pages_to_read, len(best_text))
        except Exception as e:
            logger.debug("  PyPDF2 실패: %s", e)

    if not best_text:
        logger.warning("  텍스트 추출 실패 (이미지 기반 PDF일 수 있음): %s", pdf_path.name)
    return best_text


def enrich_single_proposal(
    session: requests.Session,
    tech_number: str,
    detail_url: str,
    proposal_path: Path,
    pdf_dir: Path,
    max_pdf_size_mb: float = 30.0,
) -> bool:
    """단일 프로포절을 PDF 데이터로 강화."""
    newtec_id = extract_newtec_id(detail_url)
    if not newtec_id:
        logger.error("newtecId 추출 실패: %s", detail_url)
        return False

    logger.info("프로포절 강화 시작: %s (newtecId=%s)", tech_number, newtec_id)

    # 메인 페이지 방문 (쿠키/세션)
    full_url = KAIA_BASE + detail_url if detail_url.startswith("/") else detail_url
    session.get(full_url, timeout=30)
    time.sleep(1)

    # 파일 목록 조회
    files = get_file_list(session, newtec_id)
    if not files:
        logger.warning("  다운로드 가능한 파일 없음")
        return False

    logger.info("  파일 %d개 발견", len(files))

    # 특허 목록도 가져오기
    patents = get_patent_list(session, newtec_id)

    # 프로포절 로드
    with open(proposal_path, encoding="utf-8") as f:
        proposal = json.load(f)

    # 기존 특허 정보 업데이트
    if patents and not proposal.get("patents"):
        proposal["patents"] = patents
        logger.info("  특허 %d건 추가", len(patents))

    # 다운로드할 파일 선별 (우선순위 + 크기 제한)
    download_targets = []
    for file_info in files:
        name = file_info["name"]
        size = file_info["size"]

        classification = classify_file(name)
        if not classification:
            continue

        # 부록은 매우 크므로 (100MB+) 스킵
        if "부록" in name:
            logger.info("  부록 스킵 (%.1f MB): %s", size / 1024 / 1024, name)
            continue

        if size > max_pdf_size_mb * 1024 * 1024:
            logger.info("  크기 초과 스킵 (%.1f MB): %s", size / 1024 / 1024, name)
            continue

        download_targets.append({
            **file_info,
            **classification,
        })

    download_targets.sort(key=lambda x: x["priority"])

    # PDF 다운로드 + 텍스트 추출
    tech_pdf_dir = pdf_dir / tech_number
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

        time.sleep(2)  # rate limiting

    # 프로포절 업데이트
    updated = False
    # 모든 추출 텍스트를 합쳐서 all_pdf_text 구성 (검색용)
    all_pdf_text = "\n\n".join(t for t in extracted_texts.values() if len(t) > 50)

    for field, text in extracted_texts.items():
        if len(text) < 10:
            continue  # 의미없는 짧은 텍스트 무시

        if field == "pdf_content":
            proposal["pdf_content"] = text
            updated = True
        elif field == "prior_art_survey_text":
            proposal["prior_art_survey_text"] = text
            updated = True
        elif field == "tech_detail_text":
            proposal["tech_detail_text"] = text
            # tech_core_content가 빈약하고 새 텍스트가 더 길면 보강
            existing_core = proposal.get("tech_core_content", "")
            if len(text) > len(existing_core) and len(text) > 200:
                proposal["tech_core_content"] = text[:5000]
            updated = True
        else:
            proposal[field] = text
            updated = True

    # all_pdf_text 저장 (모든 PDF에서 추출한 전체 텍스트)
    if all_pdf_text:
        proposal["all_extracted_text"] = all_pdf_text

    # differentiation_claim 보강: PDF 내용에서 차별성 관련 부분 추출
    if not proposal.get("differentiation_claim") and proposal.get("pdf_content"):
        pdf_text = proposal["pdf_content"]
        # "차별" 또는 "기존" 또는 "개선" 키워드 주변 텍스트 추출
        diff_sections = []
        for keyword in ["차별", "기존 기술", "개선", "비교", "우수", "특징"]:
            idx = pdf_text.find(keyword)
            if idx >= 0:
                start = max(0, idx - 200)
                end = min(len(pdf_text), idx + 800)
                diff_sections.append(pdf_text[start:end])
        if diff_sections:
            proposal["differentiation_claim"] = "\n---\n".join(diff_sections[:3])

    # test_results 보강
    if not proposal.get("test_results") and proposal.get("pdf_content"):
        pdf_text = proposal["pdf_content"]
        for keyword in ["시험 결과", "성능 시험", "테스트", "실험 결과", "성적서"]:
            idx = pdf_text.find(keyword)
            if idx >= 0:
                start = max(0, idx - 100)
                end = min(len(pdf_text), idx + 1000)
                proposal["test_results"] = pdf_text[start:end]
                break

    # field_application 보강
    if not proposal.get("field_application") and proposal.get("pdf_content"):
        pdf_text = proposal["pdf_content"]
        for keyword in ["현장 적용", "시공 실적", "적용 현장", "활용 실적", "시공 사례"]:
            idx = pdf_text.find(keyword)
            if idx >= 0:
                start = max(0, idx - 100)
                end = min(len(pdf_text), idx + 1000)
                proposal["field_application"] = pdf_text[start:end]
                break

    if updated:
        proposal["enrichment_source"] = "kaia_pdf"
        proposal["enrichment_files"] = [t["name"] for t in download_targets if t["url"]]

        with open(proposal_path, "w", encoding="utf-8") as f:
            json.dump(proposal, f, ensure_ascii=False, indent=2, default=str)

        logger.info("  프로포절 업데이트 완료: %d개 필드", len(extracted_texts))
        return True
    else:
        logger.warning("  추출된 텍스트 없음")
        return False


def list_files_for_tech(tech_number: str) -> None:
    """특정 기술의 다운로드 파일 목록을 출력."""
    list_path = settings.dynamic_kb_dir / "cnt_designated" / "designated_list.json"
    with open(list_path, encoding="utf-8") as f:
        techs = json.load(f)

    detail_url = ""
    for t in techs:
        if t.get("tech_number") == tech_number:
            detail_url = t.get("detail_url", "")
            break

    if not detail_url:
        print(f"기술 {tech_number}의 detail_url 없음")
        return

    newtec_id = extract_newtec_id(detail_url)
    session = _create_session()
    full_url = KAIA_BASE + detail_url
    session.get(full_url, timeout=30)
    time.sleep(1)

    files = get_file_list(session, newtec_id)
    patents = get_patent_list(session, newtec_id)

    print(f"\n기술 {tech_number} (newtecId={newtec_id})")
    print(f"{'='*60}")
    print(f"다운로드 파일 ({len(files)}건):")
    for i, f in enumerate(files, 1):
        size_mb = f["size"] / 1024 / 1024
        match = classify_file(f["name"])
        tag = f" → [{match['field']}]" if match else ""
        print(f"  {i}. {f['name']} ({size_mb:.1f} MB){tag}")

    if patents:
        print(f"\n지식재산권 ({len(patents)}건):")
        for p in patents:
            print(f"  - [{p['type']}] {p['title']} ({p['register_number']})")


def _create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Referer": f"{KAIA_BASE}/portal/newtec/nView.do",
    })
    return session


def enrich_all_proposals(
    max_pdf_size_mb: float = 30.0,
    tech_numbers: list[str] | None = None,
) -> dict:
    """모든 프로포절을 PDF 데이터로 강화."""
    list_path = settings.dynamic_kb_dir / "cnt_designated" / "designated_list.json"
    with open(list_path, encoding="utf-8") as f:
        techs = json.load(f)

    # tech_number → detail_url 매핑
    url_map = {t["tech_number"]: t.get("detail_url", "") for t in techs}

    proposals_dir = settings.proposals_dir
    pdf_dir = proposals_dir / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)

    # 대상 프로포절
    proposal_files = sorted(proposals_dir.glob("proposal_*.json"))

    session = _create_session()
    stats = {"total": 0, "enriched": 0, "no_files": 0, "failed": 0, "skipped": 0}

    for pf in proposal_files:
        tech_number = pf.stem.replace("proposal_", "")

        if tech_numbers and tech_number not in tech_numbers:
            continue

        stats["total"] += 1

        # 이미 강화된 프로포절은 스킵
        with open(pf, encoding="utf-8") as f:
            existing = json.load(f)
        if existing.get("enrichment_source") == "kaia_pdf" and existing.get("pdf_content"):
            logger.info("이미 강화됨, 스킵: %s", tech_number)
            stats["skipped"] += 1
            continue

        detail_url = url_map.get(tech_number, "")
        if not detail_url:
            logger.warning("detail_url 없음: %s", tech_number)
            stats["failed"] += 1
            continue

        try:
            success = enrich_single_proposal(
                session, tech_number, detail_url, pf, pdf_dir,
                max_pdf_size_mb=max_pdf_size_mb,
            )
            if success:
                stats["enriched"] += 1
            else:
                stats["no_files"] += 1
        except Exception as e:
            logger.error("프로포절 강화 실패 %s: %s", tech_number, e)
            stats["failed"] += 1

        time.sleep(3)  # rate limiting between techs

    logger.info(
        "프로포절 강화 완료: 총 %d건, 강화 %d건, 파일없음 %d건, 실패 %d건, 스킵 %d건",
        stats["total"], stats["enriched"], stats["no_files"], stats["failed"], stats["skipped"],
    )
    return stats


def main():
    parser = argparse.ArgumentParser(description="KAIA PDF 다운로드 → 프로포절 강화")
    parser.add_argument("--tech-number", type=str, help="단건 처리 (기술번호)")
    parser.add_argument("--list-files", type=str, help="파일 목록만 확인 (기술번호)")
    parser.add_argument("--max-pdf-size", type=float, default=30.0, help="최대 PDF 크기 (MB, 기본 30)")
    parser.add_argument("--force", action="store_true", help="이미 강화된 프로포절도 재처리")
    args = parser.parse_args()

    if args.list_files:
        list_files_for_tech(args.list_files)
    elif args.tech_number:
        enrich_all_proposals(
            max_pdf_size_mb=args.max_pdf_size,
            tech_numbers=[args.tech_number],
        )
    else:
        enrich_all_proposals(max_pdf_size_mb=args.max_pdf_size)


if __name__ == "__main__":
    main()
