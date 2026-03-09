# Handbox v2 고도화 — 연구 플랫폼 수준 달성

## Context
시연에서 "연구에 부적절하며 수준이 너무 낮다"는 평가. 핵심 문제:
1. **LLM API 오류** — 워크플로우 노드가 사용자 설정 무시, env var 순서로 잘못된 provider 호출
2. **결과 미리보기 부재** — 노드 결과가 텍스트로만 표시, 시각적 직관성 없음
3. **워크플로우 생성 품질** — 복잡한 지시 이행 불가, config(path 등) 미설정
4. **파일 첨부 불가** — 채팅에서 파일 첨부→노드 자동 연결 불가
5. **백엔드 도구 stub** — data-filter, regex-extract, files-read, folder-read 미구현

---

## Phase 1: LLM Provider 라우팅 수정 (CRITICAL)

### 근본 원인
`local.rs:execute_llm_chat()`이 env var 우선순위로 provider 자동선택:
`ANTHROPIC → OPENAI → AWS IAM → BEDROCK_BEARER → LOCAL`
→ 사용자가 Bedrock 선택해도 ANTHROPIC_API_KEY가 env에 있으면 Anthropic으로 감

### 1.1 — ToolInput에 llm_provider 필드 추가
**File**: `crates/hb-tool-executor/src/lib.rs`
```rust
pub struct ToolInput {
    pub tool_ref: String,
    pub inputs: serde_json::Value,
    pub config: serde_json::Value,
    #[serde(default)]
    pub llm_provider: Option<String>, // NEW: "bedrock"|"openai"|"anthropic"|"local"
}
```

### 1.2 — ExecutionContext에 llm_provider 전달
**File**: `crates/hb-runner/src/scheduler.rs`
- `ExecutionContext`에 `pub llm_provider: Option<String>` 추가
- `with_llm_provider()` builder 메서드 추가
- `execute_native_tool()`에 provider 파라미터 추가 → `ToolInput.llm_provider`에 주입

### 1.3 — execute_llm_chat 수정
**File**: `crates/hb-tool-executor/src/local.rs`
- `input.llm_provider` 있으면 해당 provider만 시도 (env var waterfall 무시)
- `None`이면 기존 waterfall 유지 (하위호환)

### 1.4 — LLMCredentials에 active_provider 추가
**File**: `crates/hb-tauri/src/state.rs`
- `pub active_provider: Option<String>` 필드 추가

### 1.5 — set_active_llm_provider Tauri command
**File**: `crates/hb-tauri/src/commands/llm.rs` + `main.rs` 등록

### 1.6 — execute_workflow에서 provider 주입
**File**: `crates/hb-tauri/src/commands/execution.rs`
- `state.llm_credentials.active_provider` → `ctx.with_llm_provider()`
- `AgentLoopRequest.provider`에도 전달

### 1.7 — Agent loop provider 해결
**File**: `crates/hb-tauri/src/commands/agent_loop.rs`
- `request.provider == None` → `AppState.llm_credentials.active_provider` 사용

### 1.8 — Frontend provider 동기화
**File**: `frontend/src/stores/llmStore.ts`
- `setActiveProvider()` 시 `invoke('set_active_llm_provider', { provider })` 호출

---

## Phase 2: 노드 결과 인라인 미리보기

### 2.1 — PrimitiveNode에 결과 미리보기
**File**: `frontend/src/components/editor/PrimitiveNode.tsx`
- `nodeDetails[id]` 구독하여 완료 시 ports 아래 접이식 미리보기 렌더링
- toolRef별 형식:
  - `file-read`/`pdf-read`: 파일명 + 첫 3줄
  - `llm-chat`/`llm-summarize`: 응답 첫 100자
  - `csv-read`: 행 수 + 컬럼 헤더
  - `display-output`: format별 렌더링 (text/json/markdown)
  - `data-filter`: 필터 결과 건수
  - 기본: JSON 키 요약
- 실패 시 빨간 에러 표시
- 최대 높이 제한 + 스크롤, 클릭 확장/축소
- `display-output`는 완료 시 자동 확장

---

## Phase 3: Agent 워크플로우 생성 품질 향상

