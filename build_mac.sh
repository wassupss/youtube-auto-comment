#!/bin/zsh
# ── macOS 전체 빌드 스크립트 ────────────────────────────────
# Python bot → 단일 실행파일 → Electron .dmg 패키지
set -e
cd "$(dirname "$0")"

echo "========================================"
echo "  유튜브봇 macOS 빌드 시작"
echo "========================================"

# ── 1. Python 가상환경 & 패키지 ─────────────────────────────
echo "\n[1/4] Python 환경 설정..."
# Homebrew Python 3.13 우선, 없으면 시스템 python3 사용
PYTHON_BIN="python3"
if [ -x "/opt/homebrew/opt/python@3.13/bin/python3.13" ]; then
  PYTHON_BIN="/opt/homebrew/opt/python@3.13/bin/python3.13"
elif [ -x "/usr/local/opt/python@3.13/bin/python3.13" ]; then
  PYTHON_BIN="/usr/local/opt/python@3.13/bin/python3.13"
fi
echo "  Python: $($PYTHON_BIN --version)"
if [ ! -d "python/.venv" ]; then
  $PYTHON_BIN -m venv python/.venv
fi
source python/.venv/bin/activate
pip install -q --upgrade pip
pip install -q -r python/requirements.txt
pip install -q pyinstaller

# ── 2. Python → 단일 실행파일 (bot) ─────────────────────────
echo "\n[2/4] Python 봇 빌드..."
rm -rf electron/python_dist
pyinstaller \
  --onefile \
  --name bot \
  --distpath electron/python_dist \
  --workpath /tmp/pyibuild_mac \
  --clean \
  --hidden-import flask \
  --hidden-import flask_cors \
  --hidden-import selenium \
  --hidden-import webdriver_manager \
  python/bot.py
deactivate
echo "  → electron/python_dist/bot 생성됨"

# ── 3. Electron 패키지 설치 ──────────────────────────────────
echo "\n[3/4] Electron 패키지 설치..."
cd electron
npm install --silent

# ── 4. Electron → .dmg ───────────────────────────────────────
echo "\n[4/4] Electron 앱 빌드 (.dmg)..."
npm run build:mac

echo "\n✅ 빌드 완료!"
echo "   결과물 위치: electron/dist/"
ls -lh dist/*.dmg 2>/dev/null || true
echo ""
echo "⚠️  macOS 보안 경고 해결 방법:"
echo "   앱 우클릭 → '열기' → '열기' 클릭  (최초 1회)"
