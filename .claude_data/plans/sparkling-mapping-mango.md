# Handbox v2 - 연구용 AI 샌드박스 플랫폼 재설계 계획

## Context

Handbox를 "MCP 백과사전이자 통합 플랫폼"으로 처음부터 재설계한다.
핵심 목적: 연구자가 모든 확장자의 문서/파일을 전처리하고, MCP 도구와 LLM을 자유롭게 조합하여
RAG, AI Agent, Chain-of-Thought 등 어떤 AI 워크플로우든 시각적으로 구축하고 실험할 수 있는 플랫폼.

**3계층 원칙:**
- Tier 1 (내장 도구): Rust로 직접 구현, 앱에 포함, 외부 의존 없음
- Tier 2 (플러그인): GitHub MCP 서버를 설치/제거하여 노드 자동 생성
- Tier 3 (LLM): API만 호출, 프로바이더 교체 가능

---

## 기존 코드 재사용 vs 재구축 판단

### 유지 (검증된 인프라)
| 파일 | 이유 |
|------|------|
| `src/registry/NodeRegistry.ts` | 싱글톤 패턴, search/subscribe 완비 |
| `src/registry/ProviderRegistry.ts` | LLM 프로바이더 추상화 완비 |
| `src/registry/NodeDefinition.ts` | NodeExecutor 인터페이스, ConfigField 타입 |
| `src/engine/ExecutionEngine.ts` | Kahn 알고리즘 토폴로지 정렬 (루프 지원 확장 필요) |
| `src/engine/types.ts` | DataType, PortDefinition (타입 추가 필요) |
| `src/nodes/GenericNode.tsx` | 범용 노드 렌더러 |
| `src/components/WorkflowEditor/` | React Flow 캔버스, 연결 검증 |
| `src/components/NodePalette/` | 카테고리별 노드 브라우저 |
| `src/components/PropertyPanel/` | ConfigField → UI 자동 생성 |
| `src/stores/workflowStore.ts` | 노드/엣지/실행 상태 |
| `src/stores/appStore.ts` | 인증, 설정 (간소화 필요) |
| `src/providers/llm/` | Bedrock, OpenAI, Anthropic 프로바이더 |
| `src-tauri/src/main.rs` | Tauri 앱 셋업 |
| `src-tauri/Cargo.toml` | 의존성 (크레이트 추가 필요) |
| `src/main.tsx` | 초기화 순서 패턴 |
| `src/App.tsx` | 인증 흐름 |

### 재구축 (새 아키텍처에 맞게)
| 대상 | 이유 |
|------|------|
| `src/executors/*` 전체 | 원자 도구 단위로 재설계 |
| `src-tauri/src/commands/*` 대부분 | 도구 도메인별 재조직 |
| `src/adapters/mcp/` | 플러그인 시스템으로 확장 |
| `src/stores/mcpStore.ts` | 플러그인 스토어로 교체 |
| `src/engine/StreamHandler.ts` | 새 스트리밍 아키텍처 |

### 삭제
| 대상 | 이유 |
|------|------|
| `src/data/workflows/` | 레거시 워크플로우 |
| `src/plugins/cnt-evaluation/` | 레거시 플러그인 |
| `src/components/ExternalAPISettingsDialog/` | 이미 삭제됨 |
| `src/executors/cloud/aws/` | Tier 1 도구로 대체 |

---

## 새 파일 구조

