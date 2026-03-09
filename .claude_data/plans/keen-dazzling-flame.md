# Handbox: 강화학습 시뮬레이션 시스템 설계

## Context

**문제**: Handbox의 워크플로우 생성 에이전트가 144개 원자화 MCP 도구에 대한 학습이 부족하여 복잡한 프롬프트에서 최적의 워크플로우를 생성하지 못함.

**목표**:
1. **20,000건 성공 목표** - NotebookLM 수준 이상의 품질 달성
2. **Claude Code 스타일 테스트 데이터** - 복잡하고 비정형적인 긴 프롬프트
3. **다중 학습 전략** - CoT, Few-shot, Chain Reasoning, Reward/Penalty 기반 MCP 도구 선택
4. **Supervisor Agent** - 버그 수집, 에이전트 성장, 로그 저장
5. **영속성 보장** - 시뮬레이션이 갑자기 중단되어도 학습 기록 유지 (SQLite WAL 모드)

**성공 루프 정의**:
```
프롬프트 → 워크플로우 생성 → 실행 → 결과 → 검증 = 1 성공
실패 시 = 0건 처리 (누적 카운트는 유지, 리셋하지 않음)
```

---

## 핵심 성능 지표

| 지표 | 설명 | 목표 |
|------|------|------|
| **XAI 직관성** | 설명 가능성 점수 | ≥ 75% |
| **NotebookLM 비교** | 벤치마크 통과율 | ≥ 70% |
| **복잡도-시간 효율** | 노드 수 대비 실행 시간 | < 500ms/node |
| **사용자 의도 정렬** | 의미적 유사도 점수 | ≥ 80% |
| **도구 선택 정확도** | 최적 도구 선택률 | ≥ 85% |

---

## 신규 파일 구조

```
src/testing/
├── RLSimulationSystem.ts     # 메인 오케스트레이터 (20,000건 루프)
├── SupervisorAgent.ts        # 버그 수집, 패턴 분석, 에이전트 성장
├── ExperienceBuffer.ts       # RL 경험 리플레이 버퍼
├── RewardCalculator.ts       # 다중 요소 보상 계산기
├── PolicyNetwork.ts          # 전략 선택 네트워크
├── MultiTurnHandler.ts       # 다중 턴 시나리오 핸들러
├── RLLogger.ts               # 영속성 로깅 (SQLite)
└── RLTypes.ts                # 타입 정의

src/types/
└── RLTypes.ts                # 전역 RL 타입
```

---

## 핵심 컴포넌트 설계

### 1. RLSimulationSystem.ts (메인 오케스트레이터)

```typescript
interface RLSimulationConfig {
  targetSuccesses: number        // 20,000
  batchSize: number              // 100
  checkpointInterval: number     // 1000
  maxRetries: number             // 3
  notebookLMThreshold: number    // 0.7
  persistenceMode: 'sqlite'
}

class RLSimulationSystem {
  private experienceBuffer: ExperienceBuffer
  private supervisor: SupervisorAgent
  private rewardCalculator: RewardCalculator
  private policyNetwork: PolicyNetwork
  private logger: RLLogger

  async runSimulation(): Promise<SimulationResult>
  async executeLoop(prompt: string): Promise<LoopResult>
  async checkpoint(): Promise<void>
  async restore(checkpointId: string): Promise<void>
}
```

**핵심 로직**:
```typescript
async runSimulation() {
  let successCount = 0
  let totalAttempts = 0

  while (successCount < this.config.targetSuccesses) {
    const prompt = this.selectPrompt()
    const state = await this.captureState()

    // 1. 전략 선택 (CoT, Few-shot, Chain 등)
    const strategy = this.policyNetwork.selectStrategy(state)

    // 2. 워크플로우 생성
    const workflow = await this.agent.generateWorkflow(prompt, strategy)

    // 3. 실행 및 검증
    const result = await this.executeAndVerify(workflow)

    // 4. 보상 계산 (-5 ~ +5, 정규화)
    const reward = this.rewardCalculator.calculate(result)

    // 5. 경험 저장 (영속성)
    await this.experienceBuffer.add({
      state, action: strategy, reward, nextState: result.state
    })

    // 6. Supervisor 학습
    await this.supervisor.learn(result)

    // 7. 카운트 업데이트
    totalAttempts++
    if (result.success) {
      successCount++
    }
    // 실패해도 누적 카운트 유지 (리셋 안 함)

    // 8. 체크포인트
    if (totalAttempts % this.config.checkpointInterval === 0) {
      await this.checkpoint()
    }
  }
}
```

