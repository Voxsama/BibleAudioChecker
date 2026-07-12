@echo off
REM ============================================================
REM  ScriptureSound QC v2.0 - build a standalone Windows .exe
REM  Just double-click this file (or run it in a terminal).
REM  Requires: Python 3.9+ installed with "Add to PATH" ticked.
REM
REM  App Icon:
REM    Place "icon.ico" next to this script for a custom app icon.
REM    You can convert PNG to ICO at: https://convertio.co/png-ico/
REM    (use 256x256 or larger PNG for best quality)
REM
REM  ffmpeg:
REM    Place "ffmpeg.exe" next to this script to bundle it inside the app.
REM
REM  OUTPUT: dist\ScriptureSoundQC.exe (single file!)
REM ============================================================
setlocal

echo.
echo ======================================
echo   ScriptureSound QC v2.0 - Build
echo ======================================
echo.

REM 1) Make sure Python is available
where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python was not found on PATH.
  echo.
  echo Install Python from https://www.python.org/downloads/
  echo and tick "Add Python to PATH" during setup, then run this again.
  echo.
  pause
  exit /b 1
)

echo Python version:
python --version
echo.

REM 2) Install build dependencies
echo [1/3] Installing dependencies...
python -m pip install --upgrade pip >nul 2>nul
python -m pip install PySide6 PyMuPDF pyinstaller "audioop-lts; python_version >= '3.13'"
if errorlevel 1 (
  echo.
  echo [ERROR] Failed to install dependencies.
  echo Check your internet connection and try again.
  echo.
  pause
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
  echo [--] No ffmpeg.exe - loudness checks need ffmpeg installed separately.
)
echo.

REM 4) Clean old build
echo [2/3] Cleaning old build files...
if exist "dist\ScriptureSoundQC.exe" del "dist\ScriptureSoundQC.exe"
if exist "build\ScriptureSoundQC" rmdir /s /q "build\ScriptureSoundQC"
echo       Done.
echo.

REM 5) Build using spec file (single .exe, excludes heavy torch/whisper)
echo [3/3] Building ScriptureSoundQC.exe...
echo       (This takes 2-5 minutes, please wait...)
echo.
pyinstaller --noconfirm ScriptureSoundQC.spec

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
  pause
  exit /b 1
)

echo.
echo ==========================================
echo   BUILD SUCCESSFUL!
echo ==========================================
echo.
echo   Your app:  dist\ScriptureSoundQC.exe
echo.
echo   Double-click it to run.
echo   Share this single .exe file with anyone!
echo.
echo   NOTE: Whisper (AI features) is NOT bundled in the .exe
echo   because it's too large (3GB+). Users who want AI
echo   auto-marking should install whisper separately:
echo     pip install openai-whisper
echo.
echo   The .exe works perfectly for all other features
echo   (loudness, silence, markers, verses, waveform, export).
echo.
pause
endlocal
