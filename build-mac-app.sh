#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================="
echo "  MyCompare — macOS App bauen"
echo "========================================="
echo ""

# 1. Ensure Python venv exists
if [ ! -d "venv" ]; then
    echo "[1/6] Erstelle Python Virtual Environment..."
    python3 -m venv venv
else
    echo "[1/6] Virtual Environment vorhanden."
fi

source venv/bin/activate
echo "[2/6] Installiere Python-Abhängigkeiten..."
pip install -q -r requirements.txt

# 2. Build React frontend
echo "[3/6] Baue React-Frontend..."
cd frontend
if [ ! -d "node_modules" ]; then
    npm install
fi
npm run build 2>&1 | tail -3
cd "$SCRIPT_DIR"

# 3. Build Python backend with PyInstaller
echo "[4/6] Baue Python-Backend (PyInstaller)..."
bash electron/build-python.sh

# 4. Generate icon (if not already done)
echo "[5/6] Erstelle App-Icon..."
cd electron
if [ ! -f "icon.icns" ]; then
    bash generate-icon.sh 2>/dev/null || echo "  Icon-Generierung übersprungen (kann später auf macOS erstellt werden)"
fi

# 5. Install Electron deps & build
echo "[6/6] Baue Electron App..."
if [ ! -d "node_modules" ]; then
    npm install
fi

npm run dist

cd "$SCRIPT_DIR"

echo ""
echo "========================================="
echo "  Fertig! Die App liegt in:"
echo "  electron/dist/"
echo "========================================="
echo ""
echo "  Zum Installieren:"
echo "  1. electron/dist/MyCompare-*.dmg öffnen"
echo "  2. MyCompare.app nach /Applications ziehen"
echo "  3. Beim ersten Start: Rechtsklick → Öffnen"
echo "     (umgeht Gatekeeper für unsignierte Apps)"
echo ""
echo "  Daten werden gespeichert in:"
echo "  ~/Library/Application Support/MyCompare/"
echo ""
