# HWPX Cover Page Image Rendering Analysis

## Cover Page Structure (Paragraph 0)

The entire cover page is **a single `<hp:p>` paragraph** (paragraph index 0) containing two shape objects in **Run 1**:

### 1. `<hp:pic>` -- The Cover Background Image (image1.jpg)
```
binaryItemIDRef = "image1"
textWrap = "IN_FRONT_OF_TEXT"   <-- KEY ISSUE
zOrder = 619
treatAsChar = 0 (floating, not inline)
vertRelTo = "PAPER"
horzRelTo = "PAPER"
vertOffset = 4294967281  (= -15 as signed int32, = -0.2px)
horzOffset = 5  (= 0.07px)
sz: width=53280, height=74580  (= 710.4 x 994.4 px -- full page)
```

### 2. `<hp:rect>` -- The Title Text Box
```
textWrap = "IN_FRONT_OF_TEXT"
zOrder = 620 (on top of the image)
treatAsChar = 0 (floating)
vertRelTo = "PAPER"
vertOffset = 8725 (= 116.3px from top)
horzOffset = 7906 (= 105.4px from left)
sz: width=38866, height=16742 (= 518.2 x 223.2 px)
```
Contains `<hp:drawText>` with `<hp:subList>` holding 4 inner paragraphs:
- "정보통신설비 BIM 라이브러리"
- "작성·활용·인증 지침"
- (empty line)
- "2025. 12."

### Section break
Paragraph 0 also contains `<hs:secPr>` marking a section/page boundary.

---

## Image Identification

| Image | File | Dimensions | Content |
|-------|------|-----------|---------|
| image1.jpg | BinData/image1.jpg | 2221x3107 | **COVER PAGE**: Light green background with colorful 3D geometric shapes (triangles, cubes, pentagons, etc.) + KICT/KiCi logos at bottom-left |
| image2.jpg | BinData/image2.jpg | 2220x3106 | **Page 2 background**: Mostly white with green gradient circle (top-left), light bulb icon, gray horizontal lines |
| image3.jpg | BinData/image3.jpg | 2669x3260 | **TOC page background**: Light green/mint gradient with faint dot pattern at bottom-right |
| image4.jpg | BinData/image4.jpg | 2669x3260 | Green gradient horizontal bars (chapter header backgrounds) |
| image5.jpg | BinData/image5.jpg | 272x3260 | Narrow vertical strip -- left sidebar background |

**Key finding**: image1.jpg is a SINGLE pre-rendered image containing BOTH the green background AND all the decorative 3D geometric shapes. They are NOT separate `<hp:pic>` elements.

---

## Why Cover Images Aren't Rendering -- Root Causes

### Problem 1: `IN_FRONT_OF_TEXT` image rendered as overlay at wrong position

The cover page image (image1) has `textWrap="IN_FRONT_OF_TEXT"`. In the viewer code (line 2511):
```typescript
} else if (item.type === 'image' && item.data.textWrap === 'IN_FRONT_OF_TEXT') {
  overlayImgs.push(item.data);
}
```
This correctly identifies it as an overlay. Then at rendering (line 2577-2586):
```tsx
{overlayImages.map((img, oi) => {
  const oSrc = resolveImageSrc(img.id);
  return <img key={...} src={oSrc} style={{
    position: 'absolute', zIndex: 1, pointerEvents: 'none',
    top: img.vertOffset || 0, left: img.horzOffset || 0,
    width: img.width || pw, height: img.height || ph,
    objectFit: 'fill',
  }} />;
})}
```

**Issue A -- vertOffset overflow**: `vertOffset = 4294967281` is parsed by `parseInt()` as a huge positive number (`4294967281`), then divided by 75 = **57,266,230 pixels**. This pushes the image way off screen. The value should be interpreted as signed int32 = `-15` HWPUNITS = `-0.2px`.

**Issue B -- zIndex: 1**: The overlay image gets `zIndex: 1` but the main content area also has `zIndex: 1` (line 2603). The cover image should be layered BEHIND the text box overlay but IN FRONT of regular content. Since both the image and the text box are `IN_FRONT_OF_TEXT`, z-ordering should use the `zOrder` attribute (619 for image, 620 for text box).

### Problem 2: `IN_FRONT_OF_TEXT` rect/textbox positioned incorrectly

The title text box (rect) also has `textWrap="IN_FRONT_OF_TEXT"` and gets added to `overlayTBs`. Its rendering (line 2665-2677) does use `vertOffset` and `horzOffset`, but the same unsigned-int overflow problem could apply.

For the rect, `vertOffset=8725` and `horzOffset=7906` are normal positive values, so these should render correctly in terms of position.

### Problem 3: The cover page has NO regular flow content

Since both elements in paragraph 0 are `IN_FRONT_OF_TEXT` (removed from `filteredContent`), the cover page ends up with **zero flow content**. The page's content div would be empty, meaning the page might not even render with the correct height, or might collapse.

---

## Summary of Required Fixes

1. **Signed int32 conversion for offsets**: `parseInt(vertOffsetAttr)` must handle unsigned-to-signed conversion:
   ```typescript
   const raw = parseInt(vertOffsetAttr);
   const signed = raw > 0x7FFFFFFF ? raw - 0x100000000 : raw;
   const vertOffset = signed / HWPUNIT_PER_PIXEL;
   ```

2. **zIndex should use zOrder attribute**: Instead of hardcoded `zIndex: 1` for overlay images and `zIndex: 3` for overlay text boxes, use the element's `zOrder` value for proper layering.

3. **Cover page might need minimum height enforcement**: When all content is floating/overlay, the page container might not get its proper `minHeight` enforced. Verify the page div always renders at `ph` height.

4. The 3D decorative shapes are NOT separate images -- they are part of image1.jpg itself. So rendering image1 correctly will show all decorative shapes.
