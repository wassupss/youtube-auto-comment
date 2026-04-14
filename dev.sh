#!/bin/zsh
# 개발 모드 실행 (빌드 없이 바로 테스트)
set -e
cd "$(dirname "$0")"

echo "🚀 개발 모드 실행..."

# Homebrew Python 3.13 우선, 없으면 시스템 python3 사용
PYTHON_BIN="python3"
if [ -x "/opt/homebrew/opt/python@3.13/bin/python3.13" ]; then
  PYTHON_BIN="/opt/homebrew/opt/python@3.13/bin/python3.13"
elif [ -x "/usr/local/opt/python@3.13/bin/python3.13" ]; then
  PYTHON_BIN="/usr/local/opt/python@3.13/bin/python3.13"
fi

# Python 서버 백그라운드 실행
if [ ! -d "python/.venv" ]; then
  echo "Python 가상환경 생성 중... ($($PYTHON_BIN --version))"
  $PYTHON_BIN -m venv python/.venv
  source python/.venv/bin/activate
  pip install -q -r python/requirements.txt
else
  source python/.venv/bin/activate
fi

python python/bot.py &
PYTHON_PID=$!
echo "Python 서버 PID: $PYTHON_PID"

# Electron 실행
cd electron
[ ! -d node_modules ] && npm install --silent
npx electron .

# 종료 시 Python도 같이 종료
kill $PYTHON_PID 2>/dev/null || true
