@echo off
chcp 65001 > nul
title 유튜브봇 Windows 빌드

echo ========================================
echo   유튜브봇 Windows 빌드 시작
echo ========================================
echo.

:: ── 사전 조건 확인 ─────────────────────────────────────────
python --version > nul 2>&1
if %errorlevel% neq 0 (
    echo [오류] Python이 없습니다. https://www.python.org 에서 설치 후
    echo        "Add Python to PATH" 반드시 체크하세요.
    pause & exit /b 1
)

node --version > nul 2>&1
if %errorlevel% neq 0 (
    echo [오류] Node.js가 없습니다. https://nodejs.org 에서 LTS 버전 설치하세요.
    pause & exit /b 1
)

:: ── 1. Python 가상환경 & 패키지 ────────────────────────────
echo [1/4] Python 환경 설정...
if not exist "python\.venv" python -m venv python\.venv
call python\.venv\Scripts\activate.bat
pip install -q --upgrade pip
pip install -q -r python\requirements.txt
pip install -q pyinstaller

:: ── 2. Python → bot.exe ────────────────────────────────────
echo [2/4] Python 봇 빌드...
if exist "electron\python_dist" rd /s /q "electron\python_dist"
pyinstaller ^
    --onefile ^
    --name bot ^
    --distpath electron\python_dist ^
    --workpath %TEMP%\pyibuild_win ^
    --clean ^
    --hidden-import flask ^
    --hidden-import flask_cors ^
    --hidden-import selenium ^
    --hidden-import webdriver_manager ^
    python\bot.py
if %errorlevel% neq 0 ( echo [오류] Python 빌드 실패! & pause & exit /b 1 )
call deactivate

:: ── 3. Electron 패키지 설치 ────────────────────────────────
echo [3/4] Electron 패키지 설치...
cd electron
call npm install --silent

:: ── 4. Electron → NSIS 인스톨러 (.exe) ────────────────────
echo [4/4] Electron 앱 빌드...
call npm run build:win
if %errorlevel% neq 0 ( echo [오류] Electron 빌드 실패! & cd .. & pause & exit /b 1 )
cd ..

echo.
echo ✅ 빌드 완료^^!
echo    결과물 위치: electron\dist\
echo.
echo ⚠️  백신이 차단 시 예외 처리 후 실행하세요.
pause
