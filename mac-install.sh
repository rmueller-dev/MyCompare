#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  MyCompare — TRUE One-Click Install & Start für macOS
#
#  Dieses Script macht ALLES automatisch:
#  - Installiert Homebrew (falls nötig)
#  - Installiert Python 3 (falls nötig)
#  - Installiert Node.js (falls nötig)
#  - Löst den Port-5000-Konflikt mit AirPlay (macOS Monterey+)
#  - Erstellt venv, installiert deps, baut Frontend
#  - Erstellt eine macOS-App im Applications-Ordner
#  - Startet den Server und öffnet den Browser
#
#  Benutzung: Doppelklick auf diese Datei im Finder
#             oder im Terminal:  ./mac-install.sh
# ═══════════════════════════════════════════════════════════════
set -e

# ─── FARBEN ───
R='\033[0;31m'
G='\033[0;32m'
Y='\033[1;33m'
B='\033[0;34m'
N='\033[0m'

clear
echo ""
echo -e "${B}╔═══════════════════════════════════════════════╗${N}"
echo -e "${B}║   MyCompare — Dokumentenvergleich             ║${N}"
echo -e "${B}║   Automatische Installation für macOS         ║${N}"
echo -e "${B}╚═══════════════════════════════════════════════╝${N}"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

STEP=1
TOTAL=7

progress() {
    echo ""
    echo -e "${Y}[$STEP/$TOTAL]${N} $1"
    STEP=$((STEP + 1))
}

ok() {
    echo -e "  ${G}✓ $1${N}"
}

# ═══════════════════════════════════════════════════════
#  STEP 1: Homebrew
# ═══════════════════════════════════════════════════════
progress "Prüfe Homebrew..."

if command -v brew &>/dev/null; then
    ok "Homebrew vorhanden ($(brew --version | head -1))"
