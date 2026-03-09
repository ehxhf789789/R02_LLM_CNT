# Notology V2.0.0 — 전체 UI 디자인 폴리시

## Context

V1.x에서 CSS 모듈화 + 디자인 토큰 + 컴포넌트 구조 정리가 완료됨.
V2에서는 **기능 변경 없이 시각적 품질을 전면 향상**하여 일관성 + 세련됨을 확보.

현재 상태:
- 에디터 영역: 매우 폴리시됨 (heading 좌측 보더, 코드 구문 강조, 위키링크 등)
- 타이틀바/사이드바: 기능적이나 시각적 최소화
- 설정/모달: 깔끔한 구조지만 스파르탄한 미학
- 입력 필드: 포커스 상태가 거의 보이지 않음
- 버튼: 호버/액티브 피드백 부족
- 컨텍스트 메뉴: radius 4px로 평탄
- 설정의 테마 선택: 단순 `<select>` 드롭다운 → 세그먼트 버튼 그룹으로 교체 필요

목표: 모든 컴포넌트의 시각적 품질을 에디터 수준으로 끌어올림

---

## Phase 0: 토큰 시스템 확장 (기반)

**파일**: `src/styles/tokens.css`, `src/styles/base/themes.css`

### tokens.css에 추가

```css
/* V2 Polish Tokens */
--focus-ring: 0 0 0 2px var(--bg-primary), 0 0 0 4px var(--accent-primary);
--shadow-xs: 0 1px 2px rgba(0, 0, 0, 0.15);
--btn-height-sm: 28px;
--btn-height-md: 32px;
--btn-height-lg: 36px;
--backdrop-blur: blur(8px);
--radius-2xl: 16px;
```

### themes.css 양쪽 테마에 추가

```css
/* Dark */
--bg-input: #2a2a2a;
--border-focus: var(--accent-primary);
--backdrop-bg: rgba(0, 0, 0, 0.6);

/* Light */
--bg-input: #ffffff;
--border-focus: var(--accent-primary);
--backdrop-bg: rgba(0, 0, 0, 0.4);
```

**검증**: 앱 시각 변화 없음, CSS 파싱 에러 없음

---

## Phase 1: 글로벌 포커스 상태 + 입력 필드 폴리시 (최고 영향)

**파일**: `src/styles/base/reset.css`, `src/styles/layout/sidebar.css`, `src/styles/modals/note-creation-modals.css`, `src/styles/components/search.css`, `src/styles/components/settings.css`, `src/styles/features/graph-view.css`

### 1a. reset.css에 글로벌 포커스 링 추가

```css
:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}
input:focus-visible, textarea:focus-visible, select:focus-visible {
  outline: none;
  box-shadow: none;
  border-color: var(--border-focus);
}
```

### 1b. 모든 입력 필드 업그레이드

| 셀렉터 | 변경 |
|---------|------|
| `.sidebar-input`, `.search-input`, `.title-input-field`, `.meeting-input-input`, `.paper-input-input`, `.literature-input-input`, `.event-input-input`, `.graph-search-input`, `.settings-select`, `.settings-size-input` | `border-radius: var(--radius-sm)` → `var(--radius-md)` |
| 위 셀렉터의 `:focus` | `box-shadow: 0 0 0 3px rgba(96,165,250,0.15)` 추가, `transition: border-color var(--duration-normal), box-shadow var(--duration-normal)` |

---

## Phase 2: 버튼 폴리시 + 마이크로 인터랙션

**파일**: `src/styles/editor-extensions/toolbar.css`, `src/styles/modals/note-creation-modals.css`, `src/styles/layout/titlebar.css`, `src/styles/components/settings.css`, `src/styles/features/calendar.css`, `src/styles/features/vault-selector.css`

### 2a. 에디터 툴바 버튼 사이즈 증가

`.editor-toolbar-btn`: `width: 26px; height: 24px` → `width: 30px; height: 28px`, `border-radius: var(--radius-md)`

### 2b. Primary 버튼 호버 리프트

모든 모달 submit 버튼에:
```css
transition: background-color var(--duration-normal), transform var(--duration-fast), box-shadow var(--duration-normal);
:hover { transform: translateY(-1px); box-shadow: 0 2px 8px rgba(0,122,204,0.3); }
:active { transform: translateY(0); box-shadow: none; }
```

### 2c. Cancel/Secondary 버튼

`border-radius: var(--radius-sm)` → `var(--radius-md)`

### 2d. 타이틀바 액션 버튼

`:hover`에 `transform: translateY(-1px); box-shadow: var(--shadow-xs)` 추가

### 2e. 설정 액션/토글 버튼

`.settings-action-btn`, `.settings-toggle-btn`: `border-radius: var(--radius-md)`, 호버 트랜지션 추가

