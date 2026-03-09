# R01_Real_Options 프로젝트 리팩토링 및 GitHub 정리 계획

## 사용자 선택사항
- **라이선스**: MIT License
- **EXE 파일**: Release에만 첨부 (리포에서 삭제)
- **이슈 문서**: docs/archive 폴더로 이동

---

## Context

사용자가 연구 프로젝트(R01_Real_Options)를 체계적으로 정리하고 GitHub에 전문적으로 공개하려고 합니다.

**현재 문제점**:
- src/ 폴더에 핵심 코드와 테스트/임시 파일이 혼재
- 중복 Figure 파일 다수 (9개 → 3개로 정리 필요)
- 루트에 개발 이슈 문서들이 산재 (8개 md 파일)
- README가 한글/영문 혼합으로 국제적 접근성 부족
- 타 환경 재현을 위한 설정 미비

**목표**:
1. 깔끔한 폴더 구조로 리팩토링
2. 영문/한글 README 분리
3. Wiki에 실물옵션 이론 문서화
4. 환경 재현 가능한 설정 (requirements, setup 등)
5. v1.0.1 릴리스 생성
6. Discussion 활성화

---

## Phase 1: 폴더 구조 리팩토링

### 1.1 목표 구조
```
R01_Real_Options/
├── README.md                    # 영문 README
├── README_KR.md                 # 한글 README
├── LICENSE                      # MIT 라이선스
├── requirements.txt             # Python 의존성
├── setup.py                     # 설치 스크립트
├── .gitignore                   # 업데이트
│
├── src/                         # 핵심 소스 코드만
│   ├── __init__.py
│   ├── valuation_engine.py      # v14 → 버전 제거
│   └── tier_system.py
│
├── data/
│   └── sample_projects.csv      # 샘플 데이터 (이름 정규화)
│
├── figures/                     # 최종 Figure만
│   ├── Figure_4-1_NPV_TPV_Comparison.png
│   ├── Figure_4-2_ROV_Decomposition.png
│   └── Figure_4-3_Sensitivity_Tornado.png
│
├── scripts/                     # 유틸리티 스크립트
│   └── generate_figures.py
│
├── docs/                        # 추가 문서
│   ├── DEVELOPMENT_LOG.md
│   └── archive/                 # 이전 이슈 문서들
│
├── tests/                       # 테스트 코드
│   └── test_valuation.py
│
└── (dist/ 폴더 삭제 - EXE는 Release에서만 첨부)
```

### 1.2 파일 이동/삭제 계획

**삭제할 파일**:
- `src/__pycache__/` (캐시)
- `src/Figure_4-*_Improved.png` (중복)
- `src/Figure_4-*_Final.png` (figures/로 이동 후)
- `src/results_*.csv` (임시 결과)
- `figures/` 초기 버전 (Final 버전으로 교체)

**이동할 파일**:
- `src/test_*.py` → `tests/`
- `src/generate_figures_*.py` → `scripts/`
- `src/realistic_10projects_complete.csv` → `data/sample_projects.csv`
- 루트 이슈 문서들 → `docs/archive/`

**이름 변경**:
- `valuation_engine_v14.py` → `valuation_engine.py`
- `generate_chapter4_figures.py` → `generate_figures.py`

---

## Phase 2: README 영문/한글 분리

### 2.1 README.md (영문)
```markdown
# BIM Real Options Valuation Model

A Python-based valuation framework for BIM design service bidding decisions
using Real Options Analysis (ROA).

## Overview
- 7 Real Options + 3 Adjustment Factors
- 3-Tier Input System (Deterministic → Derived → Probabilistic)
- Monte Carlo Simulation (5,000 iterations)

## Quick Start
## Installation
## Usage
## Model Architecture
## References
## License
```

### 2.2 README_KR.md (한글)
```markdown
# BIM 실물옵션 가치평가 모델

건설 BIM 설계용역 입찰 의사결정을 위한 실물옵션 기반 가치평가 프레임워크

## 개요
## 빠른 시작
## 설치 방법
## 사용법
## 모델 구조
## 참고문헌
## 라이선스
```

---

## Phase 3: 환경 재현 설정

### 3.1 requirements.txt 보강
```
numpy>=1.21.0
pandas>=1.3.0
matplotlib>=3.4.0
scipy>=1.7.0
```

### 3.2 setup.py 생성
```python
from setuptools import setup, find_packages

setup(
    name="bim-rov-valuation",
    version="1.0.1",
    packages=find_packages(),
    install_requires=[...],
    python_requires=">=3.8",
)
```

### 3.3 .gitignore 업데이트
- `__pycache__/`
- `*.pyc`
- `dist/*.exe` (릴리스에서만 첨부)
- `.claude/`

---

## Phase 4: Wiki 컨텐츠 (GitHub 웹에서 수동)

### 추천 Wiki 페이지 구조:
1. **Home** - 프로젝트 개요
2. **Real Options Theory** - 실물옵션 이론 설명
   - NPV의 한계
   - 실물옵션의 개념
   - 7가지 옵션 유형 상세
3. **3-Tier System** - 입력 시스템 설명
4. **Model Architecture** - 모델 구조 다이어그램
5. **Usage Guide** - 상세 사용 가이드
6. **API Reference** - 함수 레퍼런스

*Wiki는 GitHub 웹에서 수동으로 생성해야 함*

---

## Phase 5: Git 커밋 및 릴리스

### 5.1 커밋 순서
1. 불필요 파일 삭제
2. 폴더 구조 변경
3. README 영문/한글 작성
4. setup.py, requirements.txt 업데이트
5. .gitignore 업데이트

### 5.2 릴리스 v1.0.1
- Tag: `v1.0.1`
- Title: "First Public Release"
- Assets: `BIM_ROV_System_v15.exe` 첨부
- Release Notes 작성

### 5.3 Discussion 활성화
- GitHub 웹 → Settings → Features → Discussions 체크

---

## Phase 6: 실행 순서

1. **파일 삭제/이동** (Bash + Write)
2. **새 폴더 생성** (Bash)
3. **README.md 작성** (Write)
4. **README_KR.md 작성** (Write)
5. **setup.py 생성** (Write)
6. **requirements.txt 업데이트** (Edit)
7. **.gitignore 업데이트** (Edit)
8. **src/__init__.py 생성** (Write)
9. **Git add + commit** (Bash)
10. **Git push** (Bash)
11. **안내: Wiki, Release, Discussion은 GitHub 웹에서 수동**

---

## Verification

### 테스트 방법:
```bash
# 1. 클린 환경에서 설치 테스트
pip install -r requirements.txt

# 2. 코드 실행 테스트
python -c "from src.valuation_engine import ValuationEngine; print('OK')"

# 3. 샘플 데이터로 평가 실행
python scripts/generate_figures.py
```

### 체크리스트:
- [ ] 폴더 구조 정리 완료
- [ ] README.md (영문) 작성
- [ ] README_KR.md (한글) 작성
- [ ] setup.py 생성
- [ ] requirements.txt 업데이트
- [ ] .gitignore 업데이트
- [ ] Git commit 완료
- [ ] Git push 완료
- [ ] (수동) Wiki 생성
- [ ] (수동) Release v1.0.1 생성
- [ ] (수동) Discussion 활성화
