"""입력 데이터셋(제안기술) 빌더.

KAIA 지정기술 상세 페이지 + PDF 홍보자료에서
평가 입력용 제안기술(proposal) 데이터셋을 구축한다.

통제 조건:
  - 모든 테스트 케이스는 이미 지정된(approved) 기술
  - KB에서 해당 기술을 제외해야 함 (controlled experiment)
"""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path

from config.settings import settings
from src.dynamic_kb.kaia_detail_crawler import KaiaDetailCrawler, KaiaDetailInfo
from src.dynamic_kb.pdf_parser import PDFParser

logger = logging.getLogger(__name__)


class ProposalBuilder:
    """평가 입력용 제안기술 데이터셋 빌더."""

    def __init__(
        self,
        crawler: KaiaDetailCrawler | None = None,
        pdf_parser: PDFParser | None = None,
        output_dir: Path | None = None,
    ):
        self.crawler = crawler or KaiaDetailCrawler()
        self.pdf_parser = pdf_parser or PDFParser()
        self.output_dir = output_dir or settings.proposals_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def build_from_tech_numbers(
        self,
        tech_numbers: list[str],
        download_pdfs: bool = True,
    ) -> list[dict]:
        """기술 번호 리스트에서 제안기술 데이터셋 구축."""
        proposals = []

        # detail_url 매핑 로드
        detail_urls = self._load_detail_urls()

        for tech_num in tech_numbers:
            logger.info("제안기술 구축: 기술번호 %s", tech_num)

            # 상세 정보 수집
            detail_url = detail_urls.get(tech_num, "")
            if detail_url:
                if download_pdfs:
                    info = self.crawler.fetch_and_download(detail_url, tech_num)
                else:
                    info = self.crawler.fetch_detail(detail_url)
                    if not info.tech_number:
                        info.tech_number = tech_num
            else:
                info = self.crawler.fetch_by_tech_number(tech_num)

            # PDF 파싱
            pdf_text = ""
            pdf_fields = {}
            for file_info in info.download_files:
                local_path = file_info.get("local_path")
                if local_path and Path(local_path).exists():
                    parsed = self.pdf_parser.parse(local_path)
                    pdf_text = parsed.text
                    pdf_fields = self.pdf_parser.extract_proposal_fields(parsed)
                    break  # 첫 번째 PDF만 사용

            # proposal 구축
            proposal = self.crawler.build_proposal_from_detail(info, pdf_text)

            # PDF에서 추출한 필드로 보강
            for key, value in pdf_fields.items():
                if value and (not proposal.get(key) or key == "full_text"):
                    proposal[key] = value

            # 저장
            out_path = self.output_dir / f"proposal_{tech_num}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(proposal, f, ensure_ascii=False, indent=2, default=str)

            proposals.append(proposal)
            logger.info("제안기술 저장: %s (%s)", out_path.name, proposal.get("tech_name", ""))

        return proposals

    def select_test_cases(
        self,
        designated_list_path: Path | None = None,
        n_cases: int = 10,
        field_filter: str | None = None,
        status_filter: str = "유효",
        seed: int | None = None,
    ) -> list[str]:
        """지정기술 목록에서 테스트 케이스를 선별.

        기준:
          - 상태: '유효' (실제 통과된 기술)
          - 분야: 선택적 필터
          - 무작위 선별 (재현성을 위해 seed 지정 가능)

        Returns:
            선별된 기술 번호 리스트
        """
        path = designated_list_path or (settings.dynamic_kb_dir / "cnt_designated" / "designated_list.json")
        if not path.exists():
            logger.error("지정기술 목록 없음: %s", path)
            return []

        with open(path, encoding="utf-8") as f:
            all_techs = json.load(f)

        # 홍보자료(enriched) 보유 기술만 후보로 선정
        enriched_dir = path.parent / "enriched"
        if enriched_dir.exists():
            enriched_nums = {
                f.stem.replace("designated_", "")
                for f in enriched_dir.glob("designated_*.json")
            }
            all_techs = [t for t in all_techs if str(t.get("tech_number", "")) in enriched_nums]
            logger.info("홍보자료 보유 기술: %d건", len(all_techs))

        # 필터링
        candidates = all_techs
        if status_filter:
            candidates = [t for t in candidates if status_filter in t.get("status", "")]
        if field_filter:
            candidates = [t for t in candidates if field_filter in t.get("tech_field", "")]

        if not candidates:
            logger.warning("조건에 맞는 기술 없음")
            return []

        if seed is not None:
            random.seed(seed)

        selected = random.sample(candidates, min(n_cases, len(candidates)))
        tech_numbers = [t.get("tech_number", "") for t in selected if t.get("tech_number")]

        logger.info(
            "테스트 케이스 선별: %d/%d건 (분야: %s, 상태: %s)",
            len(tech_numbers), len(candidates), field_filter or "전체", status_filter,
        )

        return tech_numbers

    def _load_detail_urls(self) -> dict[str, str]:
        """designated_list.json에서 tech_number → detail_url 매핑을 로드."""
        path = settings.dynamic_kb_dir / "cnt_designated" / "designated_list.json"
        if not path.exists():
            return {}
        with open(path, encoding="utf-8") as f:
            items = json.load(f)
        return {
            item["tech_number"]: item.get("detail_url", "")
            for item in items
            if item.get("tech_number")
        }

    def load_proposals(self) -> list[dict]:
        """저장된 제안기술 데이터셋 로드."""
        proposals = []
        for f in sorted(self.output_dir.glob("proposal_*.json")):
            with open(f, encoding="utf-8") as fp:
                proposals.append(json.load(fp))
        return proposals
