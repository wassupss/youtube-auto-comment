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
import itertools
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import queue

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
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
DEFAULT_TXT_FILE = os.path.join(BASE_DIR, "messages.txt")

if platform.system() == "Windows":
    DEFAULT_BRAVE_PATH = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
else:
    DEFAULT_BRAVE_PATH = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"

# OS별 브라우저 기본 경로 (우선순위 순)
BROWSER_PATHS = {
    "chrome": {
        "Windows": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Google\Chrome\Application\chrome.exe"),
            os.path.join(os.environ.get("PROGRAMFILES", ""), r"Google\Chrome\Application\chrome.exe"),
        ],
        "Darwin":  ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"],
        "Linux":   ["/usr/bin/google-chrome", "/usr/bin/chromium-browser", "/usr/bin/chromium"],
    },
    "brave": {
        "Windows": [
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
            os.path.join(os.environ.get("LOCALAPPDATA", ""), r"BraveSoftware\Brave-Browser\Application\brave.exe"),
        ],
        "Darwin":  ["/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"],
        "Linux":   ["/usr/bin/brave-browser", "/usr/bin/brave"],
    },
}

def resolve_browser_path(cfg: dict) -> str:
    """browser_type 에 따라 실행파일 경로 반환 (여러 경로 중 존재하는 것 사용)"""
    browser_type = cfg.get("browser_type", "chrome")
    if browser_type == "custom":
        path = cfg.get("browser_path", "")
        # macOS: .app 번들 경로가 들어온 경우 실행파일 경로로 자동 보정
        if path.endswith(".app"):
            app_name = os.path.splitext(os.path.basename(path))[0]
            path = os.path.join(path, "Contents", "MacOS", app_name)
        return path
    os_name = platform.system()  # 'Windows' | 'Darwin' | 'Linux'
    candidates = BROWSER_PATHS.get(browser_type, BROWSER_PATHS["chrome"]).get(os_name, [])
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return candidates[0] if candidates else ""  # 없으면 첫 번째 경로 반환 (에러 메시지용)

DEFAULT_CONFIG = {
    "youtube_url": "",
    "txt_file": "messages.txt",
    "browser_type": "chrome",
    "browser_path": "",
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

def validate_browser_path(path: str) -> bool:
    """실행파일 경로 기본 검증 (custom 모드일 때만 사용)"""
    if not path:
        return True  # chrome/brave는 자동 경로 사용이므로 빈값 허용
    normalized = os.path.normpath(path)
    if ".." in normalized:
        return False
    return True

# ── 전역 상태 ──────────────────────────────────────────────
log_queue = queue.Queue()
bot_running = False
bot_thread = None
driver_ref = None
login_ready = threading.Event()
last_log_data = []  # 마지막 실행 결과 보관 (다운로드용)

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
    # 파일이 없으면 빈 파일만 생성 (샘플 문구 없음 - 사용자가 앱에서 직접 입력)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write("")

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
    if not validate_browser_path(cfg.get("browser_path", "")):
        return jsonify({"ok": False, "msg": "유효하지 않은 브라우저 경로입니다."}), 400
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
    cfg = request.json or {}
    # 저장된 config와 병합 (누락 키 보완)
    saved = load_config()
    saved.update({k: v for k, v in cfg.items() if v not in (None, "")})
    cfg = saved
    save_config(cfg)
    bot_running = True
    bot_thread = threading.Thread(target=_run_bot, args=(cfg,), daemon=True)
    bot_thread.start()
    return jsonify({"ok": True})

@app.route("/report/download")
def download_report():
    if not last_log_data:
        return jsonify({"ok": False, "msg": "다운로드할 리포트가 없습니다."}), 404
    import io
    from flask import send_file
    df = pd.DataFrame(last_log_data)
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    filename = f"홍보결과_{time.strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(buf, as_attachment=True, download_name=filename,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/report/status")
def report_status():
    return jsonify({"available": len(last_log_data) > 0, "count": len(last_log_data)})

@app.route("/bot/login-ready", methods=["POST"])
def login_ready_signal():
    login_ready.set()
    return jsonify({"ok": True})

