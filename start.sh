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

# 3. Build React frontend (rebuild if source is newer than build)
NEEDS_BUILD=0
if [ ! -d "frontend/build" ]; then
    NEEDS_BUILD=1
elif [ -n "$(find frontend/src -newer frontend/build/index.html -name '*.js' 2>/dev/null)" ]; then
    NEEDS_BUILD=1
fi

if [ "$NEEDS_BUILD" = "1" ]; then
    echo "[3/4] Baue React-Frontend..."
    cd frontend
    if [ ! -d "node_modules" ]; then
        npm install --silent 2>/dev/null || npm install
    fi
    npm run build 2>&1 | tail -1
    cd "$SCRIPT_DIR"
else
    echo "[3/4] Frontend bereits gebaut (aktuell)."
fi

# 4. Find free port (AirPlay on macOS uses 5000)
PORT=5000
if command -v lsof &>/dev/null; then
    if lsof -i :5000 &>/dev/null 2>&1; then
        PORT=5050
        echo "  Hinweis: Port 5000 belegt (vermutlich AirPlay). Verwende Port $PORT."
    fi
fi

echo "[4/4] Starte Server auf http://localhost:$PORT ..."
echo ""

# Open browser (works on Linux, macOS, WSL)
(sleep 2 && {
    if command -v open &>/dev/null; then
        open "http://localhost:$PORT"
    elif command -v xdg-open &>/dev/null; then
        xdg-open "http://localhost:$PORT"
    elif command -v wslview &>/dev/null; then
        wslview "http://localhost:$PORT"
    fi
}) &

# Run with gunicorn (production WSGI server)
gunicorn \
    --bind "127.0.0.1:$PORT" \
    --workers 2 \
    --timeout 600 \
    --access-logfile - \
    "app.main:create_app()"
