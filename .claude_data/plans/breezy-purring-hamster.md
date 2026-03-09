# Handbox v2 확장 구현 계획

---

## 🚨 긴급 버그 수정 (우선 처리)

### 문제: AWS Bedrock 연결되어 있는데 시뮬레이션 응답 반환

**근본 원인:**
1. `AWSCloudProvider.isConnected() = true` (UI에서 AWS 연결됨)
2. `BedrockLLMProvider.isConnected() = false` (connect() 호출된 적 없음)
3. 두 프로바이더의 연결 상태가 **동기화되지 않음**

**코드 흐름:**
```
IntegratedWorkflowAgent.tryBedrockFallback()
  → ProviderRegistry.getConnectedLLMProviders()
  → BedrockLLMProvider.isConnected() = false (connect() 호출 안됨)
  → 빈 배열 반환
  → invoke_bedrock 직접 호출 시도
  → 실패 시 연결 안내 반환 (시뮬레이션 아님)
```

**BUT! 시뮬레이션이 나오는 진짜 이유:**
- `LocalLLMProvider.generate()`가 먼저 호출됨
- Ollama가 없으면 `model: 'simulation'` 반환
- 시뮬레이션 감지 후 Bedrock 폴백 시도
- `BedrockLLMProvider.isConnected() = false` → 빈 배열
- `invoke_bedrock` 직접 호출도 실패
- 결국 시뮬레이션 응답 그대로 반환됨

---

### 해결 방안

**수정 파일:** `src/services/IntegratedWorkflowAgent.ts`

**방안 1: BedrockLLMProvider 직접 연결 후 사용**
```typescript
private async tryBedrockFallback(...): Promise<...> {
  // BedrockLLMProvider 직접 가져와서 connect 시도
  const bedrockProvider = ProviderRegistry.getLLMProvider('bedrock')
  if (bedrockProvider && !bedrockProvider.isConnected()) {
    await bedrockProvider.connect({})  // 연결 시도
  }

  if (bedrockProvider?.isConnected()) {
    const response = await bedrockProvider.invoke({...})
    return { success: true, content: response.text }
  }

  // Tauri 직접 호출 폴백
  ...
}
```

**방안 2: AWSCloudProvider 연결 시 BedrockLLMProvider도 자동 연결**
`src/providers/cloud/AWSCloudProvider.ts` 수정:
```typescript
async testConnection(): Promise<boolean> {
  const result = await invoke('test_aws_connection')
  this.connected = result.connected

  // Bedrock LLM Provider도 연결 동기화
  if (this.connected) {
    const bedrockProvider = ProviderRegistry.getLLMProvider('bedrock')
    if (bedrockProvider) {
      await bedrockProvider.connect({})
    }
  }

  return this.connected
}
```

**방안 3 (권장): invoke_bedrock 직접 호출 우선**
`tryBedrockFallback()`에서 ProviderRegistry 확인 전에 invoke_bedrock 직접 호출:
```typescript
private async tryBedrockFallback(...): Promise<...> {
  // 1. Tauri invoke_bedrock 직접 호출 (가장 확실)
  try {
    const bedrockResult = await invoke('invoke_bedrock', {...})
    return { success: true, content: bedrockResult.response }
  } catch (e) {
    console.warn('invoke_bedrock 실패:', e)
  }

  // 2. 실패 시 ProviderRegistry 확인 (이건 이미 구현됨)
  ...
}
```

---

### 수정할 파일

| 파일 | 변경 |
|------|------|
| `src/services/IntegratedWorkflowAgent.ts` | `tryBedrockFallback()` - invoke_bedrock 직접 호출 우선 |
| `src/providers/cloud/AWSCloudProvider.ts` | (선택) testConnection에서 BedrockLLMProvider 연결 동기화 |

---

## Context

사용자가 Handbox의 통합 LLM 대화 UI를 확장하여 다음 기능을 구현하고자 합니다:

1. **워크플로우 JSON 즉시 로드** - 대화 UI에서 JSON 파일 업로드 → 캔버스에 바로 로드
2. **워크플로우 JSON 분석 및 개선 제안** - LLM이 첨부된 JSON을 이해하고 개선 방향 제안
3. **상세 프롬프트 구체화** - RAG, 에이전트, 자동화 프로세스에 대해 직관적이고 상세한 되묻기 질문
4. **복잡한 워크플로우 지원** - 다수 페르소나 에이전트 + 다수결 투표 (CNT 평가 시스템처럼)
5. **페르소나 시스템** - 전문가 경험치/경력 편차를 반영한 사전 정의 시스템

**예시 워크플로우 (CNT 통합 평가 시스템):**
- 10명의 AI 평가위원 (구조, 시공, 재료, 경제성, 특허, 안전, 환경, 지반, 정책, 지속가능성)
- 각 평가위원은 stance(보수적/진보적/중립적), expertise, evaluation_focus 등 상세 페르소나
- RAG 시스템: 정적 KB + 동적 KB → 통합 검색
- 투표 집계 → 검증 → 결과 출력

