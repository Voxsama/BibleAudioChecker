@echo off
REM ============================================================
REM  ScriptureSound QC v2.5 - build the self-contained Windows installer
REM
REM  BUILD MACHINE requirements only:
REM    - 64-bit Python 3.11 or 3.12 on PATH
REM    - Inno Setup 6
REM    - ffmpeg.exe beside this script
REM
REM  END USERS only run Output\ScriptureSoundQC_v2.5_Setup.exe.
REM  They do not need Python, pip, FFmpeg, or any Python packages.
REM ============================================================
setlocal
cd /d "%~dp0"

set "APP_EXE=dist\ScriptureSoundQC.exe"
set "INSTALLER=Output\ScriptureSoundQC_v2.5_Setup.exe"

echo.
echo ==============================================
echo   ScriptureSound QC v2.5 - Installer Build
echo ==============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python was not found on the build machine.
  goto :failed
)

python -c "import sys, struct; assert sys.version_info[:2] in [(3,11),(3,12)], 'Use Python 3.11 or 3.12'; assert struct.calcsize('P') == 8, 'Use 64-bit Python'"
if errorlevel 1 (
  echo [ERROR] This build requires 64-bit Python 3.11 or 3.12.
  goto :failed
)

if not exist "ffmpeg.exe" (
  echo [ERROR] ffmpeg.exe is required beside build_windows.bat.
  echo Download the Windows essentials build, extract bin\ffmpeg.exe,
  echo place it in this folder, and run the build again.
  goto :failed
)
echo [OK] ffmpeg.exe will be embedded in the application.

set "ISCC="
where ISCC.exe >nul 2>nul && set "ISCC=ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC (
  echo [ERROR] Inno Setup 6 was not found on the build machine.
  echo Install it from https://jrsoftware.org/isdl.php and retry.
  goto :failed
)

echo.
echo [1/5] Installing the complete application and build dependencies...
python -m pip install --upgrade pip
if errorlevel 1 goto :dependency_failed
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :dependency_failed

echo.
echo [2/5] Verifying packages used by packaged features...
python -c "import fitz, numpy, openai, pedalboard, pyloudnorm, PySide6, scipy, torch, whisper; print('All runtime packages are available.')"
if errorlevel 1 goto :dependency_failed

echo.
echo [3/5] Cleaning previous build output...
if exist "build\ScriptureSoundQC" rmdir /s /q "build\ScriptureSoundQC"
if exist "%APP_EXE%" del /q "%APP_EXE%"
if exist "%INSTALLER%" del /q "%INSTALLER%"

echo.
echo [4/5] Building the self-contained application...
python -m PyInstaller --noconfirm --clean ScriptureSoundQC.spec
if errorlevel 1 (
  echo [ERROR] PyInstaller failed.
  goto :failed
)
if not exist "%APP_EXE%" (
  echo [ERROR] PyInstaller did not create %APP_EXE%.
  goto :failed
)

echo.
echo [5/5] Compiling the single-file installer...
"%ISCC%" installer_windows.iss
if errorlevel 1 (
  echo [ERROR] Inno Setup failed.
  goto :failed
)
if not exist "%INSTALLER%" (
  echo [ERROR] The expected installer was not created: %INSTALLER%
  goto :failed
)

echo.
echo ==============================================
echo   BUILD SUCCESSFUL
echo ==============================================
echo.
echo   Installer: %INSTALLER%
echo.
echo Give that one Setup.exe to end users. It contains the application,
echo Python runtime, Python packages, Qt, and FFmpeg.
echo Local Whisper model weights are downloaded on first use and cached.
echo.
if not defined CI pause
exit /b 0

:dependency_failed
echo [ERROR] A required Python package could not be installed or imported.
:failed
echo.
echo BUILD FAILED. Review the error above.
echo.
if not defined CI pause
exit /b 1
