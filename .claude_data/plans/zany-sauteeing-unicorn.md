# Galaxy S23 앱 미실행 문제 분석 및 해결 계획

## Context

Galaxy S23에서 VLM Product Inspector APK가 실행되지 않는 문제.
**Android SDK/NDK/Java 미설치 상태** → 데스크탑에서 먼저 테스트/디버깅 후, Android 환경 구축 시 배포 버전 생성.

## 근본 원인 분석 (Galaxy S23 크래시)

1. **Android 타겟 미초기화** — `src-tauri/gen/` 비어 있음. `npx tauri android init` 미실행
2. **`tokenizers` onig 피처** — Oniguruma C 라이브러리의 Android ARM64 크로스컴파일 실패
3. **`ort` (ONNX Runtime)** — Android ARM64용 libonnxruntime.so 미포함
4. **`tokio` full features** — Android 비호환 기능 포함
5. **`beforeBuildCommand` 누락** — 프로덕션 빌드 시 프론트엔드 미빌드

---

## Phase 1: 데스크탑 테스트 환경 구축 (지금 진행)

### Step 1. `tauri.conf.json` 수정
- `beforeBuildCommand`: `""` → `"npm run build"` (프로덕션 빌드 시 프론트엔드 자동 빌드)

### Step 2. Rust 의존성 선제 수정 (Android 호환성 준비)
**파일: `src-tauri/Cargo.toml`**
- `tokenizers`: `onig` 피처 제거 → 순수 Rust regex 백엔드 사용
- `tokio`: `full` → 필요한 feature만 (`rt-multi-thread`, `macros`, `fs`, `io-util`, `sync`, `time`)

### Step 3. ONNX 세션 빌더 최적화
**파일: `src-tauri/src/model/inference.rs`**
- Android 타겟 조건부 컴파일로 스레드 수 제한 추가 (`#[cfg(target_os = "android")]`)

### Step 4. 데스크탑 테스트 실행
```bash
npx tauri dev
```
- 420x780 창에서 모바일 UI 확인
- 전체 워크플로우: 홈 → 모델 다운로드 → 로드 → 이미지 분석 → 결과

---

## Phase 2: Android 빌드 (추후 — Android SDK 설치 후)

> Android Studio + SDK (API 24+) + NDK r25+ + JDK 설치 필요

1. `npx tauri android init`
2. AndroidManifest.xml 퍼미션 설정
3. `npx tauri android build --debug` → Galaxy S23 테스트
4. `npx tauri android build` → 릴리즈 APK

---

## 수정 대상 파일

| 파일 | 변경 내용 |
|------|-----------|
| `src-tauri/tauri.conf.json` | `beforeBuildCommand` 추가 |
| `src-tauri/Cargo.toml` | tokenizers onig 제거, tokio features 축소 |
| `src-tauri/src/model/inference.rs` | Android 조건부 세션 빌더 최적화 |

## 검증

- `npx tauri dev` → 데스크탑 창에서 전체 워크플로우 정상 동작 확인
