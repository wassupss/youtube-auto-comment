"""
유튜브 자동 채팅 봇 - Python Flask API 서버
Electron에서 HTTP로 호출
"""
import time
import random
import os
import json
import threading
import sys
import platform
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import queue

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd

app = Flask(__name__)
# ── localhost에서만 접근 허용 (Electron 렌더러 프로세스 전용) ──
CORS(app, origins=["null", "file://"])  # Electron은 file:// 또는 null origin 사용

# ── 경로 처리 ──────────────────────────────────────────────
def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = get_base_dir()
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
DEFAULT_TXT_FILE = os.path.join(BASE_DIR, "YTN_live.txt")

if platform.system() == "Windows":
    DEFAULT_BRAVE_PATH = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
else:
    DEFAULT_BRAVE_PATH = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"

DEFAULT_CONFIG = {
    "youtube_url": "https://www.youtube.com/watch?v=FJfwehhzIhw",
    "txt_file": "YTN_live.txt",   # 파일명만 저장 → BASE_DIR 기준으로 resolve
    "brave_path": DEFAULT_BRAVE_PATH,
    "interval": 60
}

def resolve_txt_path(txt_file: str) -> str:
    """config에 저장된 txt_file이 절대경로면 그대로, 파일명만 있으면 BASE_DIR 기준으로 반환"""
    if os.path.isabs(txt_file):
        resolved = txt_file
    else:
        resolved = os.path.join(BASE_DIR, txt_file)
    # 경로 순회 공격 방지: BASE_DIR 또는 절대경로 파일만 허용
    resolved = os.path.normpath(resolved)
    return resolved

def validate_url(url: str) -> bool:
    """YouTube URL만 허용"""
    return url.startswith("https://www.youtube.com/") or url.startswith("https://youtu.be/")

def validate_brave_path(path: str) -> bool:
    """실행파일 경로 기본 검증"""
    if not path:
        return False
    normalized = os.path.normpath(path)
    # 경로 순회 방지
    if ".." in normalized:
        return False
    return True

# ── 전역 상태 ──────────────────────────────────────────────
log_queue = queue.Queue()
bot_running = False
bot_thread = None
driver_ref = None

# ── 설정 ───────────────────────────────────────────────────
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in DEFAULT_CONFIG.items():
                    data.setdefault(k, v)
                return data
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

# ── 메시지 파일 ────────────────────────────────────────────
def load_messages(file_path):
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def ensure_sample_txt(path):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write("📢 홍보 문구 1번입니다. 여기에 내용을 입력하세요.\n")
            f.write("📢 홍보 문구 2번입니다. 줄마다 하나씩 작성하세요.\n")
            f.write("📢 홍보 문구 3번입니다. 빈 줄은 무시됩니다.\n")

# ── API 라우트 ─────────────────────────────────────────────
@app.route("/config", methods=["GET"])
def get_config():
    cfg = load_config()
    ensure_sample_txt(resolve_txt_path(cfg["txt_file"]))
    return jsonify(cfg)

@app.route("/config", methods=["POST"])
def post_config():
    cfg = request.json
    # 입력값 검증
    if not validate_url(cfg.get("youtube_url", "")):
        return jsonify({"ok": False, "msg": "유효하지 않은 YouTube URL입니다."}), 400
    if not validate_brave_path(cfg.get("brave_path", "")):
        return jsonify({"ok": False, "msg": "유효하지 않은 Brave 경로입니다."}), 400
    try:
        cfg["interval"] = max(10, min(3600, int(cfg.get("interval", 60))))
    except (ValueError, TypeError):
        cfg["interval"] = 60
    save_config(cfg)
    return jsonify({"ok": True})

@app.route("/messages", methods=["GET"])
def get_messages():
    cfg = load_config()
    path = resolve_txt_path(cfg["txt_file"])
    if not os.path.exists(path):
        return jsonify({"content": ""})
    with open(path, "r", encoding="utf-8") as f:
        return jsonify({"content": f.read()})

@app.route("/messages", methods=["POST"])
def post_messages():
    cfg = load_config()
    path = resolve_txt_path(cfg["txt_file"])
    # BASE_DIR 하위 경로만 쓰기 허용
    if not path.startswith(BASE_DIR):
        return jsonify({"ok": False, "msg": "허용되지 않는 경로입니다."}), 403
    content = request.json.get("content", "")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return jsonify({"ok": True})