---

## Phase 3: 설정 테마 선택기 개선 (TSX + CSS)

**파일**: `src/components/features/Settings.tsx`, `src/styles/components/settings.css`

### 3a. 테마 `<select>` → 세그먼트 버튼 그룹 교체

**Settings.tsx 변경** (line ~157-165):

```tsx
// Before
<select className="settings-select" value={theme} onChange={...}>
  <option value="dark">{t('themeDark', language)}</option>
  <option value="light">{t('themeLight', language)}</option>
  <option value="system">{t('themeSystem', language)}</option>
</select>

// After
<div className="settings-theme-toggle">
  {(['dark', 'light', 'system'] as const).map(mode => (
    <button
      key={mode}
      className={`settings-theme-btn${theme === mode ? ' active' : ''}`}
      onClick={() => setTheme(mode, vaultPath)}
    >
      <span className="settings-theme-icon">
        {mode === 'dark' ? '🌙' : mode === 'light' ? '☀️' : '💻'}
      </span>
      {t(`theme${mode.charAt(0).toUpperCase() + mode.slice(1)}` as any, language)}
    </button>
  ))}
</div>
```

주의: 사용자가 이모지 요청하지 않았으므로 Lucide 아이콘 사용 검토 — 이미 프로젝트에서 lucide-react 사용 중이면 `<Moon size={14}/>`, `<Sun size={14}/>`, `<Monitor size={14}/>` 사용.

### 3b. settings.css에 세그먼트 버튼 스타일 추가

```css
.settings-theme-toggle {
  display: flex;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  overflow: hidden;
  background: var(--bg-tertiary);
}
.settings-theme-btn {
  display: flex; align-items: center; gap: var(--space-2);
  padding: 6px 14px;
  font-size: var(--font-base);
  color: var(--text-muted);
  background: transparent;
  border: none; cursor: pointer;
  transition: all var(--duration-normal);
  border-right: 1px solid var(--border-color);
}
.settings-theme-btn:last-child { border-right: none; }
.settings-theme-btn:hover { background: var(--bg-hover); color: var(--text-primary); }
.settings-theme-btn.active {
  background: var(--accent-color, var(--color-link));
  color: #111; font-weight: 600;
}
.settings-theme-icon { font-size: var(--font-lg); line-height: 1; }
```

---

## Phase 4: 모달 현대화

**파일**: `src/styles/components/settings.css`, `src/styles/modals/note-creation-modals.css`, `src/styles/layout/animations.css`, `src/styles/modals/hover-window-app.css`

### 4a. 모달 입장 애니메이션 (animations.css)

```css
@keyframes modalEnter {
  from { opacity: 0; transform: scale(0.95) translateY(8px); }
  to { opacity: 1; transform: scale(1) translateY(0); }
}
@keyframes modalOverlayEnter {
  from { opacity: 0; }
  to { opacity: 1; }
}
```

### 4b. 배경 블러

`.settings-overlay`, 기타 모달 오버레이:
```css
background-color: var(--backdrop-bg);
backdrop-filter: var(--backdrop-blur);
-webkit-backdrop-filter: var(--backdrop-blur);
animation: modalOverlayEnter 0.2s ease-out;
```

### 4c. 모든 모달에 입장 애니메이션 적용

`.settings-modal`, `.title-input-modal`, `.meeting-input-modal`, `.paper-input-modal`, `.literature-input-modal`, `.event-input-modal`, `.confirm-delete-modal`, `.alert-modal`:
```css
animation: modalEnter 0.2s cubic-bezier(0.22, 1, 0.36, 1);
```

### 4d. 설정 모달 탭 디자인

```css
.settings-tabs { width: 140px; padding: 8px 6px; gap: 2px; }
.settings-tab {
  border-radius: 0 var(--radius-md) var(--radius-md) 0;
  transition: all var(--duration-fast);
}
.settings-tab.active { font-weight: 500; }
```

### 4e. 설정 모달 border-radius

`.settings-modal`: `var(--radius-lg)` → `var(--radius-xl)`

---

## Phase 5: 컨텍스트 메뉴 + 드롭다운 폴리시

**파일**: `src/styles/components/context-menu.css`, `src/styles/editor-extensions/editor-context-menu.css`

### 메뉴 컨테이너: `border-radius: var(--radius-sm)` → `var(--radius-lg)`, padding `var(--space-2)`

### 메뉴 아이템: `border-radius: var(--radius-sm)`, `margin: 0 var(--space-1)`

### 파일트리 컨텍스트 메뉴에 fadeIn 애니메이션 적용 (editor-context-menu.css의 `contextMenuFadeIn` 재사용)

---

