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

// Path to the bundled backend binary
function getBackendBinary() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'backend', 'mycompare-backend');
  }
  return path.join(PROJECT_ROOT, 'dist', 'mycompare-backend', 'mycompare-backend');
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
// Start the bundled backend binary
// ---------------------------------------------------------------------------
async function startBackend() {
  serverPort = await findFreePort();

  const backendBin = getBackendBinary();
  const fs = require('fs');
  if (!fs.existsSync(backendBin)) {
    dialog.showErrorBox(
      'MyCompare — Fehler',
      `Backend-Binary nicht gefunden:\n${backendBin}\n\n` +
      'Bitte neu bauen: cd <repo> && bash build-mac-app.sh'
    );
    app.quit();
    return;
  }

  backendProcess = spawn(backendBin, ['--port', String(serverPort), '--host', '127.0.0.1'], {
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
      'Bitte das App-Bundle neu installieren oder support@mycompare.app kontaktieren.'
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
