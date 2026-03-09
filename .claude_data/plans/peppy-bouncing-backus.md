# 스케치 템플릿 최적화 플랜

## Context
캔버스(스케치) 노드의 UX가 불편함. 현재 노드는 `<textarea>`를 사용해 항상 편집 가능한 상태이고, 드래그/편집이 혼재되어 있으며, 리치텍스트 포맷이 표현 안 되고, 복사/붙여넣기와 텍스트 중앙정렬 기능이 없음.

## 핵심 파일
- `src/components/CanvasEditor.tsx` (1503줄) - 메인 캔버스 컴포넌트
- `src/App.css` (11490~12238줄) - 캔버스 CSS
- `src/types.ts` (278~309줄) - CanvasNode 타입 정의
- `src/utils/i18n.ts` - 다국어 번역

---

## 1. 더블클릭 편집 모드 (드래그/편집 분리)

**현재 문제**: textarea가 항상 활성화 → 노드 드래그가 어렵고, hover 시 테두리/영역 판별이 불편
**해결 방향**: 기본 = 이동 모드, 더블클릭 = 편집 모드, 외부 클릭 = 편집 해제

### 변경사항 (CanvasEditor.tsx):
- `editingNode` state 추가: `useState<string | null>(null)`
- **View 모드** (editingNode !== node.id):
  - `<div>` 렌더링 (cursor: move, 전체 영역 드래그 가능)
  - 텍스트를 마크다운 파싱하여 포맷 적용된 HTML로 표시
- **Edit 모드** (editingNode === node.id):
  - 기존 `<textarea>` 표시 (자동 focus)
  - textarea의 mouseDown에서 `stopPropagation()` 유지
- **이벤트 변경**:
  - 노드 `onDoubleClick` → `setEditingNode(node.id)` (현재 textarea의 stopPropagation 제거하고 노드 레벨에서 처리)
  - `handleCanvasMouseDown` → `setEditingNode(null)` 추가
  - `handleNodeMouseDown` → editingNode이 아닌 다른 노드 클릭 시 `setEditingNode(null)`
- **CSS**: `.canvas-node-text-display` 클래스 추가 (cursor: move, user-select: none)

---

## 2. 노드 내 리치텍스트 표현

**현재 문제**: `<textarea>`는 서식 표현 불가
**해결 방향**: View 모드에서 간단한 마크다운 파싱 → HTML 렌더링

### 구현:
- `renderNodeText(text: string)` 유틸 함수 생성 (CanvasEditor.tsx 내부):
  - `- item` → `<ul><li>item</li></ul>` (불릿 리스트)
  - `1. item` → `<ol><li>item</li></ol>` (번호 리스트)
  - `> quote` → `<blockquote>quote</blockquote>` (인용)
  - `# heading` → `<strong>heading</strong>` (굵게, h1~h3 지원)
  - `**bold**` → `<strong>bold</strong>`
  - `*italic*` → `<em>italic</em>`
  - 일반 줄 → `<p>text</p>`
- View 모드 `<div>`에서 `dangerouslySetInnerHTML`로 렌더링
- **CSS**: `.canvas-node-text-display` 내 ul, ol, blockquote, p 등 기본 스타일 추가

---

## 3. 텍스트 중앙 정렬 옵션

**현재 문제**: 모든 텍스트가 좌측 상단부터 시작, 플로우차트 라벨처럼 중앙 배치 불가
**해결 방향**: `textAlign` 속성 추가하여 속성 패널에서 토글

### 변경사항:
- **types.ts**: `CanvasNode`에 `textAlign?: 'top-left' | 'center'` 필드 추가
- **CanvasEditor.tsx**:
  - View 모드 div에 `textAlign`에 따른 CSS 적용
  - `center`: `display:flex; align-items:center; justify-content:center; text-align:center;`
  - `top-left` (기본): 현재와 동일
  - Edit 모드 textarea에도 `text-align: center` 적용 (center인 경우)
