"""
transcriber.py — speech-to-text engine for Bible audio verification.

Two modes:
  1. LOCAL: uses openai-whisper (runs on CPU/GPU locally, no internet needed)
  2. API:   uses OpenAI's Whisper API (requires API key + internet, better accuracy)

Supports all Indian languages via Whisper's multilingual models:
  Hindi, Tamil, Telugu, Kannada, Malayalam, Bengali, Marathi, Gujarati,
  Punjabi, Urdu, Odia, Assamese, Nepali, Sanskrit, etc.

Usage:
  transcriber = Transcriber(mode="local", model="medium", language="hi")
  result = transcriber.transcribe_segment(wav_path, start_s=12.5, end_s=45.2)
  print(result.text)
"""

from __future__ import annotations

import os
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .wavio import read_wav_info, read_pcm


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------
@dataclass
class TranscriptionSegment:
    """A single transcribed audio segment."""
    verse_number: int = 0          # which verse this segment corresponds to
    start_s: float = 0.0           # start time in the WAV
    end_s: float = 0.0             # end time in the WAV
    text: str = ""                 # transcribed text
    language: str = ""             # detected/specified language
    confidence: float = 0.0        # average confidence (0.0-1.0) if available


@dataclass
class TranscriptionResult:
    """Full transcription result for a file."""
    segments: List[TranscriptionSegment] = field(default_factory=list)
    full_text: str = ""
    language: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and len(self.segments) > 0


class TranscriberError(RuntimeError):
    pass


def _missing_dependency_message(display_name: str, pip_name: str) -> str:
    """Return an actionable dependency message for source or packaged runs."""
    if getattr(sys, "frozen", False):
        return ("%s is missing from this installation. Reinstall ScriptureSound QC "
                "using the complete Windows installer." % display_name)
    return ("%s is not installed. Install with: pip install %s" %
            (display_name, pip_name))


# ---------------------------------------------------------------------------
# Audio segment extraction (write a temp WAV for a time range)
# ---------------------------------------------------------------------------
def _extract_segment_wav(src_path: str, start_s: float, end_s: float,
                         dst_path: str) -> None:
    """Extract a time range from a WAV file and write it as a new WAV.

    Uses raw PCM reading from wavio to handle 24-bit/EXTENSIBLE formats.
    Writes a standard 16-bit PCM WAV that Whisper can read.
    """
    info = read_wav_info(src_path)
    sr = info.sample_rate
    sw = info.sampwidth
    ch = info.channels

    start_frame = max(0, int(start_s * sr))
    end_frame = min(info.n_frames, int(end_s * sr))
    n_frames = end_frame - start_frame

    if n_frames <= 0:
        raise TranscriberError("Segment is empty (%.2fs - %.2fs)" % (start_s, end_s))

    raw = read_pcm(src_path, info, start_frame, n_frames)

    # Convert to 16-bit mono PCM for Whisper compatibility
    samples_16 = _to_16bit_mono(raw, sw, ch)

    # Write standard WAV header + data
    _write_wav_16bit(dst_path, samples_16, sr)


def _to_16bit_mono(raw: bytes, sw: int, ch: int) -> bytes:
    """Convert raw PCM bytes (any bit depth, any channels) to 16-bit mono."""
    # First: decode to list of integers at original bit depth
    frame_count = len(raw) // (sw * ch)
    samples = []

    for i in range(frame_count):
        # Take only channel 0 (mono-ify by taking first channel)
        offset = i * sw * ch
        sample_bytes = raw[offset:offset + sw]

        if sw == 1:
            # 8-bit unsigned
            val = struct.unpack("<B", sample_bytes)[0] - 128
            val = int(val * 256)  # scale to 16-bit range
        elif sw == 2:
            # 16-bit signed
            val = struct.unpack("<h", sample_bytes)[0]
        elif sw == 3:
            # 24-bit signed (little-endian)
            b = sample_bytes
            val = b[0] | (b[1] << 8) | (b[2] << 16)
            if val & 0x800000:
                val -= 0x1000000
            val = val >> 8  # scale 24-bit to 16-bit
        elif sw == 4:
            # 32-bit signed
            val = struct.unpack("<i", sample_bytes)[0]
            val = val >> 16  # scale to 16-bit
        else:
            val = 0

        # Clamp to int16 range
        val = max(-32768, min(32767, val))
        samples.append(val)

    # Pack as 16-bit little-endian
    return struct.pack("<%dh" % len(samples), *samples)


