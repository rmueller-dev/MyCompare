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
    echo "[1/5] Erstelle Python Virtual Environment..."
    python3 -m venv venv
else
    echo "[1/5] Virtual Environment vorhanden."
fi

source venv/bin/activate
echo "[2/5] Installiere Python-Abhängigkeiten..."
pip install -q -r requirements.txt

# 2. Build React frontend
echo "[3/5] Baue React-Frontend..."
cd frontend
if [ ! -d "node_modules" ]; then
    npm install
fi
npm run build 2>&1 | tail -3
cd "$SCRIPT_DIR"

# 3. Generate icon (if not already done)
echo "[4/5] Erstelle App-Icon..."
cd electron
if [ ! -f "icon.icns" ]; then
    bash generate-icon.sh 2>/dev/null || echo "  Icon-Generierung übersprungen (kann später auf macOS erstellt werden)"
fi

# 4. Install Electron deps & build
echo "[5/5] Baue Electron App..."
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
echo "  Zum Installieren: .dmg Datei öffnen und"
echo "  MyCompare.app nach /Applications ziehen."
echo ""
