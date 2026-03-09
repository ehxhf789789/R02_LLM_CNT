# Claude Code 대화 기록 및 플랜 백업

이 디렉토리에는 Claude Code의 프로젝트별 대화 기록, 메모리, 플랜이 백업되어 있습니다.

## 구조

```
.claude_data/
├── memory/               # 프로젝트 메모리
│   └── MEMORY.md         # 프로젝트 컨텍스트 (자동 로드)
└── plans/                # 아키텍처/구현 플랜 (.md)
```

## 타 환경에서 복원하는 방법

### 1. 메모리 복원 (가장 중요)

메모리는 Claude Code가 세션 간 컨텍스트를 유지하는 핵심 파일입니다.

```bash
# Windows
mkdir -p "%USERPROFILE%\.claude\projects\<project-key>\memory"
cp .claude_data/memory/MEMORY.md "%USERPROFILE%\.claude\projects\<project-key>\memory\"

# Linux/Mac
mkdir -p ~/.claude/projects/<project-key>/memory
cp .claude_data/memory/MEMORY.md ~/.claude/projects/<project-key>/memory/
```

`<project-key>`는 Claude Code가 프로젝트 경로를 기반으로 자동 생성합니다.
새 환경에서 Claude Code를 한 번 실행하면 해당 디렉토리가 생성됩니다.

### 2. 플랜 복원

```bash
# Windows
cp .claude_data/plans/*.md "%USERPROFILE%\.claude\plans\"

# Linux/Mac
cp .claude_data/plans/*.md ~/.claude/plans/
```

### 3. 대화 기록

대화 기록(.jsonl)은 AWS 키 등 민감 정보가 포함되어 Git에서 제외합니다.
로컬에서 직접 복사하세요: `~/.claude/projects/<project-key>/*.jsonl`

## 최종 업데이트

- 날짜: 2026-03-09
- 플랜: 23개
- 프로젝트 메모리: MEMORY.md (프로젝트 구조, KB 현황, API 상태 등)
