#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv-linux/bin/python ]]; then
  echo "Run bash setup_linux.sh first." >&2
  exit 1
fi
exec .venv-linux/bin/python main.py "$@"