```
Handbox/
├── src-tauri/src/
│   ├── main.rs                          # Tauri 앱 (유지, 커맨드 등록 업데이트)
│   ├── commands/
│   │   ├── mod.rs                       # 모듈 선언
│   │   │
│   │   ├── # === Tier 1: 내장 도구 (NEW) ===
│   │   ├── tool_io.rs                   # file.read, file.write, file.list, file.info, http.request
│   │   ├── tool_transform.rs            # json.parse, json.query, csv.parse, text.split, text.regex, text.template, xml.parse
│   │   ├── tool_storage.rs              # kv.*, vector.*, sqlite.*
│   │   ├── tool_doc.rs                  # doc.parse (범용 문서 파서), doc.convert
│   │   ├── tool_process.rs              # code.eval, shell.exec
│   │   │
│   │   ├── # === Tier 2: 플러그인 시스템 (NEW) ===
│   │   ├── plugin_manager.rs            # 플러그인 설치/제거/빌드
│   │   ├── plugin_mcp.rs               # MCP 서버 실행/통신 (기존 mcp.rs 확장)
│   │   │
│   │   ├── # === Tier 3: LLM/클라우드 (유지+정리) ===
│   │   ├── aws_service.rs               # AWS SDK (유지)
│   │   ├── credentials.rs               # OS 키체인 (유지)
│   │   │
│   │   └── # === 인프라 (유지) ===
│   │       workflow.rs                  # 워크플로우 저장/로드 (유지, 간소화)
│   │
│   └── tools/                           # 도구 구현 헬퍼 (NEW)
│       ├── mod.rs
│       ├── doc_parsers.rs              # 확장자별 파서 구현
│       ├── json_query.rs              # JSONPath 엔진
│       ├── template_engine.rs         # 템플릿 엔진
│       ├── text_chunker.rs            # 스마트 청킹 엔진
│       └── vector_index.rs            # 벡터 인덱스 (HNSW)
│
├── src/
│   ├── main.tsx                         # (유지) 초기화 순서
│   ├── App.tsx                          # (유지) 인증 흐름
│   │
│   ├── registry/                        # (유지)
│   │   ├── NodeRegistry.ts
│   │   ├── NodeDefinition.ts
│   │   └── ProviderRegistry.ts
│   │
│   ├── engine/                          # (유지 + 확장)
│   │   ├── ExecutionEngine.ts           # 루프/분기 지원 추가
│   │   ├── types.ts                     # 새 DataType 추가
│   │   └── StreamHandler.ts             # 재구축
│   │
│   ├── tools/                           # === NEW: Tier 1 도구 노드 정의 ===
│   │   ├── index.ts                     # registerAllTools()
│   │   ├── io.tools.ts                  # file.read, file.write, file.list, file.info, http.request
│   │   ├── transform.tools.ts           # json.*, csv.*, text.*, xml.*
│   │   ├── storage.tools.ts             # kv.*, vector.*, sqlite.*
│   │   ├── doc.tools.ts                # doc.parse, doc.convert
│   │   ├── process.tools.ts             # code.eval, shell.exec
│   │   ├── control.tools.ts             # if, switch, loop, forEach, while, merge, split, gate
│   │   ├── variable.tools.ts            # variable.get/set, constant
│   │   ├── debug.tools.ts              # log, inspect, breakpoint
│   │   ├── viz.tools.ts                # table.view, chart.view, json.view, text.view, stats.view
│   │   └── llm.tools.ts                # llm.chat, llm.embed, llm.structured, prompt.*
│   │
│   ├── plugins/                         # === NEW: Tier 2 플러그인 시스템 ===
│   │   ├── PluginManager.ts             # 설치/제거/활성화/비활성화
│   │   ├── PluginStore.ts               # Zustand 스토어
│   │   ├── PluginToNode.ts              # MCP 도구 → NodeDefinition 변환
│   │   └── types.ts                     # PluginManifest, PluginStatus
│   │
│   ├── providers/                       # (유지)
│   │   ├── llm/BedrockLLMProvider.ts
│   │   ├── llm/OpenAIProvider.ts
│   │   ├── llm/AnthropicProvider.ts
│   │   └── embedding/BedrockEmbeddingProvider.ts
│   │
│   ├── components/                      # (유지 + 신규)
│   │   ├── WorkflowEditor/              # (유지)
│   │   ├── NodePalette/                 # (유지, 카테고리 업데이트)
│   │   ├── PropertyPanel/               # (유지)
│   │   ├── MainLayout/                  # (유지)
│   │   ├── PluginManagerDialog/         # NEW: 플러그인 관리 UI
│   │   ├── PluginStoreDialog/           # NEW: 플러그인 스토어 UI
│   │   └── ExecutionDebugger/           # NEW: 실행 디버거 UI
│   │
│   ├── nodes/                           # (유지)
│   │   ├── GenericNode.tsx
│   │   ├── InputNode.tsx
│   │   └── OutputNode.tsx
│   │
│   └── stores/                          # (유지 + 교체)
│       ├── workflowStore.ts             # (유지)
│       ├── appStore.ts                  # (유지, 간소화)
│       ├── pluginStore.ts               # NEW: 플러그인 상태
│       ├── credentialStore.ts           # (유지)
│       └── executionStore.ts            # (유지)
```

---

## Phase 1: Tier 1 내장 도구 — Rust 백엔드

### 1-1. IO 도구 (`tool_io.rs`)

#### `tool_file_read`
```rust
#[tauri::command]
pub async fn tool_file_read(
    path: String,
    encoding: Option<String>,      // auto, utf-8, euc-kr, shift-jis, cp949...
    offset: Option<u64>,           // 바이트 오프셋 (대용량 부분 읽기)
    limit: Option<u64>,            // 최대 바이트 수
    as_binary: Option<bool>,       // true면 base64로 반환
) -> Result<serde_json::Value, String>
// 반환: { data, encoding_detected, size, mime_type, truncated, metadata: { modified, created } }
```
**원리:** 파일 경로를 받아 인코딩을 자동 감지(BOM 확인 → chardetng 크레이트)하고, 텍스트/바이너리를 구분하여 반환. 대용량 파일은 offset/limit으로 스트리밍 읽기.
**핵심 크레이트:** `encoding_rs` (인코딩 변환), `chardetng` (인코딩 감지), `infer` (MIME 감지)

#### `tool_file_write`
```rust
#[tauri::command]
pub async fn tool_file_write(
    path: String,
    content: String,
    encoding: Option<String>,      // 기본 utf-8
    mode: Option<String>,          // overwrite, append, atomic
    create_dirs: Option<bool>,     // 상위 디렉토리 자동 생성
    backup: Option<bool>,          // 덮어쓰기 전 .bak 생성
) -> Result<serde_json::Value, String>
// 반환: { success, path, size, backup_path }
```
**원리:** atomic 모드는 임시파일에 쓴 뒤 rename으로 교체 (쓰기 중 크래시 시 데이터 보호). backup 모드는 기존 파일을 .bak으로 복사 후 덮어쓰기.

