# 메타데이터 패널 → 태그 전용 패널 전환 계획

## Context
현재 메타데이터 패널은 기본 정보(읽기 전용), 노트 상태, 패싯 태그, 시멘틱 관계, 타입별 필드 등 5개 섹션으로 구성되어 있으나, 실제 사용 빈도가 높은 것은 패싯 태그뿐이다. 사용자가 거의 사용하지 않는 섹션이 대부분이고, YAML 모드도 실용성이 낮다. 메타데이터 패널을 완전히 새로운 **태그 전용 패널**로 교체하고, YAML 모드는 설정의 개발자 모드 탭으로 이동한다.

## 변경 요약

| 파일 | 작업 | 설명 |
|------|------|------|
| `src/components/metadata/TagPanel.tsx` | **생성** | 새 태그 전용 패널 컴포넌트 |
| `src/components/HoverEditor.tsx` | **수정** | MetadataEditor → TagPanel 교체, 아이콘/상태명 변경 |
| `src/components/Settings.tsx` | **수정** | 'developer' 탭 추가 + devMode 토글 UI |
| `src/utils/i18n.ts` | **수정** | 새 i18n 키 추가 + 기존 키 업데이트 |
| `src/App.css` | **수정** | .tag-panel-* 스타일 추가, .hover-editor-tag-panel 스타일 추가 |

### 삭제 대상 (더 이상 사용되지 않는 파일)
- `MetadataEditor.tsx`, `MetadataForm.tsx`, `RelationEditor.tsx`, `ValidationPanel.tsx`

### 유지 (재사용)
- `FacetedTagEditor.tsx`, `HierarchicalTagSelector.tsx`, `YamlEditor.tsx`

---

## Step 1: i18n 키 추가 (`src/utils/i18n.ts`)

**새 키 (ko/en):**
- `tags`: '태그' / 'Tags'
- `tagsMode`: '태그' / 'Tags'
- `selectFileForTags`: '파일을 선택하여 태그를 편집하세요.' / 'Select a file to edit tags.'
- `tagPanelLoading`: '태그 로딩 중...' / 'Loading tags...'
- `noTags`: '이 파일에는 태그가 없습니다.' / 'This file has no tags.'
- `developer`: '개발자' / 'Developer'
- `developerTools`: '개발자 도구' / 'Developer Tools'
- `devModeLabel`: '개발자 모드' / 'Developer Mode'
- `devModeDesc`: 'YAML 편집기 등 개발자 도구를 활성화합니다.' / 'Enable developer tools such as YAML editor.'
- `on`: '켜짐' / 'ON'
- `off`: '꺼짐' / 'OFF'

**기존 키 업데이트:**
- `scToggleMetadata` (ko): 'Hover 창 메타데이터' → 'Hover 창 태그'
- `scToggleMetadata` (en): 'Hover Window Metadata' → 'Hover Window Tags'

---

## Step 2: TagPanel.tsx 생성 (`src/components/metadata/TagPanel.tsx`)

MetadataEditor를 대체하는 완전히 새로운 컴포넌트.

**구조:**
```
TagPanel
├── tag-panel-header (제목 "태그" + devMode일 때 태그/YAML 모드 토글 + 저장 표시)
└── tag-panel-content
    ├── [mode=tags] FacetedTagEditor (기존 컴포넌트 재사용)
    └── [mode=yaml, devMode만] YamlEditor (기존 컴포넌트 재사용)
```

**핵심 로직:**
- `useFrontmatter` 훅으로 프론트매터 로드/저장 (MetadataEditor와 동일)
- auto-save 디바운스 로직 유지 (autoSaveDelay 사용)
- Ctrl+S 수동 저장 유지
- `handleTagChange`: tags 필드만 업데이트, 나머지 frontmatter 필드는 보존
- `useDevMode()` 훅으로 개발자 모드 여부 확인 → YAML 모드 토글 표시/숨김
- FacetedTagEditor 내부의 "패싯 태그" 타이틀은 CSS로 숨김 (`.tag-panel .faceted-tag-editor-title { display: none; }`) — 패널 헤더에 이미 "태그"가 있으므로 중복 방지

---

## Step 3: HoverEditor.tsx 수정

1. **import 변경**: `MetadataEditor` → `TagPanel`, `LayoutList` → `Tags` (lucide-react)
2. **상태명 변경**: `showMetadata`/`setShowMetadata` → `showTags`/`setShowTags`
3. **토글 버튼**: 아이콘 `<Tags size={14} />`, title `t('tags', language)`
4. **패널 렌더링**: `.hover-editor-metadata-panel` → `.hover-editor-tag-panel`, `<MetadataEditor>` → `<TagPanel>`
5. **키보드 단축키**: Ctrl+Shift+M 유지 (동작 동일, 상태명만 변경)

---

## Step 4: Settings.tsx 수정

1. `SettingsTab` 타입에 `'developer'` 추가
2. TABS 배열에 `{ id: 'developer', label: t('developer', language) }` 추가
3. developer 탭 콘텐츠 추가:
   - "개발자 도구" 섹션 헤더
   - devMode 토글 (기존 `settings-toggle-btn` 패턴 활용)
   - `devMode`/`setDevMode` — settingsStore에 이미 존재 (UI 미노출 상태)
4. `useSettingsStore`에서 `devMode`, `setDevMode` 디스트럭처링 추가

---

## Step 5: App.css 스타일 추가

**새 클래스:**
- `.tag-panel` — flex column, height 100%
- `.tag-panel-empty`, `.tag-panel-loading` — 센터 정렬 메시지
- `.tag-panel-header` — flex, 패딩, 하단 보더
- `.tag-panel-title` — 14px, 600 weight
- `.tag-panel-header-actions` — flex, gap
- `.tag-panel-mode-toggle` — devMode용 태그/YAML 토글
- `.tag-panel-mode-btn` / `.active` — 토글 버튼 스타일
- `.tag-panel-saving` — 저장 중 표시
- `.tag-panel-content` — flex 1, overflow-y auto
- `.hover-editor-tag-panel` — width 360px, border-left (기존 metadata-panel과 유사)
- `.hover-editor-tag-section` — 폴더 노트용 (border-top, max-height)
- `.tag-panel .faceted-tag-editor-title` — display: none (타이틀 중복 숨김)

---

## Step 6: 미사용 파일 정리

삭제 대상:
- `src/components/metadata/MetadataEditor.tsx`
- `src/components/metadata/MetadataForm.tsx`
- `src/components/metadata/RelationEditor.tsx`
- `src/components/metadata/ValidationPanel.tsx`

미사용 CSS 클래스도 정리 (`.metadata-editor`, `.metadata-form`, `.form-section`, `.form-field`, `.maturity-*`, `.mode-toggle` 등)

---

## 검증 방법

1. 앱 실행 후 노트 열기 → 헤더의 태그 아이콘(Tags) 클릭 → 태그 패널 표시 확인
2. 패싯 태그 추가/삭제 → auto-save 동작 확인
3. 설정 → 개발자 탭 → 개발자 모드 ON → 태그 패널에 태그/YAML 토글 표시 확인
4. 개발자 모드 OFF → YAML 토글 숨김 확인
5. Ctrl+Shift+M 단축키로 태그 패널 토글 확인
6. 폴더 노트에서도 태그 패널 정상 렌더링 확인
