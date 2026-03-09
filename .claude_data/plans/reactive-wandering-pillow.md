# MARL(MAPPO) 기반 고속도로 공사구간(Work Zone) VSL 제어 시뮬레이션 프로젝트 기획

## Context
- **목적**: 학회 컨퍼런스 발표용 논문 (대한교통학회 등, 6~8 pages)
- **기반 모델**: 5km 직선 고속도로, e1~e5 (5 edges), 2→1 lane closure work zone
- **제어 전략**: MARL(MAPPO) 기반 VSL(가변속도제한) — 공사구간 상류부 2~3개 에이전트
- **핵심 기여**: "MARL 기반 Work Zone VSL의 가능성과 효과성 시연"
- **참고**: 조정훈 외(서울대) DDPG VSL+RM, Wu et al. SUMO-DVSL, ChatGPT 대화 설계안

---

## 1단계: 환경 구축

### 1.1 SUMO 설치
- Windows용 SUMO 최신 안정판 다운로드 및 설치
- 환경변수 `SUMO_HOME` 설정 (예: `C:\Program Files (x86)\Eclipse\Sumo`)
- PATH에 SUMO bin 폴더 추가
- 설치 확인: `sumo --version`, `sumo-gui --version`

### 1.2 Python 환경 구축
```
필수 패키지:
- traci / libsumo          # SUMO Python 인터페이스
- gymnasium                # RL 환경 표준 인터페이스
- torch                    # PyTorch (MAPPO 구현)
- numpy, pandas            # 데이터 처리
- matplotlib, seaborn      # 시각화
- tensorboard              # 학습 모니터링
- pyyaml                   # 설정 관리
```

### 1.3 프로젝트 구조
```
R04_RL_Road_Simulation/
├── sumo_files/                   # SUMO 시뮬레이션 파일
│   ├── workzone.net.xml          # 네트워크 정의 (기존 파일 기반 수정)
│   ├── routes.rou.xml            # 경로/차량 정의
│   ├── detectors.add.xml         # 검지기 정의 (확장)
│   └── workzone.sumocfg          # SUMO 설정
├── env/                          # MARL 환경
│   ├── __init__.py
│   ├── sumo_env.py               # SUMO-TraCI 연동 환경
│   └── multi_agent_env.py        # Multi-Agent 래퍼
├── agents/                       # MAPPO 에이전트
│   ├── __init__.py
│   ├── mappo.py                  # MAPPO 알고리즘 구현
│   ├── actor_critic.py           # Actor-Critic 네트워크
│   └── buffer.py                 # 경험 리플레이 버퍼
├── baselines/                    # 비교용 Baseline 정책
│   ├── no_control.py             # 제어 없음
│   ├── static_vsl.py             # 고정 VSL
│   └── rule_based_vsl.py         # 규칙 기반 VSL
├── train.py                      # 학습 메인 스크립트
├── evaluate.py                   # 평가 스크립트
├── plot_results.py               # 결과 시각화
├── configs/
│   └── config.yaml               # 하이퍼파라미터 & 시뮬레이션 설정
├── results/                      # 학습/평가 결과 저장
├── requirements.txt
└── README.md
```

---

## 2단계: SUMO 네트워크 설계 (기존 모델 기반 수정)

### 2.1 네트워크 토폴로지 (5km / 5 edges / 2→1 merge)
```
(Upstream 2L)      (Warning/VSL 2L)    (Taper 2L)        (Activity 1L)      (Recovery 2L)
e1 ──────────────> e2 ────────────────> e3 ──────────────> e4 ──────────────> e5
0.0km           1.8km               2.8km             3.2km             4.2km        5.0km
                     [VSL zone]          [merge: 2→1]
```

### 2.2 Edge별 파라미터 (기존 시뮬레이션.zip과 동일 구조 활용)
| Edge | 구간 역할 | 길이(m) | 차로수 | 속도(km/h) | 비고 |
|------|----------|---------|--------|-----------|------|
| e1 | Upstream (자유류) | 1800 | 2 | 100 | 워밍업/안정 구간 |
| e2 | Warning / VSL 적용 | 1000 | 2 | 100 | **VSL 에이전트 제어 구간** |
| e3 | Transition / Taper | 400 | 2 | 80 | e3→e4에서 2→1 merge |
| e4 | Activity (Lane closure) | 1000 | 1 | 70 | **병목 핵심 (1차로)** |
| e5 | Recovery / Downstream | 800 | 2 | 100 | 정체 해소/회복 관찰 |

