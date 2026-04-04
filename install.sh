#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════
#  MyCompare — One-Click Installer
#  Dokumentenvergleich für Juristen
# ═══════════════════════════════════════════════════════
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
echo -e "${BLUE}   MyCompare — Installer${NC}"
echo -e "${BLUE}   Dokumentenvergleich mit Verifikation${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ─── CHECK PREREQUISITES ───
echo -e "${YELLOW}[1/6]${NC} Prüfe Voraussetzungen..."

# Python 3
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PY_VER=$(python --version 2>&1 | grep -oP '\d+' | head -1)
    if [ "$PY_VER" -ge 3 ]; then
        PYTHON=python
    else
        echo -e "${RED}FEHLER: Python 3 wird benötigt. Bitte installieren: https://www.python.org/downloads/${NC}"
        exit 1
    fi
else
    echo -e "${RED}FEHLER: Python 3 nicht gefunden.${NC}"
    echo ""
    echo "Installation:"
    echo "  macOS:   brew install python3"
    echo "  Ubuntu:  sudo apt install python3 python3-venv python3-pip"
    echo "  Windows: https://www.python.org/downloads/"
    exit 1
fi
echo -e "  Python: ${GREEN}$($PYTHON --version)${NC}"

# Node.js
if command -v node &>/dev/null; then
    echo -e "  Node.js: ${GREEN}$(node --version)${NC}"
else
    echo -e "${RED}FEHLER: Node.js nicht gefunden.${NC}"
    echo ""
    echo "Installation:"
    echo "  macOS:   brew install node"
    echo "  Ubuntu:  sudo apt install nodejs npm"
    echo "  Windows: https://nodejs.org/"
    exit 1
fi

# npm
if ! command -v npm &>/dev/null; then
    echo -e "${RED}FEHLER: npm nicht gefunden. Bitte Node.js neu installieren.${NC}"
    exit 1
fi
echo -e "  npm: ${GREEN}$(npm --version)${NC}"

# ─── PYTHON VIRTUAL ENVIRONMENT ───
echo ""
echo -e "${YELLOW}[2/6]${NC} Erstelle Python Virtual Environment..."
if [ ! -d "venv" ]; then
    $PYTHON -m venv venv
    echo -e "  ${GREEN}Erstellt.${NC}"
else
    echo -e "  ${GREEN}Bereits vorhanden.${NC}"
fi

# Activate venv
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
elif [ -f "venv/Scripts/activate" ]; then
    source venv/Scripts/activate
fi

# ─── PYTHON DEPENDENCIES ───
echo ""
echo -e "${YELLOW}[3/6]${NC} Installiere Python-Abhängigkeiten..."
pip install -q --upgrade pip 2>/dev/null || true
pip install -q -r requirements.txt
echo -e "  ${GREEN}Installiert.${NC}"

# ─── NODE DEPENDENCIES ───
echo ""
echo -e "${YELLOW}[4/6]${NC} Installiere Frontend-Abhängigkeiten..."
cd frontend
npm install --silent 2>/dev/null || npm install
echo -e "  ${GREEN}Installiert.${NC}"

# ─── BUILD FRONTEND ───
echo ""
echo -e "${YELLOW}[5/6]${NC} Baue Frontend..."
npm run build 2>&1 | tail -1
cd "$SCRIPT_DIR"
echo -e "  ${GREEN}Build erfolgreich.${NC}"

# ─── CREATE LAUNCHER SCRIPT ───
echo ""
echo -e "${YELLOW}[6/6]${NC} Erstelle Starter..."

# Create platform-specific launcher
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
    # Windows .bat file
    cat > MyCompare.bat << 'WINEOF'
@echo off
title MyCompare - Dokumentenvergleich
echo ========================================
echo   MyCompare - Dokumentenvergleich
echo ========================================
echo.
cd /d "%~dp0"
call venv\Scripts\activate.bat
echo Starte Server auf http://localhost:5000 ...
start http://localhost:5000
python -m app.main
WINEOF
    echo -e "  ${GREEN}MyCompare.bat erstellt${NC}"
    LAUNCHER="MyCompare.bat"
else
    chmod +x start.sh
    LAUNCHER="./start.sh"
fi

# ─── CREATE DESKTOP SHORTCUT (Linux) ───
if [[ "$OSTYPE" == "linux-gnu"* ]] && [ -d "$HOME/Desktop" ]; then
    cat > "$HOME/Desktop/MyCompare.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=MyCompare
Comment=Dokumentenvergleich mit Verifikation
Exec=bash -c 'cd "$SCRIPT_DIR" && ./start.sh'
Icon=accessories-text-editor
Terminal=true
Categories=Office;
EOF
    chmod +x "$HOME/Desktop/MyCompare.desktop" 2>/dev/null || true
    echo -e "  ${GREEN}Desktop-Verknüpfung erstellt${NC}"
fi

# ─── DONE ───
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
echo -e "${GREEN}   Installation erfolgreich!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
echo ""
echo -e "  Starten mit: ${BLUE}${LAUNCHER}${NC}"
echo ""
echo -e "  Der Server läuft auf: ${BLUE}http://localhost:5000${NC}"
echo ""
echo -e "  Unterstützte Dateitypen: DOCX, XLSX, PPTX, PDF"
echo ""
read -p "Jetzt starten? (j/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Jj]$ ]]; then
    exec bash start.sh
fi
