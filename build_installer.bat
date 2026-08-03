@echo off
setlocal

set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"

if not exist "dist-beta\ScriptureSoundQC\ScriptureSoundQC.exe" (
  echo [ERROR] dist-beta\ScriptureSoundQC\ScriptureSoundQC.exe was not found.
  echo Build the standalone application first with build_windows.bat.
  exit /b 1
)

if not exist "icon.ico" (
  echo [ERROR] icon.ico was not found.
  exit /b 1
)

if exist "%ISCC%" goto iscc_found
echo [ERROR] Inno Setup 6 was not found at:
echo %ISCC%
echo Download it from https://jrsoftware.org/isdl.php
exit /b 1

:iscc_found

echo Building the ScriptureSoundQC installer...
"%ISCC%" "installer\ScriptureSoundQC.iss"
if errorlevel 1 exit /b 1

echo.
echo Installer created in dist\installer
endlocal