### 2.3 Merge 구현 (핵심)
기존 모델에서 e3_1 → e4_0만 연결되던 것을 수정:
```
e3 lane 0 → e4 lane 0  (연결)
e3 lane 1 → e4 lane 0  (연결)
→ 두 차로가 한 차로로 합류하는 "진짜 merge" 구현
→ 차선변경/끼어들기 상호작용 발생 → Work Zone 특성 강화
```

### 2.4 Detector 배치 (5개 지점)
```
① det_e1_end:   e1 끝쪽 (pos=1500, length=300)  → Upstream 관측
② det_e2_mid:   e2 중간 (pos=300, length=400)    → VSL 구간 관측
③ det_e3_start: e3 시작 (pos=0, length=400)      → Taper 직전 관측
④ det_e4_start: e4 시작 (pos=0, length=300)      → 병목 직후 관측
⑤ det_e5_mid:   e5 중간 (pos=200, length=400)    → Downstream 관측
```
- 샘플링 주기: **30초** (RL 제어 주기와 동일)
- 검지기 유형: Lane Area Detector (E2)

### 2.5 교통 수요 설정 (routes.rou.xml)
```
차량 유형:
  - Car: length=5m, maxSpeed=33.33m/s, accel=2.6, decel=4.5
  - Truck: length=12m, maxSpeed=25.0m/s, accel=1.3, decel=4.0

교통량 프로파일 (1시간):
  Phase 1 (0~600초, 10분):   400대/h (워밍업)
  Phase 2 (600~2400초, 30분): 1500~2000대/h (피크, 병목 발생)
  Phase 3 (2400~3600초, 20분): 600대/h (회복)

departLane="random" → 차선 무작위 진입
```

---

## 3단계: MARL 환경 설계

### 3.1 Multi-Agent 문제 정식화
```
에이전트 수: N = 2 (컨퍼런스 축소 버전)
  - Agent 1: e1 구간 VSL 제어 (upstream)
  - Agent 2: e2 구간 VSL 제어 (warning zone)

협조적(cooperative) 문제: 모든 에이전트가 동일한 전역 보상 r_t 공유
CTDE 구조: 학습 시 중앙 Critic, 실행 시 분산 Actor
```

### 3.2 관측 공간 (Observation Space) — 에이전트별 Local
```python
# 에이전트 i의 관측: 자기 segment + 인접 segment (앞뒤 1개씩)
o_t_i = [
    v_i_prev,    # 이전 segment 평균 속도 (m/s)
    rho_i_prev,  # 이전 segment 밀도 (veh/km)
    HB_i_prev,   # 이전 segment 급감속 비율

    v_i,         # 자기 segment 평균 속도
    rho_i,       # 자기 segment 밀도
    HB_i,        # 자기 segment 급감속 비율

    v_i_next,    # 다음 segment 평균 속도
    rho_i_next,  # 다음 segment 밀도
    HB_i_next,   # 다음 segment 급감속 비율

    v_limit_i,   # 현재 자기 segment 속도제한
]
# 관측 차원: 10 per agent
```

### 3.3 전역 상태 (Global State) — Centralized Critic용
```python
s_t = [v_1, rho_1, HB_1, v_limit_1,  # segment 1
       v_2, rho_2, HB_2, v_limit_2,  # segment 2
       ...
       v_N, rho_N, HB_N, v_limit_N]  # segment N
# + 병목구간(e4) 상태 + downstream(e5) 상태
```

### 3.4 행동 공간 (Action Space) — 이산 증분 제어
```python
# 각 에이전트: 현재 속도제한 대비 증감
A_i = {-1, 0, +1}
# -1: 현 속도제한 - 10 km/h
#  0: 유지
# +1: 현 속도제한 + 10 km/h

# 적용 후 클리핑:
v_limit_new = clip(v_limit_old + 10 * a_i, v_min=60, v_max=100)  # km/h

# Joint action: a_t = (a_1, a_2)
```

