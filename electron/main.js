const { app, BrowserWindow, dialog, Menu, shell } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');
const net = require('net');
const fs = require('fs');

let mainWindow = null;
let backendProcess = null;
let serverPort = null;

const IS_PACKAGED = app.isPackaged;
const PROJECT_ROOT = path.join(__dirname, '..');

// Single-instance lock: focus existing window instead of opening a second one
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });
}

// ---------------------------------------------------------------------------
// Find a free port
// ---------------------------------------------------------------------------
function findFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.listen(0, '127.0.0.1', () => {
      const port = server.address().port;
      server.close(() => resolve(port));
    });
    server.on('error', reject);
  });
}

// ---------------------------------------------------------------------------
// Wait until Flask is ready
// ---------------------------------------------------------------------------
function waitForServer(port, retries = 60, delay = 500) {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    const check = () => {
      const req = http.get(`http://127.0.0.1:${port}/api/documents`, (res) => {
        resolve();
      });
      req.on('error', () => {
        attempts++;
        if (attempts >= retries) {
          reject(new Error('Server did not start in time'));
        } else {
          setTimeout(check, delay);
        }
      });
      req.setTimeout(2000, () => {
        req.destroy();
        attempts++;
        if (attempts >= retries) {
          reject(new Error('Server did not start in time'));
        } else {
          setTimeout(check, delay);
        }
      });
    };
    check();
  });
}

// ---------------------------------------------------------------------------
// Start the backend (PyInstaller binary in production, gunicorn in dev)
// ---------------------------------------------------------------------------
async function startBackend() {
  serverPort = await findFreePort();

  let backendCmd, backendArgs, backendEnv, backendCwd;

  if (IS_PACKAGED) {
    const userData = app.getPath('userData');
    const frontendDir = path.join(process.resourcesPath, 'frontend', 'build');

    if (!fs.existsSync(userData)) {
      fs.mkdirSync(userData, { recursive: true });
    }

    backendCmd = path.join(process.resourcesPath, 'mycompare-backend', 'mycompare-backend');
    backendArgs = ['--port', String(serverPort)];
    backendCwd = userData;
    backendEnv = {
      ...process.env,
      FRONTEND_DIR: frontendDir,
      MYCOMPARE_DATA_DIR: userData,
    };
  } else {
    // Development: use gunicorn from venv
    const venvPython = path.join(PROJECT_ROOT, 'venv', 'bin', 'python');
    const gunicorn = path.join(PROJECT_ROOT, 'venv', 'bin', 'gunicorn');

    if (!fs.existsSync(venvPython)) {
      dialog.showErrorBox(
        'MyCompare — Fehler',
        'Python Virtual Environment nicht gefunden.\n\n' +
        'Bitte zuerst im Terminal ausführen:\n' +
        `cd "${PROJECT_ROOT}" && bash start.sh\n\n` +
        'Danach die App erneut starten.'
      );
      app.quit();
      return;
    }

    backendCmd = gunicorn;
    backendArgs = [
      '--bind', `127.0.0.1:${serverPort}`,
      '--workers', '2',
      '--timeout', '3600',
      '--access-logfile', '-',
      'app.main:create_app()',
    ];
    backendCwd = PROJECT_ROOT;
    backendEnv = {
      ...process.env,
      PATH: path.join(PROJECT_ROOT, 'venv', 'bin') + ':' + process.env.PATH,
      VIRTUAL_ENV: path.join(PROJECT_ROOT, 'venv'),
    };
  }

  backendProcess = spawn(backendCmd, backendArgs, {
    cwd: backendCwd,
    env: backendEnv,
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  backendProcess.stdout.on('data', (data) => {
    console.log(`[backend] ${data.toString().trim()}`);
  });

  backendProcess.stderr.on('data', (data) => {
    console.log(`[backend] ${data.toString().trim()}`);
  });

  backendProcess.on('error', (err) => {
    console.error('Failed to start backend:', err);
    dialog.showErrorBox(
      'MyCompare — Fehler',
      `Backend konnte nicht gestartet werden:\n${err.message}`
    );
    app.quit();
  });

  backendProcess.on('exit', (code, signal) => {
    console.log(`Backend exited with code ${code}, signal ${signal}`);
    backendProcess = null;
  });

  await waitForServer(serverPort);
}

// ---------------------------------------------------------------------------
// Kill the backend on quit
// ---------------------------------------------------------------------------
function stopBackend() {
  if (backendProcess) {
    console.log('Stopping backend...');
    backendProcess.kill('SIGTERM');
    setTimeout(() => {
      if (backendProcess) {
        backendProcess.kill('SIGKILL');
      }
    }, 5000);
  }
}

// ---------------------------------------------------------------------------
// Create the main application window
// ---------------------------------------------------------------------------
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    title: 'MyCompare',
    titleBarStyle: 'hiddenInset',
    trafficLightPosition: { x: 15, y: 15 },
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
    show: false,
  });

  mainWindow.loadURL(`http://127.0.0.1:${serverPort}`);

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });
}

