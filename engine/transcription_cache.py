"""Persistent cache for expensive local Whisper word timelines."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Dict, List, Optional


CACHE_SCHEMA = 1
DECODE_PROFILE = "independent-windows-v1"


def transcript_cache_dir() -> str:
    override = os.environ.get("BAC_TRANSCRIPT_CACHE", "").strip()
    if override:
        return os.path.abspath(os.path.expanduser(override))
    return os.path.join(
        os.path.expanduser("~"), ".bible_audio_checker", "transcripts")


def _cache_identity(
        wav_path: str, language: str, model: str,
        script_prompt: str = "") -> Dict:
    stat = os.stat(wav_path)
    return {
        "schema": CACHE_SCHEMA,
        "profile": DECODE_PROFILE,
        "path": os.path.abspath(wav_path),
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "language": (language or "").strip().lower(),
        "model": (model or "").strip().lower(),
        "prompt_sha256": hashlib.sha256(
            (script_prompt or "").encode("utf-8")).hexdigest(),
    }


def transcript_cache_path(
        wav_path: str, language: str, model: str,
        script_prompt: str = "", cache_dir: str = "") -> str:
    identity = _cache_identity(
        wav_path, language, model, script_prompt)
    digest = hashlib.sha256(
        json.dumps(
            identity, sort_keys=True,
            separators=(",", ":")).encode("utf-8")).hexdigest()
    return os.path.join(
        cache_dir or transcript_cache_dir(), digest + ".json")


def load_cached_timeline(
        wav_path: str, language: str, model: str,
        script_prompt: str = "", cache_dir: str = ""
        ) -> Optional[List[Dict]]:
    identity = _cache_identity(
        wav_path, language, model, script_prompt)
    path = transcript_cache_path(
        wav_path, language, model, script_prompt, cache_dir)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as stream:
            payload = json.load(stream)
        if payload.get("identity") != identity:
            return None
        words = payload.get("words")
        return words if isinstance(words, list) else None
    except Exception:
        return None


def save_cached_timeline(
        wav_path: str, language: str, model: str,
        words: List[Dict], script_prompt: str = "", cache_dir: str = ""
        ) -> str:
    directory = cache_dir or transcript_cache_dir()
    os.makedirs(directory, exist_ok=True)
    path = transcript_cache_path(
        wav_path, language, model, script_prompt, directory)
    temporary = path + ".tmp"
    payload = {
        "identity": _cache_identity(
            wav_path, language, model, script_prompt),
        "words": list(words),
    }
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False)
    os.replace(temporary, path)
    return path
