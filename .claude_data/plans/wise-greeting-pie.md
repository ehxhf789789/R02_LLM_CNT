# Handbox Universal Sandbox v2.0 - UI/UX 전면 재설계

## Context

**문제**: 현재 Handbox는 외부 연구 API (KISTI, KIPRIS 등)에 복잡하게 의존하며, 핵심 데이터 파이프라인 기능이 분산되어 있음. 비개발자가 직관적으로 AI 워크플로우를 설계하기 어려움.

**목표**: 6개 핵심 노드 카테고리로 단순화하고, 로컬/클라우드 저장소 통합, RAG, 프롬프트 엔지니어링을 직관적으로 구현.

**핵심 변경사항**:
1. DATA API 제거 (KISTI, KIPRIS, KAIA, NTIS 등)
2. 더미 확장 슬롯 추가 (Azure, GCP CLI - 비활성화)
3. 6개 핵심 카테고리로 재구성: Data → Storage → RAG → Prompt → LLM → Viz

---

## 새로운 노드 카테고리 구조

```
┌─────────────────────────────────────────────────────────────────┐
│  1. data       데이터 로드    Excel, PDF, CSV, TXT 로드 + 전처리  │
│  2. storage    저장소         Local(SQLite/JSON) / Cloud(S3)    │
│  3. rag        RAG 검색       임베딩, 벡터 검색, 컨텍스트 구성    │
│  4. prompt     프롬프트       템플릿, Few-shot, CoT, 자동생성    │
│  5. ai         AI 모델        Bedrock LLM (Claude, Llama, Titan) │
│  6. viz        시각화         텍스트, JSON, 차트, 테이블         │
│  7. control    제어 흐름      조건분기, 병합, 스크립트 (기존 유지) │
│  8. export     내보내기       Excel, PDF 출력 (기존 유지)        │
│  9. extension  확장 슬롯      Azure/GCP CLI (준비중, 비활성화)   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 구현 계획

### Phase 1: 정리 및 제거 (1일)

**삭제할 파일:**
- `src/components/ExternalAPISettingsDialog/` (전체 삭제)

**수정할 파일:**

| 파일 | 변경 내용 |
|------|-----------|
| `src/components/MainLayout/index.tsx` | ExternalAPISettingsDialog 제거, 툴바에서 외부 API 버튼 제거 |
| `src/stores/appStore.ts` | `ExternalAPIType`, `ExternalAPIConfig`, `externalAPIs` 상태 제거 |
| `src/executors/index.ts` | KISTI, CNT 관련 executor import 및 등록 제거 |

---

### Phase 2: 새 노드 Executor 구현 (4일)

**새 파일 생성:**

```
src/executors/
├── data/
│   ├── DataLoaderExecutor.ts      # 파일 로드 (Excel, PDF, CSV, TXT)
│   └── DataPreprocessExecutor.ts  # 스크립트 전처리 (JS/Python)
├── storage/
│   ├── LocalStorageExecutor.ts    # SQLite/JSON 로컬 저장
│   ├── CloudStorageExecutor.ts    # AWS S3 + 임베딩
│   └── UnifiedStorageExecutor.ts  # 로컬/클라우드 통합 토글
├── rag/
│   ├── RAGRetrieverExecutor.ts    # 문서 검색
│   └── ContextBuilderExecutor.ts  # LLM용 컨텍스트 구성
├── prompt/
│   ├── PromptAgentExecutor.ts     # 짧은 명령 → 프롬프트 자동 생성
│   ├── FewShotExecutor.ts         # Few-shot 예제 빌더
│   └── ChainOfThoughtExecutor.ts  # CoT 프롬프트 생성
├── viz/
│   ├── ChartViewerExecutor.ts     # 차트 시각화 (bar, line, pie)
│   ├── TableViewerExecutor.ts     # 테이블 뷰어
│   └── StatsViewerExecutor.ts     # 통계 요약
└── extension/
    └── CLIExtensionExecutor.ts    # 더미 CLI 확장 (비활성화)
