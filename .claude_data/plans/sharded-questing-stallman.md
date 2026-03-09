# GitHub Wiki 재설계 계획

## Context
현재 wiki/ 폴더는 ko/en 서브디렉토리로 나뉘어 있지만, GitHub Wiki는 **플랫 구조**다.
GitHub Wiki에 복사 붙여넣기로 등록할 수 있도록 재설계 필요.

## 핵심 문제
1. GitHub Wiki는 `repo.wiki.git` 별도 리포 → 모든 .md 파일이 루트에 플랫하게 위치
2. `_Sidebar.md`는 하나만 존재 (양국어 모두 포함해야 함)
3. 이미지는 wiki 리포에 직접 업로드하거나 메인 리포 raw URL 사용
4. 링크 형식: `[텍스트](페이지이름)` (확장자 없이)
5. 현재 내용을 더 직관적/비주얼하게 개선

## 설계

### 디렉토리 구조 (wiki/ 폴더 → GitHub Wiki 리포로 복사)
```
wiki/
├── Home.md                    ← 양국어 랜딩 페이지
├── _Sidebar.md                ← 양국어 사이드바 네비게이션
├── _Footer.md                 ← 공통 푸터
├── images/                    ← GIF/이미지 파일
│
├── 시작하기.md                 ← KO pages (한국어 페이지명)
├── 화면-구성.md
├── 사이드바.md
├── 호버-윈도우.md
├── 노트-관리.md
├── 에디터-기본.md
├── 에디터-고급.md
├── 위키링크.md
├── 캔버스.md
├── 검색.md
├── 그래프-뷰.md
├── 캘린더.md
├── 문서-미리보기.md
├── 템플릿.md
├── 태그.md
├── 설정.md
├── 단축키.md
├── 볼트-동기화.md
├── 팁과-트릭.md
│
├── EN-Getting-Started.md      ← EN pages (EN- 접두사)
├── EN-Interface-Overview.md
├── EN-Sidebar-Explorer.md
├── EN-Hover-Windows.md
├── EN-Note-Management.md
├── EN-Editor-Basics.md
├── EN-Editor-Advanced.md
├── EN-Wikilinks.md
├── EN-Canvas.md
├── EN-Search.md
├── EN-Graph-View.md
├── EN-Calendar.md
├── EN-Document-Preview.md
├── EN-Templates.md
├── EN-Tags.md
├── EN-Settings.md
├── EN-Keyboard-Shortcuts.md
├── EN-Vault-Sync.md
├── EN-Tips-Tricks.md
│
└── GIF-CHECKLIST.md           ← GIF 제작 체크리스트
```

### 링크 형식
- KO 내부 링크: `[시작하기](시작하기)` (GitHub Wiki 자동 매핑)
- EN 내부 링크: `[Getting Started](EN-Getting-Started)`
- 이미지: `![alt](images/filename.gif)`
- 한↔영 전환: Home.md에서 각 언어 섹션 링크

### 개선 포인트 (더 직관적으로)
1. 각 페이지 상단에 한줄 요약 + 아이콘으로 섹션 구분
2. GIF 플레이스홀더를 더 명확한 박스 형태로
3. 단계별 설명에 번호+이모지 사용
4. 네비게이션 링크를 상/하단 모두 배치
5. _Sidebar.md에 양국어 섹션을 깔끔하게 분리

### 작업 순서
1. 기존 wiki/ 폴더 정리 (ko/, en/ 제거, 플랫 구조로 변환)
2. Home.md 재작성 (양국어 랜딩)
3. _Sidebar.md 재작성 (양국어 네비)
4. _Footer.md 생성
5. KO 19페이지 재작성 (한글 파일명 + 개선된 포맷)
6. EN 19페이지 재작성 (EN- 접두사 + 개선된 포맷)
7. GIF-CHECKLIST.md 유지
8. WIKI-SETUP-GUIDE.md 생성 (GitHub Wiki에 등록하는 방법 가이드)
