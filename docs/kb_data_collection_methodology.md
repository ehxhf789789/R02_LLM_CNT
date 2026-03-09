# 지식 베이스(KB) 데이터 수집 방법론

## 1. 개요

본 연구의 지식 베이스는 건설신기술(CNT) 평가를 위한 전문가 에이전트의 지식 기반으로 활용된다.
평가의 신뢰성을 확보하기 위해 **6개 데이터 소스**에서 다양한 유형의 선행기술 자료를 수집하였으며,
각 소스별 수집 방법, 탐색 조건, 품질 관리 기준을 아래에 기술한다.

### 1.1 KB 구성 체계

| 구분 | 데이터 소스 | 유형 | 역할 |
|---|---|---|---|
| 정적 KB | 평가기준 (신규성/진보성) | 규칙 | 평가 프레임워크 |
| 동적 KB | KIPRIS 특허 | 선행기술 | 신규성 비교 대상 |
| 동적 KB | 학술 논문 (국내외) | 선행기술 | 진보성·독창성 근거 |
| 동적 KB | CODIL 건설기준 | 기술기준 | 기술 맥락 참조 |
| 동적 KB | KCSC 건설기준 | 설계기준 | 표준·규격 참조 |
| 동적 KB | KAIA 지정기술 | 기존 CNT | 유사기술 비교 |

### 1.2 대분류 체계

건설신기술 분류 체계에 따라 3개 대분류로 구분하여 수집:

| 대분류 코드 | 분야 | 설명 |
|---|---|---|
| CIV | 토목 | 교량, 터널, 도로, 기초, 내진, 하천 등 |
| ARC | 건축 | 방수, 단열, 구조보강, 모듈러, 에너지 등 |
| MEC | 기계설비 | 건설기계, 소음방지, 환기, 배관, 소방 등 |

---

## 2. 데이터 소스별 수집 방법론

### 2.1 특허 데이터 (KIPRIS)

#### 2.1.1 수집 개요

| 항목 | 내용 |
|---|---|
| **데이터 소스** | KIPRIS (한국특허정보원) Open API |
| **수집 클라이언트** | `src/dynamic_kb/kipris_client.py` |
| **수집 방식** | REST API 키워드 검색 |
| **탐색 대상** | 국내 등록/공개 특허 |
| **탐색 기간** | 전체 (API 연도 필터 미지원) |
| **분류 기준** | 건설 분야 키워드 매트릭스 (분류별 10~18개) |

#### 2.1.2 수집 단계

**1단계: 기본 수집 (KIPRIS API)**
- 분류별 건설기술 키워드로 API 검색 (max_results=100/키워드)
- 수집 필드: 제목, 초록, 출원인, 출원번호, 등록번호, 공개번호, 출원일
- 중복 제거: application_number 기준

**2단계: 청구항 보강 (Google Patents 스크래핑)**
- KIPRIS API는 청구항(claims)을 제공하지 않음
- Google Patents (`patents.google.com/patent/KR{번호}/ko`)에서 청구항 추출
- 스크립트: `scripts/enrich_patents_full.py`
- ID 생성 전략 (멀티 서픽스 폴백):
  1. 등록번호 → `KR{num}B1` → `KR{num}A1`
  2. 공개번호 → `KR{num}A` → `KR{num}A1`
  3. 출원번호 → `KR{num}A` → `KR{num}A1`
- HTML 파싱: `section[itemprop=claims]` 요소에서 텍스트 추출

**3단계: 최근 5년 보강 (2021+ 집중 수집)**
- 스크립트: `scripts/collect_recent_patents.py`
- KIPRIS API에 연도 필터가 없으므로 **후처리 필터링** 적용
- `application_date`, `register_date`, `open_date` 중 하나라도 2021년 이후이면 포함
- 최신 트렌드 키워드 54개 (분류별 18개):
  - CIV: 스마트 도로 시공, 디지털 트윈 교량, 3D 프린팅 콘크리트, 탄소중립 건설 등
  - ARC: 제로에너지 건축, 모듈러 건축 시공, 스마트 건축 자동화 등
  - MEC: 건설로봇 자동화, IoT 건설안전 모니터링, 자율주행 굴착기 등
