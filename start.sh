#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================="
echo "  MyCompare — Dokumentenvergleich"
echo "========================================="
echo ""

# 1. Python virtual environment
if [ ! -d "venv" ]; then
    echo "[1/4] Erstelle Python Virtual Environment..."
    python3 -m venv venv
else
    echo "[1/4] Virtual Environment vorhanden."
fi

source venv/bin/activate

# 2. Python dependencies
echo "[2/4] Installiere Python-Abhängigkeiten..."
pip install -q -r requirements.txt

# 3. Build React frontend
echo "[3/4] Baue React-Frontend..."
cd frontend
if [ ! -d "node_modules" ]; then
    npm install --silent 2>/dev/null || npm install
fi
npm run build 2>&1 | tail -1
cd "$SCRIPT_DIR"

# 4. Start Flask server
echo "[4/4] Starte Server auf http://localhost:5000 ..."
echo ""

# Open browser (works on Linux, macOS, WSL)
(sleep 2 && {
    if command -v xdg-open &>/dev/null; then
        xdg-open http://localhost:5000
    elif command -v open &>/dev/null; then
        open http://localhost:5000
    elif command -v wslview &>/dev/null; then
        wslview http://localhost:5000
    fi
}) &

# Run Flask
python -m app.main
