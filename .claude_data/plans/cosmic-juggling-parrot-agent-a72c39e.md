# HWPX Lineseg Analysis Plan

## Goal
Analyze lineseg data in the HWPX file to understand page boundary detection.

## Steps
1. Extract section0.xml from the HWPX ZIP file
2. Parse XML and count pageBreak="1" paragraphs
3. Analyze lineseg vertpos/vertsize data for first 30 paragraphs
4. Detect page boundaries via vertpos resets
5. Compare page counts from both methods
6. Show full lineseg data around page breaks

## Approach
- Use Python with xml.etree.ElementTree
- HWPX is a ZIP file containing Contents/section0.xml
- Namespace: hp = http://www.hancom.co.kr/hwpml/2016/HwpContents

## Script to Run
The analysis requires running a Python script that:
1. Opens the HWPX as a ZIP file
2. Extracts Contents/section0.xml
3. Parses all `<hp:p>` elements for pageBreak and lineseg data
4. Detects vertpos resets to find page boundaries
5. Compares both page counting methods

The script is purely read-only - it only reads the HWPX file and prints analysis results.

## Status
Waiting for plan mode to be deactivated to run the analysis script.
