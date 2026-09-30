@echo off
REM ============================================================
REM  ScriptureSound QC Beta - build the fast-start Windows app folder
REM  Just double-click this file (or run it in a terminal).
REM  Requires: Python 3.12 installed with "Add to PATH" ticked.
REM
REM  App Icon:
REM    Place "icon.ico" next to this script for a custom app icon.
REM    You can convert PNG to ICO at: https://convertio.co/png-ico/
REM    (use 256x256 or larger PNG for best quality)
REM
REM  ffmpeg:
REM    Place "ffmpeg.exe" next to this script to bundle it inside the app.
REM
REM  OUTPUT: dist-beta\ScriptureSoundQC\ (fast-start installed app)
REM ============================================================
setlocal
cd /d "%~dp0"

echo.
echo ======================================
echo   ScriptureSound QC Beta - Build
echo ======================================
echo.

REM 1) Prefer the project's isolated Python, then fall back to PATH
set "BUILD_PYTHON="
if exist "%~dp0.venv\Scripts\python.exe" set "BUILD_PYTHON=%~dp0.venv\Scripts\python.exe"
if not defined BUILD_PYTHON (
  where python >nul 2>nul
  if not errorlevel 1 set "BUILD_PYTHON=python"
)
if not defined BUILD_PYTHON (
  echo [ERROR] Python was not found on PATH.
  echo.
  echo Install Python from https://www.python.org/downloads/
  echo and tick "Add Python to PATH" during setup, then run this again.
  echo.
  if not defined CI pause
  exit /b 1
)

echo Python version:
"%BUILD_PYTHON%" --version
"%BUILD_PYTHON%" -c "import sys; assert sys.version_info[:2] == (3, 12), 'Python 3.12 is required'"
if errorlevel 1 exit /b 1
echo.

REM 2) Install build dependencies
echo [1/3] Installing dependencies...
REM Build in a fresh environment so previously installed GPU wheels cannot leak in.
if exist ".windows-build-venv" rmdir /s /q ".windows-build-venv"
"%BUILD_PYTHON%" -m venv .windows-build-venv
if errorlevel 1 exit /b 1
set "BUILD_PYTHON=%~dp0.windows-build-venv\Scripts\python.exe"
"%BUILD_PYTHON%" -m pip install --upgrade pip >nul 2>nul
"%BUILD_PYTHON%" -m pip install torch --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 exit /b 1
"%BUILD_PYTHON%" -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (
  echo.
  echo [ERROR] Failed to install dependencies.
  echo Check your internet connection and try again.
  echo.
  if not defined CI pause
  exit /b 1
)
echo       Done.
echo.

REM 3) Check for optional files
if exist "%~dp0icon.ico" (
  echo [OK] icon.ico found - will use custom app icon.
) else (
  echo [--] No icon.ico - will use default icon.
)
if exist "%~dp0ffmpeg.exe" (
  echo [OK] ffmpeg.exe found - will bundle inside app.
) else (
  echo [ERROR] Add ffmpeg.exe before building the full offline installer.
  exit /b 1
)
echo.

REM 4) Clean old build
echo [2/3] Cleaning old build files...
if exist "dist-beta\ScriptureSoundQC" rmdir /s /q "dist-beta\ScriptureSoundQC"
if exist "dist-beta\ScriptureSoundQC.exe" del "dist-beta\ScriptureSoundQC.exe"
if exist "build-beta\ScriptureSoundQC" rmdir /s /q "build-beta\ScriptureSoundQC"
echo       Done.
echo.

REM 5) Build using spec file (installed folder, bundles the AI runtime)
echo [3/3] Building ScriptureSoundQC.exe...
echo       (This takes 2-5 minutes, please wait...)
echo.
"%BUILD_PYTHON%" -m PyInstaller --noconfirm --distpath dist-beta --workpath build-beta ScriptureSoundQC.spec

if errorlevel 1 (
  echo.
  echo ==========================================
  echo   BUILD FAILED! See error messages above.
  echo ==========================================
  echo.
  echo Common fixes:
  echo   - Make sure PySide6 is installed: pip install PySide6
  echo   - Delete "build" and "dist" folders and try again
  echo   - Try: pip install --force-reinstall pyinstaller
  echo.
  if not defined CI pause
  exit /b 1
)

echo.
"%BUILD_PYTHON%" -m pip check
if errorlevel 1 exit /b 1
"%BUILD_PYTHON%" -m pip freeze > "dist-beta\ScriptureSoundQC-Windows-dependencies.txt"
set "QT_QPA_PLATFORM=offscreen"
set "BAC_SELF_TEST_OUTPUT=%CD%\dist-beta\packaging-self-test.txt"
start /wait "" "dist-beta\ScriptureSoundQC\ScriptureSoundQC.exe" --packaging-self-test
if errorlevel 1 (
  if exist "%BAC_SELF_TEST_OUTPUT%" type "%BAC_SELF_TEST_OUTPUT%"
  exit /b 1
)
echo ==========================================
echo   BUILD SUCCESSFUL!
echo ==========================================
echo.
echo   Your app:  dist-beta\ScriptureSoundQC\ScriptureSoundQC.exe
echo.
echo   Double-click it to run.
echo   Distribute the Setup installer; it packages this entire folder.
echo.
echo   NOTE: The .exe includes the Whisper runtime, but not model weights.
echo   End users download and verify a multilingual model from:
echo     Processing ^> AI Model Packs
echo   Python and command-line tools are not required for end users.
echo.
if not defined CI pause
endlocal
