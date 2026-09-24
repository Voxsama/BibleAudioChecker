#!/usr/bin/env bash
# Source installation for Ubuntu, Zorin OS, and Debian desktops.
set -euo pipefail
cd "$(dirname "$0")"

case "${1:-}" in
  "") ;;
  --help|-h)
    echo "Usage: bash setup_linux.sh"
    echo "Installs the full app, including local AI with CPU PyTorch, in .venv-linux."
    exit 0 ;;
  *) echo "Unknown option: $1" >&2; exit 1 ;;
esac
if (( $# > 1 )); then
  echo "Usage: bash setup_linux.sh" >&2
  exit 1
fi
if [[ "$(uname -s)" != "Linux" ]] || ! command -v apt-get >/dev/null 2>&1; then
  echo "This helper requires an Ubuntu/Debian-based Linux desktop (including Zorin OS)." >&2
  exit 1
fi
if (( EUID == 0 )); then
  echo "Run this script as your normal user, without sudo." >&2
  echo "It will request sudo only for system packages." >&2
  exit 1
fi

# Qt's X11 libraries also support running through XWayland on Wayland desktops.
PACKAGES=(python3 python3-venv ffmpeg libegl1 libopengl0 libxcb-cursor0
          libxcb-xinerama0 libxkbcommon-x11-0 libasound2t64)
# Debian releases before the time64 transition use libasound2 instead.
if ! apt-cache show libasound2t64 >/dev/null 2>&1; then
  PACKAGES[${#PACKAGES[@]}-1]=libasound2
fi
MISSING=()
for package in "${PACKAGES[@]}"; do
  if [[ "$(dpkg-query -W -f='${Status}' "$package" 2>/dev/null || true)" != "install ok installed" ]]; then
    MISSING+=("$package")
  fi
done
if (( ${#MISSING[@]} )); then
  echo "Installing system packages (sudo may ask for your password)..."
  if ! sudo apt-get update; then
    echo "[WARNING] Some package lists could not be refreshed. Trying the available lists." >&2
    echo "APT will still verify packages and stop if a required package cannot be installed." >&2
  fi
  sudo apt-get install -y "${MISSING[@]}"
fi

python3 -c 'import sys; assert (3, 10) <= sys.version_info[:2] < (3, 13), "Use Python 3.10–3.12; Python 3.12 is recommended."'
if [[ ! -x .venv-linux/bin/python ]]; then
  python3 -m venv .venv-linux
fi
PYTHON="$PWD/.venv-linux/bin/python"
"$PYTHON" -c 'import sys; assert (3, 10) <= sys.version_info[:2] < (3, 13), "Recreate .venv-linux with Python 3.10–3.12."'
"$PYTHON" -m pip install --upgrade pip
# CPU wheels avoid downloading CUDA libraries on machines without NVIDIA GPUs.
"$PYTHON" -m pip install torch --index-url https://download.pytorch.org/whl/cpu
"$PYTHON" -m pip install -r requirements.txt

echo "Checking installed packages and Qt..."
"$PYTHON" -m pip check
QT_QPA_PLATFORM=offscreen "$PYTHON" - <<'PY'
from PySide6.QtWidgets import QApplication
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from gui.app import MainWindow
from engine.mastering import dependencies_available
from engine.loudness import ffmpeg_available
import fitz
app = QApplication([])
assert dependencies_available(), "Mastering dependencies are missing."
assert ffmpeg_available(), "FFmpeg is missing."
print("[OK] Desktop imports, Qt, mastering, PDF, and FFmpeg are available.")
PY
"$PYTHON" main.py --packaging-self-test
"$PYTHON" scripts/install_linux_desktop.py

echo
echo "Setup finished. Open ScriptureSound QC from your Applications menu, or run:"
echo "  bash run_linux.sh"