---

## 구현 계획

### Phase 1: 기반 타입 정의 (신규 파일)

#### 1.1 ChatTypes.ts 확장
**파일:** `src/types/ChatTypes.ts`

```typescript
// 추가할 타입
export interface FileAttachment {
  id: string
  name: string
  type: 'workflow-json' | 'document' | 'image' | 'other'
  size: number
  content?: string  // JSON/텍스트 내용
  status: 'uploading' | 'ready' | 'error'
}

export interface WorkflowAnalysisContext {
  workflowId: string
  workflowName: string
  nodeCount: number
  edgeCount: number
  nodeTypes: string[]
  issues: string[]
  suggestions: string[]
}

// ChatMessage에 attachments, analysisContext 필드 추가
```

#### 1.2 PersonaTypes.ts (신규)
**파일:** `src/types/PersonaTypes.ts`

```typescript
export interface PersonaDefinition {
  id: string
  name: string
  title: string                    // 직함 (예: "구조공학 수석연구원")
  domain: string                   // 전문 분야

  expertise: {
    primary: string[]              // 주 전문영역
    secondary: string[]            // 부 전문영역
    keywords: string[]             // 관련 키워드
  }

  experience: {
    years: number                  // 연차
    level: 'junior' | 'mid' | 'senior' | 'expert' | 'master'
    credentials: string[]          // 자격/학위
  }

  stance: 'conservative' | 'progressive' | 'neutral' | 'balanced'
  evaluationFocus: string[]
  systemPrompt: string             // LLM 시스템 프롬프트

  category: string
  isBuiltin: boolean
}

// 경험 레벨별 가중치 (다수결 투표 시 활용)
export const EXPERIENCE_WEIGHTS = {
  junior: 0.6, mid: 0.8, senior: 1.0, expert: 1.2, master: 1.5
}
```

#### 1.3 builtinPersonas.ts (신규)
**파일:** `src/data/builtinPersonas.ts`

- 5-10개의 내장 페르소나 템플릿 (공학, 경제, 법률, 환경, 정책 분야)
- 각 페르소나는 경력 레벨, 평가 성향, 시스템 프롬프트 포함

---

### Phase 2: PromptAnalyzer 확장

**파일:** `src/services/PromptAnalyzer.ts`

#### 2.1 ACTION_KEYWORDS 확장
```typescript
// RAG 관련 키워드 추가
'rag': ['지식베이스', '문서검색', '벡터', '임베딩', 'RAG', '검색증강', '색인'],
'embedding': ['임베딩', 'embed', '벡터화', '벡터DB'],
'kb': ['지식베이스', 'knowledge base', 'KB', 'opensearch', 'pinecone', 'chroma'],

// 에이전트/페르소나 관련 키워드 추가
'persona': ['페르소나', '전문가', '역할', '관점', '경험', '연차', '성향'],
'multi_agent': ['다중에이전트', '복수평가', '위원회', '패널', '투표', '다수결'],
'evaluation': ['평가', '심사', '점수', '판정', '검토', '기준'],
```

#### 2.2 상세 질문 생성 함수 추가
- `generateRAGClarificationQuestions()` - 데이터 소스, 임베딩 모델, 청킹 전략 질문
- `generateAgentClarificationQuestions()` - 페르소나 정의, 평가 기준, 에이전트 수 질문
- `generateEvaluationClarificationQuestions()` - 점수 체계, 투표 방식, 합격 기준 질문

---

### Phase 3: WorkflowChat UI 확장

**파일:** `src/components/WorkflowChat/index.tsx`

#### 3.1 파일 업로드 UI
- 입력 영역 옆에 파일 첨부 버튼 (AttachFile 아이콘)
- 드래그 앤 드롭 오버레이 지원
- JSON 파일 파싱 후 검증

#### 3.2 업로드 옵션 다이얼로그
- "캔버스에 바로 로드" 버튼 → 즉시 deserializeWorkflow 호출
- "AI에게 분석 요청" 버튼 → LLM에게 워크플로우 분석 요청
- "AI에게 개선 요청" 버튼 → 개선 제안 생성

#### 3.3 기존 함수 활용
- `parseWorkflowJSON()` from `src/utils/workflowSerializer.ts`
- `deserializeWorkflow()` from `src/services/WorkflowOrchestratorAgent.ts`

---

### Phase 4: WorkflowOrchestratorAgent 확장

**파일:** `src/services/WorkflowOrchestratorAgent.ts`

#### 4.1 워크플로우 JSON 분석 기능
```typescript
export async function analyzeWorkflowJSON(
  workflow: WorkflowFile,
  userRequest: string,
): Promise<WorkflowAnalysisResult>
```
- 노드/엣지 구조 분석
- 잠재적 문제점 식별
- 개선 제안 생성

---

### Phase 5: Executor 구현

#### 5.1 CustomAgentExecutor (신규)
**파일:** `src/executors/agent/CustomAgentExecutor.ts`