## Phase 6: 사이드바 시각적 위계

**파일**: `src/styles/layout/sidebar.css`, `src/styles/components/folder-tree.css`

### 섹션 라벨: `font-weight: 700`, `letter-spacing: 0.8px`
### 폴더 트리 아이템: `border-radius: var(--radius-sm)`, `margin: 0 var(--space-2)`
### 사이드바 푸터: `background-color: var(--bg-secondary)`, 버튼 호버에 `translateX(2px)` 추가

---

## Phase 7: 캘린더 + 그래프 뷰 폴리시

**파일**: `src/styles/features/calendar.css`, `src/styles/features/graph-view.css`

### 캘린더 오늘 날짜 원형 뱃지:
```css
.calendar-day.today .calendar-day-number {
  background: rgba(0, 122, 204, 0.2);
  border-radius: var(--radius-full);
  width: 28px; height: 28px;
  display: inline-flex; align-items: center; justify-content: center;
}
```

### 메모 칩: `border-radius: var(--radius-md)`, 호버 리프트 `translateY(-1px)`

### 라이트 모드 캘린더 메모 칩 색상 추가:
```css
html[data-theme="light"] .calendar-day-memo-chip.memo { background: #e8f5e9; color: #2e7d32; }
html[data-theme="light"] .calendar-day-memo-chip.task { background: #ffebee; color: #c62828; }
```

### 그래프 설정 패널: `border-radius: var(--radius-xl)`, 토글 32px 사이즈, 레전드 바에 `backdrop-filter: blur(4px)` + 반투명 배경

---

## Phase 8: 백링크 패널 + 검색 결과 폴리시

**파일**: `src/styles/components/right-panel.css`, `src/styles/components/search.css`

### 백링크 아이템: `border-radius: var(--radius-sm)`, `margin: 0 var(--space-2)`, 호버 트랜지션
### 백링크 파일명: `font-size: var(--font-md)` (base에서 상향)
### 검색 탭: active에 `color: var(--accent-color)` 추가, `:hover:not(.active)`에 미묘한 배경
### 검색 아이템: `border-radius: var(--radius-sm)`, `margin: 0 var(--space-2)`

---

## Phase 9: 로딩 스크린 + 볼트 선택기

**파일**: `src/styles/features/loading-screen.css`, `src/styles/features/vault-selector.css`

### 로딩 스피너: 48px 사이즈, 0.8s 더 부드러운 easing
### 로딩 텍스트: `font-size: 28px`, `letter-spacing: -0.5px` (타이트한 간격)

### 볼트 선택기 버튼: `:hover`에 `translateY(-2px) + var(--shadow-md)`
### 볼트 컨테이너: `border-radius: var(--radius-xl)`, 입장 애니메이션

---

## Phase 10: 라이트 테마 미세 조정

**파일**: `src/styles/base/themes.css`

### 그림자 밝기: `--shadow-color: rgba(0,0,0,0.08)` (라이트 모드)

---

## 실행 순서 및 의존성

```
Phase 0 (토큰 확장) ← 필수 기반
  ↓
Phase 1 (포커스 + 입력) ← 접근성, 최고 영향
  ↓
Phase 2 (버튼 폴리시) ← 전체 앱 인터랙션
  ↓
Phase 3 (테마 선택기) ← TSX + CSS 변경
  ↓
Phase 4 (모달 현대화) ← animations.css 필요
  ↓
Phase 5~10 (병렬 가능, 독립적)
```

## 수정 파일 목록

| Phase | CSS 파일 | TSX 파일 |
|-------|---------|---------|
| 0 | `tokens.css`, `themes.css` | - |
| 1 | `reset.css`, `sidebar.css`, `note-creation-modals.css`, `search.css`, `settings.css`, `graph-view.css` | - |
| 2 | `toolbar.css`, `note-creation-modals.css`, `titlebar.css`, `settings.css`, `calendar.css`, `vault-selector.css` | - |
| 3 | `settings.css` | `Settings.tsx` |
| 4 | `settings.css`, `note-creation-modals.css`, `animations.css` | - |
| 5 | `context-menu.css`, `editor-context-menu.css` | - |
| 6 | `sidebar.css`, `folder-tree.css` | - |
| 7 | `calendar.css`, `graph-view.css` | - |
| 8 | `right-panel.css`, `search.css` | - |
| 9 | `loading-screen.css`, `vault-selector.css` | - |
| 10 | `themes.css` | - |

## 검증

각 Phase 완료 후:
1. `npm run build` 통과
2. 다크/라이트 테마 전환 확인
3. 해당 컴포넌트의 호버/포커스/액티브 상태 테스트
4. 모달 열기/닫기 애니메이션 확인
5. 콘솔 에러 없음
