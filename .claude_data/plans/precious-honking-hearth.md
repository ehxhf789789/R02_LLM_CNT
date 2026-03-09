# Notology v1.0.5 Implementation Plan

## Context
사용자가 5가지 버그/기능 개선을 요청함. Event 템플릿 기능 보완, Meeting 날짜 형식 변경, 브라우저 alert 대신 내부 UI 사용, Ctrl+1~6 단축키 동작 수정, 컨텍스트 메뉴 서브메뉴 표시 문제, 위키링크 파싱 오류 수정.

---

## 1. Event 템플릿 - ParticipantInput 추가

**파일:** `src/components/EventInputModal.tsx`

**현재:** 참가자 필드가 단순 text input (line 125-131)
**목표:** MeetingInputModal처럼 ParticipantInput 컴포넌트 사용 (@ 멘션 지원)

**변경 사항:**
```typescript
// Line 4: import 추가
import ParticipantInput from './ParticipantInput';

// Line 123-132: participants input 교체
<div className="event-input-field">
  <label className="event-input-label">{t('eventParticipants', language)}</label>
  <ParticipantInput
    value={formData.participants}
    onChange={(participants) => setFormData({ ...formData, participants })}
    placeholder={t('eventParticipantsPlaceholder', language)}
  />
</div>
```

---

## 2. Meeting 날짜/시간 형식 분리

**파일:** `src/utils/templateUtils.ts`

**현재:** frontmatter.date에 ISO 날짜만 저장 (line 86)
**목표:** "2026-02-11, 09:55" 형식으로 저장

**변경 사항 (line 85-91):**
```typescript
case 'MTG':
  // date와 time을 쉼표로 구분하여 저장
  if (customVariables?.date && customVariables?.time) {
    frontmatter.date = `${customVariables.date}, ${customVariables.time}`;
  } else if (customVariables?.date) {
    frontmatter.date = customVariables.date;
  } else {
    frontmatter.date = now;
  }
  // ... participants 처리 유지
```

---

## 3. alert() -> AlertModal 대체

**영향 파일 및 라인:**
| 파일 | 라인 | 현재 |
|------|------|------|
| EventInputModal.tsx | 54 | `alert(t('eventTitleRequired', language))` |
| MeetingInputModal.tsx | 54 | `alert(t('meetingTitleRequired', language))` |

**변경 방법:**
```typescript
// import 추가
import { modalActions } from '../stores/zustand/modalStore';

// alert() 대체
modalActions.showAlertModal(t('warning', language), t('eventTitleRequired', language));
```

**i18n 키 확인 필요:** `warning` 또는 유사한 제목용 키

---

## 4. Ctrl+1~6 Heading 단축키

**파일:** `src/utils/editorPool.ts`

**현재:** StarterKit 기본 설정만 사용, Heading 단축키 미구현
**목표:** Mod+1~6으로 H1~H6 토글

**변경 사항 (line 136-140):**
```typescript
import Heading from '@tiptap/extension-heading';

// StarterKit에서 heading 비활성화
StarterKit.configure({
  link: false,
  italic: false,
  paragraph: false,
  heading: false,  // 커스텀 Heading 사용
}),

// 커스텀 Heading 추가 (line 142 근처)
Heading.configure({
  levels: [1, 2, 3, 4, 5, 6],
}).extend({
  addKeyboardShortcuts() {
    return {
      'Mod-1': () => this.editor.commands.toggleHeading({ level: 1 }),
      'Mod-2': () => this.editor.commands.toggleHeading({ level: 2 }),
      'Mod-3': () => this.editor.commands.toggleHeading({ level: 3 }),
      'Mod-4': () => this.editor.commands.toggleHeading({ level: 4 }),
      'Mod-5': () => this.editor.commands.toggleHeading({ level: 5 }),
      'Mod-6': () => this.editor.commands.toggleHeading({ level: 6 }),
    };
  },
}),
```

---

## 5. 컨텍스트 메뉴 서브메뉴 위치/z-index 수정

