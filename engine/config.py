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

    # ---------------------------------------------------------------------------
    # Toggle-able checks — enable/disable entire check categories
    # ---------------------------------------------------------------------------
    enable_format: bool = True         # check sample rate / bit depth
    enable_loudness: bool = True       # check integrated LUFS
    enable_true_peak: bool = True      # check true peak dBTP
    enable_head_silence: bool = True   # check head silence duration
    enable_tail_silence: bool = True   # check tail silence duration
    enable_markers: bool = True        # check marker presence, spelling, chapter title
    enable_verses: bool = True         # check verse completeness against KJV DB
    enable_script_verification: bool = False  # compare audio transcription against PDF script

    # ---------------------------------------------------------------------------
    # VST3 plugin settings
    # ---------------------------------------------------------------------------
    use_vst_plugins: bool = False      # toggle to use VSTs instead of built-in effects
    vst_compressor_path: str = ""      # path to user's compressor VST3 plugin
    vst_limiter_path: str = ""         # path to user's limiter VST3 plugin
    vst_eq_path: str = ""              # path to user's EQ VST3 plugin

    # ---------------------------------------------------------------------------
    # Script verification settings
    # ---------------------------------------------------------------------------
    whisper_mode: str = "local"        # "local" (openai-whisper) or "api" (OpenAI API)
    whisper_model: str = "medium"      # local model size: tiny, base, small, medium, large
    whisper_language: str = ""         # language code (e.g. "hi", "ta", "te") — empty = auto-detect
    openai_api_key: str = ""           # API key for OpenAI Whisper API mode
    script_match_threshold: float = 0.6  # minimum similarity ratio to consider a match (0.0-1.0)

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
