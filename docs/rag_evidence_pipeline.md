# RAG 기반 근거 생성 및 출처 추적 파이프라인

## 1. 개요

본 시스템은 건설신기술 평가 시 에이전트가 생성하는 평가 판단의 **근거(evidence)**와 **출처(source)**를
벡터DB→RAG 검색→프롬프트 주입→구조화된 응답→앙상블 집계→의장 검증의 전 과정에서 추적한다.

### 1.1 근거 추적 전체 흐름

```
┌─────────────────────────────────────────────────────────────────┐
│                    RAG → Evidence → Validation                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ① 벡터DB 검색 (KBVectorizer.search)                            │
│     └→ source_type별 top_k 문서 검색                              │
│                                                                  │
│  ② 계층적 KB 조립 (KBAssembler.assemble)                         │
│     └→ Level 1: 평가기준 (공통)                                   │
│     └→ Level 2: 특허/논문/지정기술/CODIL (분야별 RAG)              │
│     └→ Level 3: 판단 기조/채점 편향 (경력별)                       │
│                                                                  │
│  ③ 선행기술 검색 (PriorArtSearcher.search)                       │
│     └→ KIPRIS + Scholar + KCI + 지정기술 API 실시간 검색           │
│                                                                  │
│  ④ 프롬프트 구축 (PromptBuilder.build_evaluation_prompt)         │
│     └→ 시스템: 역할 + 판단 기조                                    │
│     └→ 유저: 평가기준 + 선행기술 + 제안기술 + 출력형식              │
│                                                                  │
│  ⑤ LLM 응답 생성 (Bedrock Claude)                                │
│     └→ 구조화된 JSON: 점수 + reasoning + evidence[] + verdict      │
│                                                                  │
│  ⑥ 근거 수집 (EnsembleEvaluator.aggregate)                      │
│     └→ 과반수 합의 근거 (consensus_evidence)                       │
│     └→ 소수 의견 (dissenting_opinions)                             │
│                                                                  │
│  ⑦ 근거 검증 (ChairmanAgent.review)                              │
│     └→ 일관성/환각/오류/이상치 점검                                 │
│     └→ hallucination_flags 생성                                    │
│                                                                  │
│  ⑧ 결과 저장 + 프론트엔드 표시                                     │
│     └→ evidence_details[], source_type별 집계, 시각화              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. 단계별 상세

### 2.1 단계 ①: 벡터DB RAG 검색

**모듈**: `src/vectordb/kb_vectorizer.py` → `KBVectorizer.search()`

벡터DB에서 제안기술과 의미적으로 유사한 선행기술 문서를 검색한다.

**검색 파라미터**:

| 호출 위치 | source_type | top_k (정합) | top_k (부분정합) | 필터 |
|----------|-------------|-------------|----------------|------|
| KBAssembler | patent | 30 | 50 | category_major |
| KBAssembler | paper | 30 | 50 | category_major |
| KBAssembler | designated_tech | 10 | 10 | category_major (한글) |
| KBAssembler | codil | 10 | 10 | category_major |

**검색 프로세스**:
1. 쿼리 텍스트(기술명+설명) → Cohere `search_query` 임베딩
2. LanceDB ANN 검색 (`limit = top_k × 2`, 필터링 여유분)
3. post-filter: `source_type`, `category_major`, `exclude_tech_numbers`
4. 상위 `top_k`건 반환 → 각 결과에 원본 `metadata_json` 포함

**자기참조 방지**:
```python
exclude_set = set(exclude_tech_numbers or []) | self._excluded_tech_numbers
results = results[~results["tech_number"].isin(exclude_set)]
```
→ 평가 대상 기술이 KB 검색 결과에 포함되지 않도록 이중 필터링

---

### 2.2 단계 ②: 계층적 KB 조립 (PIKE-RAG 패턴)

**모듈**: `src/evaluation/kb_assembler.py` → `KBAssembler.assemble()`

에이전트 프로파일(전문분야, 매칭수준, 경력)에 따라 3단계 계층으로 KB를 차별화 조립한다.

#### Level 1: 공통 지식 (모든 에이전트 공유)

| 구성요소 | 내용 | 소스 |
|---------|------|------|
| evaluation_criteria | 신규성(50점) + 진보성(50점) 기준표 | `src/static_kb/evaluation_criteria.py` |
| manual_sections | 건설신기술 지정제도 운영요령 파싱본 | `src/static_kb/manual_parser.py` |

#### Level 2: 분야별 지식 (RAG 검색 결과)

| 구성요소 | 검색 대상 | 에이전트별 차이 |
|---------|----------|---------------|
| prior_patents | 벡터DB 특허 검색 | 정합 30건 / 부분정합 50건 |
| prior_papers | 벡터DB 논문 검색 | 정합 30건 / 부분정합 50건 |
| designated_techs | 벡터DB 지정기술 검색 | 10건 (한글 분류명 필터) |
| codil_docs | 벡터DB CODIL 검색 | 10건 |

**정합 vs 부분정합 차이**:
- **정합(70%)**: 전문분야 직접 일치 → 적은 수의 고관련 문서 → 깊이 있는 분석
- **부분정합(30%)**: 인접 분야 → 많은 수의 문서 → 넓은 시각 + 교차 분야 인사이트

#### Level 3: 경력별 행동 특성

| 경력 | 판단 기조 | 채점 편향 |
|------|----------|----------|
| 고경력(15년+, 30%) | 본질적 차별성 집중, 증빙에 관대, 경험 기반 정성 판단 | novelty_weight=1.1, evidence_strictness=0.8 |
| 중경력(7-14년, 40%) | 기준표 충실 + 현장 적용성, 정량·정성 균형 | 모든 가중치 1.0 (균형) |
| 저경력(3-6년, 30%) | 문언 엄격 적용, 증빙 중시, 보수적 판정 | novelty_weight=0.9, evidence_strictness=1.2 |

---

### 2.3 단계 ③: 선행기술 실시간 검색 (RAG-Novelty)

**모듈**: `src/evaluation/prior_art_searcher.py` → `PriorArtSearcher.search()`

벡터DB 검색과 별도로, 외부 API를 통해 실시간 선행기술을 검색한다.

**검색 흐름**:
1. 기술명 + 설명에서 키워드 추출 (규칙 기반: 2+자 명사, 불용어 제거, 바이그램)
2. KIPRIS API: 특허 검색 (최대 15건)
3. Semantic Scholar + KCI API: 논문 검색 (최대 15건)
4. 로컬 저장소: 지정기술 검색 (최대 10건)
5. 자기참조 제외 필터 적용

**PriorArtContext 구조**:
```python
@dataclass
class PriorArtContext:
    patents: list[dict]          # KIPRIS 특허
    papers: list[dict]           # Scholar + KCI 논문
    designated_techs: list[dict] # 기존 지정기술

    def to_context_text(self) -> str:
        # 프롬프트에 삽입할 선행기술 텍스트 생성
