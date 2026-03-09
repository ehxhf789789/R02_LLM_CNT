"""건설신기술 매뉴얼 PDF 파싱 모듈.

PDF 매뉴얼에서 평가 기준, 절차, 서식 등을 추출하여 구조화된 지식으로 변환한다.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from config.settings import settings

logger = logging.getLogger(__name__)


def parse_manual_pdf(pdf_path: Path) -> dict:
    """매뉴얼 PDF를 파싱하여 섹션별 텍스트를 추출.

    Returns:
        dict: 섹션명을 키로, 텍스트 내용을 값으로 하는 딕셔너리.
    """
    try:
        import pdfplumber
    except ImportError:
        logger.error("pdfplumber 패키지 필요: pip install pdfplumber")
        return {}

    if not pdf_path.exists():
        logger.error("PDF 파일 없음: %s", pdf_path)
        return {}

    sections: dict[str, str] = {}
    current_section = "서문"
    current_text: list[str] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text:
                continue

            for line in text.split("\n"):
                stripped = line.strip()
                if not stripped:
                    continue

                # 섹션 헤더 감지 (제N장, N., 부록 등)
                if _is_section_header(stripped):
                    if current_text:
                        sections[current_section] = "\n".join(current_text)
                    current_section = stripped
                    current_text = []
                else:
                    current_text.append(stripped)

        # 마지막 섹션 저장
        if current_text:
            sections[current_section] = "\n".join(current_text)

    logger.info("매뉴얼 파싱 완료: %d개 섹션 추출", len(sections))
    return sections


def _is_section_header(line: str) -> bool:
    """섹션 헤더인지 판별."""
    import re

    patterns = [
        r"^제\s*\d+\s*장",      # 제1장, 제 2 장
        r"^제\s*\d+\s*절",      # 제1절
        r"^제\s*\d+\s*조",      # 제1조
        r"^\d+\.\s+\S",         # 1. 제목
        r"^부록",               # 부록
        r"^별표",               # 별표
        r"^[IVX]+\.\s+\S",     # I. 제목
    ]
    return any(re.match(p, line) for p in patterns)


def save_parsed_manual(sections: dict, output_path: Path | None = None) -> Path:
    """파싱 결과를 JSON 파일로 저장."""
    if output_path is None:
        output_path = settings.static_kb_dir / "evaluation_manual" / "manual_parsed.json"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(sections, f, ensure_ascii=False, indent=2)

    logger.info("파싱 결과 저장: %s", output_path)
    return output_path


def load_parsed_manual(path: Path | None = None) -> dict:
    """저장된 파싱 결과를 로드."""
    if path is None:
        path = settings.static_kb_dir / "evaluation_manual" / "manual_parsed.json"

    if not path.exists():
        return {}

    with open(path, encoding="utf-8") as f:
        return json.load(f)