```

**각 노드 사양:**

#### data.file-loader
```typescript
{
  type: 'data.file-loader',
  category: 'data',
  meta: { label: '파일 로드', icon: 'InsertDriveFile', color: '#3b82f6' },
  ports: {
    inputs: [],
    outputs: [
      { name: 'data', type: 'json', description: '파싱된 데이터' },
      { name: 'text', type: 'text', description: '텍스트 내용' }
    ]
  },
  configSchema: [
    { key: 'file_path', label: '파일 경로', type: 'file' },
    { key: 'file_type', label: '파일 유형', type: 'select',
      options: ['auto', 'excel', 'csv', 'pdf', 'txt', 'json'] }
  ],
  runtime: 'tauri'
}
```

#### storage.unified
```typescript
{
  type: 'storage.unified',
  category: 'storage',
  meta: { label: '저장소', icon: 'Storage', color: '#8b5cf6' },
  configSchema: [
    { key: 'mode', label: '저장 위치', type: 'select',
      options: [
        { label: '로컬 (SQLite)', value: 'local-sqlite' },
        { label: '로컬 (JSON)', value: 'local-json' },
        { label: 'AWS S3', value: 'cloud-s3' },
        { label: 'AWS + 벡터DB', value: 'cloud-vector' }
      ]
    },
    { key: 'collection', label: '컬렉션명', type: 'text' },
    { key: 'auto_embed', label: '자동 임베딩', type: 'toggle' }
  ]
}
```

#### prompt.agent
```typescript
{
  type: 'prompt.agent',
  category: 'prompt',
  meta: { label: '프롬프트 생성', icon: 'AutoAwesome', color: '#f59e0b' },
  ports: {
    inputs: [{ name: 'command', type: 'text', description: '짧은 명령어' }],
    outputs: [{ name: 'prompt', type: 'text', description: '생성된 프롬프트' }]
  },
  configSchema: [
    { key: 'style', label: '프롬프트 스타일', type: 'select',
      options: ['concise', 'detailed', 'structured', 'few-shot', 'cot'] },
    { key: 'language', label: '언어', type: 'select',
      options: [{ label: '한국어', value: 'ko' }, { label: 'English', value: 'en' }] }
  ]
}
```

---

### Phase 3: Rust 백엔드 확장 (3일)

**새 파일:**

#### `src-tauri/src/commands/data_loader.rs`
```rust
// Excel 파싱 (calamine 사용)
pub async fn parse_excel(file_path: String, sheet_index: Option<usize>)
  -> Result<ExcelData, String>

// CSV 파싱
pub async fn parse_csv(file_path: String, delimiter: Option<char>)
  -> Result<CsvData, String>

// 파일 타입 자동 감지
pub fn detect_file_type(file_path: String) -> String
```

#### `src-tauri/src/commands/local_storage.rs`
```rust
// SQLite 초기화
pub async fn init_sqlite(db_path: String) -> Result<(), String>

// 데이터 저장/조회
pub async fn sqlite_save(db_path: String, table: String, data: Value) -> Result<i64, String>
pub async fn sqlite_query(db_path: String, sql: String) -> Result<Vec<Value>, String>