- 저장 경로: `data/dynamic/patents_recent/{cat}/`

#### 2.1.3 품질 관리

| 품질 지표 | 기준 | 현황 |
|---|---|---|
| 초록 보유율 | >20자 | 99.97% (4,496/4,497) |
| 청구항 보유율 | >50자 | 기존 68.2% (2,388/3,500), 최근추가 43.5% (434/997), 합산 62.8% (2,822/4,497) |
| 벡터화 품질 필터 | format_patent() < 80자 → 제외 | 적용 |
| content_status 태깅 | full/claims/description/abstract_only/no_content | 적용 |

#### 2.1.4 탐색 키워드 (기본 수집)

| 분류 | 키워드 |
|---|---|
| CIV | 교량 보수보강, 터널 시공, 도로 포장, 말뚝 기초, 내진 보강, 하천 제방, 연약지반 처리, PHC 말뚝, PSC 거더, NATM 터널, 숏크리트, FRP 보강, 프리캐스트, CIP 콘크리트, 건설 폐기물 재활용 등 |
| ARC | 건축 방수, 외단열, 철근콘크리트, 커튼월, 내화구조, 프리캐스트, 고강도 콘크리트, 지붕 방수, 옥상 녹화, 건축물 내진보강 등 |
| MEC | 건설기계, 소음방지, 환기설비, 배관시공, 소방설비, 지열시스템, BIM 건설관리 등 |

---

### 2.2 학술 논문

#### 2.2.1 논문 소스 구성

| 소스 | API/방식 | 언어 | 특징 |
|---|---|---|---|
| Semantic Scholar | Academic Graph API | 영문 위주 | 초기 수집 소스 |
| OpenAlex | REST API | 영문/국문 | 100% 초록 보장, 가장 대규모 |
| CrossRef | REST API | 영문 위주 | DOI 기반, 최신 논문 풍부 |
| OpenAlex (한국 학술지) | REST API (source 필터) | 국문/영문 | 한국 건설 학술지 대상 |

#### 2.2.2 Semantic Scholar 논문

| 항목 | 내용 |
|---|---|
| **API** | Semantic Scholar Academic Graph API v1 |
| **수집 클라이언트** | `src/dynamic_kb/scholar_client.py` |
| **초기 수집** | 분류별 키워드 검색 → 1,265건 |
| **초록 보유율** | 57.2% (초기) → 96.5% (보강 후) |
| **보강 방법** | 방안 A: SS Detail API + CrossRef DOI fallback |
|  | 방안 B: DOI → 출판사 페이지 스크래핑 (+13건) |
|  | 방안 C: 초록 미보유 논문 제거 + OpenAlex 보충 (-524, +491) |
| **Rate limit** | 심각 (429 에러 빈발, 5초 간격 필요) |

**보강 스크립트:**
- `scripts/fill_scholar_abstracts.py` (방안 A)
- `scripts/scrape_doi_abstracts.py` (방안 B)
- `scripts/replace_scholar_with_openalex.py` (방안 C)

#### 2.2.3 OpenAlex 논문

