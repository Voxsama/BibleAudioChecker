"""Download and manage the optional Meta MMS Assamese precision pack.

Only the shared MMS acoustic model and the Assamese (``asm``) adapter are
downloaded.  Files are pinned to one repository revision, downloaded with
resume support, SHA-256 verified, and kept outside the packaged executable.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional, Tuple


MMS_PACK_KEY = "mms-1b-all-asm"
MMS_REPO_ID = "facebook/mms-1b-all"
MMS_REVISION = "3d33597edbdaaba14a8e858e2c8caa76e3cec0cd"


@dataclass(frozen=True)
class MMSFile:
    relative_path: str
    size: int
    sha256: str


MMS_FILES: Tuple[MMSFile, ...] = (
    MMSFile(
        "model.safetensors", 3859521128,
        "0f1d95ce43d27e03d5d8dd56c697c805460f967c793dd2cbec2e8e8012deda98"),
    MMSFile(
        "adapter.asm.safetensors", 9346840,
        "63019b35c4b529b134f3ec25f3afe9afb9edb1271ec68921bfbb43d7570a6e20"),
    MMSFile(
        "vocab.json", 1340148,
        "0375a07a977a599040a7ff333b6974996965cd93754020619518c15db7691f01"),
    MMSFile(
        "config.json", 2040,
        "ee172ef39a0e40c55403fb811fa0f56c6198c7ed21a2bdf5bd0e72e52c07a41c"),
    MMSFile(
        "preprocessor_config.json", 254,
        "f724fdad65341e79bd9741888fe4e8ce1bb2e7b44fc8216c28c591afb1e202f4"),
    MMSFile(
        "special_tokens_map.json", 96,
        "9046da57c270c8e74d0f38832b4adce269c9d914ef21d2a0925e7772152dd793"),
    MMSFile(
        "tokenizer_config.json", 397,
        "42a65547cf0654d12263ece7c909c4b0c574b660c78658f806c772cc223bc01b"),
    MMSFile(
        "vocabs/asm.txt", 951,
        "2d80fe995b9318d33e1d15b46a9b7e7087761623e3f1c89cd120a8edbf158b01"),
)
MMS_TOTAL_BYTES = sum(item.size for item in MMS_FILES)
_MANIFEST = ".scripturesoundqc-verified.json"


class MMSPackError(RuntimeError):
    pass


class MMSPackCancelled(MMSPackError):
    pass


def mms_pack_dir() -> str:
    override = os.environ.get("BAC_MMS_CACHE", "").strip()
    if override:
        return os.path.abspath(os.path.expanduser(override))
    return os.path.join(
        os.path.expanduser("~"), ".bible_audio_checker", "models",
        MMS_PACK_KEY)


def _manifest_path(root: str) -> str:
    return os.path.join(root, _MANIFEST)


def _file_url(relative_path: str) -> str:
    encoded = "/".join(
        urllib.parse.quote(part)
        for part in relative_path.replace("\\", "/").split("/"))
    return (
        "https://huggingface.co/%s/resolve/%s/%s?download=true" %
        (MMS_REPO_ID, MMS_REVISION, encoded))


def _sha256_file(
        path: str,
        progress_callback: Optional[Callable[[int], None]] = None,
        cancel_callback: Optional[Callable[[], bool]] = None) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            if cancel_callback and cancel_callback():
                raise MMSPackCancelled(
                    "Model verification paused. It can be resumed later.")
            block = stream.read(8 * 1024 * 1024)
            if not block:
                break
            digest.update(block)
            if progress_callback:
                progress_callback(len(block))
    return digest.hexdigest().lower()


def _manifest_valid(root: str) -> bool:
    try:
        with open(_manifest_path(root), "r", encoding="utf-8") as stream:
            manifest = json.load(stream)
    except (OSError, ValueError, TypeError):
        return False
    if manifest.get("revision") != MMS_REVISION:
        return False
    for item in MMS_FILES:
        path = os.path.join(root, item.relative_path)
        if not os.path.isfile(path) or os.path.getsize(path) != item.size:
            return False
    return True


def is_mms_pack_installed(root: str = "") -> bool:
    return _manifest_valid(root or mms_pack_dir())


def partial_mms_bytes(root: str = "") -> int:
    root = root or mms_pack_dir()
    total = 0
    for item in MMS_FILES:
        final_path = os.path.join(root, item.relative_path)
        partial_path = final_path + ".part"
        if os.path.isfile(final_path):
            total += min(os.path.getsize(final_path), item.size)
        elif os.path.isfile(partial_path):
            total += min(os.path.getsize(partial_path), item.size)
    return total


def verify_mms_pack(
        root: str = "", progress_callback=None,
        cancel_callback=None) -> bool:
    root = root or mms_pack_dir()
    completed = 0
    for item in MMS_FILES:
        path = os.path.join(root, item.relative_path)
        if not os.path.isfile(path) or os.path.getsize(path) != item.size:
            return False

        def on_block(size: int) -> None:
            nonlocal completed
            completed += size
            if progress_callback:
                progress_callback(completed, MMS_TOTAL_BYTES)

        if _sha256_file(
                path, progress_callback=on_block,
                cancel_callback=cancel_callback) != item.sha256:
            return False

    manifest = {
        "key": MMS_PACK_KEY,
        "repository": MMS_REPO_ID,
        "revision": MMS_REVISION,
        "verified_at": time.time(),
        "files": {
            item.relative_path: {
                "size": item.size, "sha256": item.sha256}
            for item in MMS_FILES
        },
    }
    os.makedirs(root, exist_ok=True)
    temporary = _manifest_path(root) + ".tmp"
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, _manifest_path(root))
    return True


def _download_one(
        item: MMSFile, root: str, base_completed: int,
        started: float, progress_callback=None,
        cancel_callback=None) -> int:
    destination = os.path.join(root, item.relative_path)
    partial = destination + ".part"
    os.makedirs(os.path.dirname(destination), exist_ok=True)

    if (
            os.path.isfile(destination) and
            os.path.getsize(destination) == item.size):
        return item.size
    if os.path.isfile(destination):
        os.remove(destination)

    existing = os.path.getsize(partial) if os.path.isfile(partial) else 0
    if existing > item.size:
        os.remove(partial)
        existing = 0

    request = urllib.request.Request(
        _file_url(item.relative_path),
        headers={
            "User-Agent": "ScriptureSoundQC/4",
            **({"Range": "bytes=%d-" % existing} if existing else {}),
        })
    try:
        response = urllib.request.urlopen(request, timeout=120)
    except Exception as exc:
        raise MMSPackError(
            "Could not download %s: %s" % (item.relative_path, exc))

    resumed = bool(existing and getattr(response, "status", None) == 206)
    if not resumed:
        existing = 0
    mode = "ab" if resumed else "wb"
    completed = existing
    try:
        with response, open(partial, mode) as output:
            while True:
                if cancel_callback and cancel_callback():
                    raise MMSPackCancelled(
                        "Download paused. It can be resumed later.")
                block = response.read(4 * 1024 * 1024)
                if not block:
                    break
                output.write(block)
                completed += len(block)
                if progress_callback:
                    progress_callback(
                        "downloading", base_completed + completed,
                        MMS_TOTAL_BYTES, time.monotonic() - started)
            output.flush()
            os.fsync(output.fileno())
    except MMSPackCancelled:
        raise
    except Exception as exc:
        raise MMSPackError(
            "Download interrupted while receiving %s: %s" %
            (item.relative_path, exc))

    if completed != item.size:
        raise MMSPackError(
            "%s was incomplete (%d of %d bytes). Download it again to "
            "resume." % (item.relative_path, completed, item.size))
    os.replace(partial, destination)
    return completed


def download_mms_pack(
        root: str = "", progress_callback=None,
        cancel_callback=None) -> Tuple[str, int, float]:
    root = root or mms_pack_dir()
    os.makedirs(root, exist_ok=True)
    remaining = max(0, MMS_TOTAL_BYTES - partial_mms_bytes(root))
    required_free = remaining + 512 * 1024**2
    if shutil.disk_usage(root).free < required_free:
        raise MMSPackError(
            "Not enough free disk space for Meta MMS Assamese. "
            "Approximately %.2f GB is required." %
            (required_free / float(1024**3)))
    started = time.monotonic()
    completed = 0
    for item in MMS_FILES:
        completed += _download_one(
            item, root, completed, started,
            progress_callback=progress_callback,
            cancel_callback=cancel_callback)

    if progress_callback:
        progress_callback(
            "verifying", 0, MMS_TOTAL_BYTES,
            time.monotonic() - started)

    def verify_progress(done: int, total: int) -> None:
        if progress_callback:
            progress_callback(
                "verifying", done, total,
                time.monotonic() - started)

    if not verify_mms_pack(
            root, progress_callback=verify_progress,
            cancel_callback=cancel_callback):
        raise MMSPackError(
            "Meta MMS checksum verification failed. The pack was not "
            "activated.")
    return root, completed, time.monotonic() - started


def remove_mms_pack(root: str = "") -> bool:
    root = os.path.abspath(root or mms_pack_dir())
    expected_name = MMS_PACK_KEY.lower()
    if os.path.basename(root).lower() != expected_name:
        raise MMSPackError("Refusing to remove an unexpected model folder.")
    if not os.path.isdir(root):
        return False
    shutil.rmtree(root)
    return True
