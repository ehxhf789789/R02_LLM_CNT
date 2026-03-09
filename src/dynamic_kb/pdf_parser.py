"""PDF 파서 (건설신기술 홍보자료용).

KAIA ntech에서 다운로드한 홍보용 PDF 책자를 파싱하여
텍스트를 추출한다.

구조:
  - 홍보용 책자 본문: 기술 개요, 특징, 시공법 등
  - 부록: 시험성적서, 인증서, 현장 사진 등
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

logger = logging.getLogger(__name__)


@dataclass
class ParsedPDF:
    """파싱된 PDF 결과."""
    file_path: str = ""
    total_pages: int = 0
    text: str = ""
    sections: dict[str, str] = field(default_factory=dict)
    tables: list[list[list[str]]] = field(default_factory=list)


class PDFParser:
    """건설신기술 홍보자료 PDF 파서."""

    # 건설신기술 홍보자료에서 흔히 사용되는 섹션 헤더
    SECTION_PATTERNS = [
        r"(?:^|\n)\s*((?:\d+\.?\s*)?기술\s*(?:개요|소개|설명))",
        r"(?:^|\n)\s*((?:\d+\.?\s*)?(?:핵심|주요)\s*(?:기술|내용))",
        r"(?:^|\n)\s*((?:\d+\.?\s*)?기존\s*기술\s*(?:대비|비교|과의))",
        r"(?:^|\n)\s*((?:\d+\.?\s*)?시공\s*(?:방법|절차|순서))",
        r"(?:^|\n)\s*((?:\d+\.?\s*)?(?:성능|품질)\s*(?:시험|검증))",
        r"(?:^|\n)\s*((?:\d+\.?\s*)?현장\s*(?:적용|시공)\s*(?:사례|실적))",
        r"(?:^|\n)\s*((?:\d+\.?\s*)?(?:특허|지식재산권))",
        r"(?:^|\n)\s*((?:\d+\.?\s*)?(?:인증|인정)\s*(?:현황|사항))",
        r"(?:^|\n)\s*((?:\d+\.?\s*)?안전성)",
        r"(?:^|\n)\s*((?:\d+\.?\s*)?친환경)",
        r"(?:^|\n)\s*((?:\d+\.?\s*)?경제성)",
        r"(?:^|\n)\s*(부록|참고자료|첨부)",
    ]

    def parse(self, pdf_path: str | Path) -> ParsedPDF:
        """PDF 파일을 파싱하여 텍스트와 섹션을 추출."""
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            logger.error("PDF 파일 없음: %s", pdf_path)
            return ParsedPDF(file_path=str(pdf_path))

        result = ParsedPDF(file_path=str(pdf_path))

        try:
            with pdfplumber.open(pdf_path) as pdf:
                result.total_pages = len(pdf.pages)
                page_texts = []

                for page in pdf.pages:
                    text = page.extract_text() or ""
                    page_texts.append(text)

                    # 테이블 추출
                    tables = page.extract_tables()
                    if tables:
                        result.tables.extend(tables)

                result.text = "\n\n".join(page_texts)

            # 섹션 분류
            result.sections = self._extract_sections(result.text)

            logger.info(
                "PDF 파싱 완료: %s (%d페이지, %d자, %d섹션)",
                pdf_path.name,
                result.total_pages,
                len(result.text),
                len(result.sections),
            )

        except Exception as e:
            logger.error("PDF 파싱 실패 (%s): %s", pdf_path, e)

        return result

    def _extract_sections(self, text: str) -> dict[str, str]:
        """텍스트에서 섹션 헤더를 찾아 분리."""
        sections: dict[str, str] = {}

        # 모든 섹션 헤더 위치 찾기
        markers: list[tuple[int, str]] = []
        for pattern in self.SECTION_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                markers.append((match.start(), match.group(1).strip()))

        if not markers:
            sections["전문"] = text
            return sections

        markers.sort(key=lambda x: x[0])

        # 첫 마커 전의 텍스트
        if markers[0][0] > 50:
            sections["서두"] = text[:markers[0][0]].strip()

        # 각 마커 사이의 텍스트
        for i, (pos, header) in enumerate(markers):
            end_pos = markers[i + 1][0] if i + 1 < len(markers) else len(text)
            content = text[pos:end_pos].strip()
            # 헤더 자체를 제거
            content = content[len(header):].strip()
            if content:
                sections[header] = content

        return sections

    def extract_proposal_fields(self, parsed: ParsedPDF) -> dict:
        """파싱된 PDF에서 평가 입력용 필드를 추출."""
        fields: dict[str, str] = {}

        for header, content in parsed.sections.items():
            header_lower = header.lower()

            if "개요" in header_lower or "소개" in header_lower:
                fields["tech_description"] = content[:2000]
            elif "핵심" in header_lower or "내용" in header_lower:
                fields["tech_core_content"] = content[:3000]
            elif "기존" in header_lower or "대비" in header_lower or "비교" in header_lower:
                fields["differentiation_claim"] = content[:2000]
            elif "시험" in header_lower or "검증" in header_lower or "성능" in header_lower:
                fields["test_results"] = content[:2000]
            elif "현장" in header_lower or "적용" in header_lower or "실적" in header_lower:
                fields["field_application"] = content[:2000]
            elif "안전" in header_lower:
                fields["safety_info"] = content[:1000]
            elif "친환경" in header_lower:
                fields["eco_info"] = content[:1000]

        # 전체 텍스트도 포함
        fields["full_text"] = parsed.text[:10000]

        return fields
