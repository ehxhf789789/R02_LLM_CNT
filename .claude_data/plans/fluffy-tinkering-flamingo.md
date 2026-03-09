# 오피스 문서 미리보기 - JavaScript 완전 내장형 구현

## Context
HWP, HWPX, DOC, DOCX, PPT, PPTX, XLS, XLSX 파일을 PDF처럼 Notology 내부에서 미리보기.
- **핵심 요구사항**: 외부 프로그램 의존성 ZERO (LibreOffice, 한컴오피스 없이)
- 편집 불필요 (외부 앱으로 열기 버튼 제공)
- 모든 렌더링은 JavaScript 라이브러리로 처리

---

## 포맷별 JavaScript 라이브러리

| 포맷 | 라이브러리 | 품질 | 구현 방식 |
|------|-----------|------|----------|
| **DOCX** | docx-preview | ✅ 우수 | HTML 렌더링 |
| **PPTX** | pptx-viewer 또는 직접 구현 | △ 보통 | Canvas/HTML |
| **XLSX** | SheetJS (xlsx) | ✅ 우수 | HTML 테이블 |
| **HWP/HWPX** | hwp.js | △ 제한적 | HTML 렌더링 |
| **DOC/PPT/XLS** | ❌ 없음 | - | 외부 앱 열기 버튼 |

---

## 아키텍처

```
파일 열기 요청
     │
     ├─ DOCX → docx-preview → HTML 렌더링
     ├─ PPTX → pptx-viewer → Canvas 렌더링
     ├─ XLSX → SheetJS → HTML 테이블
     ├─ HWP/HWPX → hwp.js → HTML 렌더링
     │
     └─ DOC/PPT/XLS (레거시) → "외부 앱으로 열기" 버튼
```

---

## Step 1: npm 패키지 설치

```bash
npm install hwp.js docx-preview xlsx
```

**참고**: PPTX는 좋은 라이브러리가 없어 직접 구현하거나 `pptx2json` + 커스텀 렌더러 사용

---

## Step 2: Rust 백엔드 - 바이너리 파일 읽기

**파일**: `src-tauri/src/lib.rs`

```rust
#[tauri::command]
async fn read_binary_file(path: String) -> Result<Vec<u8>, String> {
    tokio::fs::read(&path).await
        .map_err(|e| format!("Failed to read file: {}", e))
}
```

- `invoke_handler`에 `read_binary_file` 추가

---

## Step 3: Viewer 컴포넌트 생성

### 3.1 HwpViewer.tsx (HWP/HWPX)
```typescript
// src/components/hover/HwpViewer.tsx
import { useEffect, useRef } from 'react';
import HWPViewer from 'hwp.js';

export function HwpViewer({ data }: { data: ArrayBuffer }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current && data) {
      new HWPViewer(containerRef.current, data);
    }
  }, [data]);

  return <div ref={containerRef} className="office-viewer-container" />;
}
```

### 3.2 DocxViewer.tsx (DOCX)
```typescript
// src/components/hover/DocxViewer.tsx
import { useEffect, useRef } from 'react';
import { renderAsync } from 'docx-preview';

export function DocxViewer({ data }: { data: ArrayBuffer }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current && data) {
      renderAsync(data, containerRef.current, undefined, {
        className: 'docx-content',
        inWrapper: true,
      });
    }
  }, [data]);

  return <div ref={containerRef} className="office-viewer-container" />;
}
```

### 3.3 XlsxViewer.tsx (XLSX)
```typescript
// src/components/hover/XlsxViewer.tsx
import { useMemo } from 'react';
import * as XLSX from 'xlsx';

export function XlsxViewer({ data }: { data: ArrayBuffer }) {
  const html = useMemo(() => {
    const workbook = XLSX.read(data, { type: 'array' });
    const sheetName = workbook.SheetNames[0];
    const sheet = workbook.Sheets[sheetName];
    return XLSX.utils.sheet_to_html(sheet);
  }, [data]);

  return (
    <div
      className="office-viewer-container xlsx-viewer"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
```

### 3.4 PptxViewer.tsx (PPTX) - 기본 구현
```typescript
// src/components/hover/PptxViewer.tsx
// PPTX는 복잡하므로 기본 텍스트 추출 또는 외부 앱 열기 안내
export function PptxViewer({ filePath }: { filePath: string }) {
  return (
    <div className="office-viewer-unsupported">
      <p>PPTX 미리보기는 제한적으로 지원됩니다.</p>
      <button onClick={() => /* 외부 앱 열기 */}>
        외부 앱으로 열기
      </button>
    </div>
  );
}
```

---

## Step 4: HoverDocumentViewer.tsx 수정

**파일**: `src/components/hover/HoverDocumentViewer.tsx`