```

---

### 2.4 단계 ④: 프롬프트 구축 (근거 요청 내장)

**모듈**: `src/evaluation/prompt_builder.py` → `PromptBuilder.build_evaluation_prompt()`

#### 프롬프트 구조

```
┌─────────────────────────────────┐
│ [시스템 프롬프트]                  │
│  - 역할: 건설신기술 평가위원       │
│  - 전문분야 + 매칭수준             │
│  - 판단 기조 (Level 3)            │
├─────────────────────────────────┤
│ [유저 프롬프트]                    │
│  ① 평가 기준 (Level 1)            │
│  ② 선행기술 조사 결과 (Level 2)    │
│     - 자기참조 경고 포함            │
│  ③ 제안기술 명세                   │
│     - 기본 정보 + PDF 추출 텍스트   │
│  ④ 출력 형식 지시                  │
│     - evidence[] 구조 명시          │
│     - source_type + source_ref 필수 │
└─────────────────────────────────┘
```

#### 핵심: evidence 출력 형식 지시

프롬프트에서 에이전트에게 요구하는 근거 구조:

```json
"evidence": [
    {
        "claim": "판단 내용",
        "source_type": "patent|paper|designated_tech|codil|evaluation_criteria|proposal",
        "source_ref": "출처 (예: 특허번호, 논문제목, 지정기술명, 기준표 항목명)",
        "relevance": "해당 소스가 판단에 어떻게 기여했는지"
    }
]
```

**근거 요구 조건** (프롬프트에 명시):
1. 최소 3개 이상의 근거 제시
2. 반드시 KB에서 참조한 소스를 명시
3. 각 점수 항목의 reasoning에 구체적 출처 인용
4. 소스 없이 판단한 항목은 confidence를 낮출 것

#### 항목별 reasoning 요구

각 평가 항목마다 별도의 reasoning 필드에서 근거 출처를 요구:

| 항목 | 필드 | 근거 요구 |
|------|------|----------|
| 차별성 (0~25) | `differentiation_reasoning` | 차별성 판단의 구체적 근거와 참조한 KB 소스 |
| 독창성 (0~25) | `originality_reasoning` | 독창성 판단의 구체적 근거와 참조한 KB 소스 |
| 품질향상 (0~15) | `quality_reasoning` | 품질향상 판단 근거와 참조 소스 |
| 개발정도 (0~15) | `development_reasoning` | 개발정도 판단 근거와 참조 소스 |
| 안전성 (0~10) | `safety_reasoning` | 안전성 판단 근거와 참조 소스 |
| 친환경성 (0~10) | `eco_reasoning` | 친환경성 판단 근거와 참조 소스 |

#### 자기참조 방지 경고

프롬프트에 명시적 경고 삽입:

> "선행기술 목록에 평가 대상 기술과 동일하거나 매우 유사한 이름의 기술이 포함되어 있다면,
> 이는 자기참조(circular reference)일 수 있으므로 해당 항목을 신규성 부정 근거로 사용하지 마세요."

---

### 2.5 단계 ⑤: LLM 응답 (구조화된 근거 생성)

**모듈**: `src/pipeline/orchestrator.py` → `_invoke_agent()`

| 파라미터 | 값 |
|---------|---|
| 모델 | Claude Sonnet 4.6 (Bedrock) |
| Temperature | 0.3 (일관성과 다양성 균형) |
| 병렬 실행 | ThreadPool, max_workers=5 |
| 패널 크기 | 10~15명 |

**에이전트 응답 JSON 구조**:

```json
{
    "agent_id": "AG-01",
    "novelty": {
        "differentiation": 20,
        "differentiation_reasoning": "KR102643336B1 특허의 지열 열교환기와 비교 시...",
        "originality": 18,
        "originality_reasoning": "OpenAlex 논문 'Novel geothermal...'에 따르면..."
    },
    "progressiveness": {
        "quality_improvement": 12,
        "quality_reasoning": "CODIL 기준 KDS 21-30-00에 의거하여...",
        "development_degree": 10,
        "development_reasoning": "현장 적용 실적 3건 확인...",
        "safety": 8,
        "safety_reasoning": "지정기술 제XXX호 대비 안전계수...",
        "eco_friendliness": 7,
        "eco_reasoning": "탄소배출 30% 저감 데이터..."
    },
    "evidence": [
        {
            "claim": "지열 열교환기 효율이 기존 대비 20% 향상",
            "source_type": "patent",
            "source_ref": "KR102643336B1",
            "relevance": "기존 특허의 열교환 효율과 직접 비교 가능"
        },
        {
            "claim": "건설기준 KDS 21-30-00의 안전계수 기준 충족",
            "source_type": "codil",
            "source_ref": "KDS 21-30-00",
            "relevance": "품질 기준 충족 여부의 정량적 근거"
        }
    ],
    "prior_art_comparison": "KR102643336B1 특허는 유사한 지열 열교환기이나...",
    "verdict": "approved",
    "confidence": 0.82
}
```

---

### 2.6 단계 ⑥: 앙상블 근거 집계

**모듈**: `src/evaluation/ensemble_evaluator.py` → `EnsembleEvaluator.aggregate()`

#### AgentVote 구조

```python
@dataclass
class AgentVote:
    agent_id: str
    novelty_score: float      # 신규성 합계 (0~50)
    progress_score: float     # 진보성 합계 (0~50)
    verdict: str              # approved | rejected
    confidence: float
    evidence: list[str]       # 근거 텍스트 목록
    evidence_details: list[dict]  # 구조화된 근거 (source_type, source_ref)
    reasoning: dict           # 항목별 reasoning
    prior_art_comparison: str # 선행기술 비교 요약
