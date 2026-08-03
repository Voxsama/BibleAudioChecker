"""Alignment backend registry used by the GUI and auto-marker engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class AlignmentBackend:
    key: str
    name: str
    description: str
    requires_transcription: bool
    available: bool = True


_BACKENDS: Dict[str, AlignmentBackend] = {
    "auto": AlignmentBackend(
        "auto", "Automatic (recommended)",
        "Use script-to-speech alignment when available, then pause fallback.",
        True),
    "whisper-script": AlignmentBackend(
        "whisper-script", "Whisper + Bible script",
        "Align timestamped transcription to the selected language script.",
        True),
    "pause": AlignmentBackend(
        "pause", "Pause draft (offline fallback)",
        "Estimate verse starts from silence and spacing; always requires review.",
        False),
}


def alignment_backends() -> List[AlignmentBackend]:
    return list(_BACKENDS.values())


def get_alignment_backend(key: str) -> AlignmentBackend:
    return _BACKENDS.get(key, _BACKENDS["auto"])

