# CLAUDE.md — 프로젝트 지침서

## 프로젝트 개요

건설신기술(CNT) 1차 평가위원회를 LLM 에이전트로 시뮬레이션하는 평가 프레임워크.
10~15명의 가상 전문위원이 독립 평가 후 다수결(2/3 찬성)로 의결한다.

## 기술 스택

- **LLM**: AWS Bedrock Claude Sonnet 4.6 (Converse API)
- **임베딩**: Cohere embed-multilingual-v3 (Bedrock, 1024차원)
- **벡터 DB**: LanceDB (로컬 파일 기반, 테이블: `cnt_knowledge_base`)
- **백엔드**: FastAPI + uvicorn (port 8000)
- **프론트엔드**: React + TypeScript + Recharts (port 3000)

## 핵심 아키텍처

- **정적 KB**: 평가기준 (신규성 50점 + 진보성 50점, 각 ≥35점 통과)
- **동적 KB**: KIPRIS(특허) + OpenAlex/CrossRef/Scholar(논문) + KAIA(지정기술) + CODIL/KCSC(건설기준)
- **벡터 KB**: 16,462건 인덱싱, 제외 메커니즘(자기참조 방지) 내장
- **에이전트 패널**: 무작위 10~15명, 정합 70% / 부분정합 30%, 경력 고30/중40/저30%
- **평가 파이프라인**: PIKE-RAG(계층적KB) → RAG-Novelty(선행기술) → PoLL(앙상블) → Chairman(검토)
- **분석 모듈**: 정확도(8-1), 일관성(8-2, Fleiss' kappa), 점수패턴(8-3, 레이더차트)

## 빌드 & 실행 명령어

```bash
# Python 의존성 설치
pip install -e .

# 벡터 DB 구축 (최초 클론 후 필수, ~6분)
py scripts/rebuild_vector_db.py

# 백엔드 실행
py -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# 프론트엔드 실행
cd frontend && npm install && npm start

# 전체 실험 실행
py scripts/run_experiment.py --phase prepare
py scripts/run_experiment.py --phase evaluate
py scripts/run_experiment.py --phase analyze
```

## 주요 파일 경로

### 설정
- `config/settings.py`: AWS, KAIA, 패널 구성 등 전체 설정
- `.env`: AWS 키, API 키 등 민감 정보 (gitignore 대상)

### 핵심 파이프라인
- `src/pipeline/orchestrator.py`: 전체 평가 오케스트레이터 (ThreadPool 병렬)
- `src/pipeline/panel_generator.py`: 에이전트 패널 생성기
- `src/pipeline/proposal_builder.py`: 테스트 케이스 선별 + 제안기술 구축
- `src/evaluation/kb_assembler.py`: PIKE-RAG 3단계 KB 어셈블러
- `src/evaluation/prompt_builder.py`: 평가 프롬프트 빌더
- `src/evaluation/chairman_agent.py`: 의장 에이전트 (일관성/환각 검토)
- `src/evaluation/ensemble_evaluator.py`: PoLL 앙상블 평가

### LLM & 벡터DB
- `src/llm/bedrock_client.py`: Bedrock LLM + 임베딩 클라이언트
- `src/vectordb/kb_vectorizer.py`: LanceDB 벡터KB 구축기 (제외 메커니즘)

### 데이터 수집
- `src/dynamic_kb/kipris_client.py`: KIPRIS 특허 검색
- `src/dynamic_kb/openalex_client.py`: OpenAlex 논문 (평가차원별 키워드 매트릭스)
- `src/dynamic_kb/kaia_detail_crawler.py`: KAIA 지정기술 크롤러 + PDF
- `src/dynamic_kb/codil_crawler.py`: CODIL 건설기준
- `src/dynamic_kb/pdf_parser.py`: 건설신기술 PDF 파서

### 스크립트
- `scripts/rebuild_vector_db.py`: 벡터DB 재구축
- `scripts/run_experiment.py`: 전체 실험 (--phase prepare/evaluate/analyze)
- `scripts/enrich_patents_full.py`: Google Patents 청구항 보강
- `scripts/collect_openalex_papers.py`: OpenAlex 논문 수집
- `scripts/collect_crossref_papers.py`: CrossRef OA 논문 수집

### 분석
- `src/analysis/accuracy_analyzer.py`: 정확도 분석 (8-1)
- `src/analysis/consistency_analyzer.py`: 일관성 분석 (8-2, Fleiss' kappa)
- `src/analysis/score_pattern_analyzer.py`: 점수 패턴 분석 (8-3)

### 문서
- `docs/kb_data_collection_methodology.md`: KB 데이터 수집 방법론
- `docs/vector_db_construction.md`: 벡터DB 구축 방법론
- `docs/rag_evidence_pipeline.md`: RAG 근거 추적 파이프라인

## KB 데이터 현황 (16,546건)

| 소스 | 건수 | 위치 |
|------|------|------|
| 특허 (KIPRIS) | 4,497 | `data/dynamic/patents/`, `patents_recent/` |
| 논문 (Scholar+OpenAlex+CrossRef+한국) | 6,406 | `data/dynamic/*_papers/` |
| CODIL 건설기준 | 3,027 | `data/dynamic/codil/` |
| KCSC 건설기준 | 300 | `data/dynamic/kcsc_standards/` |
| 지정기술 (KAIA) | 2,316 | `data/dynamic/cnt_designated/` |
| 제안기술 | 27건 JSON + PDF | `data/proposals/` |

## 개발 규칙

- Python 실행: `py` 명령어 사용
- 콘솔 인코딩: cp949, 파일 인코딩: UTF-8
- 실제 데이터 기반 KB 구축 (합성/가짜 데이터 사용 금지)
- AWS Bedrock Region: us-east-1
- LLM 모델: us.anthropic.claude-sonnet-4-6-20250514-v1:0
- 임베딩 모델: cohere.embed-multilingual-v3

## 환경 셋업 (타 환경)

1. `git lfs install && git clone` (LFS로 PDF 관리)
2. `pip install -e .`
3. `.env.example` → `.env` 복사 후 AWS 키 입력
4. `py scripts/rebuild_vector_db.py` (벡터DB 재구축, ~6분)
5. `.claude_data/` 내 메모리/플랜 복원 — 상세는 `.claude_data/README.md` 참조