| 항목 | 내용 |
|---|---|
| **API** | OpenAlex REST API (https://api.openalex.org/works) |
| **수집 클라이언트** | `src/dynamic_kb/openalex_client.py` |
| **탐색 전략** | 6개 평가차원 × 3개 분류 = 18개 키워드 그룹 |
| **탐색 기간** | from_year=2015 (기본), from_year=2021 (최근 보강) |
| **초록 필터** | API 레벨에서 has_abstract=true 또는 len(abstract) ≥ 30 |
| **초록 보유율** | 100% |

**6개 평가차원 키워드 매트릭스:**

| 평가차원 | 검색 키워드 예시 |
|---|---|
| originality (독창성) | novel construction method, innovative structural design |
| differentiation (차별성) | comparative analysis construction, performance superiority |
| quality_improvement (품질향상) | durability improvement, quality control construction |
| development_maturity (개발완성도) | field application construction, pilot test infrastructure |
| safety (안전성) | structural safety evaluation, construction worker safety |
| eco_friendliness (친환경성) | sustainable construction, carbon neutral infrastructure |

**최근 5년 보강 키워드 (2021+):**
- CIV: digital twin bridge monitoring, 3D printing concrete construction, carbon neutral infrastructure, drone inspection bridge tunnel, AI structural health monitoring, autonomous construction equipment 등 12개
- ARC: zero energy building construction, modular offsite construction, passive house retrofit 등 10개
- MEC: construction robot automation, IoT construction safety wearable, autonomous excavator machine learning 등 10개

#### 2.2.4 CrossRef 논문

| 항목 | 내용 |
|---|---|
| **API** | CrossRef REST API (https://api.crossref.org/works) |
| **수집 클라이언트** | `src/dynamic_kb/crossref_client.py` |
| **탐색 조건** | `filter=from-pub-date:2021-01-01,type:journal-article` |
| **정렬** | `sort=published, order=desc` |
| **초록 필터** | abstract 필드 보유 + len ≥ 30 |
| **초록 보유율** | 100% |
| **HTML 태그 제거** | `re.sub(r'<[^>]+>', '', abstract)` |

#### 2.2.5 한국 국내 논문 (OpenAlex 한국 학술지)

| 항목 | 내용 |
|---|---|
| **수집 방식** | OpenAlex Sources API로 한국 건설 학술지 ID 확보 → Works API 필터링 |
| **스크립트** | `scripts/collect_korean_papers.py` |
| **탐색 기간** | from_publication_date:2015-01-01 이후 |
| **초록 필터** | has_abstract=true, inverted_index → 텍스트 재구성 |
| **한국 관련 판별** | language=ko, country_code=KR, 학술지명 한국 관련 키워드 |

**수집 대상 한국 건설 학술지:**

| 분류 | 학술지명 | OpenAlex ID |
|---|---|---|
| CIV | 대한토목학회 학술대회 | S4306495324 |
| CIV | KSCE Journal of Civil Engineering | S109054653 |
| CIV | Korean Journal of Construction Engineering and Management | S2913678714 |
| CIV | Journal of Korean Society of Steel Construction | S2911319145 |
| CIV | Journal of the Korean Recycled Construction Resources Institute | S4210232354 |
| ARC | 한국건축시공학회 논문집 | S4306496179 |
| ARC | 한국건축시공학회 학술·기술논문발표회 논문집 | S4306496175 |
| ARC | Journal of the Korea Institute of Building Construction | S4210227761 |
| MEC | Korean Journal of Construction Engineering and Management | S2913678714 |

**키워드 검색 보충:**
- 한국어: 교량 보수보강, 터널 시공 안전, 건축물 방수, 모듈러 건축, 건설기계 자동화 등
- 영문: bridge construction Korea, seismic retrofitting, building waterproofing system 등

---

### 2.3 CODIL 건설기준

| 항목 | 내용 |
|---|---|
| **데이터 소스** | CODIL (건설산업지식정보시스템, codil.or.kr) |
| **수집 클라이언트** | `src/dynamic_kb/codil_client.py` |
| **수집 방식** | CODIL 검색 API 크롤링 |
| **수집 필드** | 제목, 저자, 발행처, 발행연도, 문서유형, URL |
| **원문 접근** | PDF 기반으로 대량 추출 제한적 |

#### 2.3.1 콘텐츠 보강 과정

원시 수집 데이터는 메타데이터만 포함 (초록/원문 미보유). 4단계 보강 전략 적용:

| 전략 | 방법 | 결과 |
|---|---|---|
| 전략 1 | CODIL 상세 페이지 재크롤링 | 성과 미미 (사이트 구조 제한) |
| 전략 2 | 검색 스니펫 텍스트 추출 | 성과 미미 |
| 전략 3 | 메타데이터 구조화 | **3,027건 100%** |
| 전략 4 | 가비지 초록 정리 (네비게이션 텍스트 제거) | 300건 정리 |

**전략 3 구조화 형식:**
```
[{doc_type}] {title} | 저자: {authors} | 발행: {publisher} ({publish_year}) | 분류: {category}
```

---

### 2.4 KCSC 건설기준

| 항목 | 내용 |
|---|---|
| **데이터 소스** | KCSC (건설기준정보센터, kcsc.re.kr) |
| **수집 방식** | Playwright 헤드리스 브라우저 (JavaScript SPA) |
| **스크립트** | `scripts/collect_kcsc_playwright.py` |
| **수집 유형** | KDS (설계기준) |
| **수집 필드** | 기준코드, 제목, 전문 텍스트, 섹션 구조 |

#### 2.4.1 수집 기술적 과제

kcsc.re.kr은 JavaScript SPA로 구현되어 일반 HTTP 요청으로는 콘텐츠 렌더링 불가.
해결: Playwright 헤드리스 Chromium 브라우저로 JS 렌더링 후 DOM 파싱.

**수집 과정:**
1. API 인터셉트: 네트워크 요청 감시 → `tn-document-groups` 엔드포인트 발견
2. 폴백: `/StandardCode/List` 페이지 전체 DOM 스캔 → 560개 표준 발견
3. KDS 300건 수집 (CIV 254건, ARC 46건)
4. 전문 텍스트 100% 보유

---

### 2.5 KAIA 지정기술

| 항목 | 내용 |
|---|---|
| **데이터 소스** | KAIA 포털 (한국건설기술연구원, kaia.re.kr) |
| **수집 클라이언트** | `src/dynamic_kb/kaia_detail_crawler.py` |
| **수집 방식** | 웹 크롤링 + AJAX API |
| **수집 필드** | 기술번호, 기술명, 신청인, 분야, 보호기간, 상태 |
| **PDF 보강** | KAIA AJAX API → PDF 다운로드 → 텍스트 추출 |

#### 2.5.1 PDF 보강 과정

| 단계 | 방법 |
|---|---|
| 1. 파일 목록 조회 | KAIA AJAX API (`selectMediaAjax2.do`) |
| 2. PDF 다운로드 | ntech.kaia.re.kr 서버에서 홍보자료 PDF |
| 3. 텍스트 추출 | `src/dynamic_kb/pdf_parser.py` (PyPDF2/pdfplumber) |
| 4. 필드 분류 | 선행기술조사, 시공절차, 기술요약, 기술소개, 지식재산권, 기술상세 |

**PDF 텍스트 추출 필드별 현황:**

| 추출 필드 | 보유 건수 | 설명 |
|---|---|---|
| prior_art_survey | 213건 | 선행기술조사 보고서 |
| procedure | 205건 | 시공절차 기술서 |
| summary | 197건 | 기술 요약 |
| intro | 191건 | 기술 소개자료 |
| ip_info | 149건 | 지식재산권 정보 |
| tech_detail | 63건 | 기술 상세 설명 |

---

## 3. 데이터 현황 총괄

### 3.1 수집 건수 요약

| 데이터 소스 | 수집 건수 | 초록/콘텐츠 보유 | 보유율 |
|---|---|---|---|
| 특허 기존 (KIPRIS) | 3,500 | 초록 3,499, 청구항 2,388 | 초록 99.97%, 청구항 68.2% |
| 특허 최근추가 | 997 | 초록 997, 청구항 434 | 초록 100%, 청구항 43.5% (등록번호 보유 501건 중 86.6% 성공) |
| Scholar 논문 | 774 | 초록 747 | 96.5% |
| OpenAlex 논문 | 2,811 | 초록 2,811 | 100% |
| CrossRef 논문 | 2,075 | 초록 2,075 | 100% |
| 한국 논문 (OpenAlex) | 746 | 초록 746 | 100% |
| CODIL | 3,027 | 구조화 메타데이터 3,027 | 100% |
| KCSC | 300 | 전문 텍스트 300 | 100% |
| KAIA 지정기술 | 500 | PDF enriched 311 | 62.2% |
| KAIA 텍스트 청크 | 1,816 | - | - |
| **합계** | **16,546** | - | - |

### 3.2 분류별 수집 건수

| 분류 | 특허(기존) | 특허(최근) | Scholar | OpenAlex | CrossRef | 한국논문 | CODIL | KCSC | KAIA |
|---|---|---|---|---|---|---|---|---|---|
| CIV | 1,510 | 355 | 326 | 1,036 | 856 | 300 | 1,016 | 254 | - |
| ARC | 1,210 | 313 | 246 | 920 | 557 | 307 | 1,005 | 46 | - |
| MEC | 780 | 329 | 202 | 855 | 662 | 139 | 1,006 | 0 | - |
| 합계 | 3,500 | 997 | 774 | 2,811 | 2,075 | 746 | 3,027 | 300 | 500 |

### 3.3 시간적 분포 (2021+ 비중)

| 데이터 소스 | 총건수 | 2021+ 건수 | 2021+ 비중 | 기준 필드 |
|---|---|---|---|---|
| 특허 기존 | 3,499 | 842 | 24.1% | application_date |
| 특허 최근추가 | 997 | 852 | 85.5% | application_date |
| **특허 합산** | **4,496** | **1,694** | **37.7%** | |
| Scholar | 771 | 527 | 68.4% | publish_year |
| OpenAlex | 2,811 | 1,884 | 67.0% | publication_year |
| CrossRef | 2,046 | 1,685 | 82.4% | published-print/online |
| **논문 합산** | **5,628** | **4,096** | **72.8%** | |
| CODIL | 3,027 | 279 (확인분) | ~100% | publish_year (2,748건 미확인) |
| KCSC | 300 | - | 현행 기준 | N/A |
| 한국 논문 | 746 | 분석 필요 | - | publication_date |
| KAIA 지정기술 | 500 | 137 | 27.4% | protection_period 시작일 |

### 3.4 특허 청구항 보강 상세 결과

**Google Patents 스크래핑 (등록번호 B1 suffix):**

| 구분 | 대상 | 성공 | 성공률 | 비고 |
|---|---|---|---|---|
| patents/ 전체 | 3,500 | 2,388 | 68.2% | 등록번호 2,623건 보유 |
| patents_recent/ CIV | 175 (등록번호) | 172 | 98.3% | |
| patents_recent/ ARC | 187 (등록번호) | 184 | 98.4% | |
| patents_recent/ MEC | 139 (등록번호) | 78 | 56.1% | 최근 등록 비율 낮음 |
| **patents_recent/ 합계** | **501** | **434** | **86.6%** | B1 suffix 100% |
| **전체 합산** | **4,497** | **2,822** | **62.8%** | |

- 미수집 563건: 등록번호 미보유 (출원/공개 단계) → Google Patents 미등록
- 실패 67건: 등록번호 보유하나 Google Patents 페이지 미존재 (최근 등록)

### 3.5 KAIA 지정기술 연도 분포

| 기간 | 건수 | 비중 |
|---|---|---|
| 2007~2010 | 72 | 14.4% |
| 2011~2015 | 162 | 32.4% |
| 2016~2020 | 129 | 25.8% |
| 2021~2026 | 137 | 27.4% |

---

## 4. 벡터 DB 구축

### 4.1 벡터화 파이프라인

```
원시 데이터 → 품질 필터 → 텍스트 포맷팅 → 배치 임베딩 → LanceDB 적재
```

| 항목 | 설정 |
|---|---|
| 벡터 DB | LanceDB (로컬) |
| 임베딩 모델 | Cohere embed-multilingual-v3 (AWS Bedrock) |
| 임베딩 차원 | 1024 |
| 배치 크기 | 50 |
| 텍스트 청킹 | 지정기술 PDF: 2,000자/청크, 최대 8,000자 |

### 4.2 품질 필터링

| 소스 | 필터 조건 | 대상 |
|---|---|---|
| 특허 | `format_patent()` 결과 < 80자 | 콘텐츠 부족 레코드 제외 |
| 논문 | abstract 미보유 또는 < 30자 | 초록 없는 논문 제외 |
| 지정기술 | test case 기술번호 제외 | controlled experiment 지원 |

### 4.3 텍스트 포맷팅

| 소스 | 포맷 |
|---|---|
| 특허 | `[특허] {title}\n출원인: {applicant} \| 출원일: {date}\n요약: {abstract}\n청구항: {claims[:2000]}` |
| 논문 | `[논문] {title}\n저자: {authors} \| 연도: {year}\n요약: {abstract}` |
| 지정기술 | `[지정기술] {name}\n분야: {field} \| 개발사: {applicant} \| 지정일: {date}\n요약: {summary}` |
| CODIL | `[건설기준] {title} \| 연도: {year}\n내용: {content}` |
| KCSC | `[건설기준] {code} {title}\n{full_text[:3000]}` |

---

## 5. 수집 제한 사항 및 대응

| 제한 사항 | 원인 | 대응 방법 |
|---|---|---|
| KIPRIS 청구항 미제공 | API 설계 한계 | Google Patents 스크래핑으로 보완 |
| KIPRIS 연도 필터 미지원 | API 파라미터 부재 | 대량 수집 후 클라이언트 측 필터링 |
| Semantic Scholar rate limit | API 정책 | 5초 간격 + progressive backoff |
| CODIL 원문 미접근 | PDF 기반 콘텐츠 | 메타데이터 구조화로 대체 |
| KCSC JavaScript SPA | 서버사이드 렌더링 없음 | Playwright 헤드리스 브라우저 |
| KAIA PDF 일부 미보유 | 사이트 미업로드 | 기본정보로 벡터화 (189건) |
| KCI/ScienceON API 제한 | API 토큰/접근 제한 | OpenAlex 한국 학술지 검색으로 대체 |

---

## 6. 데이터 수집 플로우

```
┌─────────────────────────────────────────────────────────┐
│                    데이터 수집 파이프라인                      │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────┐   ┌──────────────┐   ┌──────────────┐    │
│  │ KIPRIS   │──→│ 기본 수집     │──→│ patents/     │    │
│  │ API      │   │ (키워드검색)  │   │ {cat}/*.json │    │
│  └──────────┘   └──────┬───────┘   └──────────────┘    │
│                        │                                │
│                        ▼                                │
│              ┌──────────────────┐   ┌──────────────┐   │
│              │ Google Patents   │──→│ 청구항 보강    │   │
│              │ 스크래핑         │   │ (claims 추가) │   │
│              └──────────────────┘   └──────────────┘   │
│                        │                                │
│                        ▼                                │
│              ┌──────────────────┐   ┌──────────────┐   │
│              │ 최근 5년 키워드  │──→│patents_recent│   │
│              │ + 후처리 필터    │   │ {cat}/*.json │   │
│              └──────────────────┘   └──────────────┘   │
│                                                         │
│  ┌──────────┐   ┌──────────────┐   ┌──────────────┐   │
│  │ Semantic │──→│ 키워드 검색   │──→│scholar_papers│   │
│  │ Scholar  │   │ + 초록 보강   │   │ {cat}/*.json │   │
│  └──────────┘   └──────────────┘   └──────────────┘   │
│                                                         │
│  ┌──────────┐   ┌──────────────┐   ┌──────────────┐   │
│  │ OpenAlex │──→│ 6차원×3분류   │──→│openalex_pape.│   │
│  │ API      │   │ 키워드 매트릭스│   │ {cat}/{dim}/ │   │
│  └──────────┘   │ + 최근 보강   │   └──────────────┘   │
│                  └──────────────┘                        │
│                                                         │
│  ┌──────────┐   ┌──────────────┐   ┌──────────────┐   │
│  │ CrossRef │──→│ 2021+ 필터   │──→│crossref_pape.│   │
│  │ API      │   │ journal-article│  │ {cat}/*.json │   │
│  └──────────┘   └──────────────┘   └──────────────┘   │
│                                                         │
│  ┌──────────┐   ┌──────────────┐   ┌──────────────┐   │
│  │ OpenAlex │──→│ 한국 학술지   │──→│korean_papers │   │
│  │(KR Jnls) │   │ source 필터   │   │ {cat}/*.json │   │
│  └──────────┘   └──────────────┘   └──────────────┘   │
│                                                         │
│  ┌──────────┐   ┌──────────────┐   ┌──────────────┐   │
│  │ CODIL    │──→│ 검색 API     │──→│ codil/       │   │
│  │          │   │ + 메타 구조화 │   │ {cat}/*.json │   │
│  └──────────┘   └──────────────┘   └──────────────┘   │
│                                                         │
│  ┌──────────┐   ┌──────────────┐   ┌──────────────┐   │
│  │ KCSC     │──→│ Playwright   │──→│kcsc_standards│   │
│  │          │   │ 헤드리스 크롤링│   │ {cat}/*.json │   │
│  └──────────┘   └──────────────┘   └──────────────┘   │
│                                                         │
│  ┌──────────┐   ┌──────────────┐   ┌──────────────┐   │
│  │ KAIA     │──→│ 크롤링+AJAX  │──→│cnt_designated│   │
│  │ 포털     │   │ + PDF 파싱    │   │ /enriched/   │   │
│  └──────────┘   └──────────────┘   └──────────────┘   │
│                                                         │
│                        ▼                                │
│  ┌──────────────────────────────────────────────────┐  │
│  │              품질 필터링 + 벡터화                    │  │
│  │  Cohere embed-multilingual-v3 (dim=1024)          │  │
│  │  → LanceDB (cnt_knowledge_base 테이블)             │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## 7. 수집 스크립트 목록

| 스크립트 | 기능 | 대상 소스 |
|---|---|---|
| `src/dynamic_kb/kipris_client.py` | KIPRIS 특허 검색 | 특허 |
| `src/dynamic_kb/scholar_client.py` | Semantic Scholar 검색 | Scholar 논문 |
| `src/dynamic_kb/openalex_client.py` | OpenAlex 검색 | OpenAlex 논문 |
| `src/dynamic_kb/crossref_client.py` | CrossRef 검색 | CrossRef 논문 |
| `src/dynamic_kb/codil_client.py` | CODIL 검색 | CODIL 기준 |
| `src/dynamic_kb/kaia_detail_crawler.py` | KAIA 크롤링+PDF | KAIA 지정기술 |
| `scripts/enrich_patents_full.py` | Google Patents 청구항 | 특허 보강 |
| `scripts/collect_recent_patents.py` | 최근 특허 추가 수집 | 특허 (2021+) |
| `scripts/collect_recent_papers.py` | 최근 논문 추가 수집 | OpenAlex+CrossRef |
| `scripts/collect_korean_papers.py` | 한국 논문 수집 | OpenAlex 한국 학술지 |
| `scripts/collect_kcsc_playwright.py` | KCSC 크롤링 | KCSC 기준 |
| `scripts/enrich_codil_content.py` | CODIL 콘텐츠 보강 | CODIL |
| `scripts/fill_scholar_abstracts.py` | Scholar 초록 보강 | Scholar |
| `scripts/scrape_doi_abstracts.py` | DOI 기반 초록 스크래핑 | Scholar |
| `scripts/replace_scholar_with_openalex.py` | Scholar→OpenAlex 대체 | Scholar+OpenAlex |
| `scripts/rebuild_vector_db.py` | 벡터DB 재구축 | 전체 |