- **속성 패널**: 노드 선택 시 정렬 토글 버튼 추가 (좌상단 / 중앙)
- **CSS**: `.canvas-node-text-display.text-center`, `.canvas-node-text.text-center` 클래스

---

## 4. 노드 복사/붙여넣기 (Ctrl+C/V)

**현재 문제**: 노드 복사/붙여넣기 기능 미구현
**해결 방향**: Ctrl+C → 선택된 노드 복사, Ctrl+V → 오프셋 적용하여 붙여넣기

### 변경사항 (CanvasEditor.tsx):
- `copiedNodes` state 추가 (또는 useRef): 복사된 노드 배열
- `copiedEdges` state: 복사된 엣지 (양쪽 노드 모두 복사셋에 포함된 경우만)
- **keydown 핸들러 추가**:
  - `Ctrl+C`: 선택된 노드(selectedNode 또는 selectedNodes) 복사
    - textarea에 포커스가 있으면(편집 중) 기본 텍스트 복사 동작 유지
  - `Ctrl+V`: 복사된 노드를 20px 오프셋으로 붙여넣기
    - 새 ID 생성, 엣지의 fromNode/toNode를 새 ID로 매핑
    - 붙여넣어진 노드들을 자동 선택
- 단일 노드: selectedNode 복사, 다중 노드: selectedNodes 복사

---

## 5. 첨부파일 드래그 앤 드롭 → 기존 노드에 링크 삽입

**현재 상태**: 파일 드롭 시 항상 새 파일 노드 생성
**해결 방향**: 드롭 위치가 기존 텍스트 노드 위인 경우 해당 노드에 위키링크 삽입

### 변경사항 (CanvasEditor.tsx):
- `handleNativeFileDrop` 및 `handleDrop` 수정:
  1. 드롭 좌표를 캔버스 좌표로 변환 (현재 코드 유지)
  2. 해당 좌표가 기존 텍스트 노드 영역 내인지 체크
  3. **노드 위에 드롭**: 해당 노드의 `text`에 `\n[[파일명]]` 추가
  4. **빈 공간에 드롭**: 현재 동작 유지 (파일 노드 생성)
- 노드 히트 테스트 함수: `findNodeAtPosition(x, y)` → 텍스트 노드 반환

---

## 구현 순서
1. **타입 수정** (types.ts): `textAlign` 필드 추가
2. **편집 모드 전환** (CanvasEditor.tsx): editingNode state + 이벤트 핸들러
3. **마크다운 렌더러** (CanvasEditor.tsx): renderNodeText 함수
4. **텍스트 정렬** (CanvasEditor.tsx + CSS): center 옵션
5. **복사/붙여넣기** (CanvasEditor.tsx): Ctrl+C/V 핸들러
6. **파일 드롭 to 노드** (CanvasEditor.tsx): 드롭 위치 판별 로직
7. **CSS 추가** (App.css): 리치텍스트 스타일, 정렬, 편집모드 시각 피드백
8. **i18n** (i18n.ts): 새 문자열 추가 (정렬 토글 등)

## 검증 방법
1. 스케치 템플릿에서 노드 생성 → 드래그로 이동 확인
2. 노드 더블클릭 → 편집모드 진입, 외부 클릭 → 해제 확인
3. 편집모드에서 `- 항목`, `1. 항목`, `> 인용` 입력 후 편집 해제 → 포맷 렌더링 확인
4. 속성 패널에서 중앙 정렬 토글 → 텍스트 위치 변경 확인
5. 노드 선택 후 Ctrl+C → Ctrl+V → 복사본 생성 확인
6. 파일을 텍스트 노드 위에 드롭 → 노드 텍스트에 [[파일명]] 추가 확인
7. 파일을 빈 공간에 드롭 → 파일 노드 생성 확인 (기존 동작 유지)