```

#### 합의 근거 추출

```python
# 과반수(>50%) 에이전트가 인용한 근거 → consensus_evidence
consensus_evidence: list[str]

# 소수 의견(반대 투표 + 사유) → dissenting_opinions
dissenting_opinions: list[str]
```

#### EnsembleResult 구조

```python
@dataclass
class EnsembleResult:
    final_verdict: str          # 최종 판정 (2/3 quorum)
    approval_ratio: float       # 찬성 비율
    avg_novelty: float          # 평균 신규성 점수
    avg_progress: float         # 평균 진보성 점수
    total_score: float          # 평균 총점
    votes: list[AgentVote]      # 개별 투표
    consensus_evidence: list[str]  # 합의 근거
    dissenting_opinions: list[str] # 소수 의견
```

---

### 2.7 단계 ⑦: 의장 에이전트 근거 검증

**모듈**: `src/evaluation/chairman_agent.py` → `ChairmanAgent.review()`

의장 에이전트는 앙상블 결과를 검토하여 근거의 품질을 검증한다.

#### 검증 항목

| 검증 항목 | 설명 | 검출 대상 |
|----------|------|----------|
| **일관성(Consistency)** | 유사 근거에 기반한 판단이 논리적으로 일관한가 | 같은 소스 인용하나 상반된 결론 |
| **환각(Hallucination)** | KB에 존재하지 않는 출처를 인용했는가 | 가짜 특허번호, 미존재 논문 제목 |
| **오류(Error)** | 점수 계산, 기준 적용이 정확한가 | 배점 범위 초과, 기준 오적용 |
| **이상치(Outlier)** | 다수 의견과 극단적으로 다른 투표가 있는가 | 합의 대비 ±20점 이상 차이 |

#### 의장 검증 입력

각 에이전트 평가에서 **상위 3개 근거**를 추출하여 의장에게 제공:

```
에이전트 AG-01 (고경력, 정합):
  투표: approved | 점수: 38/32 | 확신도: 0.82
  주요 근거:
    1. [patent] KR102643336B1 — 지열 열교환기 효율 비교
    2. [codil] KDS 21-30-00 — 안전계수 기준 충족 확인
    3. [evaluation_criteria] 차별성 25점 기준 — 성능 20% 향상 인정
  선행기술 비교: KR102643336B1 특허는 유사하나 열매체 순환 방식에서 차별...
