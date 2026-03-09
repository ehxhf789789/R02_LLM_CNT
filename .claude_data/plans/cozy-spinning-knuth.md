# PPTX 뷰어 고충실도 렌더링 계획 (v2)

## Context
현재 JS 기반 PptxViewer는 원본 대비 ~50-60% 수준. 마름모/삼각형 등 도형이 사각형으로 렌더링, 커넥터가 전부 직선, 테이블 스타일 미적용, 폰트 잘못됨, 그림자 없음 등 미리보기로 부적합. 애니메이션 제외, 정적 렌더링을 원본과 최대한 일치시키는 것이 목표.

## 대상 파일
- `src/components/hover/PptxViewer.tsx` (~2231줄)
- `src/App.css` (pptx CSS, 7634~7710줄)

## 이미 구현된 항목 (이전 세션)
- ✅ themeColors 전체 체인 전달
- ✅ a:bodyPr (wrap, padding, anchor, vert, autoFit 파싱)
- ✅ 문단 속성 (lineHeight, spaceBefore/After, marginLeft, indent, letterSpacing)
- ✅ 셀 마진, 테이블 overflow, 셀 fill direct-children-only 파싱
- ✅ srcRect 이미지 크롭, 도형 blipFill, objectFit:'fill'
- ✅ 레이아웃/마스터 장식 셰이프 상속 + z-order
- ✅ 세로 스크롤, IntersectionObserver, Ctrl+Wheel 줌
- ✅ p:style (fillRef/lnRef/fontRef)
- ✅ placeholder 텍스트 렌더링 (slide에서만)

---

## Phase 0: 테마 폰트 해석 (~30줄)

**영향**: 모든 텍스트의 폰트가 잘못됨. `+mj-lt`/`+mn-lt` 등이 스킵되어 브라우저 기본 폰트로 표시.

### 변경사항
1. `parseThemeXml` 반환값 확장 → `{ colors: ThemeColors, fonts: ThemeFonts }`
```typescript
interface ThemeFonts {
  majorLatin: string;  // a:majorFont > a:latin typeface
  minorLatin: string;  // a:minorFont > a:latin typeface
  majorEA: string;     // a:majorFont > a:ea typeface
  minorEA: string;     // a:minorFont > a:ea typeface
}
```
2. `parseRunProperties`에서 `+mj-lt` → `themeFonts.majorLatin` 등으로 해석
3. `themeFonts`를 `parseRunProperties` → `parseTextBody` → `parseShapeTree` → `parseSlideXml` 전체 체인에 전달

---

## Phase 1: Preset Shape Geometry SVG 렌더링 (~350줄)

**영향**: 마름모, 삼각형, 육각형, 별, 흐름도, 콜아웃 등 모든 도형이 사각형으로 렌더링됨.

### 변경사항
1. `PRESET_SHAPE_PATHS` 룩업 테이블 생성 — `Record<string, (w, h, adj?) => string>`
2. 카테고리별 SVG path 생성 함수:
   - **기본도형** (15개): rect, triangle, rtTriangle, diamond, parallelogram, trapezoid, pentagon, hexagon, octagon, plus, cross, frame, donut, foldedCorner, can
   - **별/장식** (8개): star4, star5, star6, star8, star10, star12, star16, star24 → `generateStarPath(w,h,points,innerRatio)` 헬퍼
   - **흐름도** (12개): flowChartProcess, flowChartDecision, flowChartTerminator, flowChartInputOutput, flowChartPreparation, flowChartDocument, flowChartMultidocument, flowChartPredefinedProcess, flowChartConnector, flowChartAlternateProcess, flowChartManualInput, flowChartManualOperation
   - **콜아웃** (4개): wedgeRectCallout, wedgeRoundRectCallout, wedgeEllipseCallout, cloudCallout
   - **기타** (6개): heart, lightningBolt, moon, cloud, plaque, noSmoking
3. 기존 CSS borderRadius 방식(ellipse, roundRect)과 화살표 SVG를 통합 SVG path 렌더러로 교체
4. `a:custGeom` (커스텀 경로) 파싱: `a:moveTo`→M, `a:lnTo`→L, `a:cubicBezTo`→C, `a:arcTo`→A, `a:close`→Z
5. `a:avLst` (조정값) 파싱하여 roundRect 코너 반지름 등에 반영
6. fallback: PRESET_SHAPE_PATHS에 없는 도형은 기존 div 렌더링 유지

### 렌더링 구조
```tsx
<div style={{ position:'absolute', left, top, width, height, transform }}>
  <svg width={w} height={h} style={{ position:'absolute' }}>
    {gradientDef}
    <path d={path} fill={fillColor} stroke={strokeColor} strokeWidth={borderWidth} />
  </svg>
  {/* 텍스트 오버레이 */}
  <div style={{ position:'relative', zIndex:1, display:'flex', ... }}>
    {paragraphs.map(renderParagraph)}
  </div>
</div>
```

---

## Phase 2: 테이블 스타일 해석 (~150줄)

**영향**: 대부분의 테이블 셀 색상이 `tableStyles.xml`의 GUID 기반 스타일에서 오는데, 현재 전혀 파싱하지 않아 테이블이 흰색으로 표시됨.

