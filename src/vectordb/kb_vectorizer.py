"""벡터 KB 구축기 (LanceDB 기반).

지식베이스 데이터를 임베딩하여 LanceDB에 저장하고,
에이전트별 RAG 검색을 지원한다.

핵심 기능:
  - 특허/논문/지정기술/CODIL 데이터를 청킹 + 임베딩
  - 메타데이터 필터링 (분류, 소스 유형 등)
  - 테스트 케이스 제외 (controlled experiment)
"""

from __future__ import annotations

import json
import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import lancedb
import pyarrow as pa

from config.settings import settings
from src.llm.bedrock_client import BedrockEmbeddingClient

logger = logging.getLogger(__name__)

# LanceDB 스키마
KB_SCHEMA = pa.schema([
    pa.field("id", pa.string()),
    pa.field("text", pa.string()),
    pa.field("source_type", pa.string()),       # patent, paper, designated_tech, codil
    pa.field("category_major", pa.string()),     # 대분류
    pa.field("category_middle", pa.string()),    # 중분류
    pa.field("title", pa.string()),
    pa.field("tech_number", pa.string()),        # 지정기술 번호 (제외용)
    pa.field("publish_year", pa.string()),       # 발행/출원 연도
    pa.field("metadata_json", pa.string()),      # 추가 메타데이터
    pa.field("vector", pa.list_(pa.float32(), 1024)),  # Cohere embed dim=1024
])


@dataclass
class KBDocument:
    """KB에 저장할 단일 문서."""
    text: str
    source_type: str
    category_major: str = ""
    category_middle: str = ""
    title: str = ""
    tech_number: str = ""
    publish_year: str = ""
    metadata: dict | None = None