```

#### 의장 출력

```json
{
    "consistency_issues": ["AG-03과 AG-07이 동일 특허를 인용하나 상반된 결론"],
    "hallucination_flags": ["AG-05가 인용한 '한국건설기술연구원(2023)' 출처 미확인"],
    "error_flags": [],
    "outlier_agents": ["AG-12: 총점 38점, 평균 대비 -25점"],
    "overall_assessment": "합의 판정(APPROVED) 유지, 환각 1건 경미",
    "recommendation": "approved"
}
```

---

### 2.8 단계 ⑧: 결과 저장 + 프론트엔드 표시

#### 결과 JSON 구조 (에이전트별)

```json
{
    "agent_id": "AG-01",
    "specialty": "토목 > 기초공학 > 말뚝기초",
    "experience": "high",
    "match_level": "exact",
    "novelty_score": 38,
    "progress_score": 32,
    "total_score": 70,
    "verdict": "approved",
    "confidence": 0.82,
    "evidence": ["근거 텍스트 1", "근거 텍스트 2", ...],
    "evidence_details": [
        {
            "claim": "판단 내용",
            "source_type": "patent",
            "source_ref": "KR102643336B1",
            "relevance": "기존 특허 대비 효율 비교"
        }
    ],
    "reasoning": {
        "differentiation_reasoning": "...",
        "originality_reasoning": "...",
        "quality_reasoning": "...",
        "development_reasoning": "...",
        "safety_reasoning": "...",
        "eco_reasoning": "..."
    },
    "prior_art_comparison": "선행기술 비교 분석 요약"
}
```

#### 프론트엔드 근거 시각화 (`ResultDetail.tsx`)

```typescript
// evidence_details를 source_type별로 집계
const allEvidenceDetails = votes.flatMap(v => v.evidence_details || []);
const sourceTypeCounts: Record<string, number> = {};
// → patent: 45, paper: 32, designated_tech: 12, codil: 8, ...
```

| 시각화 요소 | 표시 내용 |
|------------|----------|
| 소스 유형 분포 | patent/paper/designated_tech/codil/evaluation_criteria 비율 차트 |
| 합의 근거 목록 | >50% 에이전트가 인용한 근거 |
| 소수 의견 | 반대 투표 에이전트의 근거와 reasoning |
| 의장 검증 결과 | 환각/오류/이상치 플래그 |

---

## 3. 근거 품질 보장 메커니즘

### 3.1 다층 품질 보장

```
Layer 1: KB 데이터 품질
  └→ 수집 단계 필터 (초록 ≥30자, 특허 텍스트 ≥80자)
  └→ 벡터DB 적재 품질 필터
  └→ 소스별 콘텐츠 보유율 관리