### 3.5 보상 함수 (Global Reward — 3항)
```python
def compute_reward():
    # (1) Delay Index — 교통 효율
    v_bar = weighted_mean_speed_all_segments()
    v_free = 27.78  # 100 km/h
    delay_index = max(0, (v_free - v_bar) / v_free)  # 0~1

    # (2) Safety Index — 급감속(Hard Braking) 비율
    HB_bar = mean_hard_braking_ratio()  # decel ≤ -3 m/s² 비율

    # (3) Speed Variance — 속도 균일성 (충격파 억제)
    speed_var = mean_speed_variance_across_segments()

    # 총 보상 (음수: 최소화 목표)
    r_t = -(w1 * delay_index + w2 * HB_bar + w3 * speed_var)
    return r_t

# 컨퍼런스용 가중치 초기값:
# w1 = 1.0 (효율), w2 = 0.5 (안전), w3 = 0.3 (안정성)
```

### 3.6 에피소드 구성
```
시뮬레이션: 3600초 (1시간)
RL step 주기: 30초 (SUMO 30 step마다 action)
총 step/episode: 120
워밍업: 첫 600초(20 step)는 통계 제외 가능
학습 에피소드: 500~1000회
```

---

## 4단계: MAPPO 알고리즘 구현

### 4.1 MAPPO 구조 (CTDE)
```
Actor (공유 파라미터 θ):
  - 입력: o_t_i (local observation, dim=10)
  - 은닉층: [128, 128] (ReLU)
  - 출력: 3개 action에 대한 softmax 확률

Critic (파라미터 φ):
  - 입력: s_t (global state, dim=전체)
  - 은닉층: [256, 256] (ReLU)
  - 출력: V(s_t) 스칼라 값
```

### 4.2 학습 알고리즘
```
PPO Clipped Objective (Multi-Agent):
L_MAPPO(θ) = (1/N) Σ_i E_t[min(r_t^i(θ) * A_t, clip(r_t^i(θ), 1-ε, 1+ε) * A_t)]

Critic Loss:
L_V(φ) = E_t[(V_φ(s_t) - R̂_t)²]

GAE (Generalized Advantage Estimation):
A_t = Σ_{l=0}^{T-t} (γλ)^l * δ_{t+l}
δ_t = r_t + γV(s_{t+1}) - V(s_t)
```

### 4.3 하이퍼파라미터
```yaml
MAPPO:
  learning_rate_actor: 3e-4
  learning_rate_critic: 5e-4
  gamma: 0.99              # 할인 계수
  gae_lambda: 0.95         # GAE λ
  clip_epsilon: 0.2        # PPO 클리핑
  n_epochs: 10             # 미니배치 반복
  batch_size: 32
  max_episodes: 800
  control_interval: 30     # 초 (RL step 주기)

네트워크:
  actor_hidden: [128, 128]
  critic_hidden: [256, 256]
  activation: "relu"
```

---

## 5단계: 실험 설계 (컨퍼런스 축소 버전)

### 5.1 비교 시나리오 (3개 Baseline + 1개 제안)
| 시나리오 | 설명 | 구현 |
|---------|------|------|
| **No Control** | 고정 속도 제한 (100/80/70 km/h) | baselines/no_control.py |
| **Static VSL** | 전 구간 70 km/h 고정 | baselines/static_vsl.py |
| **Rule-based VSL** | 밀도 임계값 기반 규칙: ρ>30→80km/h, ρ>50→60km/h | baselines/rule_based_vsl.py |
| **MARL-VSL (MAPPO)** | 2-agent MAPPO 기반 동적 VSL | **제안 방법** |

### 5.2 교통 수요 시나리오 (2개)
```
시나리오 A (Peak/Off-peak 변동): 현재 3단계 교통량 프로파일
시나리오 B (고수요 지속): 2000대/h 일정 유지 (worst case)
```

