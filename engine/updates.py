"""Background-safe release checking for ScriptureSoundQC.

The updater deliberately does not replace a running executable. It discovers
new releases from the official GitHub feed and hands the HTTPS release page to
the GUI. The signed Inno Setup installer remains responsible for upgrades.
"""

from __future__ import annotations

import json
import os
import platform
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Iterable, Tuple


DEFAULT_RELEASES_API = (
    "https://api.github.com/repos/Voxsama/BibleAudioChecker/"
    "releases?per_page=20")
DEFAULT_RELEASES_PAGE = (
    "https://github.com/Voxsama/BibleAudioChecker/releases")


@dataclass(frozen=True)
class UpdateInfo:
    update_available: bool
    version: str
    title: str
    notes: str
    page_url: str
    download_url: str = ""
    published_at: str = ""
    releases_found: bool = True


def version_key(value: str) -> Tuple[int, int, int, int, int]:
    """Return an ordering key for tags such as v4.0.1-beta.2 and v4.1."""
    text = str(value or "").strip().lower()
    number_match = re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", text)
    if not number_match:
        return (0, 0, 0, 0, 0)
    core = tuple(int(part or 0) for part in number_match.groups())
    stage_rank = 4  # final/stable release
    stage_number = 0
    for stage, rank in (("dev", 0), ("alpha", 1), ("beta", 2), ("rc", 3)):
        stage_match = re.search(r"%s[.\-_ ]*(\d*)" % stage, text)
        if stage_match:
            stage_rank = rank
            stage_number = int(stage_match.group(1) or 0)
            break
    return core + (stage_rank, stage_number)


def _update_target(platform_name: str = "", machine: str = "") -> str:
    """Return the installer family for the running application."""
    os_name = str(platform_name or sys.platform).strip().lower()
    architecture = str(machine or platform.machine()).strip().lower()
    if os_name.startswith("win"):
        return "windows"
    if os_name == "darwin":
        if architecture in {"x86_64", "amd64", "x64"}:
            return "mac-intel"
        if architecture in {"arm64", "aarch64"}:
            return "mac-apple-silicon"
    return ""


def _installer_url(assets: Iterable[dict], target: str) -> str:
    """Select only an installer that can run on the requested target."""
    candidates = []
    for asset in assets or []:
        name = str(asset.get("name") or "")
        url = str(asset.get("browser_download_url") or "")
        if not url.lower().startswith("https://"):
            continue
        lower_name = name.lower()
        score = -1
        if target == "windows" and lower_name.endswith(".exe"):
            score = 10
            if "setup" in lower_name or "installer" in lower_name:
                score += 5
        elif target == "mac-intel" and lower_name.endswith(".pkg"):
            if "intel" in lower_name or "x86_64" in lower_name:
                score = 15
            elif "universal" in lower_name:
                score = 10
        elif target == "mac-apple-silicon" and lower_name.endswith(".pkg"):
            if ("apple-silicon" in lower_name or "arm64" in lower_name or
                    "aarch64" in lower_name):
                score = 15
            elif "universal" in lower_name:
                score = 10
        if score < 0:
            continue
        candidates.append((score, url))
    return max(candidates, default=(0, ""))[1]


def select_update(releases: Iterable[dict], current_version: str,
                  channel: str = "beta", platform_name: str = "",
                  machine: str = "") -> UpdateInfo:
    """Select the newest eligible release returned by the GitHub API."""
    current_key = version_key(current_version)
    target = _update_target(platform_name, machine)
    valid = []
    found = False
    for release in releases or []:
        if not isinstance(release, dict) or release.get("draft"):
            continue
        found = True
        tag = str(release.get("tag_name") or release.get("name") or "")
        key = version_key(tag)
        if key[:3] == (0, 0, 0):
            continue
        is_prerelease = bool(release.get("prerelease")) or key[3] < 4
        if str(channel).lower() == "stable" and is_prerelease:
            continue
        if key > current_key:
            download_url = _installer_url(
                release.get("assets") or [], target)
            if download_url:
                valid.append((key, release, tag, download_url))

    if not valid:
        return UpdateInfo(
            update_available=False,
            version=current_version,
            title="No update available",
            notes=("No published releases were found in the official feed."
                   if not found else
                   "No newer compatible installer is published for this computer."),
            page_url=DEFAULT_RELEASES_PAGE,
            releases_found=found,
        )

    _key, release, tag, download_url = max(valid, key=lambda item: item[0])
    page_url = str(release.get("html_url") or DEFAULT_RELEASES_PAGE)
    if not page_url.lower().startswith("https://"):
        page_url = DEFAULT_RELEASES_PAGE
    return UpdateInfo(
        update_available=True,
        version=tag,
        title=str(release.get("name") or tag),
        notes=str(release.get("body") or "No release notes were provided."),
        page_url=page_url,
        download_url=download_url,
        published_at=str(release.get("published_at") or ""),
    )


def check_for_updates(current_version: str, channel: str = "beta",
                      timeout: float = 12.0, platform_name: str = "",
                      machine: str = "") -> UpdateInfo:
    """Fetch the official releases feed and return the newest eligible build."""
    api_url = os.environ.get(
        "SCRIPTURESOUNDQC_UPDATE_API", DEFAULT_RELEASES_API).strip()
    request = urllib.request.Request(
        api_url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "ScriptureSoundQC-UpdateChecker/%s" % current_version,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read(2 * 1024 * 1024)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise RuntimeError(
                "The official update feed is not published yet.") from exc
        raise RuntimeError("Update server returned HTTP %d." % exc.code) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(
            "Could not reach the update server. Check your internet connection.") from exc

    try:
        releases = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("The update server returned invalid release data.") from exc
    if not isinstance(releases, list):
        raise RuntimeError("The update server returned an unexpected response.")
    return select_update(
        releases, current_version, channel, platform_name, machine)
