# Notology v1.0.6 Update Plan

## Context
Notology v1.0.5에서 v1.0.6으로 업데이트. 첨부파일 링크 색상/아이콘 버그, 이름 변경 다이얼로그 UX, 그래프 뷰 연락처 연결, 다중 노트 선택, 컨테이너 클릭 동작 변경 등 15가지 개선사항 반영.

---

## Phase A: 첨부파일 시스템 (Tasks 1, 3, 13, 14)

### Task 1+13: 첨부파일 링크 색상 수정 (보라색 → 초록 계열)

**근본 원인**: `fileLookupStore.ts`의 `isInAttFolder`가 `noteStemPath + '.md_att'`로 경로를 구성하나, 실제 폴더는 `NoteStem_att` (`.md` 없음). 키가 안 맞아서 항상 false 반환 → `.attachment` 클래스 미적용 → 기본 보라색 표시.

**수정 파일**:
- `src/stores/zustand/fileLookupStore.ts` (lines 330, 340): `.md_att` → `_att`
  ```
  // Line 330: (noteStemPath + '.md_att') → (noteStemPath + '_att')
  // Line 340: (noteStemPath + '.md_att') → (noteStemPath + '_att')
  ```

### Task 3: 첨부파일 확장자별 아이콘/색상 구분

**새 파일**: `src/utils/attachmentCategory.ts` — 공유 유틸리티
```typescript
// 확장자 카테고리 매핑 함수
export function getAttachmentCategory(fileName: string): string
// 카테고리: image, document, data, code, contact, media, archive, markdown, other
```

