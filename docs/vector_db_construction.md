# 벡터 데이터베이스 구축 방법론

## 1. 개요

건설신기술(CNT) LLM 평가 시스템의 핵심 인프라인 벡터 데이터베이스(Vector DB)는
6개 이종 데이터 소스에서 수집된 16,546건의 문서를 단일 벡터 공간에 통합하여,
에이전트별 RAG(Retrieval-Augmented Generation) 검색을 지원한다.

### 1.1 기술 스택

| 구성요소 | 기술 | 버전/사양 |
|---------|------|----------|
| 벡터 DB 엔진 | LanceDB | 로컬 파일 기반, PyArrow 스키마 |
| 임베딩 모델 | Cohere embed-multilingual-v3 | AWS Bedrock 호스팅 |
| 임베딩 차원 | 1024 | float32 |
| 검색 방식 | ANN (Approximate Nearest Neighbor) | LanceDB 내장 |
| 테이블명 | `cnt_knowledge_base` | 단일 테이블 |
| 저장 경로 | `data/vector_db/` | LanceDB 디렉토리 |

### 1.2 핵심 모듈

| 모듈 | 파일 경로 | 역할 |
|------|----------|------|
| KBVectorizer | `src/vectordb/kb_vectorizer.py` | 벡터DB 구축 + 검색 |
| BedrockEmbeddingClient | `src/llm/bedrock_client.py` | Cohere 임베딩 API 호출 |
| rebuild_vector_db.py | `scripts/rebuild_vector_db.py` | 전체 재구축 스크립트 |

---

## 2. 스키마 설계

### 2.1 LanceDB 테이블 스키마

```
cnt_knowledge_base (PyArrow Schema)
├── id: string            — MD5 해시 (text[:200] 기반 중복 방지)
├── text: string          — 포맷팅된 전문 텍스트 (임베딩 대상)
├── source_type: string   — patent | paper | designated_tech | codil | kcsc_standard
├── category_major: string — 대분류 (CIV/ARC/MEC 또는 토목/건축/기계설비)
├── category_middle: string — 중분류 (지정기술에만 적용)
├── title: string          — 문서 제목
├── tech_number: string    — 지정기술 번호 (제외 메커니즘용)
├── publish_year: string   — 발행/출원 연도
├── metadata_json: string  — 원본 레코드 전체 (JSON 직렬화)
└── vector: list<float32>[1024] — Cohere 임베딩 벡터
```

### 2.2 설계 결정 근거

| 설계 요소 | 결정 | 근거 |
|----------|------|------|
| 단일 테이블 | 모든 소스를 하나의 테이블에 통합 | 크로스 소스 검색 및 필터링 유연성 |
| MD5 ID | text[:200] 해시 | 동일 콘텐츠 중복 방지, 재구축 시 일관성 |
| metadata_json | 원본 전체 JSON 직렬화 | 검색 결과에서 원본 필드 접근 가능 |
| category_major 이중 체계 | 코드(CIV) + 한글명(토목) | 특허·논문은 코드, 지정기술은 한글명으로 저장 |
| tech_number 필드 | 지정기술 전용 | 평가 대상 기술의 자기참조(circular reference) 방지 |

---

## 3. 문서 포맷팅 파이프라인

### 3.1 소스별 텍스트 포맷 규칙

원시 JSON 데이터를 임베딩 대상 텍스트로 변환하는 포맷 함수:

#### 3.1.1 특허 (`_format_patent`)

```
[특허] {title}
출원인: {applicant_name} | 출원일: {application_date}
요약: {abstract}
청구항: {claims[:2000]}
```

- 청구항이 있으면 최대 2,000자까지 포함 (핵심 청구항 1~3항)
- 청구항 유무에 따라 벡터 품질 차등: 청구항 포함 시 기술 범위 명시적 표현

#### 3.1.2 논문 (`_format_paper`)

```
[논문] {title}
저자: {authors} | 연도: {publish_year}
요약: {abstract}
```

#### 3.1.3 지정기술 기본 (`_format_designated_tech`)

```
[지정기술] {tech_name}
분야: {tech_field} | 개발사: {applicant} | 지정일: {designated_date}
요약: {summary}
```

#### 3.1.4 지정기술 PDF 보강 (`_format_enriched_tech`)

```
[지정기술 {field_label}] {tech_name} (제{tech_number}호)
{chunk_text}
```

