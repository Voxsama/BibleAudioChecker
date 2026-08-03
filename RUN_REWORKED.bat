@echo off
setlocal
cd /d "%~dp0"

set "APP_PYTHON=%~dp0.venv\Scripts\python.exe"
set "BAC_FFMPEG=%~dp0ffmpeg.exe"
set "PYTHONUTF8=1"

if not exist "%APP_PYTHON%" (
  echo ScriptureSoundQC's local runtime is missing.
  echo Recreate it with:
  echo   python -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
  pause
  exit /b 1
)

"%APP_PYTHON%" main.py
if errorlevel 1 (
  echo.
  echo The app could not start.
  echo Repair the local runtime with:
  echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
  pause
  exit /b 1
)

endlocal