#### `tool_file_list`
```rust
#[tauri::command]
pub async fn tool_file_list(
    path: String,
    pattern: Option<String>,       // glob 패턴: "**/*.pdf", "*.xlsx"
    recursive: Option<bool>,       // 하위 디렉토리 포함
    include_hidden: Option<bool>,
    sort_by: Option<String>,       // name, size, modified, type
    limit: Option<usize>,
) -> Result<serde_json::Value, String>
// 반환: { files: [{ name, path, size, is_dir, extension, modified }], total_count }
```
**핵심 크레이트:** `glob` (패턴 매칭), `walkdir` (재귀 탐색)

#### `tool_file_info`
```rust
#[tauri::command]
pub async fn tool_file_info(
    path: String,
) -> Result<serde_json::Value, String>
// 반환: { name, extension, size, size_human, mime_type, is_text, is_binary,
//         created, modified, accessed, permissions, parent_dir }
```

#### `tool_http_request`
```rust
#[tauri::command]
pub async fn tool_http_request(
    url: String,
    method: Option<String>,        // GET, POST, PUT, DELETE, PATCH
    headers: Option<HashMap<String, String>>,
    body: Option<String>,
    timeout_ms: Option<u64>,       // 기본 30000
    follow_redirects: Option<bool>,
    response_type: Option<String>, // text, json, binary
) -> Result<serde_json::Value, String>
// 반환: { status, status_text, headers, body, elapsed_ms, content_type }
```
**핵심 크레이트:** `reqwest` (이미 있음)

---

### 1-2. Transform 도구 (`tool_transform.rs` + `tools/json_query.rs` + `tools/template_engine.rs`)

#### `tool_json_query` — 플랫폼 핵심 도구 #1
```rust
#[tauri::command]
pub async fn tool_json_query(
    data: serde_json::Value,       // 입력 JSON
    query: String,                 // 쿼리 표현식
) -> Result<serde_json::Value, String>
```
**쿼리 문법 (Level 2):**
```
경로 접근:      "users[0].name"           → "Kim"
배열 순회:      "users[*].name"           → ["Kim", "Lee"]
필터:          "users[?age > 27]"        → [{ age: 30, ... }]
필터+추출:      "users[?age > 27].name"   → ["Kim"]
집계:          "users[*].score | sum"    → 285
             "users[*].score | avg"    → 95
             "users | count"           → 3
             "users[*].score | min"    → 85
             "users[*].score | max"    → 100
정렬:          "users | sort_by(.age)"   → [sorted]
역정렬:        "users | sort_by(.age) | reverse" → [reverse sorted]
슬라이스:       "users[0:2]"              → 첫 2개
고유값:        "users[*].dept | unique"  → ["eng", "design"]
플래튼:        "data[*].items | flatten" → [모든 아이템 평탄화]
키 추출:       "users[0] | keys"         → ["name", "age", "dept"]
값 추출:       "users[0] | values"       → ["Kim", 30, "eng"]
중첩:          "data.teams[*].members[?role == 'lead'].name"
```
**구현:** `tools/json_query.rs`에 자체 파서 + 평가기 구현. serde_json::Value를 재귀 탐색.
**이것이 플랫폼 품질을 좌우하는 #1 도구** — 모든 데이터 변환이 여기를 통과.

#### `tool_json_parse`
```rust
#[tauri::command]
pub async fn tool_json_parse(
    text: String,
    strict: Option<bool>,          // false면 JSON5/JSONC 허용
) -> Result<serde_json::Value, String>
```

#### `tool_json_stringify`
```rust
#[tauri::command]
pub async fn tool_json_stringify(
    data: serde_json::Value,
    pretty: Option<bool>,
    indent: Option<usize>,         // 기본 2
) -> Result<String, String>
```

#### `tool_csv_parse`
```rust
#[tauri::command]
pub async fn tool_csv_parse(
    text: String,
    delimiter: Option<String>,     // auto-detect, comma, tab, pipe, semicolon
    has_header: Option<bool>,      // 기본 true
    type_inference: Option<bool>,  // 숫자/불리언 자동 변환
    max_rows: Option<usize>,
) -> Result<serde_json::Value, String>
// 반환: { headers, rows: [{ col1: val1, ... }], row_count, column_count, types_detected }
```
**핵심:** 구분자 자동 감지 — 첫 5줄에서 ,/\t/|/; 빈도 분석

#### `tool_csv_stringify`
```rust
#[tauri::command]
pub async fn tool_csv_stringify(
    data: serde_json::Value,       // [{ key: val }] 배열
    delimiter: Option<String>,
    include_header: Option<bool>,
) -> Result<String, String>
```

