"""
auto_marker.py - AI-powered automatic marker placement for Bible audio files.

Combines multiple approaches to detect verse boundaries:
  1. Whisper transcription with word-level timestamps (primary, for supported languages)
  2. Script matching: aligns transcribed text to PDF verse text
  3. Pause/silence detection: finds gaps between verses (fallback for unsupported langs)
  4. Correction memory: adjusts timing based on past user corrections

Output:
  - Writes markers into a new WAV file (original is never modified)
  - Keeps original filename with "_marked" suffix (e.g. GEN_001.wav -> GEN_001_marked.wav)
  - Markers: "Chapter Title" at start, "Verse 1", "Verse 2", etc.

Usage:
    from engine.auto_marker import auto_mark_file, AutoMarkResult
    result = auto_mark_file("GEN_001.wav", verses={1: "In the beginning...", ...},
                            language="hi")
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .correction_memory import CorrectionMemory
from .marker_writer import write_markers, generate_output_path
from .wavio import read_wav_info, read_pcm


@dataclass
class MarkerPlacement:
    """A single marker to be placed in the audio."""
    label: str
    sample_offset: int
    time_s: float
    confidence: float = 0.0  # 0.0-1.0, how confident we are in the placement
    method: str = ""         # "whisper", "pause", "correction", "fallback"


@dataclass
class AutoMarkResult:
    """Result of the auto-marking process."""
    output_path: str = ""
    markers: List[MarkerPlacement] = field(default_factory=list)
    method_used: str = ""     # "whisper", "pause", "combined"
    total_verses: int = 0
    markers_placed: int = 0
    warnings: List[str] = field(default_factory=list)
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and self.markers_placed > 0


def _whisper_available() -> bool:
    """Check if Whisper is available for local transcription."""
    try:
        import whisper  # noqa: F401
        return True
    except ImportError:
        return False


def _detect_pauses(wav_path: str, min_pause_s: float = 0.3,
                   threshold_dbfs: float = -40.0,
                   sample_rate: int = 0) -> List[Tuple[float, float]]:
    """Detect silence/pause regions in an audio file.

    Returns a list of (start_time, end_time) tuples for each detected pause,
    sorted by start time.

    Args:
        wav_path: path to the WAV file
        min_pause_s: minimum pause duration to consider (seconds)
        threshold_dbfs: amplitude threshold below which audio is "silent"
        sample_rate: override sample rate (0 = read from file)
    """
    import audioop

    info = read_wav_info(wav_path)
    sr = sample_rate or info.sample_rate
    sw = info.sampwidth
    ch = info.channels

    if sr <= 0 or sw <= 0:
        return []

    max_amp = float(2 ** (8 * sw - 1))
    threshold_amp = (10 ** (threshold_dbfs / 20.0)) * max_amp

    # Read audio in chunks for analysis
    chunk_duration_s = 0.01  # 10ms chunks
    chunk_frames = max(1, int(sr * chunk_duration_s))
    total_frames = info.n_frames

    pauses: List[Tuple[float, float]] = []
    pause_start: Optional[float] = None
    frame_pos = 0

    while frame_pos < total_frames:
        n_read = min(chunk_frames, total_frames - frame_pos)
        raw = read_pcm(wav_path, info, frame_pos, n_read)

        if not raw:
            break

        # Convert to mono for analysis
        if ch == 2:
            mono = audioop.tomono(raw, sw, 0.5, 0.5)
        elif ch > 2:
            block = sw * ch
            mono = bytearray()
            for i in range(0, len(raw) - block + 1, block):
                mono += raw[i:i + sw]
            mono = bytes(mono)
        else:
            mono = raw

        # Check peak amplitude
        try:
            peak = audioop.max(mono, sw)
        except Exception:
            peak = 0

        current_time = frame_pos / float(sr)

        if peak <= threshold_amp:
            # Silent
            if pause_start is None:
                pause_start = current_time
        else:
            # Not silent
            if pause_start is not None:
                pause_end = current_time
                pause_duration = pause_end - pause_start
                if pause_duration >= min_pause_s:
                    pauses.append((pause_start, pause_end))
                pause_start = None

        frame_pos += n_read

    # Handle trailing silence
    if pause_start is not None:
        pause_end = total_frames / float(sr)
        pause_duration = pause_end - pause_start
        if pause_duration >= min_pause_s:
            pauses.append((pause_start, pause_end))

    return pauses


def _match_text_similarity(text_a: str, text_b: str) -> float:
    """Compute a simple similarity ratio between two text strings.

    Uses character-level comparison (suitable for multi-script text including
    Indic languages where word boundaries may differ from transcription).
    """
    if not text_a or not text_b:
        return 0.0

    a = text_a.strip().lower()
    b = text_b.strip().lower()

    if a == b:
        return 1.0

    # Simple longest common subsequence ratio
    len_a = len(a)
    len_b = len(b)

    if len_a == 0 or len_b == 0:
        return 0.0

    # Use a simplified comparison: count matching characters in order
    # This is more efficient than full LCS for our purposes
    matches = 0
    j = 0
    for char in a:
        while j < len_b:
            if b[j] == char:
                matches += 1
                j += 1
                break
            j += 1

    return (2.0 * matches) / (len_a + len_b)


def _transcribe_with_timestamps(wav_path: str, language: str,
                                model: str = "medium"
                                ) -> Optional[List[Dict]]:
    """Transcribe audio with word-level timestamps using Whisper.

    Returns a list of word dictionaries with 'start', 'end', 'word' keys,
    or None if Whisper is not available.
    """
    if not _whisper_available():
        return None

    try:
        import whisper
        model_obj = whisper.load_model(model)
        options = {"word_timestamps": True}
        if language:
            options["language"] = language

        result = model_obj.transcribe(wav_path, **options)

        word_timeline = []
        for seg in result.get("segments", []):
            for word_info in seg.get("words", []):
                word_timeline.append({
                    "start": word_info.get("start", seg.get("start", 0)),
                    "end": word_info.get("end", seg.get("end", 0)),
                    "word": word_info.get("word", "").strip(),
                })

        # If no word-level timestamps, use segment-level
        if not word_timeline:
            for seg in result.get("segments", []):
                word_timeline.append({
                    "start": seg.get("start", 0),
                    "end": seg.get("end", 0),
                    "word": seg.get("text", "").strip(),
                })

        return word_timeline
    except Exception:
        return None


def _find_verse_boundaries_by_transcription(
        word_timeline: List[Dict],
        verses: Dict[int, str],
        sample_rate: int) -> List[MarkerPlacement]:
    """Match transcribed words to script verses to find verse start times.

    Uses a sliding window over the word timeline, matching accumulated text
    against each verse's text to find the best alignment.
    """
    if not word_timeline or not verses:
        return []

    markers: List[MarkerPlacement] = []
    verse_nums = sorted(verses.keys())

    # Build full transcription text with word boundaries
    full_text = " ".join(w["word"] for w in word_timeline)

    # For each verse, find where in the transcription it starts
    text_cursor = 0  # position in word_timeline
    for verse_num in verse_nums:
        verse_text = verses[verse_num]
        if not verse_text.strip():
            continue

        # Search forward from current position
        best_score = 0.0
        best_idx = text_cursor

        # Try matching verse text against windows of transcription
        verse_word_count = len(verse_text.split())
        search_window = max(verse_word_count * 3, 20)
        search_end = min(len(word_timeline), text_cursor + search_window)

        for start_idx in range(text_cursor, search_end):
            # Build candidate text from this position
            end_idx = min(start_idx + verse_word_count * 2, len(word_timeline))
            candidate_words = [w["word"] for w in word_timeline[start_idx:end_idx]]
            candidate_text = " ".join(candidate_words)

            score = _match_text_similarity(verse_text, candidate_text)
            if score > best_score:
                best_score = score
                best_idx = start_idx

        # Use the best match position
        if best_idx < len(word_timeline):
            start_time = word_timeline[best_idx]["start"]
            sample_offset = int(start_time * sample_rate)
            markers.append(MarkerPlacement(
                label="Verse %d" % verse_num,
                sample_offset=sample_offset,
                time_s=start_time,
                confidence=best_score,
                method="whisper",
            ))
            text_cursor = best_idx + 1

    return markers


def _find_verse_boundaries_by_pauses(
        pauses: List[Tuple[float, float]],
        expected_verses: int,
        sample_rate: int,
        head_silence_s: float = 2.0) -> List[MarkerPlacement]:
    """Use detected pauses to estimate verse boundaries.

    Strategy:
      - Sort pauses by duration (longest first)
      - Select the top N pauses that match expected verse count
      - Use the midpoint of each pause as the verse boundary

    Args:
        pauses: list of (start_s, end_s) pause regions
        expected_verses: number of verses expected (from script)
        sample_rate: audio sample rate
        head_silence_s: initial silence to skip
    """
    if not pauses or expected_verses <= 0:
        return []

    # Filter out head and tail silence (first and last pause if they touch edges)
    filtered_pauses = []
    for start, end in pauses:
        # Skip pauses in the head silence region
        if end <= head_silence_s + 0.5:
            continue
        filtered_pauses.append((start, end))

    if not filtered_pauses:
        return []

    # We need (expected_verses - 1) boundaries between verses
    # (The first verse starts after any initial content like chapter title)
    needed_boundaries = expected_verses - 1

    if len(filtered_pauses) <= needed_boundaries:
        # Use all available pauses
        selected = filtered_pauses
    else:
        # Sort by pause duration (longest = most likely verse boundaries)
        by_duration = sorted(filtered_pauses, key=lambda p: p[1] - p[0], reverse=True)
        selected = by_duration[:needed_boundaries]
        # Re-sort by time
        selected.sort(key=lambda p: p[0])

    markers: List[MarkerPlacement] = []
    for i, (start, end) in enumerate(selected):
        # Place marker at the end of the pause (where speech resumes)
        boundary_time = end
        verse_num = i + 2  # First boundary = start of verse 2
        sample_offset = int(boundary_time * sample_rate)
        confidence = min(1.0, (end - start) / 1.0)  # longer pauses = higher confidence
        markers.append(MarkerPlacement(
            label="Verse %d" % verse_num,
            sample_offset=sample_offset,
            time_s=boundary_time,
            confidence=confidence,
            method="pause",
        ))

    return markers


def auto_mark_file(wav_path: str, verses: Dict[int, str],
                   language: str = "", model: str = "medium",
                   reader_id: str = "",
                   output_path: Optional[str] = None,
                   correction_memory: Optional[CorrectionMemory] = None,
                   progress_callback=None) -> AutoMarkResult:
    """Auto-mark a WAV file with verse markers.

    This is the main entry point for the auto-marking feature.

    Args:
        wav_path: path to the input WAV file
        verses: dict mapping verse_number -> verse_text (from PDF parser)
        language: language code for Whisper (e.g. "hi", "ta")
        model: Whisper model size (tiny, base, small, medium, large)
        reader_id: optional reader identifier for correction memory
        output_path: output file path (default: input_marked.wav)
        correction_memory: CorrectionMemory instance for learning adjustments
        progress_callback: optional callable(stage: str, progress: float) for UI updates

    Returns:
        AutoMarkResult with the output path and placed markers
    """
    result = AutoMarkResult()

    # Validate input
    if not os.path.isfile(wav_path):
        result.error = "WAV file not found: %s" % wav_path
        return result

    if not verses:
        result.error = "No verse text provided. Load a script PDF first."
        return result

    # Determine output path
    if output_path is None:
        output_path = generate_output_path(wav_path)
    result.output_path = output_path
    result.total_verses = len(verses)

    # Read WAV info
    try:
        info = read_wav_info(wav_path)
    except Exception as e:
        result.error = "Could not read WAV file: %s" % e
        return result

    sample_rate = info.sample_rate
    if sample_rate <= 0:
        result.error = "Invalid sample rate in WAV file"
        return result

    duration_s = info.n_frames / float(sample_rate)

    # Initialize correction memory
    if correction_memory is None:
        correction_memory = CorrectionMemory()

    # Notify progress
    if progress_callback:
        progress_callback("analyzing", 0.1)

    # Strategy 1: Try Whisper transcription with timestamps
    markers: List[MarkerPlacement] = []
    method_used = ""

    if _whisper_available():
        if progress_callback:
            progress_callback("transcribing", 0.2)

        word_timeline = _transcribe_with_timestamps(wav_path, language, model)
        if word_timeline:
            if progress_callback:
                progress_callback("matching", 0.6)

            markers = _find_verse_boundaries_by_transcription(
                word_timeline, verses, sample_rate)
            method_used = "whisper"

    # Strategy 2: Fall back to pause detection if Whisper unavailable or produced
    # insufficient markers
    if len(markers) < len(verses) * 0.5:
        if progress_callback:
            progress_callback("detecting pauses", 0.4)

        pauses = _detect_pauses(wav_path, min_pause_s=0.3, threshold_dbfs=-40.0)

        pause_markers = _find_verse_boundaries_by_pauses(
            pauses, len(verses), sample_rate)

        if not markers or len(pause_markers) > len(markers):
            markers = pause_markers
            method_used = "pause" if not method_used else "combined"

        # Record pause observations for learning
        for start, end in pauses:
            pause_dur = end - start
            if 0.1 <= pause_dur <= 5.0:
                correction_memory.add_pause_observation(language, pause_dur, reader_id)

    # If still no markers, create evenly spaced markers as last resort
    if not markers and len(verses) > 0:
        if progress_callback:
            progress_callback("estimating", 0.5)

        # Skip first ~2s (head silence) and last ~2s (tail silence)
        usable_start = min(2.0, duration_s * 0.05)
        usable_end = max(duration_s - 2.0, duration_s * 0.95)
        usable_duration = usable_end - usable_start

        verse_nums = sorted(verses.keys())
        interval = usable_duration / max(1, len(verse_nums))

        for i, verse_num in enumerate(verse_nums):
            t = usable_start + i * interval
            markers.append(MarkerPlacement(
                label="Verse %d" % verse_num,
                sample_offset=int(t * sample_rate),
                time_s=t,
                confidence=0.2,
                method="fallback",
            ))
        method_used = method_used or "fallback"
        result.warnings.append(
            "Used evenly-spaced estimation (no Whisper, insufficient pauses detected).")

    # Apply correction memory adjustments
    if correction_memory.has_data(language, reader_id):
        if progress_callback:
            progress_callback("applying corrections", 0.7)

        for marker in markers:
            # Extract verse number from label
            verse_num = 0
            label_parts = marker.label.split()
            if len(label_parts) >= 2 and label_parts[-1].isdigit():
                verse_num = int(label_parts[-1])

            if verse_num > 0:
                adjusted_time = correction_memory.get_adjustment(
                    language, verse_num, marker.time_s, reader_id)
                # Only apply if adjustment is reasonable (within 5 seconds)
                if abs(adjusted_time - marker.time_s) < 5.0:
                    marker.time_s = adjusted_time
                    marker.sample_offset = int(adjusted_time * sample_rate)
                    marker.method += "+corrected"

    # Add Chapter Title marker at the beginning
    chapter_title_time = 0.0
    # Place it right after any head silence
    for marker in markers:
        if marker.time_s > 0:
            # Place chapter title a bit before the first verse
            chapter_title_time = max(0.0, markers[0].time_s - 1.0) if markers else 0.0
            break

    all_markers = [MarkerPlacement(
        label="Chapter Title",
        sample_offset=int(chapter_title_time * sample_rate),
        time_s=chapter_title_time,
        confidence=0.9,
        method="auto",
    )] + markers

    # Sort markers by time
    all_markers.sort(key=lambda m: m.sample_offset)

    # Ensure no duplicate positions (minimum 100ms apart)
    min_gap_samples = int(0.1 * sample_rate)
    for i in range(1, len(all_markers)):
        if all_markers[i].sample_offset - all_markers[i-1].sample_offset < min_gap_samples:
            all_markers[i].sample_offset = all_markers[i-1].sample_offset + min_gap_samples
            all_markers[i].time_s = all_markers[i].sample_offset / float(sample_rate)

    # Clamp all markers within valid range
    max_offset = info.n_frames - 1
    for marker in all_markers:
        marker.sample_offset = max(0, min(marker.sample_offset, max_offset))
        marker.time_s = marker.sample_offset / float(sample_rate)

    if progress_callback:
        progress_callback("writing", 0.85)

    # Write output file with markers
    try:
        marker_tuples = [(m.sample_offset, m.label) for m in all_markers]
        write_markers(wav_path, output_path, marker_tuples)
    except Exception as e:
        result.error = "Failed to write output file: %s" % e
        return result

    if progress_callback:
        progress_callback("done", 1.0)

    result.markers = all_markers
    result.method_used = method_used
    result.markers_placed = len(all_markers)

    if not _whisper_available():
        result.warnings.append(
            "Whisper not available. Used pause detection only. "
            "Install openai-whisper for better accuracy.")

    return result


def auto_mark_files(wav_paths: List[str], verses: Dict[int, str],
                    language: str = "", model: str = "medium",
                    reader_id: str = "",
                    correction_memory: Optional[CorrectionMemory] = None,
                    progress_callback=None) -> List[AutoMarkResult]:
    """Auto-mark multiple WAV files.

    Args:
        wav_paths: list of WAV file paths
        verses: dict mapping verse_number -> verse_text
        language: language code for Whisper
        model: Whisper model size
        reader_id: optional reader identifier
        correction_memory: CorrectionMemory instance
        progress_callback: callable(file_index, total_files, stage, progress)

    Returns:
        List of AutoMarkResult, one per input file
    """
    if correction_memory is None:
        correction_memory = CorrectionMemory()

    results = []
    total = len(wav_paths)

    for i, wav_path in enumerate(wav_paths):
        def file_progress(stage, progress):
            if progress_callback:
                progress_callback(i, total, stage, progress)

        result = auto_mark_file(
            wav_path, verses, language=language, model=model,
            reader_id=reader_id, correction_memory=correction_memory,
            progress_callback=file_progress)
        results.append(result)

    return results


if __name__ == "__main__":
    import sys
    print("auto_marker.py - AI Auto-Marker for Bible Audio")
    print("Whisper available: %s" % _whisper_available())
    print()
    print("Usage:")
    print("  from engine.auto_marker import auto_mark_file")
    print("  result = auto_mark_file('GEN_001.wav', {1: 'In the beginning...'})")
    if len(sys.argv) > 1:
        print("\nDetecting pauses in: %s" % sys.argv[1])
        pauses = _detect_pauses(sys.argv[1])
        print("Found %d pauses:" % len(pauses))
        for start, end in pauses[:20]:
            print("  %.3fs - %.3fs (%.3fs)" % (start, end, end - start))