### 5.3 성능 지표 (KPI) — 6개
1. **ATT (Average Travel Time)**: 평균 여행시간 (초)
2. **Mean Speed**: 전체 네트워크 평균 속도 (m/s)
3. **Time Loss**: 이상적 조건 대비 시간 손실 (초)
4. **Throughput**: 단위시간당 도착 차량 수 (veh/h)
5. **Hard Braking Rate**: 급감속 발생 비율 (안전 지표)
6. **Speed Variance**: 구간별 속도 분산 (충격파 지표)

### 5.4 실험 반복
- 각 시나리오 × 각 제어정책: **10회 반복** (다른 랜덤 시드)
- 평균 ± 표준편차로 결과 보고

---

## 6단계: 결과 도출 및 시각화

### 6.1 필수 시각화 (논문 Figure)
1. **학습 곡선** (Fig.1): Episode vs. Cumulative Reward (수렴 확인)
2. **시공간 속도 다이어그램** (Fig.2): 위치(x) × 시간(y) × 속도(color)
   - No Control vs. MARL-VSL 비교 (충격파 완화 시각화)
3. **VSL 제어 이력** (Fig.3): 시간별 각 에이전트의 속도제한 변화
4. **KPI 비교 막대그래프** (Fig.4): 4개 정책 × 6개 KPI

### 6.2 필수 표 (논문 Table)
1. **네트워크 파라미터 표**: Edge별 길이/차로/속도
2. **RL 하이퍼파라미터 표**: MAPPO 설정값
3. **성능 비교 표**: 시나리오별 × 정책별 KPI 비교 (평균±표준편차)

### 6.3 논문 구조 (컨퍼런스 6~8 pages)
```
1. 서론 (1p)
   - 고속도로 공사구간(Work Zone) 문제 정의
   - 기존 VSL 제어의 한계 (정적/규칙기반)
   - MARL 접근의 필요성 및 연구 기여

2. 문헌 고찰 (0.5~1p)
   - Work Zone 교통 관리 연구
   - RL/MARL 기반 VSL 제어 선행 연구

3. 방법론 (2~2.5p)
   3.1 SUMO 시뮬레이션 환경
   3.2 MARL 문제 정식화 (상태/행동/보상)
   3.3 MAPPO 알고리즘 (CTDE 구조)

4. 실험 설계 (1p)
   4.1 네트워크 및 교통 수요
   4.2 비교 시나리오
   4.3 성능 지표

5. 결과 분석 (1.5~2p)
   5.1 학습 수렴 분석
   5.2 교통 효율 비교
   5.3 안전성 비교
   5.4 시공간 교통류 분석

6. 결론 및 향후 연구 (0.5p)
   - 요약, 한계점, 향후 저널 확장 방향
```

---

## 7단계: 구현 순서 (실행 계획)

### Phase 1: 환경 준비
- [ ] SUMO 설치 (Windows installer)
- [ ] 환경변수 SUMO_HOME 설정
- [ ] Python 가상환경 생성 & requirements.txt 패키지 설치
- [ ] 기존 시뮬레이션 파일(시뮬레이션.zip) SUMO-GUI로 정상 실행 확인

### Phase 2: SUMO 모델 수정
- [ ] workzone.net.xml: merge 연결 수정 (e3 both lanes → e4)
- [ ] detectors.add.xml: 5개 지점 검지기 재배치, 30초 주기
- [ ] routes.rou.xml: 교통량 프로파일 조정 (시나리오 A/B)
- [ ] workzone.sumocfg: 출력 설정 업데이트
- [ ] Baseline(No Control) 시뮬레이션 실행 → 기준 성능 확인

### Phase 3: RL 환경 구현
- [ ] sumo_env.py: TraCI 연동 (start/step/reset/close)
- [ ] multi_agent_env.py: Multi-Agent 래퍼 (observation/action 분배)
- [ ] 상태 수집 함수: 각 segment 속도/밀도/급감속 비율
- [ ] 행동 적용 함수: traci.edge.setMaxSpeed()
- [ ] 보상 계산 함수: 3항 보상 (delay + safety + variance)
- [ ] 환경 테스트: 랜덤 액션으로 에피소드 정상 완료 확인

### Phase 4: MAPPO 구현 및 학습
- [ ] actor_critic.py: Actor/Critic 네트워크 정의
- [ ] buffer.py: 경험 버퍼 (GAE 계산)
- [ ] mappo.py: MAPPO 학습 루프
- [ ] train.py: 학습 메인 (TensorBoard 로깅)
- [ ] 학습 실행 및 수렴 확인 (800 에피소드)

