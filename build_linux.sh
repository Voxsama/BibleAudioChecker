#!/usr/bin/env bash
# Build on Ubuntu 22.04 x86_64 with Python 3.12 for Ubuntu 22.04+ / Zorin 17+.
set -euo pipefail
cd "$(dirname "$0")"
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || {
  echo "Build on x86_64 Linux." >&2; exit 1;
}
command -v ffmpeg >/dev/null || { echo "Install ffmpeg before building." >&2; exit 1; }
PYTHON="${LINUX_PYTHON:-python3.12}"
"$PYTHON" -c 'import sys; assert sys.version_info[:2] == (3, 12), "Python 3.12 is required"'
rm -rf .linux-build-venv
"$PYTHON" -m venv .linux-build-venv
PYTHON=.linux-build-venv/bin/python
"$PYTHON" -m pip install --upgrade pip
# CPU wheels avoid shipping NVIDIA libraries to every user.
"$PYTHON" -m pip install torch --index-url https://download.pytorch.org/whl/cpu
"$PYTHON" -m pip install -r requirements.txt pyinstaller
"$PYTHON" -m pip check
rm -rf build-linux dist-linux
"$PYTHON" -m PyInstaller --noconfirm --clean --workpath build-linux --distpath dist-linux ScriptureSoundQC.spec
QT_QPA_PLATFORM=offscreen dist-linux/ScriptureSoundQC/ScriptureSoundQC --packaging-self-test
"$PYTHON" -m pip freeze > dist-linux/ScriptureSoundQC-Linux-x86_64-dependencies.txt
"$PYTHON" scripts/build_linux_installer.py --app dist-linux/ScriptureSoundQC \
  --output dist-linux/ScriptureSoundQC-Beta-Linux-x86_64-Offline.sh