### 2. SupervisorAgent.ts (학습 관리자)

```typescript
interface BugPattern {
  id: string
  pattern: string           // 정규식 또는 의미적 패턴
  frequency: number
  severity: 'low' | 'medium' | 'high' | 'critical'
  resolution?: string
  examples: FailureExample[]
}

class SupervisorAgent {
  private bugPatterns: Map<string, BugPattern>
  private learningHistory: LearningEntry[]

  // 버그 패턴 탐지 및 수집
  async detectBugPattern(failure: FailureResult): Promise<BugPattern | null>

  // 패턴 기반 학습
  async learn(result: LoopResult): Promise<void>

  // Few-shot 예제 생성
  generateFewShotExamples(category: string): Example[]

  // 에이전트 성장 지표
  getGrowthMetrics(): GrowthMetrics
}
```

### 3. ExperienceBuffer.ts (경험 리플레이)

```typescript
interface Experience {
  id: string
  timestamp: Date
  state: State                  // 현재 상태
  action: Action                // 선택한 전략
  reward: number                // -5 ~ +5
  nextState: State              // 결과 상태
  metadata: {
    promptHash: string
    workflowId: string
    executionTime: number
    nodeCount: number
  }
}

class ExperienceBuffer {
  private db: SQLiteDB          // WAL 모드로 영속성 보장

  async add(exp: Experience): Promise<void>
  async sample(batchSize: number): Promise<Experience[]>
  async getByReward(minReward: number): Promise<Experience[]>

  // 우선순위 리플레이 (TD-error 기반)
  async samplePrioritized(batchSize: number): Promise<Experience[]>
}
```

### 4. RewardCalculator.ts (보상 계산기)

```typescript
interface RewardFactors {
  executionSuccess: boolean       // +2 / -3
  notebookLMComparison: number    // -2 ~ +2
  xaiScore: number                // -1 ~ +1
  nodeEfficiency: number          // -1 ~ +1
  intentAlignment: number         // -1 ~ +1
  toolSelectionAccuracy: number   // -1 ~ +1
}

class RewardCalculator {
  // 다중 요소 보상 계산 (범위: -5 ~ +5)
  calculate(result: LoopResult): number {
    let reward = 0

    // 실행 성공/실패 (가장 큰 가중치)
    reward += result.success ? 2 : -3

    // NotebookLM 비교 (벤치마크)
    reward += this.compareWithNotebookLM(result) * 2

    // XAI 직관성 점수
    reward += result.xaiScore * 1

    // 노드 효율성 (적절한 노드 수)
    reward += this.calculateNodeEfficiency(result) * 1

    // 의도 정렬도
    reward += this.calculateIntentAlignment(result) * 1

    // 정규화 (-5 ~ +5 범위로 클램프)
    return Math.max(-5, Math.min(5, reward))
  }
}
```

### 5. PolicyNetwork.ts (전략 선택)

```typescript
enum Strategy {
  COT = 'chain_of_thought',
  FEWSHOT = 'few_shot',
  CHAIN_REASONING = 'chain_reasoning',
  TEMPLATE_MATCH = 'template_match',
  HYBRID = 'hybrid'
}

class PolicyNetwork {
  private strategyWeights: Map<Strategy, number>
  private contextEmbeddings: EmbeddingCache

  // ε-greedy 전략 선택
  selectStrategy(state: State): Strategy

  // 보상 기반 가중치 업데이트
  updateWeights(strategy: Strategy, reward: number): void

  // 컨텍스트 기반 전략 추천
  recommendStrategy(prompt: string): Strategy
}
```