@app.route("/bot/stop", methods=["POST"])
def stop_bot():
    global bot_running
    # bot_running만 False로 → _run_bot() finally 블록에서 파일 저장 후 정상 종료
    bot_running = False
    login_ready.set()  # 로그인 대기 중이면 즉시 해제
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
    global bot_running, driver_ref, last_log_data
    # 누락된 키를 DEFAULT_CONFIG로 보완
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    messages = load_messages(resolve_txt_path(cfg["txt_file"]))
    if not messages:
        _log("❌ 문구 파일이 비어있거나 없습니다.")
        _log("__DONE__")
        bot_running = False
        return

    options = Options()
    browser_exe = resolve_browser_path(cfg)
    if not browser_exe or not os.path.exists(browser_exe):
        _log(f"❌ 브라우저를 찾을 수 없습니다: {browser_exe or '(경로 없음)'}")
        _log(f"   Chrome 또는 Brave가 기본 경로에 설치되어 있는지 확인하세요.")
        _log(f"   설정 탭에서 브라우저 종류를 'custom'으로 바꾸고 직접 경로를 입력할 수도 있습니다.")
        _log("__DONE__")
        bot_running = False
        return
    options.binary_location = browser_exe
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    _log(f"🌐 브라우저 경로: {browser_exe}")

    # webdriver-manager로 chromedriver 자동 다운로드/캐싱
    # PyInstaller 빌드 환경에서도 홈 디렉토리에 캐싱하므로 안정적으로 동작
    try:
        wdm_cache = os.path.join(os.path.expanduser("~"), ".youtubebot_cache", "wdm")
        os.makedirs(wdm_cache, exist_ok=True)
        os.environ["WDM_LOCAL"] = "1"           # 로컬 캐시 사용
        os.environ["WDM_CACHE_PATH"] = wdm_cache

        _log("🔧 ChromeDriver 준비 중... (첫 실행 시 다운로드, 잠시 대기)")
        driver_path = ChromeDriverManager().install()
        service = Service(executable_path=driver_path)
        driver = webdriver.Chrome(service=service, options=options)
        driver_ref = driver
    except Exception as e:
        _log(f"❌ 브라우저 실행 실패: {e}")
        _log(f"   인터넷 연결을 확인하거나 앱을 재시작해보세요.")
        _log("__DONE__")
        bot_running = False
        return

    driver.get(cfg["youtube_url"])
    _log("🔐 브라우저에서 YouTube에 로그인 후, 앱의 [로그인 완료] 버튼을 눌러주세요.")
    _log("__WAIT_LOGIN__")  # 앱에 로그인 버튼 표시 신호

    # 로그인 완료 버튼 누를 때까지 대기 (최대 10분)
    login_ready.clear()
    login_ready.wait(timeout=600)

    if not bot_running:
        try:
            driver.quit()
        except Exception:
            pass
        driver_ref = None
        _log("__DONE__")
        return

    _log("✅ 로그인 확인! 채팅 전송을 시작합니다.")

    log_data = []
    round_num = 0

    try:
        msg_cycle = itertools.cycle(messages)  # 문구 무한 순환
        msg_index = 0

        while bot_running:
            msg = next(msg_cycle)

            # 한 바퀴 돌 때마다 라운드 표시
            if msg_index % len(messages) == 0:
                round_num += 1
                _log(f"── 🔄 {round_num}회차 시작 (총 {len(messages)}개 문구) ──")

            try:
                wait = WebDriverWait(driver, 10)

                # 채팅 iframe으로 전환
                try:
                    chat_iframe = wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "iframe#chatframe"))
                    )
                    driver.switch_to.frame(chat_iframe)
                except Exception:
                    pass

                # contenteditable div 찾기
                chat_box = None
                selectors = [
                    "div#input[contenteditable]",
                    "div[aria-label='채팅...'][contenteditable]",
                    "div[aria-label='Chat...'][contenteditable]",
                    "yt-live-chat-text-input-field-renderer #input",
                ]
                for sel in selectors:
                    try:
                        chat_box = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, sel)))
                        break
                    except Exception:
                        continue

                if chat_box is None:
                    _log("⚠️ 채팅 입력창을 찾을 수 없습니다. 로그인 또는 채팅 활성화 여부를 확인하세요.")
                    driver.switch_to.default_content()
                    msg_index += 1
                    continue

                chat_box.click()
                time.sleep(0.3)
                chat_box.send_keys(msg)
                time.sleep(0.3)
                chat_box.send_keys(Keys.ENTER)

                driver.switch_to.default_content()

                now = time.strftime('%H:%M:%S')
                pos = (msg_index % len(messages)) + 1
                _log(f"[{now}] {round_num}회차 {pos}/{len(messages)}번 전송: {msg}")
                log_data.append({"시간": now, "회차": round_num, "문구": msg, "결과": "성공"})

            except Exception as e:
                _log(f"⚠️ 전송 오류 (건너뜀): {e}")
                try:
                    driver.switch_to.default_content()
                except Exception:
                    pass

            msg_index += 1

            if not bot_running:
                break

            sleep_time = random.uniform(30 * 60, 60 * 60)  # 30분~60분 랜덤
            next_time = time.strftime('%H:%M:%S', time.localtime(time.time() + sleep_time))
            _log(f"  ⏱ 다음 전송까지 {sleep_time/60:.0f}분 대기... (예정 시각: {next_time})")
            for _ in range(int(sleep_time)):
                if not bot_running:
                    break
                time.sleep(1)
    finally:
        if log_data:
            last_log_data = log_data  # 메모리에 보관 → 앱에서 다운로드 버튼으로 저장
            _log(f"✅ 총 {len(log_data)}건 전송 완료. 리포트 다운로드 버튼을 눌러 저장하세요.")
            _log("__REPORT_READY__")  # 앱에 다운로드 버튼 표시 신호
        else:
            _log("ℹ️ 전송된 문구가 없어 리포트가 생성되지 않았습니다.")
        _log("[중지] 봇이 중지되었습니다.")
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
