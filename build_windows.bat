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

REM 2) Install the build dependencies
echo Installing dependencies (first run may take a few minutes)...
python -m pip install --upgrade pip >nul
python -m pip install PySide6 PyMuPDF openai-whisper openai pyinstaller
if errorlevel 1 (
  echo [ERROR] Failed to install dependencies. Check your internet connection.
  pause
  exit /b 1
)

REM 3) Icon
set ICON_ARG=
if exist "%~dp0icon.ico" (
  echo Found icon.ico - using custom app icon.
  set ICON_ARG=--icon "%~dp0icon.ico"
) else (
  echo.
  echo [NOTE] No icon.ico found. To add your logo:
  echo        Place "icon.ico" (256x256+) next to this script.
  echo        Convert PNG to ICO at: https://convertio.co/png-ico/
  echo.
)

REM 4) If an ffmpeg.exe is sitting in this folder, bundle it INSIDE the app
set FFMPEG_ARG=
if exist "%~dp0ffmpeg.exe" (
  echo Found ffmpeg.exe - it will be bundled inside the app.
  set FFMPEG_ARG=--add-binary "%~dp0ffmpeg.exe;."
) else (
  echo.
  echo [NOTE] No ffmpeg.exe found next to this script.
  echo        The app will still build, but loudness/true-peak checks need ffmpeg.
  echo        For a fully self-contained app: download ffmpeg.exe, drop it in this
  echo        folder, and run this script again.
  echo.
)

REM 5) Build a single-file, windowed executable
echo Building ScriptureSoundQC.exe ...
pyinstaller --noconfirm --clean --onefile --windowed --name "ScriptureSoundQC" %ICON_ARG% %FFMPEG_ARG% --add-data "engine;engine" main.py
if errorlevel 1 (
  echo [ERROR] Build failed.
  pause
  exit /b 1
)

echo.
echo === DONE ===
echo Your app is here:  dist\ScriptureSoundQC.exe
echo Double-click it to run. You can copy that single .exe anywhere.
echo.
pause
endlocal