**문제:**
- 서브메뉴가 hover 창 뒤에 가려짐
- 화면 오른쪽 끝에서 서브메뉴가 잘림

**파일:** `src/components/EditorContextMenu.tsx`

**변경 사항 (위치 감지 로직 추가):**
```typescript
// state 추가
const [submenuPosition, setSubmenuPosition] = useState<'right' | 'left'>('right');

// useLayoutEffect에서 서브메뉴 위치 계산 (line 65-102 근처)
useLayoutEffect(() => {
  if (!menuRef.current) return;
  const rect = menuRef.current.getBoundingClientRect();
  // ... 기존 위치 조정 로직 ...

  // 서브메뉴 오버플로우 감지 (서브메뉴 너비 약 130px)
  const submenuWidth = 140;
  if (rect.right + submenuWidth > window.innerWidth - 16) {
    setSubmenuPosition('left');
  } else {
    setSubmenuPosition('right');
  }

  setAdjustedPos({ x, y });
}, [position]);

// 서브메뉴 div에 클래스 추가 (line 184, 252, 354)
<div className={`editor-context-submenu ${submenuPosition === 'left' ? 'submenu-left' : ''}`}>
```

**파일:** `src/App.css`

**변경 사항 (line 8080 근처):**
```css
.editor-context-submenu {
  position: absolute;
  left: 100%;
  top: 0;
  /* 기존 스타일 유지 */
  z-index: 1000001 !important;
}

/* 왼쪽 위치 옵션 추가 */
.editor-context-submenu.submenu-left {
  left: auto;
  right: 100%;
}
```

---

## 6. Wikilink 파싱 - 대괄호 포함 파일명 처리

**문제:** `[[[디자인여백플러스] 통장사본 (2).pdf]]`에서 내부 `]`가 파싱을 중단시킴

**파일:** `src-tauri/src/search/parser.rs`

**현재 (line 6):**
```rust
let re = Regex::new(r"\[\[([^\]]+)\]\]").unwrap();
```

**변경:**
```rust
/// Extract wiki-links ([[...]]) from content
/// Handles filenames containing ] by using non-greedy matching until ]]
pub fn extract_wiki_links(content: &str) -> Vec<String> {
    // .+? = non-greedy, ]] 가 먼저 나오면 중단
    let re = Regex::new(r"\[\[(.+?)\]\]").unwrap();
    re.captures_iter(content)
        .map(|cap| cap[1].to_string())
        .collect()
}
```

**설명:** `[^\]]+` (] 제외 문자들) 대신 `.+?` (non-greedy any char)를 사용하여 첫 번째 `]]`에서 매칭 종료

---

## 검증 방법

1. **Event 참가자 @ 멘션**
   - Event 노트 생성 → 참가자 필드에 `@` 입력 → 연락처 자동완성 확인

2. **Meeting 날짜 형식**
   - Meeting 노트 생성 → frontmatter의 date 필드가 "2026-02-11, 09:55" 형식인지 확인

3. **AlertModal**
   - 각 모달에서 제목 없이 생성 시도 → 브라우저 alert 대신 내부 모달 표시 확인

4. **Ctrl+1~6 단축키**
   - 에디터에서 텍스트 선택 → Ctrl+1~6 입력 → H1~H6 토글 확인

5. **컨텍스트 메뉴 서브메뉴**
   - 화면 오른쪽 끝에서 우클릭 → 제목/콜아웃 서브메뉴가 왼쪽으로 열리는지 확인
   - hover 창 위에서 우클릭 → 서브메뉴가 hover 창 위에 표시되는지 확인

6. **Wikilink 대괄호**
   - `[테스트] 파일.pdf` 파일 생성 → `[[[테스트] 파일.pdf]]` 링크 생성 → 링크 정상 동작 확인

---

## 버전 업데이트

**파일:** `package.json`, `src-tauri/Cargo.toml`, `src-tauri/tauri.conf.json`
- version: "1.0.4" → "1.0.5"