**수정 파일**:
- `src/extensions/WikiLink.ts` — renderHTML (line 150), decoration plugin (line ~286), text decoration (line ~430)에 `att-{category}` 클래스 추가
- `src/App.css` — 카테고리별 색상/아이콘 CSS 추가:
  - `.att-image`: 초록 (#34d399), Image 아이콘
  - `.att-document`: 주황 (#fb923c), FileText 아이콘
  - `.att-data`: 황색 (#fbbf24), Database 아이콘
  - `.att-code`: 시안 (#22d3ee), Code 아이콘
  - `.att-contact`: 시안 (#22d3ee), User 아이콘
  - `.att-media`: 보라 (#a78bfa), Music 아이콘
  - `.att-archive`: 회색 (#9ca3af), Archive 아이콘
  - `.att-markdown`: 틸 (#00d4aa), FileText 아이콘
  - `.att-other`: 기본 틸 (#00d4aa), Paperclip 아이콘

### Task 14: Search 첨부 탭 확장자별 행 색상

**수정 파일**:
- `src/components/search/SearchResultItem.tsx` — `AttachmentResultRow`에 `att-row-{category}` 클래스 추가
- `src/App.css` — 각 카테고리별 왼쪽 border 색상 추가

---

## Phase B: 소규모 수정 (Tasks 2, 5, 6, 8)

### Task 2: 첨부파일 이름 변경 시 확장자 숨김

**수정 파일**: `src/components/RenameDialog.tsx` (line 21)
```
// 기존: isAttachment → setNewName(name) [확장자 포함]
// 변경: isAttachment → setNewName(name.replace(/\.[^.]+$/, '')) [확장자 제거]
```
handleRename 함수는 이미 원래 확장자를 복원하므로 추가 수정 불필요.

### Task 5: 오타 체크(spellcheck) 제거

**수정 파일**:
- `src/utils/editorPool.ts` (line 221): `spellcheck: 'false'` 추가
- `src/components/ContainerView.tsx` (line 351): `spellcheck: 'false'` 추가

### Task 6: 그래프 뷰 노드 색상 설정 제거

**수정 파일**: `src/components/GraphView.tsx` (lines 745-771)
- `canvasNodeColor` 설정 섹션 전체 삭제 (3개 color picker + subtitle)

### Task 8: Storage 컨테이너 색상 변경

**수정 파일**: `src/App.css`
- 기존 분홍(#c586c0) → 올리브 그린(#8b9a6b)으로 변경
- expanded/has-children 변형: #a0b080 (밝은 올리브)
- 관련 lines: 1511, 1616, 1620, 1637 + 기타 storage 관련 색상

---

## Phase C: 컨테이너 클릭 동작 (Task 9)

### Task 9: 단일 클릭 → 포커스, 더블 클릭 → 이동

**수정 파일**: `src/components/FolderTree.tsx`
- `focusedContainer` state 추가
- `handleContainerClick`: 포커스만 설정 (selectContainer 호출 안 함)
- `handleContainerDoubleClick`: 실제 `selectContainer()` + `onRootContainerChange()` 호출
- `handleFolderClick`도 동일 패턴 적용 (서브폴더)
- JSX에 `onDoubleClick` 핸들러 추가, `focused` CSS 클래스 적용

**수정 파일**: `src/App.css`
- `.container-tree-item.focused` 스타일 추가 (연한 파란 배경 + 왼쪽 테두리)
- `.folder-tree-item.focused` 스타일 추가

---

## Phase D: 그래프 연락처 연결 + 템플릿 검증 (Tasks 4, 7)

### Task 4: @멘션 연락처 그래프 뷰 연결

**근본 원인**: `parser.rs`의 `extract_wiki_links`가 `[[fileName|@displayName]]`에서 전체 문자열(`fileName|@displayName`)을 추출. 그래프 뷰에서 `|` 포함 문자열은 매칭 실패.

**수정 파일**: `src-tauri/src/search/parser.rs` (lines 6-13)
```rust
// 파이프(|) 앞 부분만 추출하도록 수정
// "fileName|@displayName" → "fileName"
.map(|cap| {
    let full = cap[1].to_string();
    if let Some(pipe_idx) = full.find('|') {
        full[..pipe_idx].to_string()
    } else {
        full
    }
})
```

### Task 7: 템플릿 생성 검증
- 코드 변경 없음. 구현 후 수동 검증:
  - 커스텀 템플릿 생성 → hover, search, graph 색상 반영 확인
  - 다중 커스텀 템플릿 → 충돌 없음 확인

---

## Phase E: 버전, 색상 일관성, 다중 선택 (Tasks 10, 11, 12)

### Task 10: 버전 v1.0.6 반영

**수정 파일**:
- `src/components/VaultSelector.tsx` (line 44): `v1.0.4` → `v1.0.6`
- `package.json` (line 4): `1.0.5` → `1.0.6`
- `src-tauri/tauri.conf.json` (line 4): `1.0.5` → `1.0.6`
- `src-tauri/Cargo.toml` (line 3): `1.0.5` → `1.0.6`

### Task 11: 색상 일관성 (청록 → 파랑 통일)

**수정 파일**: `src/App.css`
- `.vault-selector-recent-item.current` (line 9338): `var(--accent-color)` → `#264f78` (다크 블루)
- `.vault-selector-recent-item.current` border: → `#007acc`
- hover 상태도 동일 적용 (lines 9346-9349)
- 전반적 선택 색상을 파란 계열로 통일

### Task 12: 다중 노트 선택 기능

**수정 파일**:
- `src/components/Search.tsx`:
  - `selectedNotePaths: Set<string>` state 추가
  - `lastSelectedNoteRef` ref 추가
  - Ctrl+클릭: 토글 선택, Shift+클릭: 범위 선택
  - 다중 선택 시 우클릭 컨텍스트 메뉴: "이동", "삭제" 옵션
  - 벌크 이동/삭제 함수 구현
- `src/components/search/SearchResultItem.tsx`:
  - `FrontmatterResultRow`, `DetailsResultCard`에 `isMultiSelected`, `onMultiClick` props 추가
- `src/App.css`:
  - `.search-row.multi-selected` 스타일 (연한 파란 배경 + 왼쪽 파란 테두리)

---

## Phase F: 앱 아이콘 변경 (Task 15)

### Task 15: 바탕화면 바로가기 아이콘 변경

**소스**: `icon/Window_icon.png` (1000x1000)

**수정 파일**: `src-tauri/icons/` 디렉토리의 모든 아이콘 파일
- `icon.ico` — Window_icon.png에서 변환 (multi-size ICO: 16, 32, 48, 256)
- `icon.png` — 512x512 리사이즈
- `32x32.png` — 32x32 리사이즈
- `128x128.png` — 128x128 리사이즈
- `128x128@2x.png` — 256x256 리사이즈
- `Square*.png` 파일들 — 각 사이즈로 리사이즈
- `StoreLogo.png` — 50x50 리사이즈

**도구**: npm의 `sharp` 또는 Python PIL, 또는 `magick` (ImageMagick) 사용하여 변환

---

## 구현 순서

1. **Phase A** (Tasks 1, 3, 13, 14) — 첨부파일 근본 수정
2. **Phase D Task 4** — Rust 코드 수정 (독립적)
3. **Phase B** (Tasks 2, 5, 6, 8) — 소규모 수정들
4. **Phase C** (Task 9) — 컨테이너 클릭 동작
5. **Phase E** (Tasks 10, 11, 12) — 버전/색상/다중선택
6. **Phase F** (Task 15) — 아이콘 변경
7. **Phase D Task 7** — 최종 검증

---

## 검증 방법

1. `npm run build` 성공 확인
2. `cargo build` (Rust 코드 변경 후) 성공 확인
3. 앱 실행 후:
   - 첨부파일 링크가 확장자별 색상으로 표시되는지 확인
   - .md 첨부파일 링크 클릭 시 정상 열림 확인
   - 이름 변경 다이얼로그에 확장자 없이 표시되는지 확인
   - 그래프 뷰에서 연락처 노드 연결 확인
   - 편집기에 빨간 밑줄(spellcheck) 없는지 확인
   - 다중 노트 선택/이동/삭제 동작 확인
   - 컨테이너 단일 클릭 포커스, 더블 클릭 이동 확인
   - VaultSelector에 v1.0.6 표시 확인
