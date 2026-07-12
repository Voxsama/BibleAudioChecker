@echo off
REM ============================================================
REM  Run ScriptureSound QC in DEBUG mode
REM  This keeps the console window open so you can see any errors.
REM  Use this if the app flashes and closes immediately.
REM ============================================================

echo.
echo === ScriptureSound QC - Debug Mode ===
echo === If you see an error below, copy it and report it ===
echo.

REM Try running from source first
python main.py
if errorlevel 1 (
  echo.
  echo -----------------------------------------------
  echo THE APP CRASHED. The error is shown above.
  echo -----------------------------------------------
  echo.
  echo Common fixes:
  echo   1. "No module named PySide6" = Run: pip install PySide6
  echo   2. "No module named engine"  = Make sure you're in the right folder
  echo   3. "DLL load failed"         = Reinstall PySide6: pip install --force-reinstall PySide6
  echo.
)

echo.
pause