### 3.1 — 시스템 프롬프트 강화
**File**: `crates/hb-tauri/src/commands/agent_loop.rs` (`build_system_prompt`)

추가 내용:
1. **워크플로우 생성 필수 규칙**:
   - file-read/pdf-read: 반드시 `config.file_path` 설정
   - display-output: 반드시 `config.format` 설정 + data 입력 연결
   - llm-chat: `config.model`, `config.system_prompt` 설정
   - 사용자가 파일 언급 시 절대경로를 config에 설정

2. **복잡한 워크플로우 예시 3개**:
   - RAG 파이프라인: pdf-read → text-split → embedding → vector-store → vector-search → llm-chat → display-output
   - 다중 문서 분석: files-read → llm-chat → text-merge → file-write
   - 데이터 처리: csv-read → data-filter → text-template → llm-chat → to-excel

3. **포트 연결 참조표** (정확한 output→input 매핑)

4. **흔한 실수 방지** 섹션

---

## Phase 4: 채팅 파일 첨부

### 4.1 — AgentChatPanel 파일 첨부 기능
**File**: `frontend/src/components/agent/AgentChatPanel.tsx`
- Paperclip 버튼 + `@tauri-apps/plugin-dialog` `open()`
- 드래그앤드롭 onDrop 핸들러
- 첨부 파일 칩 표시 (파일명 + X 버튼)
- 전송 시 메시지 앞에 `[첨부 파일: path]` 자동 삽입

---

## Phase 5: 백엔드 도구 구현 완성

### 5.1 — regex 의존성
**File**: `crates/hb-tool-executor/Cargo.toml` — `regex = "1"` 추가

### 5.2 — 도구 구현
**File**: `crates/hb-tool-executor/src/local.rs`
- `regex-extract`: `regex::Regex` 실제 정규식 매칭
- `data-filter`: `"field op value"` 조건 파싱 (eq/ne/gt/lt/contains)
- `files-read`: 여러 파일 경로 각각 읽기
- `folder-read`: 폴더 + glob 패턴 파일 목록 읽기
- dispatch match에 `"files-read"`, `"folder-read"` arm 추가

---

## 수정 파일 요약

| Phase | File | 변경 |
|-------|------|------|
| 1 | `crates/hb-tool-executor/src/lib.rs` | ToolInput.llm_provider |
| 1 | `crates/hb-runner/src/scheduler.rs` | ExecutionContext.llm_provider + 전달 |
| 1 | `crates/hb-tool-executor/src/local.rs` | execute_llm_chat provider 분기 |
| 1 | `crates/hb-tauri/src/state.rs` | LLMCredentials.active_provider |
| 1 | `crates/hb-tauri/src/commands/llm.rs` | set_active_llm_provider 커맨드 |
| 1 | `crates/hb-tauri/src/main.rs` | 커맨드 등록 |
| 1 | `crates/hb-tauri/src/commands/execution.rs` | provider 주입 |
| 1 | `crates/hb-tauri/src/commands/agent_loop.rs` | provider 해결 |
| 1 | `frontend/src/stores/llmStore.ts` | backend 동기화 |
| 2 | `frontend/src/components/editor/PrimitiveNode.tsx` | 인라인 미리보기 |
| 3 | `crates/hb-tauri/src/commands/agent_loop.rs` | 시스템 프롬프트 강화 |
| 4 | `frontend/src/components/agent/AgentChatPanel.tsx` | 파일 첨부 UI |
| 5 | `crates/hb-tool-executor/Cargo.toml` | regex 의존성 |
| 5 | `crates/hb-tool-executor/src/local.rs` | 도구 구현 완성 |

## 검증
1. `cargo build` — 전체 백엔드 빌드
2. `cargo test -p hb-tauri` — 기존 테스트 통과
3. `npx tsc --noEmit` — 프론트엔드 타입 체크
4. `npx vitest run` — 프론트엔드 테스트
5. 수동: Bedrock 설정 → 워크플로우 llm-chat 실행 → 정상 동작
6. 수동: 노드 실행 후 인라인 미리보기 확인
7. 수동: 파일 첨부 → 에이전트가 경로 인식 확인