### 6. RLLogger.ts (영속성 로깅)

```typescript
class RLLogger {
  private db: SQLiteDB  // WAL 모드

  // 즉시 커밋으로 영속성 보장
  async logExperience(exp: Experience): Promise<void>
  async logCheckpoint(cp: Checkpoint): Promise<void>
  async logBugPattern(bug: BugPattern): Promise<void>

  // 복구용 쿼리
  async getLastCheckpoint(): Promise<Checkpoint | null>
  async getExperiencesSince(checkpoint: string): Promise<Experience[]>

  // 통계
  async getStats(): Promise<SimulationStats>
}
```

---

## 12-Point 성공 체크리스트 (기존 WorkflowSimulator 확장)

```typescript
const SUCCESS_CHECKLIST = {
  // 구조적 검증 (4점)
  hasValidStructure: boolean,       // 유효한 DAG 구조
  hasRequiredNodes: boolean,        // 필수 노드 포함
  hasValidConnections: boolean,     // 연결 유효성
  hasNoOrphanNodes: boolean,        // 고아 노드 없음

  // 실행 검증 (4점)
  executionCompleted: boolean,      // 실행 완료
  noRuntimeErrors: boolean,         // 런타임 에러 없음
  outputsGenerated: boolean,        // 출력 생성됨
  withinTimeLimit: boolean,         // 시간 제한 내

  // 품질 검증 (4점)
  intentAligned: boolean,           // 의도 정렬
  xaiExplainable: boolean,          // XAI 설명 가능
  notebookLMPassing: boolean,       // NotebookLM 기준 통과
  toolSelectionOptimal: boolean,    // 최적 도구 선택
}

// 12점 만점 중 10점 이상 = 성공
function isSuccess(checklist: typeof SUCCESS_CHECKLIST): boolean {
  const score = Object.values(checklist).filter(Boolean).length
  return score >= 10
}
```

---

## 테스트 데이터 생성 (Claude Code 스타일)

```typescript
const COMPLEX_PROMPTS = [
  // 다중 파일 처리
  `여러 PDF 파일을 읽어서 각각 텍스트 추출하고,
   중요 내용만 필터링해서 요약한 후,
   엑셀로 정리해서 저장해줘.
   각 파일별로 시트를 분리하고 목차도 만들어줘.`,

  // 조건부 분기
  `이메일 내용을 분석해서 긍정적이면 감사 답장,
   부정적이면 사과 답장을 자동 생성해줘.
   답장 템플릿은 기존 것 참고하고.`,

  // RAG + LLM 조합
  `우리 회사 문서들을 벡터 DB에 넣고,
   사용자 질문에 맞는 문서를 검색해서
   컨텍스트 기반으로 답변 생성하는
   RAG 파이프라인 만들어줘.`,

  // 다중 턴 수정
  `아까 만든 워크플로우에서
   요약 노드를 번역 노드로 바꾸고,
   출력 형식을 JSON으로 변경해줘.`,

  // 복합 데이터 변환
  `CSV 파일 5개를 읽어서 공통 컬럼 기준으로 병합하고,
   결측치는 평균값으로 채우고,
   통계 요약본과 차트도 같이 생성해줘.`,
]
```

---

## 기존 파일 수정

| 파일 | 변경 내용 |
|------|----------|
| `src/testing/WorkflowSimulator.ts` | RLSimulationSystem과 통합, 12-point 체크리스트 export |
| `src/services/IntegratedWorkflowAgent.ts` | PolicyNetwork 전략 적용, XAI 트레이싱 강화 |
| `src/services/XAIService.ts` | 보상 계산용 점수 API 추가 |
| `src/main.tsx` | RLSimulationSystem 초기화 옵션 |

---

