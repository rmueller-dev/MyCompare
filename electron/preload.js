// Preload script — runs in renderer before web page loads.
// Currently minimal; can expose Electron APIs to the React app via
// contextBridge if needed in the future.

const { contextBridge } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  isElectron: true,
  platform: process.platform,
});