### 변경사항
1. `ppt/tableStyles.xml`을 ZIP에서 로드, `parseTableStylesXml()` 함수 추가
```typescript
interface TableStyleBand {
  fillColor?: string;
  fontColor?: string;
  fontBold?: boolean;
}
interface TableStyleDef {
  wholeTbl?: TableStyleBand;
  band1H?: TableStyleBand; band2H?: TableStyleBand;
  firstRow?: TableStyleBand; lastRow?: TableStyleBand;
  firstCol?: TableStyleBand; lastCol?: TableStyleBand;
}
```
2. `a:tblPr`에서 `tblStyle` GUID 읽기 → `TableProps.tblStyleId` 추가
3. `getCellBg(cell, rowIdx, colIdx)` 수정: 직접 fill 없으면 스타일에서 조회
   - 우선순위: cell fill > firstRow/lastRow/firstCol/lastCol > bandRow > wholeTbl
4. 스타일의 `fontColor`/`fontBold`를 테이블 셀 텍스트에 적용
5. Office 기본 스타일 GUID `{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}` 하드코딩 fallback
   - firstRow: accent1 fill + 흰 텍스트 + bold
   - band1H: accent1 tint 40%, band2H: accent1 tint 20%

---

## Phase 3: 커넥터 라우팅 (~120줄)

**영향**: 모든 커넥터가 직선 대각선으로 렌더링됨. 직각 꺾임(bent), 곡선(curved) 커넥터가 매우 흔함.

### 변경사항
1. `p:cxnSp` 파싱 시 `a:prstGeom prst` 읽기 → `connectorType` 필드 추가
2. `a:avLst > a:gd` 파싱 → `adjustValues` (꺾임 위치 비율)
3. `buildConnectorPath(w, h, type, adj, flipH, flipV)` 함수:
   - `straightConnector1` → `M0,0 L${w},${h}`
   - `bentConnector2` → 직각 1단 꺾임
   - `bentConnector3` → adj1 기반 중간점 직각 꺾임
   - `bentConnector4/5` → 다단 꺾임
   - `curvedConnector2/3/4/5` → Bezier 곡선
4. 기존 `<line>` → `<path d={...} fill="none">` 교체
5. `flipH`/`flipV` 처리: path 좌표 반전 (CSS transform 대신 경로 자체에서)

---

## Phase 4: 그림자 효과 (~40줄)

**영향**: 전문적 PPT에서 drop shadow 매우 흔함. 없으면 평면적으로 보임.

### 변경사항
1. `ShapeElement`에 `shadow?: { offsetX, offsetY, blur, color, inset? }` 추가
2. `p:spPr > a:effectLst > a:outerShdw` 파싱:
   - `blurRad` (EMU→px), `dist` (EMU→px), `dir` (60000분의 1도→degree)
   - offsetX = cos(dir) * dist, offsetY = sin(dir) * dist
   - color: `a:srgbClr` or `a:schemeClr` with alpha
3. `a:innerShdw` → `inset: true`
4. 렌더링: CSS `boxShadow` (div 기반) 또는 SVG `filter: drop-shadow()` (SVG 기반)

---

## Phase 5: 텍스트 Auto-Fit (~25줄)

**영향**: 텍스트가 도형을 넘어가거나 잘림. PowerPoint에서는 자동 축소됨.

### 변경사항
1. `a:normAutofit`의 `fontScale`과 `lnSpcReduction` 속성 파싱
2. `TextBodyProps`에 `fontScale?: number` (0~1), `lnSpcReduction?: number` (0~1) 추가
3. 렌더링 시 텍스트 컨테이너에 `fontSize: ${fontScale*100}%` 적용
4. `lnSpcReduction` → line-height 비례 감소

---

## Phase 6: 부가 개선 (~100줄)

### 6-1. 불릿 색상/크기/폰트
- `a:buClr`, `a:buSzPct`/`a:buSzPts`, `a:buFont` 파싱 → Paragraph에 추가
- `renderParagraph`에서 불릿 span에 color/fontSize/fontFamily 적용

### 6-2. 화살표 끝 유형
- 현재 모든 마커가 삼각형. `stealth`→화살촉, `oval`→원, `diamond`→마름모 SVG 마커 추가
- `w`/`len` 속성(sm/med/lg) 반영하여 마커 크기 조절

### 6-3. showMasterSp 확인
- `p:cSld showMasterSp="0"` 체크 → 마스터 셰이프 상속 억제

### 6-4. lstStyle 기본 체인
- `p:txBody > a:lstStyle > a:lvl1pPr` 등에서 레벨별 기본 폰트/크기/불릿 읽기

### 6-5. bgRef 완전 해석
- theme `a:fmtScheme > a:bgFillStyleLst[idx-1000]`에서 gradient/image fill 조회

---

## 구현 순서

| 순서 | Phase | 영향도 | 예상 줄수 |
|------|-------|--------|-----------|
| 1 | Phase 0 (테마 폰트) | ★★★★★ | ~30 |
| 2 | Phase 1 (도형 geometry) | ★★★★★ | ~350 |
| 3 | Phase 2 (테이블 스타일) | ★★★★★ | ~150 |
| 4 | Phase 3 (커넥터 라우팅) | ★★★★ | ~120 |
| 5 | Phase 4 (그림자) | ★★★ | ~40 |
| 6 | Phase 5 (텍스트 auto-fit) | ★★★ | ~25 |
| 7 | Phase 6 (부가 개선) | ★★ | ~100 |

**총 예상 추가: ~815줄 → 파일 약 3050줄**

## 검증
1. `npm run tauri dev` → 호버 윈도우에서 실제 PPTX 미리보기
2. PowerPoint 원본과 시각적 비교
3. `npx tsc --noEmit && npx vite build` 빌드 확인
