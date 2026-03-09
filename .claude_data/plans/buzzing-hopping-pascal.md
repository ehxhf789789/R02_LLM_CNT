# Handbox v2: 동적 지식베이스 + 워크플로우 세부 수정 + 에이전트별 RAG 스코핑

## Context
이전 세션(A~D)에서 리치 미리보기, 도구 확장, 에이전트 고도화가 완료됨. 이제 연구 목적 활용에 필요한 3가지 핵심 기능을 추가한다:
1. 외부 API를 호출하여 동적 지식베이스를 구축하는 파이프라인 (REST 도구 + RAG 출처 추적)
2. 프롬프트로 워크플로우를 세부 수정하는 도구 (노드 추가/수정/삭제, 엣지 관리)
3. 에이전트/프로젝트별 자동 벡터 컬렉션 스코핑

## 핵심 발견 사항
- `web_fetch`는 GET만 지원, 헤더/바디 불가 → 새 `http_request` 도구 필요
- `workflow_add_node`, `workflow_remove_node`, `workflow_connect`, `workflow_set_config`, `workflow_select_node`이 dispatch_tool에 **이미 구현됨** (agent_loop.rs:1708-1768)
- 하지만 `build_tool_definitions()`에 등록되지 않아 function calling으로 호출 불가
- 벡터 컬렉션은 글로벌 flat namespace → 프로젝트/에이전트 스코핑 없음

---

## 작업 영역 3개

### 1. REST API 도구 + RAG 출처 파이프라인

#### 1a. `tool_http_request` (system_tools.rs)
`tool_web_fetch` 뒤에 추가 (line ~963). reqwest 재활용, 신규 의존성 없음.

```rust
pub async fn tool_http_request(
    url: String,
    method: Option<String>,       // GET/POST/PUT/DELETE/PATCH
    headers: Option<Value>,       // {"Authorization": "Bearer ..."}
    body: Option<String>,
    params: Option<Value>,        // 쿼리 파라미터
    timeout_ms: Option<u64>,
    max_chars: Option<usize>,
) -> Result<Value, String>
```

반환: `{text, status, headers, url, method, is_json, response_json, elapsed_ms}`

#### 1b. `api_ingest` 복합 도구 (agent_loop.rs dispatch)
http_request → 텍스트 청킹 → 임베딩 → vector_store를 자동 체이닝.

출처 메타데이터 자동 포함:
```json
{
  "source": "https://api.example.com/data",
  "source_type": "api",
  "source_label": "Example API",
  "chunk_id": 0,
  "total_chunks": 5,
  "ingested_at": "2026-03-04T...",
  "http_status": 200
}
```

헬퍼 함수: `chunk_text(text, chunk_size)` — 20% 오버랩 청킹

#### 1c. `vector_search` 출력 강화
기존 결과에 출처 인용 포맷 추가:
```
1. [score=0.92] doc_chunk_3
   Source: Example API (chunk 3)
   Text: The extracted content...
```

#### 1d. 도구 등록
- `build_tool_definitions`: `http_request` (web 카테고리), `api_ingest` (rag 카테고리)
- `dispatch_tool`: 두 match arm 추가
- `classify_task_tools`: "api", "rest", "ingest", "knowledge" 키워드 → web+rag 카테고리
- `main.rs invoke_handler`: `tool_http_request` 등록

### 2. 워크플로우 세부 수정 도구

#### 2a. 기존 도구 등록 (build_tool_definitions만 추가)
이미 dispatch에 구현된 5개 도구를 function calling tool definition으로 등록:
- `workflow_add_node` — 단일 노드 추가
- `workflow_remove_node` — 노드 삭제 (연결 엣지도 같이)
- `workflow_connect` — 두 노드 연결
- `workflow_set_config` — 노드 설정 변경
- `workflow_select_node` — 노드 선택/하이라이트

#### 2b. 신규 도구 3개 (dispatch + definition)
| 도구 | 기능 | 비고 |
|------|------|------|
| `workflow_update_node` | 라벨/위치 변경 | emit `update_node` 이벤트 |
| `workflow_remove_edge` | 엣지 삭제 | edge_id 또는 source+target |
| `workflow_list` | 캔버스 현재 상태 조회 | 이벤트 round-trip (3s timeout) |

