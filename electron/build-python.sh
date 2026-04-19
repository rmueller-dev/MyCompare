#!/usr/bin/env bash
# Builds the Flask backend into a self-contained directory with PyInstaller.
# Output: dist/mycompare-backend/ (picked up by electron-builder as extraResources)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "--- PyInstaller: Aktiviere venv ---"
source venv/bin/activate

pip install -q pyinstaller

echo "--- PyInstaller: Bereinige alte Builds ---"
rm -rf dist/mycompare-backend build/mycompare-backend mycompare-backend.spec 2>/dev/null || true

echo "--- PyInstaller: Baue Backend-Binary ---"
pyinstaller \
  --onedir \
  --name mycompare-backend \
  --collect-all pdfplumber \
  --collect-all pdfminer \
  --collect-all openpyxl \
  --collect-all docx \
  --collect-all pptx \
  --collect-all PIL \
  --collect-all reportlab \
  --collect-all pytesseract \
  --hidden-import=sqlalchemy.dialects.sqlite \
  --hidden-import=flask_cors \
  --hidden-import=app \
  --hidden-import=app.main \
  --hidden-import=app.models \
  --hidden-import=app.routes \
  --hidden-import=app.ai_analysis \
  --hidden-import=app.diff_engine \
  --hidden-import=app.extractors \
  --hidden-import=app.image_diff \
  --hidden-import=werkzeug.serving \
  --hidden-import=werkzeug.debug \
  server.py

echo "--- PyInstaller: Fertig — dist/mycompare-backend/ ---"
