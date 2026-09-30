#!/bin/bash
# The build appends the compressed application after __ARCHIVE_BELOW__.
set -euo pipefail
if [[ "$(uname -s)" != Linux || "$(uname -m)" != x86_64 ]]; then
  echo "This installer requires x86_64 Linux." >&2; exit 1
fi
if [[ $EUID == 0 ]]; then
  echo "Run as your normal desktop user, without sudo." >&2; exit 1
fi
data_dir="${XDG_DATA_HOME:-$HOME/.local/share}"
if [[ "$data_dir" != /* || "$data_dir" == *$'\n'* || "$data_dir" == *$'\r'* ]]; then
  echo "XDG_DATA_HOME must be an absolute, single-line path." >&2; exit 1
fi
root="$data_dir/scripturesound-qc"
mkdir -p "$root" "$data_dir/applications"
# Prevent simultaneous installs from replacing each other's app directory.
if ! mkdir "$root/install.lock" 2>/dev/null; then
  echo "Another install is running. If an earlier install was interrupted, remove $root/install.lock and retry." >&2; exit 1
fi
if ! work=$(mktemp -d "$root/install.XXXXXX"); then
  rmdir "$root/install.lock"; exit 1
fi
cleanup() {
  if [[ ! -e "$root/app" && -d "$work/previous" ]]; then
    mv "$work/previous" "$root/app" || return
  fi
  rm -rf "$work"
  rmdir "$root/install.lock"
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
echo "Unpacking ScriptureSoundQC and dependencies (no internet needed)..."
line=$(awk '/^__ARCHIVE_BELOW__$/ {print NR + 1; exit}' "$0")
tail -n +"$line" "$0" > "$work/app.tar.gz"
actual=$(sha256sum < "$work/app.tar.gz")
if [[ "${actual%% *}" != '@PAYLOAD_SHA256@' ]]; then
  echo "Installer is damaged. Nothing was replaced; download it again." >&2; exit 1
fi
tar -xzf "$work/app.tar.gz" -C "$work" --no-same-owner
test -x "$work/ScriptureSoundQC/ScriptureSoundQC"
# Check the frozen imports before replacing a previously installed version.
QT_QPA_PLATFORM=offscreen "$work/ScriptureSoundQC/ScriptureSoundQC" --packaging-self-test
if [[ -e "$root/app" ]]; then mv "$root/app" "$work/previous"; fi
if ! mv "$work/ScriptureSoundQC" "$root/app"; then
  if [[ -d "$work/previous" ]]; then mv "$work/previous" "$root/app"; fi
  exit 1
fi
# WorkingDirectory keeps any relative app files out of the caller's folder.
# Desktop Exec uses its own quoting rules, distinct from shell quoting.
desktop_escape() {
  local value="$1"
  value=${value//\\/\\\\}
  value=${value//$'\t'/\\t}
  value=${value//$'\n'/\\n}
  value=${value//$'\r'/\\r}
  printf '%s' "$value"
}
exec_path="$root/app/ScriptureSoundQC"
exec_path=${exec_path//\\/\\\\}
exec_path=${exec_path//\"/\\\"}
exec_path=${exec_path//\$/\\\$}
exec_path=${exec_path//\`/\\\`}
exec_path=${exec_path//%/%%}
cat > "$data_dir/applications/scripturesound-qc.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=ScriptureSoundQC
Comment=Bible audio checking, markers and mastering
Exec="$(desktop_escape "$exec_path")"
Path=$(desktop_escape "$root/app")
Icon=$(desktop_escape "$root/app/_internal/assets/logo.svg")
Terminal=false
Categories=AudioVideo;Audio;
EOF
if command -v update-desktop-database >/dev/null; then
  update-desktop-database "$data_dir/applications" || true
fi
echo "Installed. Open ScriptureSoundQC from your Applications menu."
echo "Language models can be downloaded separately inside the app."
exit 0
__ARCHIVE_BELOW__
