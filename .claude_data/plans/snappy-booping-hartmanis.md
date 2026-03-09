# V 1.0.4 — 동기화 안전성 + 성능 최적화 + 구조 정리

## 개요

3가지 축으로 최적화:
- **A. 동기화 안전성** — 데이터 손실 방지 (3건)
- **B. 성능 최적화** — 속도 개선 (4건)
- **C. 구조 정리** — 리팩토링 패턴 통일 (2건)

---

## Phase 1: 동기화 안전성 (Critical)

### A1. 벌크 동기화 시 배치 refresh

**파일**: `src/stores/zustand/hoverStore.ts`, `src/stores/appStore.tsx`

**문제**: `vault-files-changed` 핸들러가 파일별 `refreshForFile(p)` 반복 호출 → 100개 파일 동기화 시 100회 `set()` 호출, 100회 subscriber 알림

**수정**:
1. `hoverStore.ts` — `refreshHoverWindowsForFiles(filePaths: string[])` 배치 메서드 추가 (인터페이스 line 58 뒤, 구현 line 403 뒤, actions line 545 뒤)
```typescript
// 인터페이스
refreshHoverWindowsForFiles: (filePaths: string[]) => void;

// 구현 — 단일 set() 호출로 N개 파일 처리
refreshHoverWindowsForFiles: (filePaths: string[]) => {
  const pathSet = new Set(filePaths);
  set((state) => ({
    hoverFiles: state.hoverFiles.map(h =>
      pathSet.has(h.filePath)
        ? { ...h, contentReloadTrigger: (h.contentReloadTrigger || 0) + 1 }
        : h
    ),
  }));
},

// actions
refreshForFiles: (filePaths: string[]) =>
  useHoverStore.getState().refreshHoverWindowsForFiles(filePaths),
```

2. `appStore.tsx` line 52-54 — 반복 호출을 배치 호출로 교체
```typescript
// Before:
for (const p of e.payload.paths) { hoverActions.refreshForFile(p); }
// After:
hoverActions.refreshForFiles(e.payload.paths);
```

---

### A2. 외부 변경 리로드 시 저장 타이머 취소

**파일**: `src/components/HoverEditor.tsx` line 938 부근

**문제**: 파일 외부 변경 감지 → content reload 시, 대기 중인 `saveTimeoutRef` 미취소. 리로드 직전 수정이 1초 후 덮어쓸 수 있음.

**수정**: line 938 `isLoadingRef.current = true;` 직전에 추가:
```typescript
// Cancel any pending auto-save before reloading external content
if (saveTimeoutRef.current) {
  clearTimeout(saveTimeoutRef.current);
  saveTimeoutRef.current = null;
}
```

참고: `isDirty` 분기(line 931-933)에는 이미 취소 코드가 있으나, non-dirty 분기에 누락됨.

---

### A3. 캐시 mtime 정확한 값 사용

**파일**: `src/stores/zustand/contentCacheStore.ts`, `src/components/HoverEditor.tsx`

**문제**: `updateContent()`가 `mtime: Date.now()` 사용 → 실제 파일 mtime과 미세 차이 → 앱 재시작 시 불필요한 캐시 재로딩

**수정**:
1. `contentCacheStore.ts` — `updateContent` 시그니처에 `mtime?` 추가 (interface line 66, 구현 line 278, actions line 540)
```typescript
// 시그니처
updateContent: (filePath: string, body: string, frontmatter: NoteFrontmatter | null, mtime?: number) => void;

// 구현 line 289
mtime: mtime ?? Date.now(),

// actions
updateContent: (filePath: string, body: string, fm: NoteFrontmatter | null, mtime?: number) =>
  useContentCacheStore.getState().updateContent(filePath, body, fm, mtime),
```

2. `HoverEditor.tsx` saveFile() line 594-598 — await로 변경
```typescript
// Before:
fileCommands.getFileMtime(win.filePath).then(m => { mtimeOnLoadRef.current = m; });
contentCacheActions.updateContent(win.filePath, bodyToSave, updatedFm);

// After:
const savedMtime = await fileCommands.getFileMtime(win.filePath);
mtimeOnLoadRef.current = savedMtime;
contentCacheActions.updateContent(win.filePath, bodyToSave, updatedFm, savedMtime);
```

---

## Phase 2: 성능 최적화

### B1. GraphView 물리 설정 변경 시 그래프 재생성 방지

**파일**: `src/components/GraphView.tsx`

**문제**: `graphSettings.physics` 변경 → 전체 그래프 destroy/recreate → 노드 위치 초기화, 물리 시뮬레이션 재시작

**수정**: 단일 useEffect (line 241-515)를 3개로 분리:

1. **Effect 1** (containerPath 변경 시): 그래프 인스턴스 생성/파괴, 이벤트 핸들러 등록, ResizeObserver
   - deps: `[containerPath]`
2. **Effect 2** (데이터/색상 변경 시): `graph.graphData()` 호출로 노드/엣지 갱신
   - deps: `[filteredData, getNodeColor]`