```typescript
// 새로운 상태 타입
type ViewerState = 'idle' | 'loading' | 'docx' | 'xlsx' | 'hwp' | 'pptx' | 'legacy' | 'error';

// 파일 확장자별 라우팅
const getViewerType = (filePath: string): ViewerState => {
  const ext = filePath.toLowerCase().split('.').pop();
  switch (ext) {
    case 'docx': return 'docx';
    case 'xlsx': return 'xlsx';
    case 'hwp':
    case 'hwpx': return 'hwp';
    case 'pptx': return 'pptx';
    case 'doc':
    case 'xls':
    case 'ppt': return 'legacy';
    default: return 'error';
  }
};

// 파일 로드 및 렌더링
const loadDocument = async () => {
  setViewerState('loading');
  try {
    const bytes = await previewCommands.readBinaryFile(filePath);
    setDocumentData(new Uint8Array(bytes).buffer);
    setViewerState(getViewerType(filePath));
  } catch (e) {
    setViewerState('error');
  }
};

// renderBody() 분기
switch (viewerState) {
  case 'docx':
    return <DocxViewer data={documentData} />;
  case 'xlsx':
    return <XlsxViewer data={documentData} />;
  case 'hwp':
    return <HwpViewer data={documentData} />;
  case 'pptx':
    return <PptxViewer filePath={filePath} />;
  case 'legacy':
    return <LegacyFileNotice filePath={filePath} />;
  // ...
}
```

---

## Step 5: tauriCommands.ts 업데이트

**파일**: `src/services/tauriCommands.ts`

```typescript
export const previewCommands = {
  // 기존 유지...
  readBinaryFile: (path: string) => invoke<number[]>('read_binary_file', { path }),
};
```

---

## Step 6: CSS 스타일

**파일**: `src/App.css`

```css
.office-viewer-container {
  width: 100%;
  height: 100%;
  overflow: auto;
  background: white;
  padding: 20px;
}

.xlsx-viewer table {
  border-collapse: collapse;
  width: 100%;
}

.xlsx-viewer td, .xlsx-viewer th {
  border: 1px solid #ddd;
  padding: 8px;
}

.office-viewer-unsupported {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 16px;
  color: var(--text-secondary);
}
```

---

## 파일 수정 목록

1. **package.json** - `hwp.js`, `docx-preview`, `xlsx` 추가
2. **src-tauri/src/lib.rs** - `read_binary_file` 명령어 추가
3. **src/components/hover/HwpViewer.tsx** - 신규
4. **src/components/hover/DocxViewer.tsx** - 신규
5. **src/components/hover/XlsxViewer.tsx** - 신규
6. **src/components/hover/PptxViewer.tsx** - 신규 (제한적)
7. **src/components/hover/HoverDocumentViewer.tsx** - 라우팅 로직 수정
8. **src/services/tauriCommands.ts** - 명령어 래퍼 추가
9. **src/App.css** - 뷰어 스타일 추가

---

## 품질 한계 (JavaScript 라이브러리)

| 포맷 | 지원 범위 | 제한 사항 |
|------|----------|----------|
| DOCX | ~90% | 복잡한 도형, 수식 일부 미지원 |
| XLSX | ~95% | 차트, 피벗 테이블 미지원 |
| HWP | ~40-70% | 복잡한 레이아웃, 임베디드 객체 미지원 |
| PPTX | ~30% | 애니메이션, 전환 효과 미지원 |
| DOC/PPT/XLS | 0% | 레거시 바이너리 형식 - 외부 앱만 가능 |

---

## 검증 방법

1. **DOCX** 파일 더블클릭 → docx-preview로 HTML 렌더링
2. **XLSX** 파일 더블클릭 → SheetJS로 테이블 렌더링
3. **HWP/HWPX** 파일 더블클릭 → hwp.js로 렌더링
4. **PPTX** 파일 더블클릭 → 기본 텍스트 또는 외부 앱 안내
5. **DOC/PPT/XLS** 파일 더블클릭 → "외부 앱으로 열기" 버튼 표시

---

## 레거시 포맷 안내 UI

DOC, PPT, XLS는 JavaScript로 렌더링 불가능한 레거시 바이너리 형식:

```typescript
function LegacyFileNotice({ filePath, language }: Props) {
  return (
    <div className="legacy-file-notice">
      <FileWarning size={48} />
      <p>{t('legacyFormatNotice', language)}</p>
      <button onClick={() => openInExternalApp(filePath)}>
        {t('openInExternalApp', language)}
      </button>
    </div>
  );
}
```

---

## i18n 추가

```typescript
// src/utils/i18n.ts
legacyFormatNotice: '이 파일 형식은 내부 미리보기를 지원하지 않습니다.',
legacyFormatNoticeEn: 'This file format does not support internal preview.',
openInExternalApp: '외부 앱으로 열기',
openInExternalAppEn: 'Open in external app',
```