// ---------------------------------------------------------------------------
// macOS application menu (vollständig lokalisiert)
// ---------------------------------------------------------------------------
function createMenu() {
  const template = [
    {
      label: 'MyCompare',
      submenu: [
        { role: 'about', label: 'Über MyCompare' },
        { type: 'separator' },
        { role: 'hide', label: 'MyCompare ausblenden' },
        { role: 'hideOthers', label: 'Andere ausblenden' },
        { role: 'unhide', label: 'Alle einblenden' },
        { type: 'separator' },
        { role: 'quit', label: 'MyCompare beenden' },
      ],
    },
    {
      label: 'Bearbeiten',
      submenu: [
        { role: 'undo', label: 'Widerrufen' },
        { role: 'redo', label: 'Wiederholen' },
        { type: 'separator' },
        { role: 'cut', label: 'Ausschneiden' },
        { role: 'copy', label: 'Kopieren' },
        { role: 'paste', label: 'Einsetzen' },
        { role: 'selectAll', label: 'Alles auswählen' },
      ],
    },
    {
      label: 'Ansicht',
      submenu: [
        { role: 'reload', label: 'Neu laden' },
        { role: 'forceReload', label: 'Erzwungenes Neuladen' },
        { type: 'separator' },
        { role: 'resetZoom', label: 'Originalgröße' },
        { role: 'zoomIn', label: 'Vergrößern' },
        { role: 'zoomOut', label: 'Verkleinern' },
        { type: 'separator' },
        { role: 'togglefullscreen', label: 'Vollbild' },
      ],
    },
    {
      label: 'Fenster',
      submenu: [
        { role: 'minimize', label: 'Minimieren' },
        { role: 'zoom', label: 'Zoomen' },
        { type: 'separator' },
        { role: 'front', label: 'Alle nach vorne bringen' },
      ],
    },
  ];

  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

// ---------------------------------------------------------------------------
// App lifecycle
// ---------------------------------------------------------------------------
app.on('ready', async () => {
  app.setAboutPanelOptions({
    applicationName: 'MyCompare',
    applicationVersion: app.getVersion(),
    credits: 'Dr. Raoul Müller — Indemnis',
    copyright: '© 2025 Indemnis',
  });

  createMenu();

  try {
    await startBackend();
    createWindow();
  } catch (err) {
    dialog.showErrorBox(
      'MyCompare — Fehler',
      `Server konnte nicht gestartet werden:\n${err.message}` +
      (IS_PACKAGED ? '' : `\n\nBitte stelle sicher, dass alle Abhängigkeiten installiert sind:\ncd "${PROJECT_ROOT}" && bash start.sh`)
    );
    app.quit();
  }
});

app.on('window-all-closed', () => {
  stopBackend();
  app.quit();
});

app.on('before-quit', () => {
  stopBackend();
});

app.on('activate', () => {
  if (mainWindow === null && serverPort) {
    createWindow();
  }
});
