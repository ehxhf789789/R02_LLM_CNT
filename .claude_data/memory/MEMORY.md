# R02_LLM_CNT Project Memory

## Project Overview
건설신기술(CNT) LLM 평가 프레임워크. 10~15명 에이전트가 독립 평가 후 다수결 의결.
AWS Bedrock Claude + LanceDB 벡터KB + FastAPI + React 구성.

## Key Architecture
- **정적 KB**: 평가기준 (신규성 50점 + 진보성 50점, 각 ≥35점 통과, 위원 2/3 찬성)
- **동적 KB**: KIPRIS(특허) + Semantic Scholar/KCI(논문) + KAIA(지정기술) + CODIL(건설기준)
- **벡터 KB**: LanceDB + Cohere embed-multilingual-v3 (Bedrock), 제외 메커니즘 포함
- **에이전트 패널**: 10~15명 무작위, 70% 정합 / 30% 부분정합, 경력(고30/중40/저30%)
- **평가 파이프라인**: PIKE-RAG(계층적KB) + RAG-Novelty(선행기술) + PoLL(앙상블) + Chairman(검토)
- **분석**: 정확도(8-1), 일관성(8-2, Fleiss' kappa), 점수패턴(8-3, 레이더차트)

## AWS Bedrock
- Region: us-east-1, Access Key: AKIARG6GBDRG3KEIVKDE
- LLM: us.anthropic.claude-sonnet-4-6-20250514-v1:0
- Embedding: cohere.embed-multilingual-v3 (dim=1024)
- Converse API 사용

## Key File Paths
- `config/settings.py`: 환경설정 (AWS, KAIA, 패널 설정 포함)
- `src/llm/bedrock_client.py`: Bedrock LLM + 임베딩 클라이언트
- `src/vectordb/kb_vectorizer.py`: LanceDB 벡터KB 구축기 (제외 메커니즘 내장)
- `src/pipeline/panel_generator.py`: 에이전트 패널 생성기 (10-15명, 70/30)
- `src/pipeline/orchestrator.py`: 전체 평가 오케스트레이터 (ThreadPool 병렬)
- `src/pipeline/proposal_builder.py`: 테스트 케이스 선별 + 제안기술 구축
- `src/evaluation/chairman_agent.py`: 의장 에이전트 (일관성/환각/오류 검토)
- `src/dynamic_kb/kaia_detail_crawler.py`: ntech 상세 크롤러 + PDF 다운로드
- `src/dynamic_kb/openalex_client.py`: OpenAlex API 클라이언트 (평가차원별 키워드 매트릭스 포함)
- `src/dynamic_kb/pdf_parser.py`: 건설신기술 홍보자료 PDF 파서
- `src/analysis/`: 정확도(8-1), 일관성(8-2, Fleiss' kappa), 점수패턴(8-3)
- `scripts/run_experiment.py`: 전체 실험 스크립트 (--phase prepare/evaluate/analyze)
- `scripts/enrich_patents_full.py`: Google Patents 청구항+설명 보강 (멀티 서픽스 폴백)
- `scripts/collect_korean_papers.py`: OpenAlex 한국 건설 학술지 논문 수집
- `scripts/collect_recent_patents.py`: 최근 5년 특허 추가 수집 (후처리 필터)
- `scripts/collect_recent_papers.py`: 최근 5년 논문 추가 수집 (OpenAlex+CrossRef)
- `docs/kb_data_collection_methodology.md`: KB 구축 방법론 문서 (논문 작성용)
- `scripts/collect_openalex_papers.py`: OpenAlex 평가차원별 체계적 논문 수집
- `scripts/collect_crossref_papers.py`: CrossRef/MDPI OA 논문 수집
- `scripts/enrich_codil_details.py`: CODIL 상세페이지 크롤링 보강
- `scripts/collect_kcsc_standards.py`: KCSC 건설기준 수집 (SPA 제약, Playwright 필요)
- `scripts/rebuild_vector_db.py`: 벡터DB 재구축

## KB Data Status (2026-03-09, Phase 2 완료)
- **특허 기존(KIPRIS)**: 3,500건 (CIV:1510, ARC:1210, MEC:780), 청구항 2,388건 (68.2%)
- **특허 최근추가**: 997건 (CIV:355, ARC:313, MEC:329), 청구항 434건 (43.5%, 등록번호 501건 중 86.6%)
- **논문(Scholar)**: 774건, 초록 96.5%
- **논문(OpenAlex)**: 2,811건 (초록 100%) — 평가차원 6×분야 3 매트릭스 + 2021+ 보강
- **논문(CrossRef)**: 2,075건 (초록 100%) — 2021+ OA 저널
- **논문(한국 학술지)**: 746건 (CIV:300, ARC:307, MEC:139) — OpenAlex 한국 건설 학술지 소스 필터
- **CODIL 건설기준**: 3,027건 (구조화 메타데이터 100%)
- **KCSC 건설기준**: 300건 (CIV:254, ARC:46) — Playwright 크롤링
- **지정기술(KAIA)**: 500건 기본 + 311건 PDF enriched (1,816 텍스트 청크)
- **벡터DB(LanceDB)**: 16,462건 적재 (16,546건 중 84건 품질 필터 제외)
- **프로포절**: 27건 (24건 PDF 보강)

## Enrichment Sources
- **특허 청구항**: Google Patents 스크래핑 (KR{등록번호}B1/ko, section[itemprop=claims]), 멀티 서픽스 폴백
- **지정기술 PDF**: KAIA AJAX API (selectMediaAjax2.do) → ntech.kaia.re.kr 다운로드
- **논문(OpenAlex)**: 무료, 키 불필요, 건설 concept 필터, 평가차원별 체계적 키워드
- **논문(CrossRef)**: 무료, 키 불필요, MDPI OA 저널 ISSN 필터
- **논문(한국 학술지)**: OpenAlex source ID 필터 (대한토목학회, KSCE, KIBC 등)
- **논문(Scholar)**: 영문 키워드 37개로 보강 검색

## End-to-End Simulation Results (2026-03-08)
- 1002 (MEC 지열 시공): APPROVED 92.9%, 69.2/100
- 1022 (CIV PHC말뚝): APPROVED 100%, 75.2/100
- 1033 (ARC 외단열 보강): APPROVED 100%, 70.5/100
- 1046 (CIV 보수보강, thin data): REJECTED 0%, 46.9/100
- 15명 패널, Bedrock Claude Sonnet 4.6, 7-12분/건

## API Status
- **OpenAlex**: 정상. 무료, 키 불필요, ~7 req/s. 가장 안정적인 논문 소스
- **CrossRef**: 정상. 무료, 키 불필요. MDPI 저널 ISSN 필터 가능
- **KIPRIS**: 정상. 무료 월 1,000건
- **Semantic Scholar**: 심한 rate limit (429). 5초 간격 필요
- **KAIA**: 정상. 크롤링+AJAX
- **CODIL**: 목록+상세 크롤링 가능 (SSL verify=False 필요)
- **KCSC**: SPA (JavaScript 렌더링) → Playwright 필요, HTTP만으로는 불가
- **ScienceON**: 비활성화 (토큰 미해결)
- **KCI**: API 키 발급 대기 (data.go.kr)

## User Preferences
- Python (py 명령어, PYTHONIOENCODING=utf-8)
- 콘솔: cp949 (파일은 UTF-8)
- 실제 데이터 기반 KB 구축 요구 (합성/가짜 데이터 불허)