else
    echo -e "  ${Y}Homebrew wird installiert...${N}"
    echo "  (Apple wird ggf. nach Ihrem Passwort fragen für die Xcode Command Line Tools)"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

    # Add brew to PATH for Apple Silicon and Intel
    if [ -f "/opt/homebrew/bin/brew" ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    elif [ -f "/usr/local/bin/brew" ]; then
        eval "$(/usr/local/bin/brew shellenv)"
    fi
    ok "Homebrew installiert"
fi

# ═══════════════════════════════════════════════════════
#  STEP 2: Python 3
# ═══════════════════════════════════════════════════════
progress "Prüfe Python 3..."

if command -v python3 &>/dev/null; then
    ok "Python vorhanden ($(python3 --version))"
else
    echo -e "  ${Y}Python 3 wird installiert...${N}"
    brew install python3
    ok "Python 3 installiert"
fi

# ═══════════════════════════════════════════════════════
#  STEP 3: Node.js
# ═══════════════════════════════════════════════════════
progress "Prüfe Node.js..."

if command -v node &>/dev/null; then
    ok "Node.js vorhanden ($(node --version))"
else
    echo -e "  ${Y}Node.js wird installiert...${N}"
    brew install node
    ok "Node.js installiert"
fi

# ═══════════════════════════════════════════════════════
#  STEP 4: Python Virtual Environment + Abhängigkeiten
# ═══════════════════════════════════════════════════════
progress "Richte Python-Umgebung ein..."

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -q --upgrade pip 2>/dev/null || true
pip install -q -r requirements.txt
ok "Python-Abhängigkeiten installiert"

# ═══════════════════════════════════════════════════════
#  STEP 5: Frontend bauen
# ═══════════════════════════════════════════════════════
progress "Baue Frontend..."

cd frontend
npm install --silent 2>/dev/null || npm install
npm run build 2>&1 | tail -1
cd "$SCRIPT_DIR"
ok "Frontend gebaut"

# ═══════════════════════════════════════════════════════
#  STEP 6: macOS App erstellen
# ═══════════════════════════════════════════════════════
progress "Erstelle macOS-App..."

APP_DIR="$HOME/Applications/MyCompare.app"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

# App launcher script
cat > "$APP_DIR/Contents/MacOS/MyCompare" << LAUNCHER
#!/usr/bin/env bash
cd "$SCRIPT_DIR"
source venv/bin/activate

# Prüfe ob Port 5000 frei ist, sonst Port 5050
PORT=5000
if lsof -i :5000 &>/dev/null; then
    PORT=5050
fi

# Browser öffnen nach kurzer Wartezeit
(sleep 2 && open "http://localhost:\$PORT") &

# Server starten
python -c "
from app.main import create_app
app = create_app()
app.run(debug=False, port=\$PORT, host='127.0.0.1')
"
LAUNCHER
chmod +x "$APP_DIR/Contents/MacOS/MyCompare"

# Info.plist
cat > "$APP_DIR/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>MyCompare</string>
    <key>CFBundleDisplayName</key>
    <string>MyCompare — Dokumentenvergleich</string>
    <key>CFBundleIdentifier</key>
    <string>de.mycompare.app</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleExecutable</key>
    <string>MyCompare</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.15</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
PLIST

# App icon (simple document icon via Python)
python3 - << 'ICONPY'
import subprocess, tempfile, os

# Create a simple SVG icon
svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
  <rect x="30" y="10" width="196" height="236" rx="15" fill="#2563eb" />
  <rect x="45" y="25" width="166" height="206" rx="10" fill="white" />
  <rect x="65" y="55" width="80" height="8" rx="4" fill="#2563eb" opacity="0.3"/>
  <rect x="65" y="75" width="126" height="6" rx="3" fill="#e5e7eb"/>
  <rect x="65" y="90" width="126" height="6" rx="3" fill="#e5e7eb"/>
  <rect x="65" y="105" width="100" height="6" rx="3" fill="#e5e7eb"/>
  <rect x="65" y="125" width="126" height="6" rx="3" fill="#fca5a5"/>
  <rect x="65" y="140" width="126" height="6" rx="3" fill="#86efac"/>
  <rect x="65" y="160" width="126" height="6" rx="3" fill="#e5e7eb"/>
  <rect x="65" y="175" width="80" height="6" rx="3" fill="#e5e7eb"/>
  <circle cx="190" cy="190" r="35" fill="#16a34a"/>
  <path d="M175 190 l10 10 l20-20" stroke="white" stroke-width="5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
</svg>'''

tmpsvg = tempfile.mktemp(suffix='.svg')
with open(tmpsvg, 'w') as f:
    f.write(svg)

# Try to convert SVG to icns via sips (built into macOS)
tmppng = tempfile.mktemp(suffix='.png')
try:
    # Use built-in qlmanage or Python to create PNG
    from xml.etree import ElementTree
    # Simple fallback - just create iconset directory
    iconset = os.path.expanduser('~/Applications/MyCompare.app/Contents/Resources/AppIcon.iconset')
    os.makedirs(iconset, exist_ok=True)

    # Try using rsvg-convert or just skip icon if not available
    for tool in ['rsvg-convert', '/opt/homebrew/bin/rsvg-convert']:
        try:
            for size in [16, 32, 64, 128, 256, 512]:
                outpng = os.path.join(iconset, f'icon_{size}x{size}.png')
                subprocess.run([tool, '-w', str(size), '-h', str(size), tmpsvg, '-o', outpng],
                             check=True, capture_output=True)
            subprocess.run(['iconutil', '-c', 'icns', iconset, '-o',
                          os.path.expanduser('~/Applications/MyCompare.app/Contents/Resources/AppIcon.icns')],
                         check=True, capture_output=True)
            break
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
except Exception:
    pass  # Icon is optional
finally:
    for f in [tmpsvg, tmppng]:
        try: os.unlink(f)
        except: pass
ICONPY

ok "MyCompare.app erstellt in ~/Applications/"

# ═══════════════════════════════════════════════════════
#  STEP 7: Starten
# ═══════════════════════════════════════════════════════
progress "Starte MyCompare..."

echo ""
echo -e "${G}╔═══════════════════════════════════════════════╗${N}"
echo -e "${G}║   Installation erfolgreich!                   ║${N}"
echo -e "${G}╚═══════════════════════════════════════════════╝${N}"
echo ""
echo -e "  ${B}Starten:${N}"
echo -e "    • Doppelklick auf ${B}MyCompare${N} in ~/Applications"
echo -e "    • Oder im Terminal: ${B}./start.sh${N}"
echo ""
echo -e "  ${B}Dateitypen:${N} DOCX, XLSX, PPTX, PDF"
echo ""

# Port 5000 check (AirPlay Receiver on macOS Monterey+)
PORT=5000
if lsof -i :5000 &>/dev/null 2>&1; then
    echo -e "  ${Y}Hinweis: Port 5000 ist belegt (vermutlich AirPlay).${N}"
    echo -e "  ${Y}Verwende stattdessen Port 5050.${N}"
    PORT=5050
fi

# Open browser + start server
(sleep 2 && open "http://localhost:$PORT") &

echo -e "  Server startet auf ${B}http://localhost:$PORT${N} ..."
echo ""

python -c "
from app.main import create_app
app = create_app()
app.run(debug=False, port=$PORT, host='127.0.0.1')
"
