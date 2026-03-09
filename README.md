# R02_LLM_CNT — 건설신기술 LLM 평가 프레임워크

건설신기술(CNT) 1차 심사위원회를 LLM 에이전트로 시뮬레이션하는 평가 프레임워크.
10~15명의 가상 전문위원이 독립 평가 후 다수결(2/3 찬성)로 의결한다.

## 기술 스택

| 구성요소 | 기술 |
|---------|------|
| LLM | AWS Bedrock Claude Sonnet 4.6 |
| 임베딩 | Cohere embed-multilingual-v3 (Bedrock, 1024차원) |
| 벡터 DB | LanceDB (로컬 파일 기반) |
| 백엔드 | FastAPI + uvicorn |
| 프론트엔드 | React + TypeScript + Recharts |
| 데이터 수집 | KIPRIS, OpenAlex, CrossRef, KAIA, CODIL, KCSC |

## 빠른 시작

### 1. 환경 설정

```bash
# 저장소 클론 (Git LFS 포함)
git lfs install
git clone https://github.com/ehxhf789789/R02_LLM_CNT.git
cd R02_LLM_CNT

# Python 환경 (3.11+)
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -e .

# 환경 변수
cp .env.example .env
# .env 파일에 AWS 키, KIPRIS 키 등 입력
```

### 2. 벡터 DB 구축

벡터 DB는 용량(643MB)으로 인해 Git에 포함되지 않으므로 로컬에서 재구축 필요:

```bash
# 문서 수 확인 (dry-run)
py scripts/rebuild_vector_db.py --dry-run

# 전체 구축 (~6분, Bedrock API 호출)
py scripts/rebuild_vector_db.py
```

### 3. 앱 실행

```bash
# 백엔드 (FastAPI)
py -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# 프론트엔드 (React) — 별도 터미널
cd frontend
npm install
npm start
```

- 백엔드: http://localhost:8000
- 프론트엔드: http://localhost:3000

### 4. 평가 실험 실행

```bash
# 전체 파이프라인 (준비 → 평가 → 분석)
py scripts/run_experiment.py --phase prepare
py scripts/run_experiment.py --phase evaluate
py scripts/run_experiment.py --phase analyze
```

## 프로젝트 구조

```
R02_LLM_CNT/
├── config/                     # 설정
│   └── settings.py             # AWS, KAIA, 패널 설정
├── data/
│   ├── dynamic/                # 수집된 KB 데이터 (JSON)
│   │   ├── patents/            # 특허 (KIPRIS) 3,500건
│   │   ├── patents_recent/     # 최근 특허 997건
│   │   ├── scholar_papers/     # Scholar 논문 774건
│   │   ├── openalex_papers/    # OpenAlex 논문 2,811건
│   │   ├── crossref_papers/    # CrossRef 논문 2,075건
│   │   ├── korean_papers/      # 한국 논문 746건
│   │   ├── codil/              # CODIL 건설기준 3,027건
│   │   ├── kcsc_standards/     # KCSC 건설기준 300건
│   │   └── cnt_designated/     # 지정기술 500건 + 1,816 청크
│   ├── proposals/              # 평가 대상 제안기술 (27건 JSON + PDF)
│   ├── static/                 # 정적 KB (평가기준, 매뉴얼)
│   └── vector_db/              # LanceDB (gitignore, rebuild 필요)
├── docs/                       # 방법론 문서
├── frontend/                   # React 프론트엔드
├── scripts/                    # 데이터 수집 및 실험 스크립트
├── src/
│   ├── api/                    # FastAPI 백엔드
│   ├── analysis/               # 정확도/일관성/점수패턴 분석
│   ├── dynamic_kb/             # 데이터 수집 클라이언트
│   ├── evaluation/             # 평가 엔진 (KB 어셈블러, 프롬프트 빌더)
│   ├── llm/                    # Bedrock LLM/임베딩 클라이언트
│   ├── models/                 # 에이전트 프로파일, 데이터 모델
│   ├── pipeline/               # 오케스트레이터, 패널 생성기
│   ├── static_kb/              # 정적 KB 파서
│   ├── storage/                # KB 저장소
│   └── vectordb/               # LanceDB 벡터DB 빌더
└── pyproject.toml
```

## KB 데이터 현황 (16,546건)

| 소스 | CIV | ARC | MEC | 합계 |
|------|-----|-----|-----|------|
| 특허 (KIPRIS) | 1,865 | 1,523 | 1,109 | 4,497 |
| 논문 (Scholar+OpenAlex+CrossRef+한국) | 2,518 | 2,030 | 1,858 | 6,406 |
| CODIL 건설기준 | 1,016 | 1,005 | 1,006 | 3,027 |
| KCSC 건설기준 | 254 | 46 | 0 | 300 |
| 지정기술 (KAIA) | - | - | - | 2,316 |
| **합계** | | | | **16,546** |

## 문서

- [KB 데이터 수집 방법론](docs/kb_data_collection_methodology.md)
- [벡터 DB 구축 방법론](docs/vector_db_construction.md)
- [RAG 근거 추적 파이프라인](docs/rag_evidence_pipeline.md)