## SQLite 스키마 (영속성)

```sql
-- 경험 버퍼
CREATE TABLE experiences (
  id TEXT PRIMARY KEY,
  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
  state_json TEXT NOT NULL,
  action TEXT NOT NULL,
  reward REAL NOT NULL,
  next_state_json TEXT,
  prompt_hash TEXT,
  workflow_id TEXT,
  execution_time_ms INTEGER,
  node_count INTEGER
);

-- 체크포인트
CREATE TABLE checkpoints (
  id TEXT PRIMARY KEY,
  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
  success_count INTEGER NOT NULL,
  total_attempts INTEGER NOT NULL,
  policy_weights_json TEXT,
  supervisor_state_json TEXT
);

-- 버그 패턴
CREATE TABLE bug_patterns (
  id TEXT PRIMARY KEY,
  pattern TEXT NOT NULL,
  frequency INTEGER DEFAULT 1,
  severity TEXT NOT NULL,
  resolution TEXT,
  examples_json TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 학습 이력
CREATE TABLE learning_history (
  id TEXT PRIMARY KEY,
  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
  event_type TEXT NOT NULL,
  details_json TEXT,
  metrics_json TEXT
);

-- WAL 모드 활성화 (갑작스러운 중단에도 데이터 보존)
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
```

---

## 구현 순서

### Phase 1: 타입 및 인프라 (1일)
1. `src/types/RLTypes.ts` - 모든 타입 정의
2. `src/testing/RLLogger.ts` - SQLite 영속성 레이어

### Phase 2: 핵심 컴포넌트 (2일)
1. `src/testing/ExperienceBuffer.ts` - 경험 리플레이
2. `src/testing/RewardCalculator.ts` - 보상 계산
3. `src/testing/PolicyNetwork.ts` - 전략 선택

### Phase 3: 학습 시스템 (2일)
1. `src/testing/SupervisorAgent.ts` - 버그 수집, 학습
2. `src/testing/MultiTurnHandler.ts` - 다중 턴 처리

### Phase 4: 통합 및 실행 (1일)
1. `src/testing/RLSimulationSystem.ts` - 메인 오케스트레이터
2. 기존 파일 수정 및 연동
3. **20,000건 시뮬레이션 시작**

---

## 검증 방법

### 1. 단위 테스트
```bash
npm run test:rl
```

### 2. 시뮬레이션 실행
```typescript
const rl = new RLSimulationSystem({
  targetSuccesses: 20000,
  batchSize: 100,
  checkpointInterval: 1000,
})
await rl.runSimulation()
```

### 3. 진행 상황 모니터링
```typescript
const stats = await rl.getStats()
console.log(`성공: ${stats.successCount} / 시도: ${stats.totalAttempts}`)
console.log(`성공률: ${(stats.successCount / stats.totalAttempts * 100).toFixed(2)}%`)
```

### 4. 복구 테스트
```typescript
// 시뮬레이션 중단 후 재시작
const rl = new RLSimulationSystem(config)
await rl.restore() // 마지막 체크포인트에서 복구
await rl.runSimulation() // 이어서 진행
```

---

## 예상 작업량

| Phase | 파일 수 | LOC | 시간 |
|-------|---------|-----|------|
| 타입/인프라 | 2 | ~300 | 0.5일 |
| 핵심 컴포넌트 | 3 | ~600 | 1일 |
| 학습 시스템 | 2 | ~500 | 1일 |
| 통합/실행 | 2 | ~400 | 0.5일 |
| **합계** | **9** | **~1800** | **3일** |

---

## 사용자 요구사항 반영

- ✅ **목표 20,000건**: RLSimulationConfig.targetSuccesses = 20000
- ✅ **실패 = 0건 처리**: 실패해도 누적 카운트 유지, 리셋 안 함
- ✅ **영속성 보장**: SQLite WAL 모드, 즉시 커밋
- ✅ **설계 완료 후 시작**: 구현 완료 즉시 시뮬레이션 시작
