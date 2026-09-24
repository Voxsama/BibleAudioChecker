"""Register this checkout in the current user's Linux Applications menu."""
import os
from pathlib import Path
import shutil
import subprocess
import sys


def desktop_value(value):
    return (str(value).replace("\\", "\\\\").replace("\n", "\\n")
            .replace("\r", "\\r").replace("\t", "\\t"))


def exec_argument(value):
    # Exec quoting is decoded after Desktop Entry string escaping.
    value = str(value).replace("%", "%%")
    for character in ('\\', '"', '`', '$'):
        value = value.replace(character, "\\" + character)
    return desktop_value('"' + value + '"')


def main():
    if sys.platform != "linux" or os.geteuid() == 0:
        raise SystemExit("Run as your normal Linux user, without sudo.")
    root = Path(__file__).resolve().parents[1]
    if not (root / ".venv-linux/bin/python").is_file():
        raise SystemExit("Run bash setup_linux.sh first.")
    data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    if not data_home.is_absolute():
        raise SystemExit("XDG_DATA_HOME must be an absolute path.")
    applications = data_home / "applications"
    applications.mkdir(parents=True, exist_ok=True)
    destination = applications / "scripturesound-qc.desktop"
    destination.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=ScriptureSound QC\n"
        "Comment=Bible audio QC, marker editing, mastering, and AI review\n"
        f"Exec=/bin/bash {exec_argument(root / 'run_linux.sh')}\n"
        f"Icon={desktop_value(root / 'assets/logo.svg')}\n"
        "Terminal=false\n"
        "Categories=AudioVideo;Audio;\n"
        "Keywords=Bible;Audio;QC;Markers;Mastering;\n",
        encoding="utf-8")
    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", str(applications)], check=True)
    print(f"Installed Applications menu entry: {destination}")


if __name__ == "__main__":
    main()
