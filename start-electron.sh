#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================="
echo "  MyCompare — Electron Desktop App"
echo "========================================="
echo ""

# 1. Ensure Python venv exists
if [ ! -d "venv" ]; then
    echo "[1/3] Erstelle Python Virtual Environment..."
    python3 -m venv venv
else
    echo "[1/3] Virtual Environment vorhanden."
fi

source venv/bin/activate
pip install -q -r requirements.txt

# 2. Build React frontend if needed
NEEDS_BUILD=0
if [ ! -d "frontend/build" ]; then
    NEEDS_BUILD=1
elif [ -n "$(find frontend/src -newer frontend/build/index.html -name '*.js' 2>/dev/null)" ]; then
    NEEDS_BUILD=1
fi

if [ "$NEEDS_BUILD" = "1" ]; then
    echo "[2/3] Baue React-Frontend..."
    cd frontend
    if [ ! -d "node_modules" ]; then
        npm install --silent 2>/dev/null || npm install
    fi
    npm run build 2>&1 | tail -1
    cd "$SCRIPT_DIR"
else
    echo "[2/3] Frontend bereits gebaut (aktuell)."
fi

# 3. Install Electron deps if needed & start
cd electron
if [ ! -d "node_modules" ]; then
    echo "[3/3] Installiere Electron..."
    npm install
else
    echo "[3/3] Electron vorhanden."
fi

echo ""
echo "Starte MyCompare Desktop App..."
echo ""

npx electron .
