@echo off
REM ============================================================
REM  ScriptureSound QC v1.5 - build a standalone Windows .exe
REM  Just double-click this file (or run it in a terminal).
REM  Requires: Python 3.9+ installed with "Add to PATH" ticked.
REM
REM  App Icon:
REM    Place "icon.ico" next to this script for a custom app icon.
REM    You can convert PNG to ICO at: https://convertio.co/png-ico/
REM    (use 256x256 or larger PNG for best quality)
REM ============================================================
setlocal

echo.
echo === ScriptureSound QC v1.5 - Windows build ===
echo.

REM 1) Make sure Python is available
where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python was not found on PATH.
  echo Install Python 3.9+ from https://www.python.org/downloads/
  echo and tick "Add Python to PATH" during setup, then run this again.
  pause
  exit /b 1
)

echo Python found:
python --version
echo.

REM 2) Install the build dependencies
echo Installing dependencies (first run may take a few minutes)...
python -m pip install --upgrade pip
python -m pip install PySide6 PyMuPDF pyinstaller
if errorlevel 1 (
  echo [ERROR] Failed to install dependencies. Check your internet connection.
  pause
  exit /b 1
)
echo.
echo Dependencies installed.
echo.

REM 3) Icon
set ICON_ARG=
if exist "%~dp0icon.ico" (
  echo Found icon.ico - using custom app icon.
  set ICON_ARG=--icon "%~dp0icon.ico"
) else (
  echo [NOTE] No icon.ico found. Place "icon.ico" next to this script for a custom icon.
)

REM 4) If an ffmpeg.exe is sitting in this folder, bundle it INSIDE the app
set FFMPEG_ARG=
if exist "%~dp0ffmpeg.exe" (
  echo Found ffmpeg.exe - it will be bundled inside the app.
  set FFMPEG_ARG=--add-binary "%~dp0ffmpeg.exe;."
) else (
  echo [NOTE] No ffmpeg.exe found. Loudness checks will need ffmpeg installed separately.
)

echo.
echo Building ScriptureSoundQC.exe ...
echo (This may take 3-10 minutes, please wait...)
echo.

REM 5) Build as a FOLDER (more reliable than --onefile for PySide6 apps)
pyinstaller --noconfirm --clean --windowed ^
  --name "ScriptureSoundQC" ^
  %ICON_ARG% ^
  %FFMPEG_ARG% ^
  --add-data "engine;engine" ^
  --add-data "gui;gui" ^
  --add-data "assets;assets" ^
  --hidden-import "engine.config" ^
  --hidden-import "engine.checker" ^
  --hidden-import "engine.bible_db" ^
  --hidden-import "engine.loudness" ^
  --hidden-import "engine.silence" ^
  --hidden-import "engine.wavio" ^
  --hidden-import "engine.wav_markers" ^
  --hidden-import "engine.waveform" ^
  --hidden-import "engine.pdf_parser" ^
  --hidden-import "engine.transcriber" ^
  --hidden-import "engine.script_verify" ^
  --hidden-import "PySide6.QtSvg" ^
  main.py

if errorlevel 1 (
  echo.
  echo [ERROR] Build failed! See errors above.
  echo.
  pause
  exit /b 1
)

echo.
echo === BUILD SUCCESSFUL ===
echo.
echo Your app is in:  dist\ScriptureSoundQC\
echo Run it with:     dist\ScriptureSoundQC\ScriptureSoundQC.exe
echo.
echo To share: zip up the entire "dist\ScriptureSoundQC" folder.
echo.
pause
endlocal