@app.route("/bot/start", methods=["POST"])
def start_bot():
    global bot_running, bot_thread
    if bot_running:
        return jsonify({"ok": False, "msg": "이미 실행 중입니다."})
    cfg = request.json or load_config()
    save_config(cfg)
    bot_running = True
    bot_thread = threading.Thread(target=_run_bot, args=(cfg,), daemon=True)
    bot_thread.start()
    return jsonify({"ok": True})

@app.route("/bot/stop", methods=["POST"])
def stop_bot():
    global bot_running, driver_ref
    bot_running = False
    if driver_ref:
        try:
            driver_ref.quit()
        except Exception:
            pass
        driver_ref = None
    log_queue.put("[중지] 봇이 중지되었습니다.")
    log_queue.put("__DONE__")
    return jsonify({"ok": True})

@app.route("/bot/status", methods=["GET"])
def bot_status():
    return jsonify({"running": bot_running})

@app.route("/log/stream")
def log_stream():
    """SSE(Server-Sent Events)로 로그 실시간 전송"""
    def generate():
        while True:
            try:
                msg = log_queue.get(timeout=30)
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
            except queue.Empty:
                yield "data: __PING__\n\n"
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.route("/health")
def health():
    return jsonify({"ok": True})

# ── 봇 실행 로직 ───────────────────────────────────────────
def _log(msg):
    log_queue.put(msg)

def _run_bot(cfg):
    global bot_running, driver_ref
    messages = load_messages(resolve_txt_path(cfg["txt_file"]))
    if not messages:
        _log("❌ 문구 파일이 비어있거나 없습니다.")
        _log("__DONE__")
        bot_running = False
        return

    options = Options()
    options.binary_location = cfg["brave_path"]
    options.add_argument("--disable-blink-features=AutomationControlled")

    try:
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), options=options
        )
        driver_ref = driver
    except Exception as e:
        _log(f"❌ 브라우저 실행 실패: {e}")
        _log("__DONE__")
        bot_running = False
        return

    driver.get(cfg["youtube_url"])
    _log("⏳ 15초 대기 중... 브라우저에서 유튜브 로그인을 완료해주세요!")

    for i in range(15, 0, -1):
        if not bot_running:
            break
        _log(f"  로그인 대기: {i}초 남음...")
        time.sleep(1)

    log_data = []
    interval = int(cfg["interval"])

    try:
        for i, msg in enumerate(messages):
            if not bot_running:
                break
            try:
                chat_box = driver.find_element(By.CSS_SELECTOR, "#focused-interaction-element")
                final_msg = f"{msg} (code:{random.randint(100, 999)})"
                chat_box.send_keys(final_msg)
                chat_box.send_keys(Keys.ENTER)
                now = time.strftime('%H:%M:%S')
                _log(f"[{now}] {i+1}/{len(messages)}번 전송 완료: {final_msg}")
                log_data.append({"시간": now, "문구": final_msg, "결과": "성공"})
            except Exception as e:
                _log(f"⚠️ 전송 오류 (건너뜀): {e}")
                continue

            sleep_time = interval + random.uniform(1, 3)
            _log(f"  ⏱ 다음 전송까지 {sleep_time:.0f}초 대기...")
            for _ in range(int(sleep_time)):
                if not bot_running:
                    break
                time.sleep(1)
    finally:
        if log_data:
            report_path = os.path.join(BASE_DIR, "홍보_결과리포트.xlsx")
            df = pd.DataFrame(log_data)
            df.to_excel(report_path, index=False)
            _log(f"✅ 완료! '홍보_결과리포트.xlsx' 저장됨.")
        try:
            driver.quit()
        except Exception:
            pass
        driver_ref = None
        bot_running = False
        _log("__DONE__")

if __name__ == "__main__":
    ensure_sample_txt(DEFAULT_TXT_FILE)
    # 반드시 127.0.0.1만 바인딩 → 외부 네트워크 접근 차단
    app.run(host="127.0.0.1", port=17117, debug=False, threaded=True)
