"""Wrap an existing offline installer with a small, hash-pinned downloader.

Only the build machine needs Python. End users use Inno Setup or OS tools.
"""
import argparse
import hashlib
from pathlib import Path
import shlex
import shutil
import subprocess
from urllib.parse import quote, urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def build(payload, base_url, platform, iscc=None):
    payload = Path(payload).resolve()
    parsed = urlsplit(base_url)
    if (parsed.scheme != "https" or not parsed.netloc or parsed.username or
            parsed.password or parsed.query or parsed.fragment or
            any(c.isspace() or c in '\"{}' for c in base_url)):
        raise ValueError("Use an HTTPS release directory URL without credentials/query/fragment.")
    suffix = {"windows": ".exe", "macos": ".pkg", "linux": ".sh"}[platform]
    if payload.suffix != suffix or "-Offline" not in payload.stem:
        raise ValueError("Expected a platform installer named with -Offline.")
    digest = sha256(payload)
    url = base_url.rstrip("/") + "/" + quote(payload.name, safe="")
    name = payload.stem.replace("-Offline", "-Online")
    if platform == "windows":
        compiler = iscc or shutil.which("ISCC")
        if not compiler:
            for folder in ("C:/Program Files (x86)/Inno Setup 6",
                           "C:/Program Files (x86)/Inno Setup 7",
                           "C:/Program Files/Inno Setup 7"):
                candidate = Path(folder) / "ISCC.exe"
                if candidate.is_file():
                    compiler = str(candidate)
                    break
        if not compiler:
            raise RuntimeError("Inno Setup 6.5+ was not found; pass --iscc.")
        subprocess.run([
            compiler, f"/DOutputPath={payload.parent}", f"/DOutputName={name}",
            f"/DPayloadURL={url}", f"/DPayloadSize={payload.stat().st_size}",
            f"/DPayloadHash={digest}", str(ROOT / "installer/Online.iss"),
        ], check=True)
        output = payload.with_name(name + ".exe")
    else:
        mac = platform == "macos"
        check = 'shasum -a 256 < "$download"' if mac else 'sha256sum < "$download"'
        action = ('echo "Download verified. Complete the macOS Installer wizard."\n'
                  '/usr/bin/open -W "$download"' if mac else 'bash "$download"')
        script = f'''#!/bin/bash
# ScriptureSoundQC online installer. No model weights are downloaded here.
set -euo pipefail
echo "Downloading ScriptureSoundQC and dependencies. Internet is required."
command -v curl >/dev/null || {{ echo "curl is required. Use the offline installer instead." >&2; exit 1; }}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
download="$work/setup{suffix}"
curl --fail --location --proto '=https' --proto-redir '=https' \\
  --retry 2 --connect-timeout 30 --output "$download" {shlex.quote(url)}
actual=$({check})
actual=${{actual%% *}}
if [[ "$actual" != {shlex.quote(digest)} ]]; then
  echo "Download verification failed. Nothing was installed. Please retry." >&2
  exit 1
fi
{action}
'''
        output = payload.with_name(name + (".command" if mac else ".sh"))
        output.write_text(script, encoding="utf-8", newline="\n")
        output.chmod(0o755)
        if mac:
            # ZIP preserves the executable bit for Finder's double-click launch.
            archive = output.with_suffix(".zip")
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as stream:
                info = zipfile.ZipInfo(output.name)
                info.create_system = 3  # Unix permissions, even on a Windows build host.
                info.external_attr = 0o100755 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                stream.writestr(info, script.encode("utf-8"))
            output.unlink()
            output = archive
    for item in (payload, output):
        item.with_name(item.name + ".sha256").write_text(
            f"{sha256(item)}  {item.name}\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--base-url", required=True,
                        help="HTTPS directory for this exact release (not latest)")
    parser.add_argument("--platform", choices=("windows", "macos", "linux"), required=True)
    parser.add_argument("--iscc")
    args = parser.parse_args()
    print(build(args.payload, args.base_url, args.platform, args.iscc))
