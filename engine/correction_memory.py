"""
correction_memory.py - learning system for auto-marker corrections.

Stores corrections in ~/.bible_audio_checker/corrections.json and uses
accumulated data to improve future auto-marking accuracy.

The system tracks:
  - Per-language, per-reader patterns (average pause between verses, reading speed)
  - Individual corrections (expected vs corrected marker positions)
  - Derived adjustment factors (speed factor, pause duration bias)

Over time, the system learns:
  - How much earlier/later markers should be placed for a given language/reader
  - Typical pause durations between verses
  - Reading speed factors relative to the model's initial estimates
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional


@dataclass
class Correction:
    """A single marker correction made by the user."""
    language: str
    verse_number: int
    expected_time: float      # time (seconds) where auto-marker placed it
    corrected_time: float     # time (seconds) where user moved it
    reader_id: str = ""       # optional reader identifier
    timestamp: float = 0.0    # when the correction was made

    @property
    def offset(self) -> float:
        """How much the marker was moved (positive = later, negative = earlier)."""
        return self.corrected_time - self.expected_time

    @property
    def speed_factor(self) -> float:
        """Ratio of corrected to expected position (>1 means reader is slower)."""
        if self.expected_time <= 0:
            return 1.0
        return self.corrected_time / self.expected_time


@dataclass
class LanguageProfile:
    """Accumulated learning data for a specific language/reader combination."""
    language: str
    reader_id: str = ""
    total_corrections: int = 0
    average_offset_s: float = 0.0       # average time offset of corrections
    average_speed_factor: float = 1.0   # average reading speed factor
    average_pause_duration: float = 0.5 # learned average pause between verses
    corrections: List[Dict] = field(default_factory=list)

    def add_correction(self, correction: Correction) -> None:
        """Add a correction and update running averages."""
        self.corrections.append(asdict(correction))
        self.total_corrections = len(self.corrections)

        # Update running averages
        offsets = [c["corrected_time"] - c["expected_time"] for c in self.corrections]
        self.average_offset_s = sum(offsets) / len(offsets) if offsets else 0.0

        factors = []
        for c in self.corrections:
            if c["expected_time"] > 0:
                factors.append(c["corrected_time"] / c["expected_time"])
        self.average_speed_factor = sum(factors) / len(factors) if factors else 1.0

    def get_adjustment(self, verse_number: int, estimated_time: float) -> float:
        """Get the suggested adjusted time for a verse marker.

        Uses learned patterns to suggest where the marker should really be placed.
        Returns the adjusted time in seconds.
        """
        if self.total_corrections == 0:
            return estimated_time

        # Apply average speed factor and offset
        adjusted = estimated_time * self.average_speed_factor
        adjusted += self.average_offset_s * 0.5  # partial offset (damped)

        # Look for verse-specific corrections
        verse_corrections = [c for c in self.corrections
                             if c["verse_number"] == verse_number]
        if verse_corrections:
            # Use the most recent correction for this specific verse
            latest = verse_corrections[-1]
            verse_offset = latest["corrected_time"] - latest["expected_time"]
            # Blend verse-specific offset (weighted more heavily)
            adjusted = estimated_time + verse_offset * 0.7 + self.average_offset_s * 0.3

        return max(0.0, adjusted)


class CorrectionMemory:
    """Persistent correction memory system.

    Stores all correction data in ~/.bible_audio_checker/corrections.json.
    Provides adjustment suggestions based on accumulated learning.
    """

    def __init__(self, storage_path: Optional[str] = None):
        if storage_path is None:
            base = os.path.join(os.path.expanduser("~"), ".bible_audio_checker")
            os.makedirs(base, exist_ok=True)
            storage_path = os.path.join(base, "corrections.json")
        self.storage_path = storage_path
        self.profiles: Dict[str, LanguageProfile] = {}
        self._load()

    def _profile_key(self, language: str, reader_id: str = "") -> str:
        """Generate a unique key for a language/reader combination."""
        return "%s:%s" % (language or "unknown", reader_id or "default")

    def _load(self) -> None:
        """Load corrections from disk."""
        if not os.path.isfile(self.storage_path):
            return
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for key, profile_data in data.get("profiles", {}).items():
                profile = LanguageProfile(
                    language=profile_data.get("language", ""),
                    reader_id=profile_data.get("reader_id", ""),
                    total_corrections=profile_data.get("total_corrections", 0),
                    average_offset_s=profile_data.get("average_offset_s", 0.0),
                    average_speed_factor=profile_data.get("average_speed_factor", 1.0),
                    average_pause_duration=profile_data.get("average_pause_duration", 0.5),
                    corrections=profile_data.get("corrections", []),
                )
                self.profiles[key] = profile
        except (json.JSONDecodeError, OSError):
            # Corrupted file, start fresh
            self.profiles = {}

    def _save(self) -> None:
        """Persist corrections to disk."""
        data = {
            "version": 1,
            "profiles": {}
        }
        for key, profile in self.profiles.items():
            data["profiles"][key] = {
                "language": profile.language,
                "reader_id": profile.reader_id,
                "total_corrections": profile.total_corrections,
                "average_offset_s": profile.average_offset_s,
                "average_speed_factor": profile.average_speed_factor,
                "average_pause_duration": profile.average_pause_duration,
                "corrections": profile.corrections,
            }
        try:
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except OSError:
            pass  # fail silently if we cannot write

    def add_correction(self, language: str, verse_number: int,
                       expected_time: float, corrected_time: float,
                       reader_id: str = "") -> None:
        """Record a user correction for a marker position.

        Args:
            language: language code (e.g. "hi", "ta")
            verse_number: which verse marker was corrected
            expected_time: time in seconds where auto-marker placed it
            corrected_time: time in seconds where user moved it
            reader_id: optional reader/narrator identifier
        """
        key = self._profile_key(language, reader_id)
        if key not in self.profiles:
            self.profiles[key] = LanguageProfile(
                language=language, reader_id=reader_id)

        correction = Correction(
            language=language,
            verse_number=verse_number,
            expected_time=expected_time,
            corrected_time=corrected_time,
            reader_id=reader_id,
            timestamp=time.time(),
        )
        self.profiles[key].add_correction(correction)
        self._save()

    def add_pause_observation(self, language: str, pause_duration: float,
                              reader_id: str = "") -> None:
        """Record an observed pause duration between verses.

        Used to learn typical inter-verse pause patterns for a reader.
        """
        key = self._profile_key(language, reader_id)
        if key not in self.profiles:
            self.profiles[key] = LanguageProfile(
                language=language, reader_id=reader_id)

        profile = self.profiles[key]
        # Exponential moving average of pause durations
        alpha = 0.3  # learning rate
        profile.average_pause_duration = (
            alpha * pause_duration + (1 - alpha) * profile.average_pause_duration
        )
        self._save()

    def get_adjustment(self, language: str, verse_number: int,
                       estimated_time: float, reader_id: str = "") -> float:
        """Get the adjusted marker time based on learned patterns.

        Returns:
            Adjusted time in seconds. If no corrections exist for this
            language/reader, returns the estimated_time unchanged.
        """
        key = self._profile_key(language, reader_id)
        profile = self.profiles.get(key)
        if profile is None:
            return estimated_time
        return profile.get_adjustment(verse_number, estimated_time)

    def get_speed_factor(self, language: str, reader_id: str = "") -> float:
        """Get the learned reading speed factor for a language/reader.

        Returns:
            Speed factor (1.0 = no adjustment, >1.0 = slower reader,
            <1.0 = faster reader).
        """
        key = self._profile_key(language, reader_id)
        profile = self.profiles.get(key)
        if profile is None:
            return 1.0
        return profile.average_speed_factor

    def get_pause_duration(self, language: str, reader_id: str = "") -> float:
        """Get the learned average pause duration between verses.

        Returns:
            Average pause in seconds (default 0.5 if no data).
        """
        key = self._profile_key(language, reader_id)
        profile = self.profiles.get(key)
        if profile is None:
            return 0.5
        return profile.average_pause_duration

    def get_profile_summary(self, language: str, reader_id: str = "") -> str:
        """Get a human-readable summary of learned patterns."""
        key = self._profile_key(language, reader_id)
        profile = self.profiles.get(key)
        if profile is None:
            return "No corrections recorded for %s." % language
        return (
            "Language: %s | Reader: %s\n"
            "  Corrections: %d\n"
            "  Average offset: %.3fs\n"
            "  Speed factor: %.3f\n"
            "  Average pause: %.3fs"
            % (profile.language, profile.reader_id or "default",
               profile.total_corrections, profile.average_offset_s,
               profile.average_speed_factor, profile.average_pause_duration)
        )

    def has_data(self, language: str, reader_id: str = "") -> bool:
        """Check if any correction data exists for the given language/reader."""
        key = self._profile_key(language, reader_id)
        return key in self.profiles and self.profiles[key].total_corrections > 0

    def clear(self, language: str = "", reader_id: str = "") -> None:
        """Clear correction data. If no arguments, clears all data."""
        if not language:
            self.profiles = {}
        else:
            key = self._profile_key(language, reader_id)
            self.profiles.pop(key, None)
        self._save()


if __name__ == "__main__":
    # Demo / test
    mem = CorrectionMemory()
    print("Correction Memory")
    print("Storage: %s" % mem.storage_path)
    print("Profiles: %d" % len(mem.profiles))
    for key, profile in mem.profiles.items():
        print("  %s: %d corrections" % (key, profile.total_corrections))