#### `tool_text_split` — 플랫폼 핵심 도구 #4 (RAG 청킹 품질)
```rust
#[tauri::command]
pub async fn tool_text_split(
    text: String,
    method: String,                // separator, tokens, sentences, sliding_window, recursive
    chunk_size: Option<usize>,     // 기본 1000
    chunk_overlap: Option<usize>,  // 기본 200
    separator: Option<String>,     // method=separator일 때
    preserve_sentences: Option<bool>, // 문장 중간 절단 방지
) -> Result<serde_json::Value, String>
// 반환: { chunks: [{ text, index, start_char, end_char, token_count_approx }], total_chunks }
```
**method별 동작:**
- `separator`: 구분자로 분할 후 chunk_size 이내로 병합
- `tokens`: 토큰 수 기준 분할 (공백+구두점 기반 근사)
- `sentences`: 문장 단위 분할 후 chunk_size 이내로 병합
- `sliding_window`: 고정 크기 윈도우를 overlap만큼 슬라이딩
- `recursive`: 큰 구분자(\n\n) → 작은 구분자(\n) → 문자 순으로 재귀 분할
**구현:** `tools/text_chunker.rs`

#### `tool_text_regex`
```rust
#[tauri::command]
pub async fn tool_text_regex(
    text: String,
    pattern: String,               // 정규식
    operation: String,             // match, match_all, replace, extract, split, test
    replacement: Option<String>,   // operation=replace일 때
    flags: Option<String>,         // i(대소문자), m(멀티라인), s(dotall)
) -> Result<serde_json::Value, String>
// match → { matched: bool, groups: [...], index }
// match_all → { matches: [{ text, index, groups }], count }
// extract → { captures: [{ name, value }] } (명명 그룹)
// replace → { result, replacements_count }
// split → { parts: [...] }
// test → { result: bool }
```
**핵심 크레이트:** `regex`

#### `tool_text_template` — 플랫폼 핵심 도구 #2
```rust
#[tauri::command]
pub async fn tool_text_template(
    template: String,
    variables: serde_json::Value,  // 변수 맵
) -> Result<String, String>
```
**템플릿 문법:**
```
변수 삽입:     {{name}}
점 접근:       {{user.name}}
조건:          {{#if condition}}...{{else}}...{{/if}}
반복:          {{#each items}}{{this.name}} ({{@index}}){{/each}}
기본값:        {{name | default:"없음"}}
대문자:        {{name | upper}}
소문자:        {{name | lower}}
자르기:        {{text | truncate:100}}
줄바꿈:        {{text | nl2br}}
JSON:         {{data | json}}
길이:          {{items | length}}
```
**구현:** `tools/template_engine.rs` — Handlebars 유사 자체 파서. 외부 크레이트 `handlebars` 사용도 가능하나, 커스텀 필터 확장성을 위해 자체 구현 권장.

#### `tool_xml_parse`
```rust
#[tauri::command]
pub async fn tool_xml_parse(text: String) -> Result<serde_json::Value, String>
// XML → JSON 변환
```
**핵심 크레이트:** `quick-xml` (이미 있음)

#### `tool_xml_stringify`
```rust
#[tauri::command]
pub async fn tool_xml_stringify(data: serde_json::Value, root_tag: Option<String>) -> Result<String, String>
```

---

### 1-3. Storage 도구 (`tool_storage.rs` + `tools/vector_index.rs`)

#### `tool_kv_set` / `tool_kv_get` / `tool_kv_delete` / `tool_kv_list`
```rust
#[tauri::command]
pub async fn tool_kv_set(
    namespace: Option<String>,     // 기본 "default"
    key: String,
    value: serde_json::Value,
    ttl_seconds: Option<u64>,      // 만료 시간 (선택)
) -> Result<serde_json::Value, String>

#[tauri::command]
pub async fn tool_kv_get(
    namespace: Option<String>,
    key: String,
) -> Result<serde_json::Value, String>
// 반환: { value, exists, created_at, updated_at }

#[tauri::command]
pub async fn tool_kv_delete(namespace: Option<String>, key: String) -> Result<bool, String>

#[tauri::command]
pub async fn tool_kv_list(
    namespace: Option<String>,
    prefix: Option<String>,        // 키 접두사 필터
    limit: Option<usize>,
) -> Result<serde_json::Value, String>
// 반환: { keys: [{ key, value_type, size, updated_at }], count }
```
**구현:** SQLite 단일 파일. `CREATE TABLE kv (namespace, key, value_json, created_at, updated_at, expires_at)`

#### `tool_vector_store` — 플랫폼 핵심 도구 #3 (RAG 심장)
```rust
#[tauri::command]
pub async fn tool_vector_store(
    collection: String,
    documents: Vec<VectorDocument>,
    // VectorDocument: { id: Option<String>, text: String, embedding: Vec<f32>, metadata: Option<Value> }
) -> Result<serde_json::Value, String>
// 반환: { stored_count, collection, ids: [...] }
```

