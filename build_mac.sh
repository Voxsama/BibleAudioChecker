#!/usr/bin/env bash
# ============================================================
#  ScriptureSound QC - build a standalone macOS .app + .pkg installer
#  Run in Terminal:   bash build_mac.sh
#  Requires: Python 3.9+ (brew install python)
#
#  App Icon:
#    Place your logo as "icon.icns" next to this script.
#    To convert a PNG to .icns:
#      mkdir icon.iconset
#      sips -z 16 16     logo.png --out icon.iconset/icon_16x16.png
#      sips -z 32 32     logo.png --out icon.iconset/icon_16x16@2x.png
#      sips -z 32 32     logo.png --out icon.iconset/icon_32x32.png
#      sips -z 64 64     logo.png --out icon.iconset/icon_32x32@2x.png
#      sips -z 128 128   logo.png --out icon.iconset/icon_128x128.png
#      sips -z 256 256   logo.png --out icon.iconset/icon_128x128@2x.png
#      sips -z 256 256   logo.png --out icon.iconset/icon_256x256.png
#      sips -z 512 512   logo.png --out icon.iconset/icon_256x256@2x.png
#      sips -z 512 512   logo.png --out icon.iconset/icon_512x512.png
#      sips -z 1024 1024 logo.png --out icon.iconset/icon_512x512@2x.png
#      iconutil -c icns icon.iconset -o icon.icns
#      rm -rf icon.iconset
#
# ============================================================
set -e
cd "$(dirname "$0")"

APP_NAME="ScriptureSoundQC"
APP_VERSION="1.5"
IDENTIFIER="com.voxsama.scripturesoundqc"

echo
echo "=== ScriptureSound QC v${APP_VERSION} - macOS build ==="
echo

if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] python3 not found. Install with: brew install python"
  exit 1
fi

echo "Installing dependencies..."
python3 -m pip install --upgrade pip >/dev/null
python3 -m pip install PySide6 PyMuPDF openai-whisper openai pyinstaller

# --- Icon ---
ICON_ARG=()
if [ -f "./icon.icns" ]; then
  echo "Found icon.icns - using custom app icon."
  ICON_ARG=(--icon "./icon.icns")
elif [ -f "./logo.png" ]; then
  echo "Found logo.png - converting to .icns..."
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
  echo
  echo "[NOTE] No icon found. To add your logo:"
  echo "       Place 'logo.png' (1024x1024 recommended) or 'icon.icns' next to this script."
  echo
fi

# --- ffmpeg ---
FFMPEG_ARG=()
if [ -f "./ffmpeg" ]; then
  echo "Found ./ffmpeg - it will be bundled inside the app."
  FFMPEG_ARG=(--add-binary "./ffmpeg:.")
else
  echo
  echo "[NOTE] No ffmpeg binary found next to this script."
  echo "       The app builds fine, but loudness/true-peak need ffmpeg."
  echo "       For a self-contained app: 'brew install ffmpeg', then:"
  echo "         cp \$(which ffmpeg) ./ffmpeg"
  echo "       and re-run this script."
  echo
fi

# --- Build .app with PyInstaller ---
echo "Building ${APP_NAME}.app ..."
pyinstaller --noconfirm --clean --windowed \
  --name "${APP_NAME}" \
  --osx-bundle-identifier "${IDENTIFIER}" \
  "${ICON_ARG[@]}" \
  "${FFMPEG_ARG[@]}" \
  --add-data "engine:engine" \
  main.py

echo
echo "Built: dist/${APP_NAME}.app"

# --- Build .pkg installer ---
echo
echo "Building ${APP_NAME}-${APP_VERSION}.pkg installer..."

PKG_ROOT="pkg_root"
rm -rf "${PKG_ROOT}"
mkdir -p "${PKG_ROOT}/Applications"
cp -R "dist/${APP_NAME}.app" "${PKG_ROOT}/Applications/"

# Use pkgbuild to create the installer package
pkgbuild \
  --root "${PKG_ROOT}" \
  --identifier "${IDENTIFIER}" \
  --version "${APP_VERSION}" \
  --install-location "/" \
  "dist/${APP_NAME}-${APP_VERSION}.pkg"

rm -rf "${PKG_ROOT}"

echo
echo "=== DONE ==="
echo
echo "Your files:"
echo "  App:       dist/${APP_NAME}.app"
echo "  Installer: dist/${APP_NAME}-${APP_VERSION}.pkg"
echo
echo "To run the app: double-click dist/${APP_NAME}.app"
echo "  (first launch: right-click > Open to bypass Gatekeeper)"
echo
echo "To distribute: share the .pkg file. Users double-click it to install"
echo "  to /Applications/${APP_NAME}.app"
echo
