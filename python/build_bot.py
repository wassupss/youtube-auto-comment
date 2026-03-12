"""
PyInstaller 빌드 스크립트
이 파일을 직접 실행: python python/build_bot.py
경로 문제 없이 어느 디렉토리에서 실행해도 동작
"""
import os
import sys
import subprocess
import shutil

# 이 스크립트 파일 기준 절대경로
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
BOT_PY = os.path.join(SCRIPT_DIR, "bot.py")
DIST_PATH = os.path.join(REPO_ROOT, "electron", "python_dist")
WORK_PATH = os.path.join(REPO_ROOT, ".pyibuild")

def main():
    # 기존 빌드 결과 정리
    if os.path.exists(DIST_PATH):
        shutil.rmtree(DIST_PATH)
    if os.path.exists(WORK_PATH):
        shutil.rmtree(WORK_PATH)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onedir",
        "--name", "bot",
        "--distpath", DIST_PATH,
        "--workpath", WORK_PATH,
        "--noconfirm",
        "--clean",
        "--console",
        "--collect-all", "selenium",
        "--collect-all", "flask",
        "--collect-all", "flask_cors",
        "--collect-all", "openpyxl",
        "--hidden-import", "selenium.webdriver.chrome.webdriver",
        "--hidden-import", "selenium.webdriver.chrome.service",
        "--hidden-import", "selenium.webdriver.chrome.options",
        "--hidden-import", "selenium.webdriver.common.by",
        "--hidden-import", "selenium.webdriver.common.keys",
        "--hidden-import", "selenium.webdriver.support.ui",
        "--hidden-import", "selenium.webdriver.support.expected_conditions",
        "--hidden-import", "pandas",
        "--hidden-import", "openpyxl",
        BOT_PY,
    ]

    print(f"[build_bot] 빌드 시작: {BOT_PY}")
    print(f"[build_bot] 출력 경로: {DIST_PATH}")

    result = subprocess.run(cmd, cwd=SCRIPT_DIR)
    if result.returncode != 0:
        print("[build_bot] ❌ 빌드 실패")
        sys.exit(1)

    # 빌드 결과 확인
    exe = os.path.join(DIST_PATH, "bot", "bot.exe" if sys.platform == "win32" else "bot")
    if os.path.exists(exe):
        print(f"[build_bot] ✅ 빌드 성공: {exe}")
    else:
        print(f"[build_bot] ❌ 실행파일 없음: {exe}")
        sys.exit(1)

if __name__ == "__main__":
    main()