#### `tool_vector_search`
```rust
#[tauri::command]
pub async fn tool_vector_search(
    collection: String,
    query_embedding: Vec<f32>,
    top_k: Option<usize>,          // 기본 5
    threshold: Option<f32>,        // 최소 유사도 (0.0~1.0)
    filter: Option<String>,        // 메타데이터 필터: "category = 'legal' AND year > 2020"
) -> Result<serde_json::Value, String>
// 반환: { results: [{ id, text, score, metadata }], search_time_ms }
```
**구현 (`tools/vector_index.rs`):**
- 단계 1 (즉시): SQLite + 브루트포스 코사인 유사도 (현재 구현 개선)
- 단계 2 (Phase 4): HNSW 인덱스 (`instant-distance` 크레이트) O(log n) 검색
- 메타데이터 필터: SQLite WHERE 절로 후보 필터링 → 벡터 검색

#### `tool_vector_hybrid_search`
```rust
#[tauri::command]
pub async fn tool_vector_hybrid_search(
    collection: String,
    query_embedding: Vec<f32>,
    query_text: String,            // 키워드 검색용
    top_k: Option<usize>,
    vector_weight: Option<f32>,    // 기본 0.7
    text_weight: Option<f32>,      // 기본 0.3
    filter: Option<String>,
) -> Result<serde_json::Value, String>
// 벡터 유사도 점수 * weight + 키워드 매칭 점수 * weight → 종합 순위
```

#### `tool_sqlite_query`
```rust
#[tauri::command]
pub async fn tool_sqlite_query(
    db_path: Option<String>,       // None이면 기본 DB
    sql: String,
    params: Option<Vec<serde_json::Value>>,
) -> Result<serde_json::Value, String>
// SELECT → { rows: [...], columns: [...], row_count }
// INSERT/UPDATE/DELETE → { affected_rows }
// CREATE/ALTER → { success }
```

#### `tool_sqlite_schema`
```rust
#[tauri::command]
pub async fn tool_sqlite_schema(
    db_path: Option<String>,
    operation: String,             // create_table, list_tables, describe_table, drop_table
    table_name: Option<String>,
    columns: Option<Vec<ColumnDef>>,
) -> Result<serde_json::Value, String>
```

---

### 1-4. 문서 파서 (`tool_doc.rs` + `tools/doc_parsers.rs`) — 모든 확장자 지원

#### `tool_doc_parse` — 범용 문서 파서
```rust
#[tauri::command]
pub async fn tool_doc_parse(
    path: String,
    options: Option<DocParseOptions>,
    // DocParseOptions: { pages, max_chars, extract_images, ocr, sheet_index }
) -> Result<serde_json::Value, String>
// 반환: { text, metadata: { title, author, pages, format, ... },
//         structured_data (테이블/시트 데이터), images (추출 이미지 경로) }
```
**확장자별 처리 전략:**

| Tier | 확장자 | 처리 방법 | 크레이트/도구 |
|------|--------|-----------|--------------|
| 네이티브 | .pdf | Rust 직접 파싱 | `pdf-extract` (있음) |
| 네이티브 | .xlsx/.xls/.ods | Rust 직접 파싱 | `calamine` (있음) |
| 네이티브 | .csv/.tsv | Rust 직접 파싱 | `csv` (있음) |
| 네이티브 | .json | Rust 직접 파싱 | `serde_json` (있음) |
| 네이티브 | .xml | Rust 직접 파싱 | `quick-xml` (있음) |
| 네이티브 | .txt/.md/.log | 텍스트 읽기 | 표준 라이브러리 |
| 네이티브 | .html | HTML→텍스트 | `scraper` 크레이트 추가 |
| 외부도구 | .docx | pandoc 호출 | `shell: pandoc -t plain` |
| 외부도구 | .pptx | pandoc 호출 | `shell: pandoc -t plain` |
| 외부도구 | .hwp | hwp5txt 호출 | `shell: hwp5txt` (Python) |
| 외부도구 | .epub | pandoc 호출 | `shell: pandoc -t plain` |
| 외부도구 | .rtf | pandoc 호출 | `shell: pandoc -t plain` |
| 외부도구 | .odt/.odp | pandoc/LibreOffice | `shell: pandoc` or `soffice --convert-to` |
| 외부도구 | .latex/.tex | pandoc 호출 | `shell: pandoc -t plain` |
| 이미지 | .png/.jpg/.tiff | OCR | `shell: tesseract` or AWS Textract API |
| 플러그인 | .rvt/.rfa | Revit MCP 플러그인 | Tier 2 플러그인 |
| 플러그인 | .dwg/.dxf | AutoCAD MCP 플러그인 | Tier 2 플러그인 |
| 플러그인 | .ifc | IFC MCP 플러그인 | Tier 2 플러그인 |
| 폴백 | 기타 모든 확장자 | 바이너리 메타데이터 | `infer` + hex dump |

**구현 로직:**
```rust
fn parse_document(path: &str, options: &DocParseOptions) -> Result<DocResult> {
    let ext = get_extension(path).to_lowercase();

    match ext.as_str() {
        // Tier: 네이티브 (Rust 직접)
        "pdf" => parse_pdf(path, options),
        "xlsx" | "xls" | "ods" => parse_spreadsheet(path, options),
        "csv" | "tsv" => parse_csv_file(path, options),
        "json" => parse_json_file(path, options),
        "xml" => parse_xml_file(path, options),
        "txt" | "md" | "log" | "ini" | "cfg" | "yaml" | "yml" | "toml" => parse_text(path, options),
        "html" | "htm" => parse_html(path, options),

        // Tier: 외부 도구 (pandoc/시스템 명령)
        "docx" | "pptx" | "epub" | "rtf" | "odt" | "odp" | "tex" | "latex" =>
            parse_via_pandoc(path, ext, options),
        "hwp" => parse_hwp(path, options),

        // Tier: 이미지 OCR
        "png" | "jpg" | "jpeg" | "tiff" | "bmp" | "gif" =>
            parse_image_ocr(path, options),

        // Tier: 폴백 (메타데이터만)
        _ => parse_binary_fallback(path, options),
    }
}
```