### Phase 5: Baseline 구현 및 비교 평가
- [ ] 3개 Baseline 정책 구현
- [ ] evaluate.py: 모든 정책 × 시나리오 × 10회 반복 평가
- [ ] plot_results.py: 학습 곡선, 시공간 다이어그램, KPI 비교 그래프
- [ ] 결과표 생성 (CSV → LaTeX 표 변환)

---

## 검증 방법

1. **SUMO 환경 검증**: `sumo-gui -c workzone.sumocfg`로 시각적 확인
2. **RL 환경 검증**: `python -m env.sumo_env`로 랜덤 에피소드 실행
3. **학습 검증**: TensorBoard에서 reward 수렴 곡선 확인
4. **성능 검증**: MARL-VSL이 No Control 대비 ATT 10%+ 감소 목표
5. **재현성**: 모든 실험에 random seed 고정

---

## 핵심 수정 파일 (기존 시뮬레이션.zip 기반)
- `시뮬레이션/workzone.net.xml` → `sumo_files/workzone.net.xml` (merge 연결 수정)
- `시뮬레이션/routes.rou.xml` → `sumo_files/routes.rou.xml` (교통량 조정)
- `시뮬레이션/detectors.add.xml` → `sumo_files/detectors.add.xml` (검지기 재배치)
- `시뮬레이션/workzone.sumocfg` → `sumo_files/workzone.sumocfg` (출력 업데이트)

## 신규 생성 파일
- `env/sumo_env.py`: SUMO-TraCI 환경
- `env/multi_agent_env.py`: MARL 래퍼
- `agents/mappo.py`: MAPPO 알고리즘
- `agents/actor_critic.py`: 신경망
- `agents/buffer.py`: 경험 버퍼
- `baselines/*.py`: 3개 Baseline 정책
- `train.py`, `evaluate.py`, `plot_results.py`: 실행 스크립트
- `configs/config.yaml`: 전체 설정

## 8단계: README 작성 및 GitHub Wiki 등록

### 8.1 README.md (핵심 요약 — 초보자 친화적)
프로젝트 루트에 README.md를 작성하여 다음 내용을 포함:
- 프로젝트 개요 (한 문단)
- 전체 시스템 구조 다이어그램 (ASCII/Mermaid)
- MARL/MAPPO가 뭔지 쉬운 비유로 설명
- 핵심 개념 (VSL, Work Zone, 병목, 보상함수)
- 빠른 시작 가이드 (설치 → 실행)
- 프로젝트 폴더 구조
- 참고 문헌

### 8.2 GitHub Wiki (상세 문서 — 5개 페이지)
GitHub Wiki를 생성하여 상세 설명:

1. **Home**: 프로젝트 전체 소개 + 목차
2. **01-배경지식**: 강화학습 기초, MARL 개념, SUMO 소개 (초보자용)
3. **02-시스템-설계**: 네트워크 구조, 에이전트 설계, 상태/행동/보상 수식
4. **03-MAPPO-알고리즘**: CTDE 구조, Actor-Critic, PPO 원리, 학습 루프
5. **04-실험-및-결과**: 실험 시나리오, KPI 정의, 예상 결과 해석 방법

### 8.3 작업 순서
- [ ] README.md 작성 (한국어, 초보자 친화적)
- [ ] Git commit & push
- [ ] GitHub Wiki 페이지 5개 생성 (gh api 또는 git clone wiki)

---

## 참고 자료
- [SUMO-DVSL (GitHub)](https://github.com/Kaimaoge/SUMO-DVSL): DDPG 기반 VSL SUMO 구현
- [조정훈 외(서울대)](https://kst.or.kr/bbs/board.php?bo_table=tugo_programbook85&wr_id=214): DDPG VSL+RM 전략
- [MAPPO Paper](https://arxiv.org/abs/2103.01955): Multi-Agent PPO 원본
- [Multi-Agent VSL (MDPI)](https://www.mdpi.com/2071-1050/15/14/11464): 다중 에이전트 VSL 연구
