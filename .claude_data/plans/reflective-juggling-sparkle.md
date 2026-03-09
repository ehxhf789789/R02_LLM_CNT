# Notology 전체 최적화 및 리팩토링 계획

## Context
HoverEditor의 열기/닫기 애니메이션에서 `filter: blur()` 사용으로 인한 GPU 성능 병목, 노트 편집 내용이 메인 뷰에 반영되기까지의 지연(~600-1100ms), 그리고 12개의 사용되지 않는 Rust 커맨드가 존재. 이 최적화를 통해 60fps 애니메이션 달성, 콘텐츠 반영 시간을 ~350-500ms로 단축, 불필요한 코드 제거를 목표로 함.

---

## Phase 1: 애니메이션 최적화 (최우선)

### 1.1 `filter: blur()` 제거 → opacity 전용 애니메이션
**이유**: `blur()`는 프레임당 8-16ms의 GPU 비용. `transform: scale()`은 inline `translate3d()` 포지셔닝과 충돌하여 사용 불가 (ghost at top-left bug — App.css:3465-3469 주석 참고). opacity만 사용하면 compositor-only 연산으로 ~1ms.

**파일**:
- `src/components/hover/hoverAnimationUtils.ts` (L15-48)
  - `AnimationKeyframes` 인터페이스에서 `filter` 필드 제거
  - `ANIMATION_KEYFRAMES`: blur 값 제거, opacity만 유지
  - `runAnimation()`: animate() 호출에서 filter 키프레임 제거
- `src/App.css` (L3472-3514)
  - 4개 `@keyframes` (open/close/minimize/restore)에서 `filter: blur()` 제거
  - `.hover-editor` (L3528): `will-change: transform, opacity` (filter 제거)
- `src/components/HoverEditor.tsx` (L156-158)
  - 복원 시 `style.filter = 'blur(8px)'` → `style.opacity = '0'` (filter 설정 제거)

### 1.2 fileTree 변경 시 불필요한 editor dispatch 제거
**이유**: fileTree가 변경될 때마다 빈 ProseMirror 트랜잭션 디스패치 발생. WikiLink 해석은 이미 ref-based callback으로 동작하므로 불필요.

**파일**: `src/components/HoverEditor.tsx` (L966-971)
- 이 useEffect 블록 전체 삭제

### 1.3 Comment decoration dispatch에 변경 감지 추가
**이유**: comments 배열 참조가 바뀔 때마다 editor 전체 재렌더. 실제 데이터가 같으면 스킵해야 함.

**파일**: `src/components/HoverEditor.tsx` (L957-964)
- `prevCommentsKeyRef = useRef('')` 추가 (refs 영역, ~L208)
- comments의 id+resolved 상태로 해시 생성, 이전과 같으면 dispatch 스킵
- `storage.commentMarks.comments` 할당은 항상 수행 (데이터 동기화)

### 1.4 useEffect 훅 통합 (20→16개)
**파일**: `src/components/HoverEditor.tsx`
- **통합 A**: L53-58 (마운트 로깅) + L141-143 (애니메이션 로깅) → 1개로
- **통합 B**: L927-940 (lock acquire+heartbeat) + L943-955 (lock check) → 1개로 (동일 deps)
- **통합 C**: L452-460 (pool callback) + L463-467 (editor log) → 1개로
- **삭제 D**: L966-971 (1.2에서 삭제)

### 1.5 Drag/resize useEffect deps 최적화
**파일**: `src/components/HoverEditor.tsx` (L1613)
- deps에서 `win.id`, `updateHoverWindow` 제거 → ref 사용
- `updateHoverWindowRef = useRef(updateHoverWindow)` + 업데이트 패턴 적용
- 이벤트 리스너 불필요한 재등록 방지

---

## Phase 2: 콘텐츠 반영 속도 최적화 (높음)

### 2.1 저장 디바운스 500ms → 300ms
**파일**: `src/components/HoverEditor.tsx`
- L413: `}, 500)` → `}, 300)`
- L702: `}, 500)` → `}, 300)` (canvas)

### 2.2 saveFile 내 이중 mtime 조회 제거 + 후처리 병렬화
**파일**: `src/components/HoverEditor.tsx` (L469-527)
- `writeFile` 후 즉시 `contentCacheActions.updateContent()` 호출 (mtime 대기 없이)
- `getFileMtime`와 `notifyFileSaved`를 `Promise.all`로 병렬 실행
- mtime 결과 수신 후 ref 업데이트

변경 전:
```
await writeFile → await getFileMtime → updateContent → notify → index
```
변경 후:
```
await writeFile → updateContent(estimated) + [getFileMtime, notify, index] 병렬
```

### 2.3 refreshStore에 batchRefresh 추가
**파일**: `src/stores/zustand/refreshStore.ts`
- `batchRefresh` 메서드 추가: search + calendar 트리거를 단일 `set()`으로
- `refreshActions`에 `batchRefresh` 추가

**호출 위치 업데이트**:
- `src/components/HoverEditor.tsx`: saveFile 내 L514+L523, comment 저장 후 L402-403, L979-980, L993-994 등

### 2.4 Comment validation 디바운스 2000ms → 1000ms
**파일**: `src/components/HoverEditor.tsx` (L407)
- `}, 2000)` → `}, 1000)`

---

## Phase 3: Dead Code 제거 (중간)

### 3.1 미사용 Rust 커맨드 12개를 generate_handler!에서 제거
**파일**: `src-tauri/src/lib.rs` (L3067-3150)

제거 대상 (프론트엔드 호출 없음 확인 완료):
| 커맨드 | 핸들러 라인 |
|--------|------------|
| `generate_suggestions` | L3072 |
| `search_backlinks` | L3090 |
| `search_att` | L3091 |
| `check_vault_integrity` | L3101 |
| `incremental_reindex` | L3107 |
| `get_reindex_progress` | L3109 |
| `check_attachment_references` | L3111 |
| `remove_note_memos` | L3122 |
| `query_memos` | L3123 |
| `reindex_memos` | L3124 |
| `read_index_state` | L3135 |
| `write_index_state` | L3136 |

함수 본체는 `#[allow(dead_code)]` 주석과 함께 유지 (향후 재사용 가능).

### 3.2 HoverEditor 내 dev-only 로그 정리
**파일**: `src/components/HoverEditor.tsx`
- `console.log` with `%c` 스타일링 (L151, L154, L1082, L1091, L1102, L1108 등) → DEV 조건부 `log()` 함수로 통일
- 이미 `log = DEV ? console.log.bind(console) : () => {}` 패턴 존재 (hoverAnimationUtils.ts:L9)

---

## 검증 방법

1. **애니메이션**: HoverEditor 열기/닫기/최소화 시 Chrome DevTools Performance 탭에서 프레임 시간 확인 (목표: <8ms/frame)
2. **콘텐츠 반영**: HoverEditor에서 노트 수정 후 메인 뷰 테이블에 반영되는 시간 측정 (목표: <500ms)
3. **WikiLink 해석**: `[[BrokenLink]]` 포함 노트 열기 → 해당 파일 생성 → 링크 스타일 변경 확인
4. **빌드**: `npm run build` + `cargo build` 성공 확인
5. **기능 회귀**: 메모 생성, 캘린더 표시, 드래그/리사이즈, 스냅, 최소화/복원 정상 동작 확인
