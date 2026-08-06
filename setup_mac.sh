#!/usr/bin/env bash
# Beginner-friendly source setup for ScriptureSoundQC on macOS.
set -euo pipefail
cd "$(dirname "$0")"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "[ERROR] setup_mac.sh can only run on macOS."
  exit 1
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "[ERROR] Homebrew was not found."
  echo "Install it from https://brew.sh and then run:"
  echo "  brew install python@3.12 ffmpeg"
  exit 1
fi

PYTHON312="$(brew --prefix python@3.12 2>/dev/null || true)/bin/python3.12"
if [[ ! -x "${PYTHON312}" ]]; then
  echo "[ERROR] Homebrew Python 3.12 was not found."
  echo "Run this command, then run setup_mac.sh again:"
  echo "  brew install python@3.12 ffmpeg"
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "[WARNING] FFmpeg is not installed."
  echo "Marker checks can still run, but loudness and true-peak checks need:"
  echo "  brew install ffmpeg"
fi

VENV_DIR=".venv-mac"
if [[ -x "${VENV_DIR}/bin/python" ]]; then
  if ! "${VENV_DIR}/bin/python" -c \
      'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)'; then
    echo "[ERROR] ${VENV_DIR} was created with the wrong Python version."
    echo "Rename or remove that folder, then run this script again."
    exit 1
  fi
  echo "Reusing the existing Python 3.12 environment: ${VENV_DIR}"
else
  echo "Creating a private Python 3.12 environment: ${VENV_DIR}"
  "${PYTHON312}" -m venv "${VENV_DIR}"
fi

PYTHON="${VENV_DIR}/bin/python"
"${PYTHON}" -m pip install --upgrade pip

if [[ "$(uname -m)" == "x86_64" ]]; then
  echo "Installing the Intel Mac binary compatibility set..."
  "${PYTHON}" -m pip install --no-cache-dir --only-binary=:all: \
    "numpy==1.26.4" \
    "torch==2.2.2" \
    "llvmlite==0.44.0" \
    "numba==0.61.2"
fi

echo "Installing ScriptureSoundQC dependencies..."
"${PYTHON}" -m pip install --no-cache-dir -r requirements.txt

echo "Checking the installation..."
"${PYTHON}" -c \
  'import PySide6, llvmlite, numba, numpy, torch; print("[OK] Required Mac packages are working.")'

echo
echo "Setup finished. Start ScriptureSoundQC with:"
echo "  source .venv-mac/bin/activate"
echo "  python main.py"