#### `tool_doc_convert`
```rust
#[tauri::command]
pub async fn tool_doc_convert(
    input_path: String,
    output_format: String,         // pdf, docx, txt, md, html, xlsx, csv, json
    output_path: Option<String>,   // None이면 자동 생성
) -> Result<serde_json::Value, String>
// 반환: { output_path, format, size }
```
**구현:** pandoc 또는 LibreOffice CLI(`soffice --convert-to`)로 위임

---

### 1-5. Process 도구 (`tool_process.rs`)

#### `tool_shell_exec`
```rust
#[tauri::command]
pub async fn tool_shell_exec(
    command: String,
    args: Option<Vec<String>>,
    working_dir: Option<String>,
    env: Option<HashMap<String, String>>,
    timeout_ms: Option<u64>,       // 기본 60000
    stdin: Option<String>,
) -> Result<serde_json::Value, String>
// 반환: { stdout, stderr, exit_code, elapsed_ms }
```
**보안:** 화이트리스트 검증 유지 (기존 cli.rs 패턴)

#### `tool_code_eval`
```rust
#[tauri::command]
pub async fn tool_code_eval(
    code: String,
    language: String,              // python, javascript
    timeout_ms: Option<u64>,       // 기본 30000
    input_data: Option<serde_json::Value>, // stdin으로 전달
) -> Result<serde_json::Value, String>
// 반환: { stdout, stderr, exit_code, result (JSON 파싱 시도) }
```
**구현:** 임시 파일 생성 → python/node 실행 → 결과 캡처 → 임시 파일 삭제

---

## Phase 2: Tier 1 내장 도구 — 프론트엔드 노드 정의

각 Rust 커맨드를 NodeDefinition으로 래핑합니다.

### 노드 정의 패턴 (모든 도구 동일 구조)

```typescript
// src/tools/io.tools.ts 예시

export const fileReadDef: NodeDefinition = {
  type: 'io.file-read',
  category: 'io',
  meta: {
    label: '파일 읽기',
    description: '텍스트/바이너리 파일을 읽습니다. 인코딩 자동 감지, 대용량 부분 읽기를 지원합니다.',
    icon: 'FileOpen',
    color: '#3b82f6',
    tags: ['file', 'read', 'io', 'text', 'binary', '파일'],
  },
  ports: {
    inputs: [
      { name: 'path', type: 'text', required: false, description: '파일 경로 (config에서도 설정 가능)' },
    ],
    outputs: [
      { name: 'text', type: 'text', required: true, description: '파일 내용 (텍스트)' },
      { name: 'metadata', type: 'json', required: false, description: '파일 메타데이터' },
    ],
  },
  configSchema: [
    { key: 'path', label: '파일 경로', type: 'file', required: true, description: '읽을 파일을 선택하세요' },
    { key: 'encoding', label: '인코딩', type: 'select', default: 'auto',
      options: [
        { label: '자동 감지', value: 'auto' },
        { label: 'UTF-8', value: 'utf-8' },
        { label: 'EUC-KR (한국어)', value: 'euc-kr' },
        { label: 'Shift-JIS (일본어)', value: 'shift-jis' },
      ] },
    { key: 'limit', label: '최대 읽기 크기 (bytes)', type: 'number', default: 0,
      description: '0이면 전체 읽기' },
  ],
  runtime: 'tauri',
  executor: {
    async execute(input, config, context) {
      const path = input.path || config.path;
      const result = await invoke('tool_file_read', {
        path,
        encoding: config.encoding === 'auto' ? null : config.encoding,
        limit: config.limit || null,
      });
      return {
        text: result.data,
        metadata: { size: result.size, mime: result.mime_type, encoding: result.encoding_detected },
      };
    }
  }
};
```

### 전체 노드 목록 (각 .tools.ts 파일별)

**io.tools.ts** (5개):
- `io.file-read`, `io.file-write`, `io.file-list`, `io.file-info`, `io.http-request`

**transform.tools.ts** (9개):
- `transform.json-parse`, `transform.json-query`, `transform.json-stringify`
- `transform.csv-parse`, `transform.csv-stringify`
- `transform.text-split`, `transform.text-regex`, `transform.text-template`
- `transform.xml-parse`

**storage.tools.ts** (8개):
- `storage.kv-get`, `storage.kv-set`, `storage.kv-delete`, `storage.kv-list`
- `storage.vector-store`, `storage.vector-search`, `storage.vector-hybrid`
- `storage.sqlite-query`