- field_label: 선행기술조사 | 신기술 상세 | 기술 소개 | 기술 요약 | 시공절차 | 지식재산권
- 2,000자 단위 청킹, 최대 8,000자 (문서당 최대 4청크)

#### 3.1.5 CODIL 건설기준 (`_format_codil`)

```
[건설기준] {title} | 연도: {publish_year}
내용: {content}
```

#### 3.1.6 KCSC 건설기준 (`_format_kcsc`)

```
[건설기준] {code} {title}
{full_text[:3000]}
```

- 전문 텍스트 최대 3,000자
- 섹션 구조가 있으면 상위 10개 섹션의 heading+content 포함

### 3.2 포맷 설계 원칙

1. **소스 유형 접두사**: `[특허]`, `[논문]`, `[지정기술]`, `[건설기준]` — 임베딩 공간에서 소스 구분 용이
2. **메타데이터 인라인 포함**: 출원인, 연도 등을 텍스트에 직접 포함 → 임베딩에 맥락 반영
3. **크기 제한**: 청구항 2,000자, KCSC 3,000자, enriched 2,000자/청크 → 임베딩 입력 크기 최적화
4. **필드 우선순위**: 제목 > 요약/초록 > 청구항/본문 순서로 배치 → 검색 시 제목 매칭 우선

---

## 4. 품질 필터링

### 4.1 적재 단계 필터

| 소스 | 필터 조건 | 제외 사유 |
|------|----------|----------|
| 특허 | `len(format_patent(r)) < 80` | 포맷 오버헤드 제외 시 실질 콘텐츠 부족 |
| 논문 | `abstract` 미보유 또는 `len(abstract) < 30` | 초록 없는 논문은 검색 품질 저하 |
| 지정기술 enriched | `len(text) < 100` | 추출 텍스트 너무 짧으면 의미 없음 |

### 4.2 제외 메커니즘 (Controlled Experiment)

```python
vectorizer.set_excluded_techs(["1002", "1022", "1033", "1046"])
```

- 평가 대상 기술(test case)을 KB에서 제외하여 자기참조 방지
- 지정기술 기본 목록 + enriched 텍스트 모두 제외
- 검색 시에도 `exclude_tech_numbers` 파라미터로 이중 필터

### 4.3 최종 적재 현황

| 구분 | 대상 | 적재 | 제외 | 제외 사유 |
|------|------|------|------|----------|
| 전체 | 16,546 | 16,462 | 84 | 품질 필터 (콘텐츠 부족) |

---

## 5. 임베딩 파이프라인

### 5.1 임베딩 처리 흐름

```
원시 JSON 데이터
    ↓
소스별 포맷팅 함수 (_format_patent, _format_paper, ...)
    ↓
품질 필터링 (최소 길이 체크)
    ↓
KBDocument 리스트 생성
    ↓
배치 분할 (batch_size=50)
    ↓
AWS Bedrock API 호출 (Cohere embed-multilingual-v3)
    - input_type: "search_document" (적재 시)
    - input_type: "search_query" (검색 시)
    ↓
MD5 ID 생성 + 메타데이터 조합
    ↓
LanceDB 테이블 적재 (mode="overwrite")
```

### 5.2 배치 처리 상세

| 파라미터 | 값 | 설명 |
|---------|---|------|
| batch_size | 50 | API 호출당 문서 수 |
| 총 배치 수 | 330 (16,462건) | ⌈16,462/50⌉ |
| API 응답 시간 | ~1초/배치 | Bedrock Cohere 기준 |
| 전체 소요 시간 | ~6분 | 330배치 × ~1초 |

### 5.3 임베딩 모델 특성

| 특성 | 설명 |
|------|------|
| 모델 | Cohere embed-multilingual-v3 |
| 다국어 지원 | 한국어 + 영어 혼합 텍스트에 최적화 |
| input_type 분리 | `search_document`(적재) / `search_query`(검색) 비대칭 임베딩 |
| 차원 | 1024 (float32) |
| 정규화 | 내장 (코사인 유사도 최적) |

---

## 6. 검색 (Retrieval) 인터페이스

### 6.1 검색 함수 시그니처

