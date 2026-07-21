#!/usr/bin/env bash
# ============================================================
#  ScriptureSound QC v2.5 — build a self-contained macOS .app + .pkg installer
#
#  Run in Terminal:   bash build_mac.sh
#
#  BUILD MACHINE requirements only:
#    - macOS 12+ (Apple Silicon or Intel)
#    - Python 3.9+ (brew install python)
#    - ffmpeg binary beside this script (cp $(which ffmpeg) ./ffmpeg)
#
#  END USERS only get the .pkg file. They do NOT need Python, pip, or ffmpeg.
# ============================================================
set -e
cd "$(dirname "$0")"

APP_NAME="ScriptureSoundQC"
APP_VERSION="2.5"
IDENTIFIER="com.voxsama.scripturesoundqc"

echo
echo "=============================================="
echo "  ScriptureSound QC v${APP_VERSION} — macOS Installer Build"
echo "=============================================="
echo

# --- Check Python ---
if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] python3 not found. Install with: brew install python"
  exit 1
fi

PYVER=$(python3 -c "import sys; print('%d.%d' % sys.version_info[:2])")
echo "[OK] Python ${PYVER}"

# --- Check ffmpeg ---
if [ -f "./ffmpeg" ]; then
  echo "[OK] ffmpeg binary found — will embed in app."
  FFMPEG_ARG=(--add-binary "./ffmpeg:.")
else
  echo
  echo "[ERROR] ffmpeg binary is required beside this script."
  echo "        Run:  brew install ffmpeg && cp \$(which ffmpeg) ./ffmpeg"
  echo "        Then re-run this script."
  echo
  exit 1
fi

# --- Icon ---
ICON_ARG=()
if [ -f "./icon.icns" ]; then
  echo "[OK] icon.icns found — using custom app icon."
  ICON_ARG=(--icon "./icon.icns")
elif [ -f "./logo.png" ]; then
  echo "[OK] logo.png found — converting to .icns..."
  mkdir -p icon.iconset
  sips -z 16 16     logo.png --out icon.iconset/icon_16x16.png      2>/dev/null
  sips -z 32 32     logo.png --out icon.iconset/icon_16x16@2x.png   2>/dev/null
  sips -z 32 32     logo.png --out icon.iconset/icon_32x32.png      2>/dev/null
  sips -z 64 64     logo.png --out icon.iconset/icon_32x32@2x.png   2>/dev/null
  sips -z 128 128   logo.png --out icon.iconset/icon_128x128.png    2>/dev/null
  sips -z 256 256   logo.png --out icon.iconset/icon_128x128@2x.png 2>/dev/null
  sips -z 256 256   logo.png --out icon.iconset/icon_256x256.png    2>/dev/null
  sips -z 512 512   logo.png --out icon.iconset/icon_256x256@2x.png 2>/dev/null
  sips -z 512 512   logo.png --out icon.iconset/icon_512x512.png    2>/dev/null
  sips -z 1024 1024 logo.png --out icon.iconset/icon_512x512@2x.png 2>/dev/null
  iconutil -c icns icon.iconset -o icon.icns
  rm -rf icon.iconset
  ICON_ARG=(--icon "./icon.icns")
else
  echo "[--] No icon found. App will use default Python icon."
fi

echo

# --- Step 1: Install ALL dependencies ---
echo "[1/5] Installing all dependencies..."
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt pyinstaller

echo
echo "[2/5] Verifying all packages..."
python3 -c "import fitz, numpy, openai, pedalboard, pyloudnorm, PySide6, scipy, torch, whisper; print('All runtime packages available.')"

# --- Step 3: Clean ---
echo
echo "[3/5] Cleaning previous build..."
rm -rf "build/${APP_NAME}" "dist/${APP_NAME}" "dist/${APP_NAME}.app" "dist/${APP_NAME}-${APP_VERSION}.pkg"

# --- Step 4: Build .app with PyInstaller ---
echo
echo "[4/5] Building ${APP_NAME}.app (this takes 5-15 minutes)..."
python3 -m PyInstaller --noconfirm --clean --windowed \
  --name "${APP_NAME}" \
  --osx-bundle-identifier "${IDENTIFIER}" \
  "${ICON_ARG[@]}" \
  "${FFMPEG_ARG[@]}" \
  --add-data "engine:engine" \
  --add-data "gui:gui" \
  --add-data "assets:assets" \
  --add-data "CHANGELOG.md:." \
  --collect-all whisper \
  --collect-all tiktoken \
  --collect-all pedalboard \
  --collect-all pyloudnorm \
  --collect-all scipy \
  --collect-all openai \
  --hidden-import engine.mastering \
  --hidden-import engine.csv_markers \
  --hidden-import engine.correction_memory \
  --hidden-import engine.auto_marker \
  --hidden-import engine.marker_writer \
  --hidden-import engine.script_verify \
  --hidden-import engine.transcriber \
  --hidden-import engine.pdf_parser \
  --hidden-import PySide6.QtSvg \
  --hidden-import scipy.signal \
  --hidden-import fitz \
  --exclude-module triton \
  --exclude-module matplotlib \
  --exclude-module pandas \
  --exclude-module tensorflow \
  --exclude-module torchaudio \
  --exclude-module torchvision \
  --exclude-module pytest \
  --exclude-module IPython \
  --exclude-module jupyter \
  main.py

echo
echo "[OK] Built: dist/${APP_NAME}.app"

# --- Step 5: Build .pkg installer ---
echo
echo "[5/5] Building ${APP_NAME}-${APP_VERSION}.pkg installer..."

PKG_ROOT="pkg_root"
rm -rf "${PKG_ROOT}"
mkdir -p "${PKG_ROOT}/Applications"
cp -R "dist/${APP_NAME}.app" "${PKG_ROOT}/Applications/"

pkgbuild \
  --root "${PKG_ROOT}" \
  --identifier "${IDENTIFIER}" \
  --version "${APP_VERSION}" \
  --install-location "/" \
  "dist/${APP_NAME}-${APP_VERSION}.pkg"

rm -rf "${PKG_ROOT}"

echo
echo "=============================================="
echo "  BUILD SUCCESSFUL"
echo "=============================================="
echo
echo "  App:       dist/${APP_NAME}.app"
echo "  Installer: dist/${APP_NAME}-${APP_VERSION}.pkg"
echo
echo "  Give the .pkg to Mac users. They double-click it,"
echo "  click Install, and everything works — no Python,"
echo "  no pip, no ffmpeg, no packages needed."
echo
echo "  First launch: right-click > Open (bypasses Gatekeeper once)."
echo
echo "  Whisper model weights download on first use of"
echo "  Auto-Mark or Script Verification (~1.5 GB, cached)."
echo