**doc.tools.ts** (2개):
- `doc.parse`, `doc.convert`

**process.tools.ts** (2개):
- `process.shell-exec`, `process.code-eval`

**control.tools.ts** (10개):
- `control.if`, `control.switch`, `control.loop`, `control.forEach`, `control.while`
- `control.merge`, `control.split`, `control.gate`
- `control.variable-get`, `control.variable-set`

**variable.tools.ts** (2개):
- `data.constant`, `data.input`

**debug.tools.ts** (3개):
- `debug.log`, `debug.inspect`, `debug.breakpoint`

**viz.tools.ts** (5개):
- `viz.table`, `viz.chart`, `viz.json`, `viz.text`, `viz.stats`

**llm.tools.ts** (6개):
- `llm.chat`, `llm.embed`, `llm.structured`
- `prompt.template`, `prompt.fewshot`, `prompt.chain`

**총 52개 내장 노드**

---

## Phase 3: Tier 2 플러그인 시스템

### 3-1. 플러그인 매니저 Rust 백엔드 (`plugin_manager.rs`)

```rust
#[tauri::command]
pub async fn plugin_install(
    source: String,                // GitHub URL 또는 로컬 경로
    manifest: Option<String>,      // manifest.json 내용 (직접 입력 시)
) -> Result<serde_json::Value, String>
// 동작: git clone → install → build → manifest 저장
// 반환: { plugin_id, name, version, tools_discovered: [...], status }

#[tauri::command]
pub async fn plugin_uninstall(plugin_id: String) -> Result<bool, String>
// 동작: 서버 종료 → 노드 등록 해제 → 폴더 삭제

#[tauri::command]
pub async fn plugin_start(plugin_id: String) -> Result<serde_json::Value, String>
// 동작: MCP 서버 프로세스 실행 → initialize → tools/list → 도구 반환

#[tauri::command]
pub async fn plugin_stop(plugin_id: String) -> Result<bool, String>
// 동작: 프로세스 종료

#[tauri::command]
pub async fn plugin_call_tool(
    plugin_id: String,
    tool_name: String,
    arguments: serde_json::Value,
) -> Result<serde_json::Value, String>
// 동작: JSON-RPC tools/call → 결과 반환

#[tauri::command]
pub async fn plugin_list() -> Result<serde_json::Value, String>
// 반환: 설치된 플러그인 목록 + 상태

#[tauri::command]
pub async fn plugin_list_available() -> Result<serde_json::Value, String>
// 반환: 추천 플러그인 목록 (하드코딩된 레지스트리)
```

### 3-2. 플러그인 스토어 (`src/plugins/PluginStore.ts`)

```typescript
interface PluginManifest {
  name: string;
  version: string;
  description: string;
  icon?: string;
  category: string;              // architecture, data, devtools, search, ...
  source: {
    type: 'github' | 'npm' | 'local';
    url: string;
  };
  runtime: 'node' | 'python' | 'rust' | 'docker';
  install: string;
  build?: string;
  entry: string;
  args: string[];
  env?: Record<string, string>;
  requirements?: {
    node?: string;
    python?: string;
    os?: string[];
  };
}

interface PluginState {
  id: string;
  manifest: PluginManifest;
  status: 'installed' | 'running' | 'stopped' | 'error';
  tools: MCPTool[];
  pid?: number;
  error?: string;
  installed_at: string;
}
```

### 3-3. 플러그인 → 노드 자동 변환 (`src/plugins/PluginToNode.ts`)

기존 `MCPToolToNode.ts` 패턴을 확장:
- 플러그인의 각 도구를 `plugin.{pluginId}.{toolName}` 타입으로 등록
- inputSchema → ConfigField[] 자동 변환
- 출력 타입 추론 (text/json/any)
- 플러그인 카테고리로 팔레트 그룹핑

### 3-4. 추천 플러그인 레지스트리 (하드코딩 초기 목록)

```typescript
const PLUGIN_REGISTRY = [
  {
    name: 'filesystem',
    description: '고급 파일 시스템 작업',
    source: 'github:modelcontextprotocol/servers/tree/main/src/filesystem',
    runtime: 'node',
    category: 'io',
  },
  {
    name: 'brave-search',
    description: '웹 검색',
    source: 'github:modelcontextprotocol/servers/tree/main/src/brave-search',
    runtime: 'node',
    category: 'search',
  },
  {
    name: 'github',
    description: 'GitHub API 통합',
    source: 'github:modelcontextprotocol/servers/tree/main/src/github',
    runtime: 'node',
    category: 'devtools',
  },
  {
    name: 'sqlite',
    description: '고급 SQLite 작업',
    source: 'github:modelcontextprotocol/servers/tree/main/src/sqlite',
    runtime: 'node',
    category: 'storage',
  },
  // ... 더 많은 공식/커뮤니티 MCP 서버
];
```

---

## Phase 4: ExecutionEngine 확장 (루프/분기 지원)

### 현재 한계
ExecutionEngine은 DAG(비순환 그래프)만 지원. 루프 불가.

### 확장 방안
`control.loop`, `control.forEach`, `control.while` 노드는 **내부적으로 서브 실행**을 수행:

