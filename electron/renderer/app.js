const API = "http://127.0.0.1:17117";

// ── 탭 전환 ────────────────────────────────────────────────
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document
      .querySelectorAll(".tab")
      .forEach((t) => t.classList.remove("active"));
    document
      .querySelectorAll(".tab-content")
      .forEach((c) => c.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById(`tab-${tab.dataset.tab}`).classList.add("active");
  });
});

// ── 로그 출력 ───────────────────────────────────────────────
const logBox = document.getElementById("log-box");
function appendLog(msg) {
  if (!msg || msg === "__PING__") return;
  const line = document.createElement("div");
  line.className = "log-line";
  if (msg.startsWith("✅") || msg.includes("완료"))
    line.classList.add("success");
  else if (msg.startsWith("❌")) line.classList.add("error");
  else if (msg.startsWith("⚠️")) line.classList.add("warn");
  else if (
    msg.startsWith("⏳") ||
    msg.startsWith("  ⏱") ||
    msg.startsWith("  로그인")
  )
    line.classList.add("info");
  line.textContent = msg;
  logBox.appendChild(line);
  logBox.scrollTop = logBox.scrollHeight;
}

document.getElementById("clear-log").addEventListener("click", () => {
  logBox.innerHTML = "";
});

// ── 상태 배지 ───────────────────────────────────────────────
const badge = document.getElementById("status-badge");
const btnStart = document.getElementById("btn-start");
const btnStop = document.getElementById("btn-stop");

function setRunning(running) {
  if (running) {
    badge.className = "badge badge-running";
    badge.textContent = "실행 중";
    btnStart.disabled = true;
    btnStop.disabled = false;
  } else {
    badge.className = "badge badge-idle";
    badge.textContent = "대기 중";
    btnStart.disabled = false;
    btnStop.disabled = true;
  }
}

// ── 설정 로드 ───────────────────────────────────────────────
async function loadConfig() {
  const res = await fetch(`${API}/config`);
  const cfg = await res.json();
  document.getElementById("youtube-url").value = cfg.youtube_url || "";
  document.getElementById("interval").value = cfg.interval || 60;

  // 브라우저 선택 복원
  const browserType = cfg.browser_type || "chrome";
  selectBrowser(browserType, cfg.browser_path || "");
}

// ── 브라우저 선택 UI ────────────────────────────────────────
const BROWSER_HINTS = {
  chrome: "Chrome 기본 설치 경로를 자동으로 사용합니다.",
  brave:  "Brave 기본 설치 경로를 자동으로 사용합니다.",
  custom: "브라우저 실행파일 경로를 직접 입력하세요.",
};

function selectBrowser(type, customPath = "") {
  document.querySelectorAll(".btn-browser").forEach((b) => {
    b.classList.toggle("active", b.dataset.browser === type);
  });
  const customRow = document.getElementById("custom-path-row");
  const hint = document.getElementById("browser-hint");
  customRow.style.display = type === "custom" ? "flex" : "none";
  hint.textContent = BROWSER_HINTS[type] || "";
  if (type === "custom" && customPath) {
    document.getElementById("browser-path").value = customPath;
  }
}

document.querySelectorAll(".btn-browser").forEach((btn) => {
  btn.addEventListener("click", () => selectBrowser(btn.dataset.browser));
});

document.getElementById("browse-browser").addEventListener("click", async () => {
  const path = await window.api.openFile([
    { name: "실행 파일", extensions: ["exe", "app", "*"] },
    { name: "모든 파일", extensions: ["*"] },
  ]);
  if (path) document.getElementById("browser-path").value = path;
});

// ── 설정 저장 ───────────────────────────────────────────────
async function getConfigFromUI() {
  const browserType = document.querySelector(".btn-browser.active")?.dataset.browser || "chrome";
  const browserPath = browserType === "custom"
    ? document.getElementById("browser-path").value.trim()
    : "";
  return {
    youtube_url: document.getElementById("youtube-url").value.trim(),
    browser_type: browserType,
    browser_path: browserPath,
    interval: parseInt(document.getElementById("interval").value) || 60,
  };
}

document.getElementById("save-config").addEventListener("click", async () => {
  const cfg = await getConfigFromUI();
  const res = await fetch(`${API}/config`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cfg),
  });
  const data = await res.json();
  if (!data.ok) { appendLog(`❌ ${data.msg}`); return; }
  showToast("설정이 저장되었습니다.");
});

// ── Brave 경로 찾아보기 ─────────────────────────────────────
// ── 문구 로드 / 저장 ────────────────────────────────────────
async function loadMessages() {
  const res = await fetch(`${API}/messages`);
  const data = await res.json();
  document.getElementById("messages-editor").value = data.content || "";
}

document
  .getElementById("reload-messages")
  .addEventListener("click", loadMessages);

document.getElementById("save-messages").addEventListener("click", async () => {
  const content = document.getElementById("messages-editor").value;
  await fetch(`${API}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  showToast("문구 파일이 저장되었습니다.");
});

// ── 봇 시작 ─────────────────────────────────────────────────
btnStart.addEventListener("click", async () => {
  const cfg = await getConfigFromUI();
  const res = await fetch(`${API}/bot/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cfg),
  });
  const data = await res.json();
  if (!data.ok) {
    appendLog(`❌ ${data.msg}`);
    return;
  }

  setRunning(true);
  logBox.innerHTML = "";
  appendLog("▶ 봇을 시작합니다...");

  // 로그 탭으로 자동 전환
  document
    .querySelectorAll(".tab")
    .forEach((t) => t.classList.remove("active"));
  document
    .querySelectorAll(".tab-content")
    .forEach((c) => c.classList.remove("active"));
  document.querySelector('[data-tab="log"]').classList.add("active");
  document.getElementById("tab-log").classList.add("active");

  // SSE 로그 수신
  const sse = new EventSource(`${API}/log/stream`);
  sse.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg === "__DONE__") {
      sse.close();
      setRunning(false);
      badge.className = "badge badge-done";
      badge.textContent = "완료";
    } else {
      appendLog(msg);
    }
  };
  sse.onerror = () => {
    sse.close();
    setRunning(false);
  };
});

// ── 봇 중지 ─────────────────────────────────────────────────
btnStop.addEventListener("click", async () => {
  await fetch(`${API}/bot/stop`, { method: "POST" });
});

// ── 토스트 메시지 ────────────────────────────────────────────
function showToast(msg) {
  const t = document.createElement("div");
  t.textContent = msg;
  Object.assign(t.style, {
    position: "fixed",
    bottom: "80px",
    left: "50%",
    transform: "translateX(-50%)",
    background: "#22c55e",
    color: "#fff",
    padding: "8px 20px",
    borderRadius: "20px",
    fontSize: "13px",
    fontWeight: "600",
    zIndex: 9999,
    pointerEvents: "none",
    opacity: "1",
    transition: "opacity 0.5s",
  });
  document.body.appendChild(t);
  setTimeout(() => {
    t.style.opacity = "0";
    setTimeout(() => t.remove(), 500);
  }, 2000);
}

// ── 초기화 ──────────────────────────────────────────────────
(async () => {
  await loadConfig();
  await loadMessages();
  setRunning(false);
})();
