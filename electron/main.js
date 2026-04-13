const { app, BrowserWindow, dialog, Menu, shell } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');
const net = require('net');

// Keep references to prevent garbage collection
let mainWindow = null;
let backendProcess = null;
let serverPort = null;

// Path to the project root (one level up from electron/)
const PROJECT_ROOT = path.join(__dirname, '..');

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
// Start the Flask/gunicorn backend
// ---------------------------------------------------------------------------
async function startBackend() {
  serverPort = await findFreePort();

  const venvPython = path.join(PROJECT_ROOT, 'venv', 'bin', 'python');
  const gunicorn = path.join(PROJECT_ROOT, 'venv', 'bin', 'gunicorn');

  // Check if venv exists
  const fs = require('fs');
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

  // Start gunicorn
  backendProcess = spawn(gunicorn, [
    '--bind', `127.0.0.1:${serverPort}`,
    '--workers', '2',
    '--timeout', '3600',
    '--access-logfile', '-',
    'app.main:create_app()',
  ], {
    cwd: PROJECT_ROOT,
    env: {
      ...process.env,
      PATH: path.join(PROJECT_ROOT, 'venv', 'bin') + ':' + process.env.PATH,
      VIRTUAL_ENV: path.join(PROJECT_ROOT, 'venv'),
    },
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

  // Wait for the server to be ready
  await waitForServer(serverPort);
}

// ---------------------------------------------------------------------------
// Kill the backend on quit
// ---------------------------------------------------------------------------
function stopBackend() {
  if (backendProcess) {
    console.log('Stopping backend...');
    backendProcess.kill('SIGTERM');
    // Force kill after 5 seconds
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

  // Open external links in default browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });
}

// ---------------------------------------------------------------------------
// macOS application menu
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
  createMenu();

  try {
    await startBackend();
    createWindow();
  } catch (err) {
    dialog.showErrorBox(
      'MyCompare — Fehler',
      `Server konnte nicht gestartet werden:\n${err.message}\n\n` +
      'Bitte stelle sicher, dass alle Abhängigkeiten installiert sind:\n' +
      `cd "${PROJECT_ROOT}" && bash start.sh`
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