```typescript
// control.forEach executor 예시
async execute(input, config, context) {
  const items = input.array;  // 순회할 배열
  const results = [];

  for (const item of items) {
    // 서브 워크플로우의 각 노드를 순차 실행
    // context.variables에 현재 아이템 설정
    context.variables['__loop_item'] = item;
    context.variables['__loop_index'] = results.length;

    // 연결된 하위 노드들 실행
    // (실행 엔진이 이 노드의 출력을 받는 노드들만 실행)
    results.push(item);  // 결과 수집
  }

  return { results, count: results.length };
}
```

---

## Phase 5: UI 컴포넌트

### 5-1. PluginManagerDialog (NEW)
- 설치된 플러그인 목록 (상태 뱃지: running/stopped/error)
- 시작/중지/제거 버튼
- 도구 목록 펼치기
- 새 플러그인 설치 (GitHub URL 입력 또는 추천 목록에서 선택)

### 5-2. ExecutionDebugger (NEW)
- 실행 로그 타임라인
- 노드별 입출력 데이터 검사
- 브레이크포인트에서 변수 확인
- 스텝 실행 (한 노드씩)

### 5-3. NodePalette 업데이트
카테고리 재구성:
```
📂 IO           (file.*, http.*)
📐 Transform    (json.*, csv.*, text.*, xml.*)
💾 Storage      (kv.*, vector.*, sqlite.*)
📄 Document     (doc.*)
⚙️ Process      (shell.*, code.*)
🔀 Control      (if, switch, loop, forEach, while, merge, split, gate)
📦 Variables    (variable.*, constant)
🧠 LLM         (llm.*, prompt.*)
📊 Visualization (viz.*)
🐛 Debug        (log, inspect, breakpoint)
🔌 Plugins      (plugin별 하위 카테고리)
```

---

## 구현 순서 및 검증

### Phase 1 (Rust 백엔드) — 핵심 도구 구현
1. `tool_io.rs` — file.read/write/list/info, http.request
2. `tools/json_query.rs` + `tool_transform.rs` — json.query, json.parse, csv.parse, text.split, text.regex, text.template
3. `tools/text_chunker.rs` — 스마트 청킹 엔진
4. `tools/template_engine.rs` — 템플릿 엔진
5. `tool_storage.rs` + `tools/vector_index.rs` — kv.*, vector.*, sqlite.*
6. `tool_doc.rs` + `tools/doc_parsers.rs` — 범용 문서 파서
7. `tool_process.rs` — shell.exec, code.eval
8. `main.rs` 업데이트 — 새 커맨드 등록

**검증:** 각 커맨드를 프론트엔드 콘솔에서 `invoke('tool_file_read', {...})` 호출하여 동작 확인

### Phase 2 (프론트엔드 노드) — 52개 노드 정의
1. `src/tools/*.tools.ts` — 모든 도구 노드 정의
2. `src/tools/index.ts` — registerAllTools()
3. `main.tsx` 업데이트 — registerAllTools() 호출
4. 기존 executors/ 정리 (레거시 제거)

**검증:** 앱 실행 → 노드 팔레트에 52개 노드 표시 → 드래그 → 연결 → 실행 → 결과 확인

### Phase 3 (플러그인 시스템) — Tier 2
1. `plugin_manager.rs` — 설치/제거/실행
2. `plugin_mcp.rs` — MCP 통신 (기존 mcp.rs 확장)
3. `src/plugins/` — PluginManager, PluginStore, PluginToNode
4. `PluginManagerDialog` — UI
5. 추천 플러그인 레지스트리

**검증:** GitHub MCP 서버 URL 입력 → 자동 설치 → 도구 발견 → 노드 팔레트에 표시 → 실행

### Phase 4 (실행 엔진 확장)
1. ExecutionEngine 루프/분기 지원
2. control.* 노드의 서브 실행 구현
3. 디버거 UI

**검증:** forEach 노드로 배열 순회 → 각 항목에 LLM 호출 → 결과 수집 워크플로우 동작 확인

### Phase 5 (통합 테스트) — 기준 파이프라인 5개 검증
1. 기본 RAG: file.read → text.split → llm.embed → vector.store → vector.search → text.template → llm.chat
2. 데이터 분석: doc.parse(Excel) → json.query → text.template → llm.chat
3. 멀티스텝 에이전트: llm.structured → control.if → 도구 실행 → 결과 피드백
4. 문서 생성: file.list → forEach → doc.parse → text.template → llm.chat → file.write
5. 플러그인 통합: plugin.brave-search → text.template → llm.chat → viz.text

---

## 추가 Cargo.toml 의존성

```toml
# 인코딩 감지/변환
encoding_rs = "0.8"
chardetng = "0.1"

# 파일 타입 감지
infer = "0.16"

# 파일 탐색
glob = "0.3"
walkdir = "2"

# HTML 파싱
scraper = "0.20"

# 정규식 (이미 있을 수 있음)
regex = "1"

# 벡터 인덱스 (Phase 4)
# instant-distance = "0.6"

# 템플릿 엔진 (자체 구현 대안)
# handlebars = "6"
```
