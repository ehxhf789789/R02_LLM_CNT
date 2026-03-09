# 본문 검색 탭: Floating Word Suggestions 기능

## Context
본문(Contents) 검색 탭의 검색 전 빈 화면에 인덱싱된 노트 본문에서 고빈도 단어를 추출하여 무작위 위치에 떠다니며 나타났다 사라지는 애니메이션으로 표시. 클릭 시 검색어로 자동 입력. TVPle 스트리밍 플랫폼 댓글 오버레이 스타일.

**성능 제약**: 병목 없어야 하며, 본문 탭 활성 + 쿼리 비어있을 때만 동작. 탭 전환 시 완전히 중지.

---

## 1. Backend: Tantivy Term Dictionary 스캔 (search/mod.rs)

### 핵심: 문서 로딩 없이 term dictionary만 읽어 O(unique_terms) 성능

**API 체인** (tantivy 0.22 검증 완료):
```
searcher.segment_readers() → &[SegmentReader]
  → segment_reader.inverted_index(field) → Arc<InvertedIndexReader>
    → inverted_index.terms() → &TermDictionary
      → term_dict.stream() → io::Result<TermStreamer>
        → stream.advance() / stream.key() / stream.value() → &TermInfo { doc_freq: u32 }
```

### `impl SearchIndex`에 추가할 함수들

**`is_valid_suggestion_term(term: &str) -> bool`**:
- CJK 문자: 2글자 이상만 허용 (단일 문자 토큰 제거, bigram 이상만)
- Latin: 3글자 이상
- 영어 불용어(the, and, for, this, that, with, have, from, http, https, www, com 등) 필터링

**`get_suggestion_terms(&self, limit: usize) -> Result<Vec<(String, u32)>, String>`**:
1. `self.reload_if_needed()?`
2. 모든 세그먼트의 `f_body` 필드 term dictionary 순회
3. `is_valid_suggestion_term` 통과하는 term만 `HashMap<String, u32>`에 doc_freq 누적
4. 빈도순 정렬 → `limit`개 반환

**위치**: `get_all_tags()` (line 2244) 뒤, `impl SearchIndex` 닫는 `}` 앞

---

## 2. Tauri Command (lib.rs)

```rust
#[tauri::command]
async fn get_suggestion_terms(
    limit: Option<usize>,
    state: tauri::State<'_, Mutex<SearchState>>,
) -> Result<Vec<(String, u32)>, String>
```
- `index.get_suggestion_terms(limit.unwrap_or(200))`
- `generate_handler!`에 등록 (get_all_used_tags 근처)

---

## 3. Frontend Wrapper (tauriCommands.ts)

`searchCommands`에 추가:
```typescript
getSuggestionTerms: (limit?: number) =>
  invoke<[string, number][]>('get_suggestion_terms', { limit }),
```

---

## 4. FloatingWords 컴포넌트 (새 파일)

**파일**: `src/components/search/FloatingWords.tsx`

### Props
```typescript
interface FloatingWordsProps {
  onWordClick: (word: string) => void;
  searchReady: boolean;
}
```

### 동작
1. **마운트 시**: `getSuggestionTerms(200)` 1회 호출, `useRef`에 캐시
2. **4초 간격** `setInterval`로 6~8개 단어 배치 생성
3. **위치**: 5×4 그리드로 분할, 이전 배치와 겹치지 않는 셀 선택 → 셀 내 랜덤 오프셋
4. **스타일**: 빈도에 비례한 font-size(12~20px), opacity(0.25~0.65)
5. **애니메이션**: CSS `@keyframes floatWord` — fade in → 드리프트 → fade out (7~10초)
6. **`onAnimationEnd`**로 완료된 단어 제거
7. **언마운트 시**: `clearInterval` + state 초기화
8. **단어 클릭**: `onWordClick(word)` → 검색어 설정
9. **terms 비어있으면**: `null` 반환 → 부모가 기존 텍스트 fallback

### 활성 DOM 요소: 최대 ~16개 (6~8개 × 2 배치 겹침)

---

## 5. Search.tsx 통합

**임포트 추가**:
```typescript
import FloatingWords from './search/FloatingWords';
```

**line 1330~1333 교체**:
```tsx
{filteredContentResults.length === 0 ? (
  <div className="search-content-empty">
    {!contentsQuery.trim() ? (
      <FloatingWords
        onWordClick={(word) => setContentsQuery(word)}
        searchReady={searchReady}
      />
    ) : searchIndexing ? t('indexInitializing', language) : t('noResults', language)}
  </div>
```

**언마운트 보장**: `contentsQuery` 입력 시 → ternary 분기 변경 → React 자동 언마운트. `mode` 변경 시 → 상위 조건부 렌더링에서 전체 언마운트.

---

## 6. CSS (App.css)

### `.search-content-empty` 수정
```css
.search-content-empty {
  position: relative;
  flex: 1;
  overflow: hidden;
}
```

### 새 CSS 추가
```css
.floating-words-container {
  position: absolute;
  inset: 0;
  overflow: hidden;
  contain: layout style;
}

.floating-word {
  position: absolute;
  will-change: transform, opacity;
  color: var(--text-muted);
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
  opacity: 0;
  animation: floatWord var(--dur) ease-in-out var(--delay) forwards;
}

.floating-word:hover {
  color: var(--accent-primary);
}

@keyframes floatWord {
  0%   { opacity: 0; transform: translate3d(0,0,0) scale(0.9); }
  15%  { opacity: var(--op); transform: translate3d(calc(var(--dx)*0.15), calc(var(--dy)*0.15), 0) scale(1); }
  50%  { opacity: var(--op); }
  85%  { opacity: calc(var(--op)*0.3); }
  100% { opacity: 0; transform: translate3d(var(--dx), var(--dy), 0) scale(0.95); }
}
```

**성능**: `transform` + `opacity`만 애니메이트 → GPU 컴포지터 스레드 처리, 메인 스레드 차단 없음. `contain: layout style`로 리페인트 격리.

---

## 수정 파일 목록

| 파일 | 변경 |
|------|------|
| `src-tauri/src/search/mod.rs` | `is_valid_suggestion_term()`, `get_suggestion_terms()` 추가 |
| `src-tauri/src/lib.rs` | `get_suggestion_terms` 커맨드 + handler 등록 |
| `src/services/tauriCommands.ts` | `getSuggestionTerms` 래퍼 |
| `src/components/search/FloatingWords.tsx` | **새 파일** — 플로팅 워드 컴포넌트 |
| `src/components/Search.tsx` | 임포트 + 빈 상태 영역에 FloatingWords 통합 |
| `src/App.css` | `.search-content-empty` 수정 + floating-words 스타일 |

---

## 검증

1. `cargo check` + `npx tsc --noEmit` 통과
2. 본문 탭 열기 → 빈 화면에 단어들 떠다님 확인
3. 단어 클릭 → 검색어 입력 + 검색 실행 확인
4. 다른 탭 전환 → 애니메이션 중지 확인
5. 검색어 입력 → 플로팅 워드 사라짐 확인
6. 빈 볼트(노트 없음) → 기존 "검색어를 입력하세요" 텍스트 표시 확인