class KBVectorizer:
    """LanceDB 기반 벡터 KB 구축기."""

    TABLE_NAME = "cnt_knowledge_base"

    def __init__(
        self,
        db_path: Path | None = None,
        embedding_client: BedrockEmbeddingClient | None = None,
        embedding_dim: int = 1024,
    ):
        self.db_path = db_path or settings.vector_db_dir
        self.db_path.mkdir(parents=True, exist_ok=True)
        self.db = lancedb.connect(str(self.db_path))
        self.embedding_client = embedding_client
        self.embedding_dim = embedding_dim
        self._excluded_tech_numbers: set[str] = set()

    def set_excluded_techs(self, tech_numbers: list[str]) -> None:
        """테스트 케이스로 사용할 기술 번호를 제외 목록에 등록."""
        self._excluded_tech_numbers = set(tech_numbers)
        logger.info("KB 제외 목록 설정: %d건", len(self._excluded_tech_numbers))

    def build_from_store(
        self,
        store_base_dir: Path | None = None,
        batch_size: int = 50,
    ) -> int:
        """저장된 KB 데이터를 벡터화하여 LanceDB에 적재.

        Returns:
            적재된 문서 수
        """
        base_dir = store_base_dir or settings.dynamic_kb_dir
        documents: list[KBDocument] = []

        # 특허 데이터 (품질 필터: 초록 또는 청구항이 있는 레코드만)
        patent_skipped = 0
        for patent_dir_name in ["patents", "patents_recent"]:
            patents_dir = base_dir / patent_dir_name
            if patents_dir.exists():
                for cat_dir in patents_dir.iterdir():
                    if cat_dir.is_dir():
                        for f in cat_dir.glob("*.json"):
                            records = self._load_json(f)
                            for r in records:
                                text = self._format_patent(r)
                                if len(text) < 80:  # 포맷 오버헤드 제외 시 실질 콘텐츠 부족
                                    patent_skipped += 1
                                    continue
                                documents.append(KBDocument(
                                    text=text,
                                    source_type="patent",
                                    category_major=cat_dir.name,
                                    title=r.get("title", ""),
                                    publish_year=self._extract_patent_year(r),
                                    metadata=r,
                                ))
        if patent_skipped:
            logger.info("특허 품질 필터: %d건 스킵 (콘텐츠 부족)", patent_skipped)

        # 논문 데이터 (기존 + OpenAlex + CrossRef) — 품질 필터: 초록 보유 논문만
        paper_skipped = 0
        for paper_dir_name in ["scholar_papers", "kci_papers", "papers",
                                "openalex_papers", "crossref_papers",
                                "korean_papers"]:
            papers_dir = base_dir / paper_dir_name
            if papers_dir.exists():
                for cat_dir in papers_dir.iterdir():
                    if cat_dir.is_dir():
                        # JSON 파일 직접 수집
                        for f in cat_dir.glob("*.json"):
                            records = self._load_json(f)
                            for r in records:
                                abstract = r.get("abstract", "")
                                if not abstract or len(abstract) < 30:
                                    paper_skipped += 1
                                    continue
                                documents.append(KBDocument(
                                    text=self._format_paper(r),
                                    source_type="paper",
                                    category_major=cat_dir.name,
                                    title=r.get("title", ""),
                                    publish_year=str(r.get("publish_year", r.get("year", ""))),
                                    metadata=r,
                                ))
                        # 하위 디렉토리 (OpenAlex 평가차원별)
                        for sub_dir in cat_dir.iterdir():
                            if sub_dir.is_dir():
                                for f in sub_dir.glob("*.json"):
                                    records = self._load_json(f)
                                    for r in records:
                                        abstract = r.get("abstract", "")
                                        if not abstract or len(abstract) < 30:
                                            paper_skipped += 1
                                            continue
                                        documents.append(KBDocument(
                                            text=self._format_paper(r),
                                            source_type="paper",
                                            category_major=cat_dir.name,
                                            title=r.get("title", ""),
                                            publish_year=str(r.get("publish_year", r.get("year", ""))),
                                            metadata=r,
                                        ))
        if paper_skipped:
            logger.info("논문 품질 필터: %d건 스킵 (초록 부재)", paper_skipped)

        # 지정기술 데이터 — 전체 포함 (홍보자료 미보유 건도 존재 정보로 KB에 포함)
        # 신규성/진보성 판단 시 기지정 기술의 존재를 알아야 하므로 전체 목록을 KB에 넣는다.
        # enriched(PDF 상세) 데이터는 별도 섹션에서 추가한다.
        designated_path = base_dir / "cnt_designated" / "designated_list.json"
        if designated_path.exists():
            records = self._load_json(designated_path)
            for r in records:
                tech_num = r.get("tech_number", "")
                # 제외 목록 체크 (평가 대상 기술 자기참조 방지)
                if tech_num in self._excluded_tech_numbers:
                    logger.debug("제외 기술: %s (%s)", tech_num, r.get("tech_name", ""))
                    continue
                documents.append(KBDocument(
                    text=self._format_designated_tech(r),
                    source_type="designated_tech",
                    category_major=self._extract_major(r.get("tech_field", "")),
                    category_middle=self._extract_middle(r.get("tech_field", "")),
                    title=r.get("tech_name", ""),
                    tech_number=tech_num,
                    publish_year=str(r.get("designated_date", ""))[:4],
                    metadata=r,
                ))

        # 지정기술 enriched 데이터 (PDF 추출 텍스트 포함)
        enriched_dir = base_dir / "cnt_designated" / "enriched"
        if enriched_dir.exists():
            for f in enriched_dir.glob("designated_*.json"):
                data = self._load_json(f)
                if isinstance(data, list):
                    data = data[0]
                tech_num = data.get("tech_number", "")
                if tech_num in self._excluded_tech_numbers:
                    continue
                texts = data.get("extracted_texts", {})
                # 선행기술조사, 기술상세, 소개자료 등을 별도 문서로 추가
                for field_name, text in texts.items():
                    if len(text) < 100:
                        continue
                    # 텍스트가 너무 길면 청킹 (2000자씩)
                    chunks = [text[i:i+2000] for i in range(0, min(len(text), 8000), 2000)]
                    for chunk_idx, chunk in enumerate(chunks):
                        documents.append(KBDocument(
                            text=self._format_enriched_tech(data, field_name, chunk),
                            source_type="designated_tech",
                            category_major=self._extract_major(data.get("tech_field", "")),
                            category_middle=self._extract_middle(data.get("tech_field", "")),
                            title=data.get("tech_name", ""),
                            tech_number=tech_num,
                            metadata={"field": field_name, "chunk": chunk_idx},
                        ))

        # CODIL 데이터
        codil_dir = base_dir / "codil"
        if codil_dir.exists():
            for cat_dir in codil_dir.iterdir():
                if cat_dir.is_dir():
                    for f in cat_dir.glob("*.json"):
                        records = self._load_json(f)
                        for r in records:
                            documents.append(KBDocument(
                                text=self._format_codil(r),
                                source_type="codil",
                                category_major=cat_dir.name,
                                title=r.get("title", ""),
                                publish_year=str(r.get("publish_year", r.get("year", ""))),
                                metadata=r,
                            ))

        # KCSC 건설기준 데이터
        kcsc_dir = base_dir / "kcsc_standards"
        if kcsc_dir.exists():
            for cat_dir in kcsc_dir.iterdir():
                if cat_dir.is_dir():
                    for f in cat_dir.glob("*.json"):
                        records = self._load_json(f)
                        for r in records:
                            documents.append(KBDocument(
                                text=self._format_kcsc(r),
                                source_type="kcsc_standard",
                                category_major=cat_dir.name,
                                title=r.get("title", r.get("code", "")),
                                metadata=r,
                            ))

        if not documents:
            logger.warning("벡터화할 문서가 없습니다.")
            return 0

        logger.info("벡터화 대상: %d건 (제외: %d건)", len(documents), len(self._excluded_tech_numbers))

        # 배치 임베딩 + LanceDB 적재
        return self._vectorize_and_store(documents, batch_size)

    def _vectorize_and_store(
        self,
        documents: list[KBDocument],
        batch_size: int,
    ) -> int:
        """문서를 배치로 임베딩하고 LanceDB에 저장."""
        if not self.embedding_client:
            self.embedding_client = BedrockEmbeddingClient()

        all_rows = []

        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            texts = [d.text for d in batch]

            logger.info("임베딩 배치 %d/%d (%d건)", i // batch_size + 1,
                       (len(documents) + batch_size - 1) // batch_size, len(batch))

            embeddings = self.embedding_client.embed_texts(texts, input_type="search_document")

            for doc, emb in zip(batch, embeddings):
                doc_id = hashlib.md5(doc.text[:200].encode()).hexdigest()
                row = {
                    "id": doc_id,
                    "text": doc.text,
                    "source_type": doc.source_type,
                    "category_major": doc.category_major,
                    "category_middle": doc.category_middle,
                    "title": doc.title,
                    "tech_number": doc.tech_number,
                    "publish_year": doc.publish_year,
                    "metadata_json": json.dumps(doc.metadata or {}, ensure_ascii=False, default=str),
                    "vector": emb,
                }
                all_rows.append(row)

        # LanceDB에 저장 (테이블이 존재하면 덮어쓰기)
        if all_rows:
            table = self.db.create_table(
                self.TABLE_NAME,
                data=all_rows,
                mode="overwrite",
            )
            logger.info("LanceDB 저장 완료: %d건 → %s", len(all_rows), self.db_path)

        return len(all_rows)

    def search(
        self,
        query: str,
        top_k: int = 20,
        source_type: str | None = None,
        category_major: str | None = None,
        exclude_tech_numbers: list[str] | None = None,
        cutoff_year: int | None = None,
    ) -> list[dict]:
        """벡터 유사도 검색.

        Args:
            query: 검색 쿼리
            top_k: 상위 K개 결과
            source_type: 소스 유형 필터 (patent, paper, designated_tech, codil)
            category_major: 대분류 필터
            exclude_tech_numbers: 제외할 기술 번호
            cutoff_year: 시간적 커트오프 — 이 연도 이후 발행된 자료를 제외.
                         통제 실험에서 평가 대상 기술의 지정연도를 기준으로
                         미래 정보 유입을 방지한다.
        """
        if not self.embedding_client:
            self.embedding_client = BedrockEmbeddingClient()

        try:
            table = self.db.open_table(self.TABLE_NAME)
        except Exception:
            logger.warning("KB 테이블이 없습니다. 먼저 build_from_store()를 실행하세요.")
            return []

        query_embedding = self.embedding_client.embed_query(query)

        search = table.search(query_embedding).limit(top_k * 2)  # 필터링 여유분

        results = search.to_pandas()

        # 메타데이터 필터링
        if source_type:
            results = results[results["source_type"] == source_type]
        if category_major:
            results = results[results["category_major"] == category_major]

        # 제외 기술 필터
        exclude_set = set(exclude_tech_numbers or []) | self._excluded_tech_numbers
        if exclude_set:
            results = results[~results["tech_number"].isin(exclude_set)]

        # 시간적 커트오프: cutoff_year 이후 발행 자료 제외
        if cutoff_year and "publish_year" in results.columns:
            def _year_ok(val):
                try:
                    return int(str(val)[:4]) <= cutoff_year
                except (ValueError, TypeError):
                    return True  # 연도 정보 없는 레코드는 포함
            results = results[results["publish_year"].apply(_year_ok)]

        results = results.head(top_k)

        return results.to_dict(orient="records")

    def _format_patent(self, record: dict) -> str:
        title = record.get("title", "")
        abstract = record.get("abstract", "")
        applicant = record.get("applicant_name", "")
        app_date = record.get("application_date", "")
        claims = record.get("claims", "")
        text = f"[특허] {title}\n출원인: {applicant} | 출원일: {app_date}\n요약: {abstract}"
        if claims:
            # 청구항은 핵심 청구항(제1항~제3항)만 포함 (텍스트 크기 제한)
            claims_truncated = claims[:2000]
            text += f"\n청구항: {claims_truncated}"
        return text

    def _format_paper(self, record: dict) -> str:
        title = record.get("title", "")
        abstract = record.get("abstract", "")
        authors = record.get("authors", "")
        year = record.get("publish_year", record.get("year", ""))
        return f"[논문] {title}\n저자: {authors} | 연도: {year}\n요약: {abstract}"

    def _format_designated_tech(self, record: dict) -> str:
        name = record.get("tech_name", "")
        field_str = record.get("tech_field", "")
        applicant = record.get("applicant", "")
        summary = record.get("summary", "")
        date = str(record.get("designated_date", ""))[:10]
        return f"[지정기술] {name}\n분야: {field_str} | 개발사: {applicant} | 지정일: {date}\n요약: {summary}"

    def _format_codil(self, record: dict) -> str:
        title = record.get("title", "")
        content = record.get("content", record.get("abstract", ""))
        year = record.get("publish_year", record.get("year", ""))
        return f"[건설기준] {title} | 연도: {year}\n내용: {content}"

    def _format_kcsc(self, record: dict) -> str:
        """KCSC 건설기준 레코드를 텍스트로 포맷팅."""
        code = record.get("code", "")
        title = record.get("title", "")
        full_text = record.get("full_text", "")
        sections = record.get("sections", [])

        text = f"[건설기준] {code} {title}"
        if full_text:
            text += f"\n{full_text[:3000]}"
        elif sections:
            for sec in sections[:10]:
                heading = sec.get("heading", "")
                content = sec.get("content", "")[:500]
                text += f"\n{heading}: {content}"
        return text

    def _format_enriched_tech(self, record: dict, field_name: str, text: str) -> str:
        """PDF에서 추출한 지정기술 enriched 텍스트를 포맷팅."""
        name = record.get("tech_name", "")
        tech_num = record.get("tech_number", "")
        field_labels = {
            "prior_art_survey": "선행기술조사",
            "tech_detail": "신기술 상세",
            "intro": "기술 소개",
            "summary": "기술 요약",
            "procedure": "시공절차",
            "ip_info": "지식재산권",
        }
        label = field_labels.get(field_name, field_name)
        return f"[지정기술 {label}] {name} (제{tech_num}호)\n{text}"

    def _extract_patent_year(self, record: dict) -> str:
        """특허 레코드에서 출원 연도를 추출."""
        app_date = record.get("application_date", "")
        if app_date and len(str(app_date)) >= 4:
            return str(app_date)[:4]
        return ""

    def _extract_major(self, field_str: str) -> str:
        parts = field_str.split(">")
        return parts[0].strip() if parts else ""

    def _extract_middle(self, field_str: str) -> str:
        parts = field_str.split(">")
        return parts[1].strip() if len(parts) > 1 else ""

    def _load_json(self, path: Path) -> list:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else [data]