Layer 2: RAG 검색 품질
  └→ 소스 유형별 분리 검색 (혼합 검색 방지)
  └→ 카테고리 필터링 (분야 관련성 보장)
  └→ 자기참조 제외 (controlled experiment)

Layer 3: 프롬프트 근거 요구
  └→ 최소 3개 evidence 필수
  └→ source_type + source_ref 구조화
  └→ 항목별 reasoning에 출처 인용 의무화
  └→ 소스 없는 판단 → confidence 감점

Layer 4: 앙상블 합의
  └→ 10~15명 독립 평가 → 과반수 합의 근거
  └→ 소수 의견 보존 (다양성 확보)
  └→ 2/3 quorum 의결

Layer 5: 의장 검증
  └→ 환각 탐지 (미존재 출처 인용)
  └→ 일관성 검증 (동일 소스, 상반 결론)
  └→ 이상치 식별
```

### 3.2 출처 유형 체계

| source_type | 설명 | 예시 출처 |
|-------------|------|----------|
| `patent` | KIPRIS 특허 | KR102643336B1, 특허 제목 |
| `paper` | 학술 논문 (국내외) | 논문 제목, DOI |
| `designated_tech` | 기존 건설신기술 | 제XXX호 기술명 |
| `codil` | CODIL 건설기준 | 기준 제목, 발행처 |
| `kcsc_standard` | KCSC 설계기준 | KDS XX-XX-XX |
| `evaluation_criteria` | 평가기준표 | 신규성 차별성 항목 |
| `proposal` | 신청서 자체 내용 | 기술 개요, 시험 결과 |

### 3.3 자기참조 방지 3중 장치

| 계층 | 방법 | 적용 시점 |
|------|------|----------|
| 벡터DB | `set_excluded_techs()` | DB 구축 시 |
| RAG 검색 | `exclude_tech_numbers` 파라미터 | 검색 시 |
| 프롬프트 | 자기참조 경고 문구 삽입 | LLM 호출 시 |

---

## 4. 파이프라인 실행 흐름 (Orchestrator)

**모듈**: `src/pipeline/orchestrator.py`

### 4.1 전체 실행 순서

```python
def evaluate(self, proposal_id: str) -> dict:
    # 1. 제안기술 로드
    proposal = self._load_proposal(proposal_id)

    # 2. 에이전트 패널 생성 (10~15명)
    panel = PanelGenerator().generate(
        category_code=proposal["category_code"],
        panel_size=random.randint(10, 15),
        exact_ratio=0.7,
    )

    # 3. 선행기술 검색 (자기참조 제외)
    prior_art = PriorArtSearcher().search(
        tech_name=proposal["tech_name"],
        tech_description=proposal["tech_description"],
        exclude_tech_numbers=[proposal.get("tech_number", "")],
    )

    # 4. 에이전트별: KB 조립 → 프롬프트 생성 → 저장
    for agent in panel:
        kb = KBAssembler(vectorizer=vectorizer).assemble(
            profile=agent,
            tech_query=f"{proposal['tech_name']} {proposal['tech_description']}",
            exclude_tech_numbers=[proposal.get("tech_number", "")],
        )
        prompt = PromptBuilder().build_evaluation_prompt(kb, prior_art, proposal)
        # prompt 저장 (재현성 확보)

    # 5. 병렬 LLM 호출 (ThreadPool, max_workers=5)
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(self._invoke_agent, agent, prompt)
                   for agent, prompt in agent_prompts]
        responses = [f.result() for f in futures]

    # 6. 응답 파싱 → AgentVote 생성
    votes = [self._parse_response(r) for r in responses]

    # 7. 앙상블 집계
    ensemble_result = EnsembleEvaluator().aggregate(votes)

    # 8. 의장 검증
    chairman_review = ChairmanAgent().review(ensemble_result, proposal)

    # 9. 결과 저장
    return self._save_result(ensemble_result, chairman_review)
