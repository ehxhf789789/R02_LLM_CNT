# HWPX 뷰어 — 페이지네이션 + 표지 + 네비게이션 개선

## Context
HWPX 뷰어의 3가지 핵심 문제:
1. 페이지 구조가 원본(251p)과 다름 — 현재 pageBreak="1"만 사용하여 148p만 인식. 한글 문서는 명시적 페이지 브레이크 없이 텍스트가 자연스럽게 다음 페이지로 넘어가는 경우가 많음.
2. 표지 이미지 미표시 — vertOffset이 uint32 오버플로(4294967281 = signed -15)로 57백만 px로 해석되어 화면 밖으로 밀림.
3. 페이지 네비게이션 UI 부재 — PDF 뷰어처럼 현재 페이지 표시/이동 기능 필요.

---

## 1. 표지 이미지 버그 수정 (signed int32 overflow)

**파일:** `src/components/hover/HwpxViewer.tsx`

**문제:** `vertOffset="4294967281"`은 uint32로 표현된 signed -15. `parseInt()`는 양수 4294967281을 반환 → ÷75 = 57,266,230px → 화면 밖.

**수정 (3곳):**
```typescript
// 헬퍼 함수 추가
function parseHwpInt(val: string): number {
  const n = parseInt(val);
  // uint32 → signed int32 변환 (값이 0x7FFFFFFF 초과 시 음수로)
  return n > 0x7FFFFFFF ? n - 0x100000000 : n;
}
```

적용 위치:
- Line ~1471: `parseImageElement` — vertOffset/horzOffset
- Line ~1523: `parseContainerElement` — containerVertOffset/containerHorzOffset
- Line ~1614: `parseRectElement` — vertOffset/horzOffset

**추가:** overlay 이미지/텍스트에 실제 `zOrder` 값 사용 (현재 하드코딩된 1, 3 대신)

---

## 2. 페이지네이션 개선 — lineseg 기반 하이브리드

**파일:** `src/components/hover/HwpxViewer.tsx` — `parseSectionXml()`

**현재 문제:** `pageBreak="1"`만으로는 148p. 실제 251p에는 단락 내부에서 발생하는 페이지 넘김(lineseg vertpos 리셋)이 포함됨.

**분석 결과:**
- 각 `<hp:p>`의 `<hp:lineseg>` vertpos 값은 해당 줄의 페이지 내 Y좌표
- vertpos가 감소하면(예: 29200 → 0) 같은 단락 내에서 페이지 브레이크 발생
- 이 패턴을 감지하면 148p → 251p에 가깝게 접근 가능

**구현:**
```
parseSectionXml 내부:
1. 기존 pageBreak="1" 로직 유지 (inter-paragraph)
2. 각 top-level <hp:p>의 lineseg에서 intra-paragraph 페이지 브레이크 감지:
   - lineseg vertpos 배열을 순회
   - vertpos[i+1] < vertpos[i] - threshold 이면 페이지 브레이크
   - threshold = max(lineHeight * 2, 2000 HWPUNIT)
3. 인트라 페이지 브레이크 수만큼 currentPageIndex++
4. 해당 단락의 pageIndex는 마지막 페이지 인덱스 사용
   (단락 분할은 하지 않음 — 단락 전체가 마지막 페이지에 할당)
```

**예상 효과:** 대부분의 문서에서 실제 페이지 수에 근접. 정확한 콘텐츠 분할은 하지 않지만, 페이지 카운트와 넘버링이 원본에 가까워짐.

---

## 3. 페이지 네비게이션 UI

**파일:**
- `src/components/hover/HwpxViewer.tsx` — 컴포넌트 로직
- `src/App.css` — 스타일

**참고 패턴:** PPTX 뷰어의 `.pptx-toolbar` (ChevronLeft/Right, slide indicator)

**구현:**

### 3A. 상태 추가
```typescript
const [currentPageIdx, setCurrentPageIdx] = useState(0);
const pageRefs = useRef<(HTMLDivElement | null)[]>([]);
const contentRef = useRef<HTMLDivElement>(null);
```

### 3B. 스크롤 기반 현재 페이지 감지
```typescript
// IntersectionObserver로 현재 보이는 페이지 추적
useEffect(() => {
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting) {
        const idx = parseInt(entry.target.getAttribute('data-page-idx') || '0');
        setCurrentPageIdx(idx);
        break;
      }
    }
  }, { root: contentRef.current, threshold: 0.3 });

  pageRefs.current.forEach(ref => ref && observer.observe(ref));
  return () => observer.disconnect();
}, [paginatedPages]);
```

### 3C. 툴바 UI (기존 zoom-indicator를 툴바로 대체)
```tsx
<div className="hwpx-toolbar">
  <button onClick={goToPrevPage} disabled={currentPageIdx === 0}>
    <ChevronLeft size={18} />
  </button>
  <input type="number" value={currentPageIdx + 1}
    onChange={e => jumpToPage(parseInt(e.target.value) - 1)}
    min={1} max={paginatedPages.length}
    className="hwpx-page-input" />
  <span className="hwpx-page-total">/ {paginatedPages.length}</span>
  <button onClick={goToNextPage} disabled={currentPageIdx === paginatedPages.length - 1}>
    <ChevronRight size={18} />
  </button>
  <span className="hwpx-zoom-indicator">{Math.round(zoom * 100)}%</span>
</div>
```

### 3D. 네비게이션 함수
```typescript
const jumpToPage = (idx: number) => {
  const clamped = Math.max(0, Math.min(paginatedPages.length - 1, idx));
  pageRefs.current[clamped]?.scrollIntoView({ behavior: 'smooth', block: 'start' });
};
const goToPrevPage = () => jumpToPage(currentPageIdx - 1);
const goToNextPage = () => jumpToPage(currentPageIdx + 1);
```

### 3E. CSS (App.css)
```css
.hwpx-toolbar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 6px 12px;
  background: var(--bg-secondary, #f0f0f0);
  border-bottom: 1px solid var(--border-color, #ddd);
  flex-shrink: 0;
  font-size: 13px;
}
.hwpx-toolbar button { /* PPTX 네비게이션 버튼 스타일 차용 */ }
.hwpx-page-input {
  width: 40px; text-align: center;
  border: 1px solid var(--border-color); border-radius: 3px;
  background: var(--bg-primary); color: var(--text-primary);
}
html[data-theme="dark"] .hwpx-toolbar { background: var(--bg-secondary); }
```

---

## 작업 순서

| 순서 | 작업 | 위험도 | 파일 |
|------|------|--------|------|
| 1 | signed int32 버그 수정 + zOrder 수정 | 낮음 | HwpxViewer.tsx |
| 2 | lineseg 기반 하이브리드 페이지네이션 | 중간 | HwpxViewer.tsx |
| 3 | 페이지 네비게이션 UI | 낮음 | HwpxViewer.tsx, App.css |
| 4 | npm run build 검증 | — | — |

---

## 검증
1. `npm run build` — TypeScript 빌드 에러 확인
2. 정보통신 지침 HWPX 열기 → 표지 이미지(녹색 배경 + 3D 도형) 표시 확인
3. 제 1장 챕터 페이지 → 녹색 배경 위에 흰색 텍스트 표시 확인
4. 페이지 수가 원본(251p)에 근접하는지 확인
5. 페이지 네비게이션 → 페이지 이동, 현재 페이지 표시 확인
6. 다크모드에서 툴바 스타일 확인