def _write_wav_16bit(path: str, pcm_data: bytes, sample_rate: int) -> None:
    """Write a standard 16-bit mono PCM WAV file."""
    n_channels = 1
    bits = 16
    byte_rate = sample_rate * n_channels * (bits // 8)
    block_align = n_channels * (bits // 8)
    data_size = len(pcm_data)
    file_size = 36 + data_size

    with open(path, "wb") as f:
        # RIFF header
        f.write(b"RIFF")
        f.write(struct.pack("<I", file_size))
        f.write(b"WAVE")
        # fmt chunk
        f.write(b"fmt ")
        f.write(struct.pack("<I", 16))  # chunk size
        f.write(struct.pack("<HHIIHH", 1, n_channels, sample_rate,
                            byte_rate, block_align, bits))
        # data chunk
        f.write(b"data")
        f.write(struct.pack("<I", data_size))
        f.write(pcm_data)


# ---------------------------------------------------------------------------
# Transcriber class
# ---------------------------------------------------------------------------
class Transcriber:
    """Speech-to-text transcriber with local (Whisper) and API modes."""

    def __init__(self, mode: str = "local", model: str = "medium",
                 language: str = "", api_key: str = ""):
        """
        Args:
            mode: "local" for openai-whisper, "api" for OpenAI API
            model: model size for local mode (tiny, base, small, medium, large)
            language: language code (e.g. "hi", "ta") or "" for auto-detect
            api_key: OpenAI API key (required for api mode)
        """
        self.mode = mode
        self.model_name = model
        self.language = language
        self.api_key = api_key
        self._local_model = None  # lazy-loaded

    def is_available(self) -> bool:
        """Check if the transcription backend is available."""
        if self.mode == "local":
            return _whisper_local_available()
        elif self.mode == "api":
            return bool(self.api_key) and _openai_available()
        return False

    def get_availability_message(self) -> str:
        """Human-readable message about availability."""
        if self.mode == "local":
            if not _whisper_local_available():
                return _missing_dependency_message("openai-whisper", "openai-whisper")
            return "Local Whisper model '%s' ready." % self.model_name
        elif self.mode == "api":
            if not self.api_key:
                return "OpenAI API key not configured."
            if not _openai_available():
                return _missing_dependency_message("OpenAI API support", "openai")
            return "OpenAI Whisper API ready."
        return "Unknown mode: %s" % self.mode

    def transcribe_file(self, wav_path: str) -> TranscriptionResult:
        """Transcribe an entire WAV file."""
        if self.mode == "local":
            return self._transcribe_local_full(wav_path)
        elif self.mode == "api":
            return self._transcribe_api_full(wav_path)
        return TranscriptionResult(error="Unknown mode: %s" % self.mode)

    def transcribe_segment(self, wav_path: str, start_s: float,
                           end_s: float, verse_number: int = 0) -> TranscriptionSegment:
        """Transcribe a specific time segment of a WAV file."""
        tmp_dir = tempfile.mkdtemp(prefix="bac_seg_")
        tmp_wav = os.path.join(tmp_dir, "segment.wav")

        try:
            _extract_segment_wav(wav_path, start_s, end_s, tmp_wav)

            if self.mode == "local":
                result = self._transcribe_local_full(tmp_wav)
            elif self.mode == "api":
                result = self._transcribe_api_full(tmp_wav)
            else:
                return TranscriptionSegment(
                    verse_number=verse_number, start_s=start_s, end_s=end_s)

            text = result.full_text if result.ok else ""
            return TranscriptionSegment(
                verse_number=verse_number,
                start_s=start_s,
                end_s=end_s,
                text=text,
                language=result.language or self.language,
            )
        except Exception as e:
            return TranscriptionSegment(
                verse_number=verse_number, start_s=start_s, end_s=end_s,
                text="[ERROR: %s]" % str(e))
        finally:
            # Cleanup
            try:
                os.remove(tmp_wav)
                os.rmdir(tmp_dir)
            except OSError:
                pass

    def transcribe_segments(self, wav_path: str,
                            segments: List[Tuple[float, float, int]]
                            ) -> List[TranscriptionSegment]:
        """Transcribe multiple segments. Each tuple is (start_s, end_s, verse_num).

        For local mode, it's more efficient to transcribe the whole file once
        and then map segments to the word-level timestamps.
        """
        if self.mode == "local" and _whisper_local_available():
            return self._transcribe_local_segments(wav_path, segments)

        # Fallback: transcribe each segment individually
        results = []
        for start_s, end_s, verse_num in segments:
            seg = self.transcribe_segment(wav_path, start_s, end_s, verse_num)
            results.append(seg)
        return results

    # ---------------------------------------------------------------------------
    # Local Whisper
    # ---------------------------------------------------------------------------
    def _get_local_model(self):
        """Lazy-load the local Whisper model."""
        if self._local_model is None:
            import whisper
            self._local_model = whisper.load_model(self.model_name)
        return self._local_model

    def _transcribe_local_full(self, wav_path: str) -> TranscriptionResult:
        """Transcribe using local openai-whisper."""
        try:
            import whisper
        except ImportError:
            return TranscriptionResult(
                error=_missing_dependency_message("openai-whisper", "openai-whisper"))

        try:
            model = self._get_local_model()
            options = {}
            if self.language:
                options["language"] = self.language

            result = model.transcribe(wav_path, **options)

            segments = []
            for seg in result.get("segments", []):
                segments.append(TranscriptionSegment(
                    start_s=seg.get("start", 0.0),
                    end_s=seg.get("end", 0.0),
                    text=seg.get("text", "").strip(),
                    language=result.get("language", self.language),
                    confidence=seg.get("avg_logprob", 0.0),
                ))

            return TranscriptionResult(
                segments=segments,
                full_text=result.get("text", "").strip(),
                language=result.get("language", self.language),
            )
        except Exception as e:
            return TranscriptionResult(error="Local transcription failed: %s" % e)

    def _transcribe_local_segments(self, wav_path: str,
                                   segments: List[Tuple[float, float, int]]
                                   ) -> List[TranscriptionSegment]:
        """Transcribe whole file locally, then map text to verse segments."""
        try:
            import whisper
            model = self._get_local_model()
            options = {"word_timestamps": True}
            if self.language:
                options["language"] = self.language

            result = model.transcribe(wav_path, **options)
            whisper_segments = result.get("segments", [])

            # Build a timeline of transcribed words with timestamps
            word_timeline = []
            for seg in whisper_segments:
                for word_info in seg.get("words", []):
                    word_timeline.append({
                        "start": word_info.get("start", seg.get("start", 0)),
                        "end": word_info.get("end", seg.get("end", 0)),
                        "word": word_info.get("word", "").strip(),
                    })

            # If word-level timestamps aren't available, fall back to segment-level
            if not word_timeline:
                for seg in whisper_segments:
                    word_timeline.append({
                        "start": seg.get("start", 0),
                        "end": seg.get("end", 0),
                        "word": seg.get("text", "").strip(),
                    })

            # Map words to verse segments by time overlap
            results = []
            for start_s, end_s, verse_num in segments:
                verse_words = []
                for w in word_timeline:
                    # Word overlaps with segment if word midpoint is within range
                    w_mid = (w["start"] + w["end"]) / 2.0
                    if start_s <= w_mid <= end_s:
                        verse_words.append(w["word"])

                text = " ".join(verse_words).strip()
                results.append(TranscriptionSegment(
                    verse_number=verse_num,
                    start_s=start_s,
                    end_s=end_s,
                    text=text,
                    language=result.get("language", self.language),
                ))

            return results

        except Exception as e:
            # Fall back to per-segment transcription
            results = []
            for start_s, end_s, verse_num in segments:
                seg = self.transcribe_segment(wav_path, start_s, end_s, verse_num)
                results.append(seg)
            return results

    # ---------------------------------------------------------------------------
    # OpenAI API
    # ---------------------------------------------------------------------------
    def _transcribe_api_full(self, wav_path: str) -> TranscriptionResult:
        """Transcribe using OpenAI's Whisper API."""
        try:
            from openai import OpenAI
        except ImportError:
            return TranscriptionResult(
                error=_missing_dependency_message("OpenAI API support", "openai"))

        if not self.api_key:
            return TranscriptionResult(error="OpenAI API key not configured.")

        try:
            client = OpenAI(api_key=self.api_key)

            with open(wav_path, "rb") as f:
                kwargs = {"model": "whisper-1", "file": f,
                          "response_format": "verbose_json"}
                if self.language:
                    kwargs["language"] = self.language
                response = client.audio.transcriptions.create(**kwargs)

            segments = []
            for seg in getattr(response, "segments", []):
                segments.append(TranscriptionSegment(
                    start_s=seg.get("start", 0.0) if isinstance(seg, dict) else getattr(seg, "start", 0.0),
                    end_s=seg.get("end", 0.0) if isinstance(seg, dict) else getattr(seg, "end", 0.0),
                    text=(seg.get("text", "") if isinstance(seg, dict) else getattr(seg, "text", "")).strip(),
                    language=getattr(response, "language", self.language),
                ))

            full_text = getattr(response, "text", "")
            return TranscriptionResult(
                segments=segments,
                full_text=full_text.strip(),
                language=getattr(response, "language", self.language),
            )
        except Exception as e:
            return TranscriptionResult(error="API transcription failed: %s" % e)


# ---------------------------------------------------------------------------
# Availability checks
# ---------------------------------------------------------------------------
def _whisper_local_available() -> bool:
    try:
        import whisper  # noqa: F401
        return True
    except ImportError:
        return False


def _openai_available() -> bool:
    try:
        import openai  # noqa: F401
        return True
    except ImportError:
        return False


def whisper_available(mode: str = "local", api_key: str = "") -> bool:
    """Check if speech-to-text is available for the given mode."""
    if mode == "local":
        return _whisper_local_available()
    elif mode == "api":
        return bool(api_key) and _openai_available()
    return False


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m engine.transcriber <file.wav> [language]")
        print("  Available: local=%s, api=%s" % (
            _whisper_local_available(), _openai_available()))
        sys.exit(1)

    lang = sys.argv[2] if len(sys.argv) > 2 else ""
    t = Transcriber(mode="local", model="base", language=lang)
    if not t.is_available():
        print("Whisper not available: %s" % t.get_availability_message())
        sys.exit(1)

    print("Transcribing: %s (language=%s)" % (sys.argv[1], lang or "auto"))
    result = t.transcribe_file(sys.argv[1])
    if result.error:
        print("ERROR: %s" % result.error)
    else:
        print("Language: %s" % result.language)
        print("Text: %s" % result.full_text[:500])
        print("Segments: %d" % len(result.segments))