#### 2c. 프론트엔드 이벤트 핸들러 (AgentCanvasBridge.ts)
`WorkflowUpdateEvent` switch에 3개 케이스 추가:
- `update_node` → `store.updateNodeLabel()` + position change
- `remove_edge` → `store.removeEdge()` (ID 또는 source+target 검색)
- `list_request` → `emit('workflow-list-response', JSON.stringify(summary))`

### 3. 에이전트별 자동 벡터 컬렉션 스코핑

#### 3a. 네이밍 컨벤션
`{project_id}__{collection_name}` (이중 밑줄 구분자)

#### 3b. 자동 생성 (run_agent_loop)
프로젝트 ID가 있으면 `{pid}__default` 컬렉션 자동 생성.

#### 3c. 자동 프리픽스 (dispatch_tool)
`vector_store`, `vector_search`, `vector_delete` 호출 시 collection 이름에 자동 프리픽스:
- `project_id` 있고 collection에 `__` 없으면 → `{pid}__{collection}`
- 이미 `__` 포함이면 그대로 사용 (명시적 스코핑)

#### 3d. 시스템 프롬프트 주입
```
## Your Knowledge Base
You have a dedicated vector collection: `proj123__default`
- Use vector_store with this collection to save knowledge
- Use vector_search to search your knowledge base
- Use api_ingest to ingest API data with source tracking
```

#### 3e. 프로젝트 컬렉션 목록
`vector_list_collections` 결과에서 현재 프로젝트 스코프 필터링 + 단축명 표시.

---

## 수정 파일 목록

| 파일 | 변경 내용 |
|------|-----------|
| `crates/hb-tauri/src/commands/system_tools.rs` | `tool_http_request` 추가 (~60줄) |
| `crates/hb-tauri/src/commands/agent_loop.rs` | dispatch: `http_request`, `api_ingest`, `workflow_update_node`, `workflow_remove_edge`, `workflow_list` + build_tool_definitions: 11개 도구 등록 + 시스템 프롬프트 + 스코핑 로직 |
| `crates/hb-tauri/src/main.rs` | invoke_handler에 `tool_http_request` 등록 |
| `frontend/src/services/AgentCanvasBridge.ts` | `update_node`, `remove_edge`, `list_request` 이벤트 핸들러 |

**새 파일 없음** — 전부 기존 파일 수정.

---

## 구현 순서

1. **Phase 1**: `tool_http_request` + dispatch + definition + main.rs 등록
2. **Phase 2**: 워크플로우 도구 등록 (기존 5개) + 신규 3개 dispatch + definition
3. **Phase 3**: 프론트엔드 AgentCanvasBridge 업데이트
4. **Phase 4**: `api_ingest` + `chunk_text` 헬퍼 + `vector_search` 출력 강화
5. **Phase 5**: 에이전트별 컬렉션 스코핑 + 시스템 프롬프트 주입
6. **Phase 6**: 빌드 검증 (cargo build + tsc --noEmit)

---

## 검증 계획

```bash
cargo build -p hb-tauri     # 0 errors
cd frontend && npx tsc --noEmit  # 0 errors
```

### 기능 검증 (앱 실행 후)
1. **REST API**: 에이전트에 "JSONPlaceholder API에서 posts 가져와줘" → `http_request` POST 확인
2. **RAG 파이프라인**: "이 API 데이터를 지식베이스에 저장해" → `api_ingest` → `vector_search`로 출처 확인
3. **워크플로우 수정**: "file-read 노드 추가해" → 캔버스에 노드 출현 확인
4. **워크플로우 세부 수정**: "두 번째 노드 라벨을 'PDF 분석'으로 바꿔" → 라벨 변경 확인
5. **엣지 삭제**: "n1과 n2 사이 연결 끊어줘" → 엣지 제거 확인
6. **컬렉션 스코핑**: 프로젝트 활성 상태에서 vector_store → 컬렉션명 `{pid}__default` 확인
