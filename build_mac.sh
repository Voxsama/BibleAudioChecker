#!/usr/bin/env bash
# ============================================================
#  Bible Audio Checker - build a standalone macOS .app
#  Run in Terminal:   bash build_mac.sh
#  Requires: Python 3.9+ (brew install python)
# ============================================================
set -e
cd "$(dirname "$0")"

echo
echo "=== Bible Audio Checker - macOS build ==="
echo

if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] python3 not found. Install with: brew install python"
  exit 1
fi

echo "Installing PySide6 and PyInstaller (first run may take a few minutes)..."
python3 -m pip install --upgrade pip >/dev/null
python3 -m pip install PySide6 pyinstaller

# Bundle a local ffmpeg binary if present next to this script
FFMPEG_ARG=()
if [ -f "./ffmpeg" ]; then
  echo "Found ./ffmpeg - it will be bundled inside the app."
  FFMPEG_ARG=(--add-binary "./ffmpeg:.")
else
  echo
  echo "[NOTE] No ffmpeg binary found next to this script."
  echo "       The app builds fine, but loudness/true-peak need ffmpeg."
  echo "       For a self-contained app: 'brew install ffmpeg', then copy the"
  echo "       binary here (cp \$(which ffmpeg) ./ffmpeg) and re-run."
  echo
fi

echo "Building ScriptureSoundQC.app ..."
pyinstaller --noconfirm --clean --windowed --name "ScriptureSoundQC" "${FFMPEG_ARG[@]}" main.py

echo
echo "=== DONE ==="
echo "Your app is here:  dist/ScriptureSoundQC.app"
echo "Double-click to run (first launch: right-click > Open to bypass Gatekeeper)."
echo
