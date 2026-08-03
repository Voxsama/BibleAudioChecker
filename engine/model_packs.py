"""Install and manage local multilingual Whisper model packs.

The desktop application bundles the Whisper runtime, but model weights remain
optional downloads because the accuracy model is several gigabytes. Downloads
are resumable, checksum-verified, and atomically moved into Whisper's cache.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import sys
import time
import urllib.request
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional


class ModelPackError(RuntimeError):
    pass


class ModelPackCancelled(ModelPackError):
    pass


@dataclass(frozen=True)
class ModelPack:
    key: str
    display_name: str
    description: str
    approx_bytes: int
    url: str
    sha256: str
    filename: str
    recommended: bool = False
    backend: str = "whisper"

    def path(self, cache_dir: str = "") -> str:
        if self.backend == "mms":
            from .mms_pack import mms_pack_dir
            return mms_pack_dir()
        return os.path.join(
            cache_dir or model_cache_dir(), self.filename)


@dataclass
class ModelPackDownloadResult:
    pack: ModelPack
    path: str
    bytes_downloaded: int
    elapsed_s: float
    verified: bool


_PACK_METADATA = {
    "tiny": (
        "Tiny multilingual", "Fast preview; lowest accuracy.",
        75 * 1024**2, False),
    "base": (
        "Base multilingual", "Small download for basic testing.",
        142 * 1024**2, False),
    "small": (
        "Small multilingual", "Balanced for lower-memory computers.",
        466 * 1024**2, False),
    "medium": (
        "Medium multilingual", "Good balance of speed and accuracy.",
        1530 * 1024**2, False),
    "turbo": (
        "Large-v3 Turbo", "Faster transcription with somewhat lower accuracy.",
        1620 * 1024**2, False),
    "large-v3": (
        "Large-v3", "Best general multilingual Whisper accuracy.",
        3100 * 1024**2, False),
}

_OFFICIAL_MODEL_URLS = {
    "tiny": (
        "https://openaipublic.azureedge.net/main/whisper/models/"
        "65147644a518d12f04e32d6f3b26facc3f8dd46e5390956a9424a650c0ce22b9/"
        "tiny.pt"),
    "base": (
        "https://openaipublic.azureedge.net/main/whisper/models/"
        "ed3a0b6b1c0edf879ad9b11b1af5a0e6ab5db9205f891f668f8b0e6c6326e34e/"
        "base.pt"),
    "small": (
        "https://openaipublic.azureedge.net/main/whisper/models/"
        "9ecf779972d90ba49c06d968637d720dd632c55bbf19d441fb42bf17a411e794/"
        "small.pt"),
    "medium": (
        "https://openaipublic.azureedge.net/main/whisper/models/"
        "345ae4da62f9b3d59415adc60127b97c714f32e89e936602e85993674d08dcb1/"
        "medium.pt"),
    "turbo": (
        "https://openaipublic.azureedge.net/main/whisper/models/"
        "aff26ae408abcba5fbf8813c21e62b0941638c5f6eebfb145be0c9839262a19a/"
        "large-v3-turbo.pt"),
    "large-v3": (
        "https://openaipublic.azureedge.net/main/whisper/models/"
        "e5b1a55b89c1367dacf97e3e19bfd829a01529dbfdeefa8caeb59b3f1b81dadb/"
        "large-v3.pt"),
}


def model_cache_dir() -> str:
    override = os.environ.get("BAC_WHISPER_CACHE", "").strip()
    if override:
        return os.path.abspath(os.path.expanduser(override))
    return os.path.join(os.path.expanduser("~"), ".cache", "whisper")


def _official_urls() -> Dict[str, str]:
    urls = dict(_OFFICIAL_MODEL_URLS)
    whisper = sys.modules.get("whisper")
    if whisper is not None:
        urls.update(dict(getattr(whisper, "_MODELS", {})))
    return urls


def available_model_packs() -> List[ModelPack]:
    urls = _official_urls()
    packs = []
    for key in ("tiny", "base", "small", "medium", "turbo", "large-v3"):
        url = urls.get(key, "")
        if not url:
            continue
        match = re.search(r"/([0-9a-f]{64})/([^/?]+)", url)
        if not match:
            continue
        display_name, description, approx_bytes, recommended = (
            _PACK_METADATA[key])
        packs.append(ModelPack(
            key=key,
            display_name=display_name,
            description=description,
            approx_bytes=approx_bytes,
            url=url,
            sha256=match.group(1),
            filename=match.group(2),
            recommended=recommended,
        ))
    from .mms_pack import MMS_PACK_KEY, MMS_TOTAL_BYTES
    packs.append(ModelPack(
        key=MMS_PACK_KEY,
        display_name="Meta MMS Assamese Precision",
        description=(
            "CTC scripture alignment for Assamese Auto-Mark; "
            "CC-BY-NC 4.0, non-commercial use only."),
        approx_bytes=MMS_TOTAL_BYTES,
        url="https://huggingface.co/facebook/mms-1b-all",
        sha256="",
        filename="",
        recommended=True,
        backend="mms",
    ))
    return packs


def get_model_pack(key: str) -> Optional[ModelPack]:
    normalized = (key or "").strip().lower()
    if normalized == "large":
        normalized = "large-v3"
    if normalized == "large-v3-turbo":
        normalized = "turbo"
    return next(
        (pack for pack in available_model_packs()
         if pack.key == normalized), None)


def is_model_pack_installed(
        key: str, cache_dir: str = "") -> bool:
    pack = get_model_pack(key)
    if pack and pack.backend == "mms":
        from .mms_pack import is_mms_pack_installed
        return is_mms_pack_installed()
    return bool(pack and os.path.isfile(pack.path(cache_dir)))


def verify_file(
        path: str, expected_sha256: str,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        cancel_callback: Optional[Callable[[], bool]] = None) -> bool:
    total = os.path.getsize(path)
    completed = 0
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            if cancel_callback and cancel_callback():
                raise ModelPackCancelled("Model verification cancelled.")
            chunk = stream.read(8 * 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            completed += len(chunk)
            if progress_callback:
                progress_callback(completed, total)
    return digest.hexdigest().lower() == expected_sha256.lower()


def verify_model_pack(key: str, cache_dir: str = "") -> bool:
    pack = get_model_pack(key)
    if not pack:
        return False
    if pack.backend == "mms":
        from .mms_pack import verify_mms_pack
        return verify_mms_pack()
    path = pack.path(cache_dir)
    return (
        os.path.isfile(path) and
        verify_file(path, pack.sha256))


def _download_pack(
        pack: ModelPack, cache_dir: str,
        progress_callback=None, cancel_callback=None
        ) -> ModelPackDownloadResult:
    os.makedirs(cache_dir, exist_ok=True)
    destination = pack.path(cache_dir)
    partial = destination + ".part"
    started = time.monotonic()

    if os.path.isfile(destination):
        existing_total = os.path.getsize(destination)

        def installed_progress(done, verify_total):
            if progress_callback:
                progress_callback(
                    "verifying", done, verify_total,
                    time.monotonic() - started)

        if verify_file(
                destination, pack.sha256,
                progress_callback=installed_progress,
                cancel_callback=cancel_callback):
            return ModelPackDownloadResult(
                pack=pack, path=destination, bytes_downloaded=0,
                elapsed_s=time.monotonic() - started, verified=True)
        os.remove(destination)

    existing = os.path.getsize(partial) if os.path.isfile(partial) else 0

    free_bytes = shutil.disk_usage(cache_dir).free
    required = max(pack.approx_bytes - existing, 0)
    if free_bytes < required + 256 * 1024**2:
        raise ModelPackError(
            "Not enough free disk space. Approximately %s is required." %
            format_bytes(required + 256 * 1024**2))

    headers = {"User-Agent": "ScriptureSoundQC/4"}
    if existing:
        headers["Range"] = "bytes=%d-" % existing
    request = urllib.request.Request(pack.url, headers=headers)
    try:
        response = urllib.request.urlopen(request, timeout=60)
    except Exception as exc:
        raise ModelPackError("Could not start model download: %s" % exc)

    status = getattr(response, "status", None)
    resumed = bool(existing and status == 206)
    if not resumed:
        existing = 0
    length_header = response.headers.get("Content-Length", "")
    remaining = int(length_header) if length_header.isdigit() else 0
    total = existing + remaining if remaining else pack.approx_bytes
    mode = "ab" if resumed else "wb"
    completed = existing

    try:
        with response, open(partial, mode) as output:
            while True:
                if cancel_callback and cancel_callback():
                    raise ModelPackCancelled(
                        "Download paused. It can be resumed later.")
                chunk = response.read(4 * 1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                completed += len(chunk)
                if progress_callback:
                    progress_callback(
                        "downloading", completed, total,
                        time.monotonic() - started)
            output.flush()
            os.fsync(output.fileno())

        if progress_callback:
            progress_callback(
                "verifying", 0, completed,
                time.monotonic() - started)

        def verify_progress(done, verify_total):
            if progress_callback:
                progress_callback(
                    "verifying", done, verify_total,
                    time.monotonic() - started)

        verified = verify_file(
            partial, pack.sha256,
            progress_callback=verify_progress,
            cancel_callback=cancel_callback)
        if not verified:
            try:
                os.remove(partial)
            except OSError:
                pass
            raise ModelPackError(
                "Checksum verification failed. The incomplete download was "
                "removed; please try again.")
        os.replace(partial, destination)
        return ModelPackDownloadResult(
            pack=pack,
            path=destination,
            bytes_downloaded=completed,
            elapsed_s=time.monotonic() - started,
            verified=True)
    except ModelPackCancelled:
        raise
    except ModelPackError:
        raise
    except Exception as exc:
        raise ModelPackError("Model download failed: %s" % exc)


def download_model_pack(
        key: str, cache_dir: str = "",
        progress_callback=None, cancel_callback=None
        ) -> ModelPackDownloadResult:
    pack = get_model_pack(key)
    if not pack:
        raise ModelPackError("Unknown AI model pack: %s" % key)
    if pack.backend == "mms":
        from .mms_pack import (
            MMSPackCancelled, MMSPackError, download_mms_pack)
        try:
            path, downloaded, elapsed = download_mms_pack(
                progress_callback=progress_callback,
                cancel_callback=cancel_callback)
        except MMSPackCancelled as exc:
            raise ModelPackCancelled(str(exc))
        except MMSPackError as exc:
            raise ModelPackError(str(exc))
        return ModelPackDownloadResult(
            pack=pack, path=path, bytes_downloaded=downloaded,
            elapsed_s=elapsed, verified=True)
    return _download_pack(
        pack, cache_dir or model_cache_dir(),
        progress_callback=progress_callback,
        cancel_callback=cancel_callback)


def remove_model_pack(key: str, cache_dir: str = "") -> bool:
    pack = get_model_pack(key)
    if not pack:
        return False
    if pack.backend == "mms":
        from .mms_pack import remove_mms_pack
        return remove_mms_pack()
    removed = False
    for path in (pack.path(cache_dir), pack.path(cache_dir) + ".part"):
        if os.path.isfile(path):
            os.remove(path)
            removed = True
    return removed


def model_pack_partial_bytes(key: str, cache_dir: str = "") -> int:
    pack = get_model_pack(key)
    if not pack:
        return 0
    if pack.backend == "mms":
        from .mms_pack import partial_mms_bytes
        return partial_mms_bytes()
    partial = pack.path(cache_dir or model_cache_dir()) + ".part"
    return os.path.getsize(partial) if os.path.isfile(partial) else 0


def format_bytes(value: int) -> str:
    amount = float(max(0, value))
    for suffix in ("B", "KB", "MB", "GB", "TB"):
        if amount < 1024.0 or suffix == "TB":
            return (
                "%.0f %s" % (amount, suffix)
                if suffix == "B" else "%.2f %s" % (amount, suffix))
        amount /= 1024.0
    return "%.2f TB" % amount