3. **Effect 3** (물리 설정 변경 시): d3Force 파라미터만 갱신 + `d3ReheatSimulation()`
   - deps: `[graphSettings.physics]`

핵심: 물리 슬라이더 변경 시 그래프 인스턴스 유지, 노드 위치 보존, 시뮬레이션만 재가열

---

### B2. Search 필터링 단일 패스 최적화

**파일**: `src/components/Search.tsx` line 181-262

**문제**: `filteredNotes`가 7회 `.filter()` + 1회 `.sort()` → 7개 중간 배열 생성

**수정**: 단일 `for...of` 루프로 통합 (useMemo 유지)
- container 필터 + query 필터 + type/tag/memo 필터 + folderNote 필터 + dedup → 한 번의 순회
- 마지막에 sort만 별도 실행

---

### B3. 모달 Lazy Loading

**파일**: `src/App.tsx` line 36-53

**문제**: 9개 모달/페이지가 즉시 import → 초기 번들 파싱/실행 비용

**수정**: `React.lazy()` 전환:
```typescript
const Calendar = lazy(() => import('./components/Calendar'));
const MoveNoteModal = lazy(() => import('./components/MoveNoteModal'));
const ContactInputModal = lazy(() => import('./components/ContactInputModal'));
const MeetingInputModal = lazy(() => import('./components/MeetingInputModal'));
const PaperInputModal = lazy(() => import('./components/PaperInputModal'));
const LiteratureInputModal = lazy(() => import('./components/LiteratureInputModal'));
const EventInputModal = lazy(() => import('./components/EventInputModal'));
const VaultSelector = lazy(() => import('./components/VaultSelector'));
const VaultLockModal = lazy(() => import('./components/VaultLockModal'));
```
각 사용처에 `<Suspense fallback={null}>` 래핑 (모달은 사용자 인터랙션으로 열리므로 지연 불감)

---

### B4. 프로덕션 console.log 제거

**파일**: `src/stores/zustand/hoverStore.ts`, `src/utils/editorPool.ts`

**hoverStore.ts**: 애니메이션 메서드 내 24개 `console.log` → 기존 `log()` 래퍼로 교체 (이미 line 9에 DEV 가드 존재). `logBottleneck()` 함수도 DEV 가드 추가.

**editorPool.ts**: 8개 `console.log` → DEV 가드 추가
```typescript
const DEV = import.meta.env.DEV;
const log = DEV ? console.log.bind(console) : () => {};
```
`console.warn` (line 222)은 유지 (예외 상황 알림 목적)

---

## Phase 3: 구조 정리

### C1. zustand barrel export 누락 수정

**파일**: `src/stores/zustand/index.ts` line 70-83, `src/components/GraphView.tsx` line 7

- `index.ts` settingsStore export에 `useGraphSettings` 추가
- `GraphView.tsx` import를 `../stores/zustand`에서 가져오도록 변경

### C2. AppProvider → AppInitializer 이름 변경

**파일**: `src/stores/appStore.tsx` line 33, `src/App.tsx` line 3

- Context Provider가 아닌 초기화 쉘이므로 `AppInitializer`로 이름 변경

---

## 수정 파일 요약

| 파일 | 변경 | 카테고리 |
|------|------|---------|
| `src/stores/zustand/hoverStore.ts` | 배치 refresh 추가 + console.log 정리 | A1, B4 |
| `src/stores/appStore.tsx` | 배치 호출로 교체 + 이름 변경 | A1, C2 |
| `src/components/HoverEditor.tsx` | saveTimeout 취소 + mtime 수정 | A2, A3 |
| `src/stores/zustand/contentCacheStore.ts` | updateContent mtime 파라미터 | A3 |
| `src/components/GraphView.tsx` | useEffect 3분리 + import 경로 | B1, C1 |
| `src/components/Search.tsx` | 단일 패스 필터 | B2 |
| `src/App.tsx` | lazy loading + AppInitializer | B3, C2 |
| `src/utils/editorPool.ts` | DEV 가드 | B4 |
| `src/stores/zustand/index.ts` | useGraphSettings export | C1 |

---

## 검증

```bash
npx tsc --noEmit          # TypeScript 체크
cd src-tauri && cargo check  # Rust 변경 없으므로 생략 가능
```

### 수동 테스트
1. 노트 편집 → hover 창 닫기 → 재오픈 → 위키링크/내용 유지 확인 (A2)
2. 동시 여러 파일 Synology 동기화 → UI 멈춤 없음 확인 (A1)
3. 그래프 물리 슬라이더 조작 → 노드 위치 유지, 부드러운 전환 (B1)
4. 검색 필터 빠른 토글 → 지연 없음 확인 (B2)
5. 앱 시작 → DevTools Network 탭에서 lazy chunk 확인 (B3)
6. 프로덕션 빌드 → DevTools Console 깨끗 확인 (B4)
