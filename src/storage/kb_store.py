"""지식베이스 저장소.

정적 KB와 동적 KB를 JSON 파일 기반으로 저장·조회한다.
각 에이전트 프로파일별로 독립된 동적 KB 디렉토리를 생성한다.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path

from config.settings import settings
from src.dynamic_kb.kaia_crawler import CNTDesignatedTech
from src.dynamic_kb.kipris_client import PatentRecord
from src.dynamic_kb.scienceon_client import PaperRecord
from src.dynamic_kb.semantic_scholar_client import SemanticScholarRecord
from src.dynamic_kb.kci_client import KCIRecord
from src.dynamic_kb.codil_crawler import CODILRecord
from src.dynamic_kb.openalex_client import OpenAlexRecord

logger = logging.getLogger(__name__)


class KBStore:
    """파일 기반 지식베이스 저장소."""

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or settings.data_dir
        self.static_dir = self.base_dir / "static"
        self.dynamic_dir = self.base_dir / "dynamic"

    # --- 특허 데이터 저장/로드 ---

    def save_patents(
        self,
        records: list[PatentRecord],
        category_code: str,
        keyword: str,
    ) -> Path:
        """특허 검색 결과를 카테고리별로 저장."""
        out_dir = self.dynamic_dir / "patents" / category_code
        out_dir.mkdir(parents=True, exist_ok=True)

        safe_keyword = keyword.replace(" ", "_").replace("/", "_")[:50]
        out_path = out_dir / f"{safe_keyword}.json"

        data = [asdict(r) for r in records]
        self._write_json(out_path, data)
        logger.info("특허 %d건 저장: %s", len(records), out_path)
        return out_path

    def load_patents(self, category_code: str) -> list[dict]:
        """카테고리별 저장된 특허 데이터를 모두 로드."""
        pat_dir = self.dynamic_dir / "patents" / category_code
        if not pat_dir.exists():
            return []

        all_records = []
        for f in pat_dir.glob("*.json"):
            all_records.extend(self._read_json(f))
        return all_records

    # --- 논문 데이터 저장/로드 ---

    def save_papers(
        self,
        records: list[PaperRecord],
        category_code: str,
        keyword: str,
    ) -> Path:
        """논문 검색 결과를 카테고리별로 저장."""
        out_dir = self.dynamic_dir / "papers" / category_code
        out_dir.mkdir(parents=True, exist_ok=True)

        safe_keyword = keyword.replace(" ", "_").replace("/", "_")[:50]
        out_path = out_dir / f"{safe_keyword}.json"

        data = [asdict(r) for r in records]
        self._write_json(out_path, data)
        logger.info("논문 %d건 저장: %s", len(records), out_path)
        return out_path

    def load_papers(self, category_code: str) -> list[dict]:
        """카테고리별 저장된 논문 데이터를 모두 로드."""
        paper_dir = self.dynamic_dir / "papers" / category_code
        if not paper_dir.exists():
            return []

        all_records = []
        for f in paper_dir.glob("*.json"):
            all_records.extend(self._read_json(f))
        return all_records

    # --- 지정 건설신기술 데이터 ---

    def save_designated_techs(self, techs: list[CNTDesignatedTech]) -> Path:
        """지정 건설신기술 목록 저장."""
        out_dir = self.dynamic_dir / "cnt_designated"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "designated_list.json"

        data = [asdict(t) for t in techs]
        self._write_json(out_path, data)
        logger.info("지정 건설신기술 %d건 저장: %s", len(techs), out_path)
        return out_path

    def load_designated_techs(self, enriched_only: bool = False) -> list[dict]:
        """저장된 지정 건설신기술 목록 로드.

        Args:
            enriched_only: True이면 홍보자료(enriched PDF)가 있는 기술만 반환.
                           KB용으로는 False(전체 포함)가 기본 — 홍보자료 미보유 건도
                           존재 정보로 포함해야 신규성/진보성 판단이 가능하다.
                           입력데이터(프로포절) 선별 시에만 True로 사용한다.
        """
        path = self.dynamic_dir / "cnt_designated" / "designated_list.json"
        if not path.exists():
            return []
        all_techs = self._read_json(path)
        if not enriched_only:
            return all_techs
        enriched_dir = self.dynamic_dir / "cnt_designated" / "enriched"
        if not enriched_dir.exists():
            logger.warning("enriched 디렉토리 없음: %s", enriched_dir)
            return all_techs
        enriched_nums = {
            f.stem.replace("designated_", "")
            for f in enriched_dir.glob("designated_*.json")
        }
        filtered = [t for t in all_techs if str(t.get("tech_number", "")) in enriched_nums]
        logger.info("지정기술 필터링: %d/%d건 (홍보자료 보유)", len(filtered), len(all_techs))
        return filtered

    # --- Semantic Scholar 논문 데이터 ---

    def save_scholar_papers(
        self,
        records: list[SemanticScholarRecord],
        category_code: str,
        keyword: str,
    ) -> Path:
        """Semantic Scholar 논문 검색 결과를 카테고리별로 저장."""
        out_dir = self.dynamic_dir / "scholar_papers" / category_code
        out_dir.mkdir(parents=True, exist_ok=True)

        safe_keyword = keyword.replace(" ", "_").replace("/", "_")[:50]
        out_path = out_dir / f"{safe_keyword}.json"

        data = [asdict(r) for r in records]
        self._write_json(out_path, data)
        logger.info("Semantic Scholar 논문 %d건 저장: %s", len(records), out_path)
        return out_path

    def load_scholar_papers(self, category_code: str) -> list[dict]:
        """카테고리별 저장된 Semantic Scholar 논문 데이터를 모두 로드."""
        paper_dir = self.dynamic_dir / "scholar_papers" / category_code
        if not paper_dir.exists():
            return []
        all_records = []
        for f in paper_dir.glob("*.json"):
            all_records.extend(self._read_json(f))
        return all_records

    # --- KCI 논문 데이터 ---

    def save_kci_papers(
        self,
        records: list[KCIRecord],
        category_code: str,
        keyword: str,
    ) -> Path:
        """KCI 논문 검색 결과를 카테고리별로 저장."""
        out_dir = self.dynamic_dir / "kci_papers" / category_code
        out_dir.mkdir(parents=True, exist_ok=True)

        safe_keyword = keyword.replace(" ", "_").replace("/", "_")[:50]
        out_path = out_dir / f"{safe_keyword}.json"

        data = [asdict(r) for r in records]
        self._write_json(out_path, data)
        logger.info("KCI 논문 %d건 저장: %s", len(records), out_path)
        return out_path

    def load_kci_papers(self, category_code: str) -> list[dict]:
        """카테고리별 저장된 KCI 논문 데이터를 모두 로드."""
        paper_dir = self.dynamic_dir / "kci_papers" / category_code
        if not paper_dir.exists():
            return []
        all_records = []
        for f in paper_dir.glob("*.json"):
            all_records.extend(self._read_json(f))
        return all_records

    # --- CODIL 건설기준 데이터 ---

    def save_codil_docs(
        self,
        records: list[CODILRecord],
        category_code: str,
        keyword: str,
    ) -> Path:
        """CODIL 문서를 카테고리별로 저장."""
        out_dir = self.dynamic_dir / "codil" / category_code
        out_dir.mkdir(parents=True, exist_ok=True)

        safe_keyword = keyword.replace(" ", "_").replace("/", "_")[:50]
        out_path = out_dir / f"{safe_keyword}.json"

        data = [asdict(r) for r in records]
        self._write_json(out_path, data)
        logger.info("CODIL 문서 %d건 저장: %s", len(records), out_path)
        return out_path

    def load_codil_docs(self, category_code: str) -> list[dict]:
        """카테고리별 저장된 CODIL 문서를 모두 로드."""
        doc_dir = self.dynamic_dir / "codil" / category_code
        if not doc_dir.exists():
            return []
        all_records = []
        for f in doc_dir.glob("*.json"):
            all_records.extend(self._read_json(f))
        return all_records

    # --- OpenAlex 논문 데이터 ---

    def save_openalex_papers(
        self,
        records: list[OpenAlexRecord],
        category_code: str,
        keyword: str,
    ) -> Path:
        """OpenAlex 논문 검색 결과를 카테고리별로 저장."""
        out_dir = self.dynamic_dir / "openalex_papers" / category_code
        out_dir.mkdir(parents=True, exist_ok=True)

        safe_keyword = keyword.replace(" ", "_").replace("/", "_")[:50]
        out_path = out_dir / f"{safe_keyword}.json"

        data = [asdict(r) for r in records]
        self._write_json(out_path, data)
        logger.info("OpenAlex 논문 %d건 저장: %s", len(records), out_path)
        return out_path

    def load_openalex_papers(self, category_code: str) -> list[dict]:
        """카테고리별 저장된 OpenAlex 논문 데이터를 모두 로드 (하위 디렉토리 포함)."""
        paper_dir = self.dynamic_dir / "openalex_papers" / category_code
        if not paper_dir.exists():
            return []
        all_records = []
        for f in paper_dir.rglob("*.json"):
            all_records.extend(self._read_json(f))
        return all_records

    # --- KCSC 건설기준 데이터 ---

    def load_kcsc_standards(self, category_code: str) -> list[dict]:
        """카테고리별 저장된 KCSC 건설기준을 모두 로드."""
        std_dir = self.dynamic_dir / "kcsc_standards" / category_code
        if not std_dir.exists():
            return []
        all_records = []
        for f in std_dir.glob("*.json"):
            all_records.extend(self._read_json(f))
        return all_records

    # --- CrossRef 논문 데이터 ---

    def load_crossref_papers(self, category_code: str) -> list[dict]:
        """카테고리별 저장된 CrossRef 논문 데이터를 모두 로드."""
        paper_dir = self.dynamic_dir / "crossref_papers" / category_code
        if not paper_dir.exists():
            return []
        all_records = []
        for f in paper_dir.glob("*.json"):
            all_records.extend(self._read_json(f))
        return all_records

    # --- 에이전트별 KB ---

    def save_agent_kb(self, agent_id: str, kb_data: dict) -> Path:
        """개별 에이전트의 통합 KB를 저장."""
        out_dir = self.dynamic_dir / "agent_kb"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{agent_id}.json"

        self._write_json(out_path, kb_data)
        logger.info("에이전트 KB 저장: %s", out_path)
        return out_path

    def load_agent_kb(self, agent_id: str) -> dict:
        """개별 에이전트의 통합 KB 로드."""
        path = self.dynamic_dir / "agent_kb" / f"{agent_id}.json"
        if not path.exists():
            return {}
        return self._read_json(path)

    # --- 유틸리티 ---

    def _write_json(self, path: Path, data) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    def _read_json(self, path: Path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