```python
KBVectorizer.search(
    query: str,                          # 검색 쿼리 (기술명 + 설명)
    top_k: int = 20,                     # 반환 문서 수
    source_type: str | None = None,      # 소스 유형 필터
    category_major: str | None = None,   # 대분류 필터
    exclude_tech_numbers: list[str] | None = None,  # 제외 기술
) -> list[dict]
```

### 6.2 검색 처리 흐름

```
검색 쿼리 텍스트
    ↓
embed_query() (input_type="search_query")
    ↓
LanceDB ANN 검색 (limit = top_k × 2)   ← 필터링 여유분 확보
    ↓
post-filter: source_type, category_major
    ↓
post-filter: exclude_tech_numbers
    ↓
head(top_k) → 결과 반환
```

### 6.3 검색 전략 (KBAssembler에서 호출)

| 소스 유형 | top_k (정합) | top_k (부분정합) | 필터 |
|----------|-------------|----------------|------|
| patent | 30 | 50 | category_major=코드 |
| paper | 30 | 50 | category_major=코드 |
| designated_tech | 10 | 10 | category_major=한글명 |
| codil | 10 | 10 | category_major=코드 |

- **정합(exact match)**: 전문분야 직접 일치 에이전트 → 적은 수의 고관련 문서
- **부분정합(partial match)**: 인접 분야 에이전트 → 더 많은 문서로 넓은 시야 확보

---

## 7. 데이터 소스별 적재 상세

### 7.1 소스별 적재 건수

| 소스 유형 | 디렉토리 | CIV | ARC | MEC | 합계 |
|----------|---------|-----|-----|-----|------|
| patent (기존) | `patents/` | 1,510 | 1,210 | 780 | 3,500 |
| patent (최근) | `patents_recent/` | 355 | 313 | 329 | 997 |
| paper (Scholar) | `scholar_papers/` | 326 | 246 | 202 | 774 |
| paper (OpenAlex) | `openalex_papers/` | 1,036 | 920 | 855 | 2,811 |
| paper (CrossRef) | `crossref_papers/` | 856 | 557 | 662 | 2,075 |
| paper (한국) | `korean_papers/` | 300 | 307 | 139 | 746 |
| codil | `codil/` | 1,016 | 1,005 | 1,006 | 3,027 |
| kcsc_standard | `kcsc_standards/` | 254 | 46 | 0 | 300 |
| designated_tech | `cnt_designated/` | - | - | - | 500 + 1,816청크 |
| **합계** | | | | | **16,546** |

### 7.2 디렉토리 스캔 순서

```
data/dynamic/
├── patents/{CIV,ARC,MEC}/*.json          → source_type="patent"
├── patents_recent/{CIV,ARC,MEC}/*.json   → source_type="patent"
├── scholar_papers/{CIV,ARC,MEC}/*.json   → source_type="paper"
├── openalex_papers/{CIV,ARC,MEC}/{dim}/*.json → source_type="paper"
├── crossref_papers/{CIV,ARC,MEC}/*.json  → source_type="paper"
├── korean_papers/{CIV,ARC,MEC}/*.json    → source_type="paper"
├── codil/{CIV,ARC,MEC}/*.json            → source_type="codil"
├── kcsc_standards/{CIV,ARC}/*.json       → source_type="kcsc_standard"
├── cnt_designated/designated_list.json   → source_type="designated_tech"
└── cnt_designated/enriched/designated_*.json → source_type="designated_tech"
```

---

## 8. 재구축 프로세스

### 8.1 재구축 스크립트 사용법

```bash
# 문서 수 확인 (dry-run)
py scripts/rebuild_vector_db.py --dry-run

# 전체 재구축
py scripts/rebuild_vector_db.py
```

### 8.2 재구축 특성

| 특성 | 설명 |
|------|------|
| 모드 | `mode="overwrite"` — 기존 테이블 완전 교체 |
| 멱등성 | 동일 데이터로 재구축 시 동일 결과 (MD5 ID) |
| 소요 시간 | ~6분 (16,462건, 330배치) |
| 비용 | AWS Bedrock Cohere 임베딩 API 호출 비용 |

### 8.3 재구축이 필요한 경우

1. 새로운 데이터 소스 추가 (논문, 특허 등 수집 후)
2. 데이터 보강 완료 (청구항, 초록 등 enrichment 후)
3. 포맷팅 로직 변경 (텍스트 구조 수정)
4. 제외 목록 변경 (테스트 케이스 추가/변경)
