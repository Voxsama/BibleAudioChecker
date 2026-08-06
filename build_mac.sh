#!/usr/bin/env bash
# Build native ScriptureSoundQC.app and .pkg artifacts on macOS.
# Run on each target architecture; Python/PyInstaller bundles are native.
set -euo pipefail
cd "$(dirname "$0")"

APP_NAME="ScriptureSoundQC"
APP_VERSION="4.0.0"
MACHINE_ARCH="$(uname -m)"
case "${MACHINE_ARCH}" in
  arm64) DEFAULT_ARCH_LABEL="apple-silicon" ;;
  x86_64) DEFAULT_ARCH_LABEL="intel" ;;
  *) DEFAULT_ARCH_LABEL="${MACHINE_ARCH}" ;;
esac
ARCH_LABEL="${MAC_ARCH_LABEL:-${DEFAULT_ARCH_LABEL}}"
IDENTIFIER="studio.versevox.scripturesoundqc"
PKG_NAME="${APP_NAME}-v4.0-Beta-macOS-${ARCH_LABEL}.pkg"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "[ERROR] macOS is required to build a .app or .pkg."
  exit 1
fi
if ! command -v productbuild >/dev/null 2>&1; then
  echo "[ERROR] Apple's productbuild tool was not found. Install Xcode tools."
  exit 1
fi

# Use Python 3.12 deliberately. Homebrew's unversioned `python3` may be 3.14;
# Pedalboard does not currently publish a Python 3.14 wheel for Intel Macs.
PYTHON312="${MAC_PYTHON:-}"
if [[ -z "${PYTHON312}" ]] && command -v python3.12 >/dev/null 2>&1; then
  PYTHON312="$(command -v python3.12)"
fi
if [[ -z "${PYTHON312}" ]] && command -v brew >/dev/null 2>&1; then
  BREW_PYTHON="$(brew --prefix python@3.12 2>/dev/null || true)/bin/python3.12"
  if [[ -x "${BREW_PYTHON}" ]]; then
    PYTHON312="${BREW_PYTHON}"
  fi
fi
if [[ -z "${PYTHON312}" || ! -x "${PYTHON312}" ]]; then
  echo "[ERROR] Python 3.12 was not found."
  echo "Install it with: brew install python@3.12"
  echo "Then run this build script again."
  exit 1
fi
if ! "${PYTHON312}" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)'; then
  echo "[ERROR] MAC_PYTHON must point to Python 3.12."
  echo "Selected interpreter: ${PYTHON312}"
  "${PYTHON312}" --version || true
  exit 1
fi

BUILD_VENV=".mac-build-venv"
rm -rf "${BUILD_VENV}"
"${PYTHON312}" -m venv "${BUILD_VENV}"
BUILD_PYTHON="${BUILD_VENV}/bin/python"

echo "=== ${APP_NAME} v4.0 Beta macOS ${ARCH_LABEL} ==="
echo "Architecture: ${MACHINE_ARCH}"
"${BUILD_PYTHON}" --version
"${BUILD_PYTHON}" -m pip install --upgrade pip

# New Numba, llvmlite, and PyTorch releases no longer publish Intel macOS
# wheels. Install the last compatible CPython 3.12 wheel set explicitly so pip
# never falls back to compiling LLVM on the GitHub Intel runner or an Intel Mac.
if [[ "${MACHINE_ARCH}" == "x86_64" ]]; then
  echo "Installing verified Intel macOS binary dependency set..."
  "${BUILD_PYTHON}" -m pip install --no-cache-dir --only-binary=:all: \
    "numpy==1.26.4" \
    "torch==2.2.2" \
    "llvmlite==0.44.0" \
    "numba==0.61.2"
fi

"${BUILD_PYTHON}" -m pip install --no-cache-dir -r requirements.txt pyinstaller
"${BUILD_PYTHON}" -c \
  'import PySide6, llvmlite, numba, numpy, torch; print("[OK] Core Mac dependencies import successfully.")'

# Generate a native .icns from the existing transparent SVG logo.
rm -rf "icon.iconset"
rm -f "icon.icns"
QT_QPA_PLATFORM=offscreen "${BUILD_PYTHON}" scripts/create_macos_icon.py
iconutil -c icns "icon.iconset" -o "icon.icns"
rm -rf "icon.iconset"

if command -v ffmpeg >/dev/null 2>&1; then
  echo "[OK] Bundling ffmpeg from $(command -v ffmpeg)"
else
  echo "[WARNING] ffmpeg is unavailable; loudness and true-peak checks will be disabled."
fi

rm -rf "build-mac" "dist-mac"
"${BUILD_PYTHON}" -m PyInstaller --noconfirm --clean \
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
