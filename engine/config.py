"""
config.py — user-editable settings with sane defaults, persisted to a JSON file
next to the app so studio-specific thresholds survive restarts.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict


@dataclass
class Config:
    # Loudness
    target_lufs: float = -18.0
    lufs_tolerance: float = 0.5        # pass if |measured - target| <= tolerance
    true_peak_max: float = -1.0        # pass if measured true peak <= this (dBTP)

    # Silence (head + tail)
    silence_seconds: float = 2.0
    silence_tolerance: float = 0.5     # seconds
    silence_threshold_dbfs: float = -60.0

    # Format (the studio spec)
    expected_sample_rate: int = 48000
    expected_bits: int = 24
    check_format: bool = True

    # Marker names (literal words). Comparison is case-insensitive, trimmed.
    chapter_title_name: str = "Chapter Title"
    heading_name: str = "Heading"
    verse_word: str = "Verse"          # verse markers look like "Verse 1", "Verse 2"...

    # Behaviour
    require_chapter_title: bool = True
    require_heading: bool = False      # headings are optional / vary by chapter
    strict_verse_spelling: bool = True # flag "Vers 3", "verse3", wrong casing, etc.

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls, path: str) -> "Config":
        if not os.path.isfile(path):
            return cls()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
            return cls(**known)
        except Exception:
            return cls()


def default_config_path() -> str:
    base = os.path.join(os.path.expanduser("~"), ".bible_audio_checker")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "config.json")