```

### 4.2 API 연동 (FastAPI)

**모듈**: `src/api/main.py`

| 엔드포인트 | 메서드 | 기능 |
|-----------|--------|------|
| `/api/evaluate` | POST | 단일 기술 평가 (백그라운드) |
| `/api/evaluate/batch` | POST | 배치 평가 |
| `/api/evaluate/status/{run_id}` | GET | 평가 진행 상황 |
| `/api/results` | GET | 결과 목록 |
| `/api/results/{run_id}` | GET | 결과 상세 (evidence 포함) |
| `/api/kb/detail` | GET | KB 상태 + 벡터DB 정보 |
| `/api/pipeline/workflow` | GET | 파이프라인 노드-엣지 그래프 |
| `/api/analysis/*` | GET | 정확도/일관성/점수패턴 분석 |

---

## 5. 핵심 모듈 참조

| 모듈 | 파일 | 핵심 기능 |
|------|------|----------|
| KBVectorizer | `src/vectordb/kb_vectorizer.py` | 벡터 적재 + RAG 검색 |
| KBAssembler | `src/evaluation/kb_assembler.py` | PIKE-RAG 3층 KB 조립 |
| PriorArtSearcher | `src/evaluation/prior_art_searcher.py` | 실시간 선행기술 검색 |
| PromptBuilder | `src/evaluation/prompt_builder.py` | 프롬프트 구축 (근거 요구 포함) |
| EnsembleEvaluator | `src/evaluation/ensemble_evaluator.py` | 앙상블 집계 + 합의 근거 |
| ChairmanAgent | `src/evaluation/chairman_agent.py` | 환각/일관성/오류 검증 |
| Orchestrator | `src/pipeline/orchestrator.py` | 전체 파이프라인 통합 |
| FastAPI App | `src/api/main.py` | REST API + 프론트엔드 서빙 |
| ResultDetail | `frontend/src/pages/ResultDetail.tsx` | 근거 시각화 |
