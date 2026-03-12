const { app, BrowserWindow, ipcMain, dialog } = require("electron");
const path = require("path");
const { spawn } = require("child_process");
const http = require("http");
const fs = require("fs");

const API_PORT = 17117;
let mainWindow = null;
let pythonProcess = null;

// ── Python 실행파일 경로 결정 ───────────────────────────────
function getPythonExePath() {
  const isPackaged = app.isPackaged;
  const platform = process.platform;

  if (isPackaged) {
    const resourcesPath = process.resourcesPath;
    const exeName = platform === "win32" ? "bot.exe" : "bot";
    return path.join(resourcesPath, "python_dist", exeName);
  } else {
    // 개발 모드: python으로 직접 실행
    return null;
  }
}

// ── Python 프로세스 강제 종료 (Windows: taskkill로 자식까지) ──
function killPythonProcess() {
  if (!pythonProcess) return;
  try {
    if (process.platform === "win32") {
      // /T: 자식 프로세스 포함, /F: 강제 종료
      spawn("taskkill", ["/pid", String(pythonProcess.pid), "/T", "/F"], {
        stdio: "ignore",
        detached: true,
      });
    } else {
      pythonProcess.kill("SIGTERM");
    }
  } catch (e) {
    console.error("Python 프로세스 종료 실패:", e);
  }
  pythonProcess = null;
}

// ── Python 서버 시작 ────────────────────────────────────────
function startPythonServer() {
  const exePath = getPythonExePath();

  if (exePath && fs.existsSync(exePath)) {
    // 패키징된 exe 실행
    pythonProcess = spawn(exePath, [], {
      stdio: "ignore",
      detached: false,
    });
  } else {
    // 개발 모드: python bot.py 직접 실행
    const botScript = path.join(__dirname, "..", "python", "bot.py");
    const pythonCmd = process.platform === "win32" ? "python" : "python3";
    pythonProcess = spawn(pythonCmd, [botScript], {
      stdio: "ignore",
      detached: false,
    });
  }

  pythonProcess.on("error", (err) => {
    console.error("Python 서버 실행 실패:", err);
  });
}

// ── Python 서버 응답 대기 ───────────────────────────────────
function waitForServer(retries = 30) {
  return new Promise((resolve, reject) => {
    const check = (n) => {
      http
        .get(`http://127.0.0.1:${API_PORT}/health`, (res) => {
          if (res.statusCode === 200) resolve();
          else if (n > 0) setTimeout(() => check(n - 1), 500);
          else reject(new Error("서버 응답 없음"));
        })
        .on("error", () => {
          if (n > 0) setTimeout(() => check(n - 1), 500);
          else reject(new Error("서버 시작 실패"));
        });
    };
    check(retries);
  });
}

// ── 메인 윈도우 생성 ────────────────────────────────────────
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 780,
    height: 820,
    minWidth: 680,
    minHeight: 700,
    title: "유튜브 자동 채팅 봇",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.loadFile(path.join(__dirname, "renderer", "index.html"));
  mainWindow.setMenuBarVisibility(false);
}

// ── IPC: 파일 다이얼로그 ────────────────────────────────────
ipcMain.handle("dialog:openFile", async (_, filters) => {
  const { canceled, filePaths } = await dialog.showOpenDialog(mainWindow, {
    properties: ["openFile"],
    filters: filters || [{ name: "All Files", extensions: ["*"] }],
  });
  return canceled ? null : filePaths[0];
});

ipcMain.handle("dialog:saveFile", async (_, defaultName, filters) => {
  const { canceled, filePath } = await dialog.showSaveDialog(mainWindow, {
    defaultPath: defaultName || "report.xlsx",
    filters: filters || [{ name: "All Files", extensions: ["*"] }],
  });
  return canceled ? null : filePath;
});

ipcMain.handle("fs:saveBuffer", async (_, filePath, buffer) => {
  const { writeFile } = require("fs").promises;
  await writeFile(filePath, Buffer.from(buffer));
  return true;
});

// ── 앱 시작 ────────────────────────────────────────────────
app.whenReady().then(async () => {
  startPythonServer();
  try {
    await waitForServer();
  } catch (e) {
    console.error(e.message);
  }
  createWindow();
});

app.on("window-all-closed", () => {
  killPythonProcess();
  app.quit();
});

app.on("before-quit", () => {
  killPythonProcess();
});
