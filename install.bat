@echo off
REM ═══════════════════════════════════════════════════════
REM  MyCompare — One-Click Installer (Windows)
REM  Dokumentenvergleich fuer Juristen
REM ═══════════════════════════════════════════════════════
title MyCompare Installer

echo.
echo ===============================================
echo   MyCompare - Installer
echo   Dokumentenvergleich mit Verifikation
echo ===============================================
echo.

cd /d "%~dp0"

REM ─── CHECK PYTHON ───
echo [1/6] Pruefe Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo FEHLER: Python 3 nicht gefunden.
    echo Bitte installieren: https://www.python.org/downloads/
    echo Wichtig: Bei der Installation "Add Python to PATH" aktivieren!
    pause
    exit /b 1
)
python --version

REM ─── CHECK NODE ───
echo [2/6] Pruefe Node.js...
node --version >nul 2>&1
if errorlevel 1 (
    echo FEHLER: Node.js nicht gefunden.
    echo Bitte installieren: https://nodejs.org/
    pause
    exit /b 1
)
node --version

REM ─── PYTHON VENV ───
echo.
echo [3/6] Erstelle Python Virtual Environment...
if not exist "venv" (
    python -m venv venv
)
call venv\Scripts\activate.bat

REM ─── PYTHON DEPS ───
echo.
echo [4/6] Installiere Python-Abhaengigkeiten...
pip install -q --upgrade pip 2>nul
pip install -q -r requirements.txt

REM ─── NODE DEPS + BUILD ───
echo.
echo [5/6] Installiere und baue Frontend...
cd frontend
call npm install --silent 2>nul
call npm run build
cd ..

REM ─── CREATE LAUNCHER ───
echo.
echo [6/6] Erstelle Starter...

(
echo @echo off
echo title MyCompare - Dokumentenvergleich
echo cd /d "%%~dp0"
echo call venv\Scripts\activate.bat
echo echo Starte MyCompare auf http://localhost:5000 ...
echo start http://localhost:5000
echo python -m app.main
) > MyCompare.bat

REM ─── CREATE DESKTOP SHORTCUT ───
if exist "%USERPROFILE%\Desktop" (
    powershell -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%USERPROFILE%\Desktop\MyCompare.lnk'); $sc.TargetPath = '%cd%\MyCompare.bat'; $sc.WorkingDirectory = '%cd%'; $sc.Description = 'Dokumentenvergleich mit Verifikation'; $sc.Save()"
    echo Desktop-Verknuepfung erstellt.
)

echo.
echo ===============================================
echo   Installation erfolgreich!
echo ===============================================
echo.
echo   Starten mit: MyCompare.bat
echo   Oder ueber die Desktop-Verknuepfung
echo.
echo   Server: http://localhost:5000
echo   Dateitypen: DOCX, XLSX, PPTX, PDF
echo.

set /p STARTIT="Jetzt starten? (j/n): "
if /i "%STARTIT%"=="j" (
    call MyCompare.bat
)

pause