- 노드 타입: `agent.custom`
- 페르소나 기반 LLM 호출
- 구조화된 평가 결과 반환 (점수, 의견, 권고사항)

#### 5.2 VotingAggregatorExecutor (신규)
**파일:** `src/executors/control/VotingAggregatorExecutor.ts`

- 노드 타입: `control.voting-aggregator`
- 다수결 투표 집계 (단순 다수결, 2/3 다수결, 만장일치, 가중 투표)
- 도메인별/기준별 점수 집계

#### 5.3 executors/index.ts 업데이트
- 새 executor 등록
- 레거시 타입 매핑 추가 (`custom-agent` → `agent.custom`)

---

## Critical Files

| 파일 | 변경 내용 |
|------|----------|
| `src/types/ChatTypes.ts` | FileAttachment, WorkflowAnalysisContext 추가 |
| `src/types/PersonaTypes.ts` | **신규** - 페르소나 타입 정의 |
| `src/data/builtinPersonas.ts` | **신규** - 내장 페르소나 템플릿 |
| `src/services/PromptAnalyzer.ts` | RAG/에이전트 키워드, 상세 질문 함수 |
| `src/services/WorkflowOrchestratorAgent.ts` | JSON 분석 기능 추가 |
| `src/services/PersonaService.ts` | **신규** - 페르소나 DB 연동 서비스 |
| `src/components/WorkflowChat/index.tsx` | 파일 업로드 UI, 드래그앤드롭, 옵션 다이얼로그 |
| `src/components/WorkflowChat/UploadOptionsDialog.tsx` | **신규** - 업로드 옵션 다이얼로그 |
| `src/executors/agent/CustomAgentExecutor.ts` | **신규** - 페르소나 기반 에이전트 |
| `src/executors/control/VotingAggregatorExecutor.ts` | **신규** - 투표 집계 (동일 가중치 기본) |
| `src/executors/index.ts` | 새 executor 등록 |
| `src-tauri/src/persona_db.rs` | **신규** - SQLite 기반 페르소나 DB |
| `src-tauri/src/main.rs` | persona_db 모듈 및 명령 등록 |

---

## 검증 계획

1. **파일 업로드 테스트**
   - JSON 파일 드래그 앤 드롭 → 캔버스 로드 확인
   - 잘못된 JSON 파일 업로드 시 오류 메시지 확인

2. **프롬프트 분석 테스트**
   - "RAG 기반 문서 검색 시스템 만들어줘" → 상세 질문 생성 확인
   - "5명의 전문가 위원회가 평가하는 워크플로우" → 페르소나 관련 질문 확인

3. **에이전트 워크플로우 테스트**
   - CustomAgent 노드 + VotingAggregator 연결
   - 다수결 투표 결과 확인

---

## 사용자 결정 사항

1. **페르소나 저장 방식**: ✅ **페르소나 DB 풀 스택**
   - Tauri 백엔드에 SQLite 기반 페르소나 DB 구축
   - 내장 템플릿 + 사용자 정의 페르소나 CRUD 지원
   - `src-tauri/src/persona_db.rs` 신규 생성 필요

2. **파일 업로드 옵션 UI**: ✅ **팝업 다이얼로그**
   - JSON 파일 업로드 후 옵션 선택 다이얼로그 표시
   - 옵션: "캔버스 로드" / "AI 분석" / "AI 개선 요청"

3. **투표 가중치**: ✅ **동일 가중치 (1인 1표)**
   - 경력 레벨 무관, 모든 평가자 동일한 투표권
   - 가중치 시스템은 구현하되 기본값은 비활성화

---

## 추가 구현 사항 (페르소나 DB)

### Tauri 백엔드 확장

**신규 파일:** `src-tauri/src/persona_db.rs`

```rust
// 페르소나 CRUD 명령어
#[tauri::command]
pub async fn save_persona(persona: PersonaDefinition) -> Result<String, String>

#[tauri::command]
pub async fn load_persona(id: &str) -> Result<PersonaDefinition, String>

#[tauri::command]
pub async fn list_personas() -> Result<Vec<PersonaDefinition>, String>

#[tauri::command]
pub async fn delete_persona(id: &str) -> Result<(), String>
```

**수정 파일:** `src-tauri/src/main.rs`
- persona_db 모듈 추가
- tauri::command 등록

### 프론트엔드 서비스

**신규 파일:** `src/services/PersonaService.ts`

```typescript
export async function savePersona(persona: PersonaDefinition): Promise<string>
export async function loadPersona(id: string): Promise<PersonaDefinition>
export async function listPersonas(): Promise<PersonaDefinition[]>
export async function deletePersona(id: string): Promise<void>
```

### 페르소나 관리 UI (선택적)

**신규 파일:** `src/components/PersonaManager/index.tsx`
- 페르소나 목록 표시
- 신규 생성 / 수정 / 삭제
- 내장 템플릿 복제