// JSON 파일 저장/로드
pub async fn json_save(file_path: String, data: Value) -> Result<(), String>
pub async fn json_load(file_path: String) -> Result<Value, String>
```

#### `src-tauri/src/commands/vector_store.rs`
```rust
// 로컬 벡터 인덱스 (usearch 사용)
pub async fn create_vector_index(name: String, dimension: usize) -> Result<(), String>
pub async fn add_vectors(index: String, vectors: Vec<Vec<f32>>, metadata: Vec<Value>) -> Result<(), String>
pub async fn search_vectors(index: String, query: Vec<f32>, top_k: usize) -> Result<Vec<SearchResult>, String>
```

**Cargo.toml 추가:**
```toml
calamine = "0.26"
rusqlite = { version = "0.32", features = ["bundled"] }
csv = "1.3"
usearch = "2.0"
```

---

### Phase 4: UI 컴포넌트 (2일)

#### 1. `src/components/StorageToggle/index.tsx`
로컬/클라우드 저장소 전환 위젯
```
┌─────────────────────────────────────┐
│  [🏠 로컬]  ◀──▶  [☁️ 클라우드]     │
│  SQLite/JSON      AWS S3+벡터DB    │
└─────────────────────────────────────┘
```

#### 2. `src/components/PromptLibrary/index.tsx`
프롬프트 템플릿 라이브러리
- Few-shot: 분류, 감정분석, NER
- Chain-of-Thought: 수학, 논리, 다단계
- ReAct: 에이전트 패턴
- 사용자 정의 템플릿

#### 3. `src/components/DataPreview/index.tsx`
실시간 데이터 미리보기
- JSON 트리 뷰어
- 테이블 뷰 (배열 데이터)
- 텍스트 미리보기

---

### Phase 5: 레지스트리 업데이트 (1일)

**`src/registry/NodeDefinition.ts`**
```typescript
export const DEFAULT_CATEGORIES: NodeCategory[] = [
  { id: 'data',      label: '데이터 로드',   icon: 'Storage',     order: 0 },
  { id: 'storage',   label: '저장소',        icon: 'CloudQueue',  order: 1 },
  { id: 'rag',       label: 'RAG 검색',      icon: 'Search',      order: 2 },
  { id: 'prompt',    label: '프롬프트',      icon: 'Edit',        order: 3 },
  { id: 'ai',        label: 'AI 모델',       icon: 'Psychology',  order: 4 },
  { id: 'viz',       label: '시각화',        icon: 'BarChart',    order: 5 },
  { id: 'control',   label: '제어 흐름',     icon: 'Hub',         order: 6 },
  { id: 'export',    label: '내보내기',      icon: 'Download',    order: 7 },
  { id: 'extension', label: '확장 (준비중)', icon: 'Extension',   order: 8 },
]
```

**`src/engine/types.ts`** - 새 데이터 타입 추가:
```typescript
| 'table-data'    // 테이블 구조 (headers + rows)
| 'chart-data'    // 차트 데이터
| 'storage-ref'   // 저장소 참조
```

---

### Phase 6: 샘플 워크플로우 (1일)

**새 예제 생성:**
```
src/examples/
├── simple-llm.json           # Input → Prompt → LLM → Output
├── local-rag.json            # File → Embed → SQLite → RAG → LLM
├── cloud-rag.json            # S3 → OpenSearch → RAG → LLM
├── document-analysis.json    # PDF → 전처리 → LLM → 차트
└── prompt-engineering.json   # Agent → Few-shot → CoT
```

---

## UI/UX 데이터 흐름

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│   DATA   │───▶│ STORAGE  │───▶│   RAG    │───▶│  PROMPT  │───▶│   LLM    │───▶│   VIZ    │
│  로드    │    │ 저장소    │    │  검색    │    │ 프롬프트  │    │  모델    │    │ 시각화   │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
     │               │               │               │               │               │
     ▼               ▼               ▼               ▼               ▼               ▼
 Excel/PDF     SQLite/JSON      검색결과+      포맷팅된         AI 응답        차트/
 CSV/TXT       S3/벡터DB        컨텍스트       프롬프트         텍스트        테이블
```

---

## 검증 방법

1. **파일 로드**: Excel, PDF, CSV 파일 로드 후 JSON 출력 확인
2. **로컬 저장**: SQLite 저장 후 쿼리 조회
3. **클라우드 저장**: S3 업로드 + 임베딩 생성 확인
4. **RAG**: 저장된 문서 검색 + 컨텍스트 생성
5. **프롬프트**: 짧은 명령 → 상세 프롬프트 변환
6. **LLM**: Claude/Llama 모델 호출 + 응답 확인
7. **시각화**: 차트/테이블 렌더링 확인

---

## 예상 일정

| Phase | 작업 | 기간 |
|-------|------|------|
| 1 | 정리 및 제거 | 1일 |
| 2 | 새 노드 Executor | 4일 |
| 3 | Rust 백엔드 | 3일 |
| 4 | UI 컴포넌트 | 2일 |
| 5 | 레지스트리 | 1일 |
| 6 | 샘플 워크플로우 | 1일 |
| **Total** | | **12일** |

---

## 핵심 파일 경로

| 파일 | 역할 |
|------|------|
| `src/executors/index.ts` | 노드 등록 중앙 관리 |
| `src/stores/appStore.ts` | 앱 상태 (저장소 모드 토글) |
| `src/registry/NodeDefinition.ts` | 카테고리 정의 |
| `src/components/MainLayout/index.tsx` | 메인 레이아웃 |
| `src-tauri/src/commands/mod.rs` | Rust 명령어 모듈 |
| `src-tauri/Cargo.toml` | Rust 의존성 |
