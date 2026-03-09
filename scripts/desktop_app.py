"""
CNT LLM 평가 프레임워크 - 데스크톱 앱 런처
FastAPI 백엔드를 시작하고, 빌드된 React 프론트엔드를 네이티브 윈도우로 표시합니다.
"""
import sys
import os
import threading
import time

# 프로젝트 루트를 path에 추가
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import webview
import uvicorn


def start_backend():
    """FastAPI 서버를 백그라운드 스레드에서 시작"""
    from src.api.main import app
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")


def wait_for_backend(url="http://127.0.0.1:8000/api/health", timeout=30):
    """백엔드가 준비될 때까지 대기"""
    import urllib.request
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def main():
    # 1) 백엔드 서버 시작 (데몬 스레드)
    backend_thread = threading.Thread(target=start_backend, daemon=True)
    backend_thread.start()

    # 2) 백엔드 준비 대기
    print("백엔드 서버 시작 대기 중...")
    if not wait_for_backend():
        print("ERROR: 백엔드 서버 시작 실패")
        sys.exit(1)
    print("백엔드 서버 준비 완료")

    # 3) 프론트엔드 URL 결정
    build_dir = os.path.join(PROJECT_ROOT, "frontend", "build", "index.html")
    if os.path.exists(build_dir):
        # 빌드된 정적 파일 사용 (FastAPI에서 서빙)
        frontend_url = "http://127.0.0.1:8000"
    else:
        # 개발 서버 사용
        frontend_url = "http://localhost:3000"

    # 4) 네이티브 윈도우 열기
    window = webview.create_window(
        title="CNT LLM 평가 프레임워크",
        url=frontend_url,
        width=1400,
        height=900,
        resizable=True,
        min_size=(1024, 700),
    )
    webview.start()


if __name__ == "__main__":
    main()
