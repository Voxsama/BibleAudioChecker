#!/usr/bin/env bash
# Build native ScriptureSoundQC.app and .pkg artifacts on macOS.
# Run on each target architecture; Python/PyInstaller bundles are native.
set -euo pipefail
cd "$(dirname "$0")"

APP_NAME="ScriptureSoundQC"
APP_VERSION="4.0.0"
ARCH_LABEL="${MAC_ARCH_LABEL:-$(uname -m)}"
IDENTIFIER="studio.versevox.scripturesoundqc"
PKG_NAME="${APP_NAME}-v4.0-Beta-macOS-${ARCH_LABEL}.pkg"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "[ERROR] macOS is required to build a .app or .pkg."
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] python3 was not found. Install Python 3.12 first."
  exit 1
fi
if ! command -v productbuild >/dev/null 2>&1; then
  echo "[ERROR] Apple's productbuild tool was not found. Install Xcode tools."
  exit 1
fi

echo "=== ${APP_NAME} v4.0 Beta macOS ${ARCH_LABEL} ==="
python3 -m pip install --upgrade pip
python3 -m pip install --no-cache-dir -r requirements.txt pyinstaller

# Generate a native .icns from the existing transparent SVG logo.
rm -rf "icon.iconset"
rm -f "icon.icns"
QT_QPA_PLATFORM=offscreen python3 scripts/create_macos_icon.py
iconutil -c icns "icon.iconset" -o "icon.icns"
rm -rf "icon.iconset"

if command -v ffmpeg >/dev/null 2>&1; then
  echo "[OK] Bundling ffmpeg from $(command -v ffmpeg)"
else
  echo "[WARNING] ffmpeg is unavailable; loudness and true-peak checks will be disabled."
fi

rm -rf "build-mac" "dist-mac"
python3 -m PyInstaller --noconfirm --clean \
  --workpath build-mac --distpath dist-mac ScriptureSoundQC.spec

APP_PATH="dist-mac/${APP_NAME}.app"
PKG_PATH="dist-mac/${PKG_NAME}"
if [[ ! -d "${APP_PATH}" ]]; then
  echo "[ERROR] ${APP_PATH} was not created."
  exit 1
fi

# productbuild is Apple's supported container for installing one app into
# /Applications. Signing is optional for local/Beta builds.
if [[ -n "${MAC_INSTALLER_SIGN_IDENTITY:-}" ]]; then
  productbuild --sign "${MAC_INSTALLER_SIGN_IDENTITY}" \
    --identifier "${IDENTIFIER}" --version "${APP_VERSION}" \
    --component "${APP_PATH}" /Applications "${PKG_PATH}"
else
  productbuild --identifier "${IDENTIFIER}" --version "${APP_VERSION}" \
    --component "${APP_PATH}" /Applications "${PKG_PATH}"
fi

echo
echo "Built app: ${APP_PATH}"
echo "Built pkg: ${PKG_PATH}"
shasum -a 256 "${PKG_PATH}"
