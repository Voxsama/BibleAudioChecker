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

import difflib
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .correction_memory import CorrectionMemory
from .marker_writer import write_markers, generate_output_path
from .wavio import read_wav_info, read_pcm

_WHISPER_MODEL_CACHE: Dict[str, object] = {}
MIN_SCRIPT_ALIGNMENT_COVERAGE = 0.08
MIN_MMS_ALIGNMENT_COVERAGE = 0.35


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
    input_path: str = ""
    output_path: str = ""
    markers: List[MarkerPlacement] = field(default_factory=list)
    method_used: str = ""     # "whisper", "pause", "combined"
    total_verses: int = 0
    markers_placed: int = 0
    headings_placed: int = 0
    warnings: List[str] = field(default_factory=list)
    error: str = ""
    needs_review: bool = False
    minimum_confidence: float = 0.0
    alignment_coverage: float = 0.0
    language_used: str = ""
    decoder_language_used: str = ""
    model_used: str = ""

    @property
    def ok(self) -> bool:
        verse_count = sum(
            1 for marker in self.markers
            if marker.label.lower().startswith("verse "))
        return not self.error and verse_count == self.total_verses


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
                                model: str = "large-v3",
                                script_prompt: str = ""
                                ) -> Optional[List[Dict]]:
    """Transcribe audio with word-level timestamps using Whisper.

    Returns a list of word dictionaries with 'start', 'end', 'word' keys,
    or None if Whisper is not available.
    """
    if not _whisper_available():
        return None

    try:
        from .transcription_cache import (
            load_cached_timeline, save_cached_timeline)

        cached = load_cached_timeline(
            wav_path, language, model, script_prompt)
        if cached is not None:
            return cached

        import whisper
        from .model_packs import model_cache_dir
        model_obj = _WHISPER_MODEL_CACHE.get(model)
        if model_obj is None:
            model_obj = whisper.load_model(
                model, download_root=model_cache_dir())
            _WHISPER_MODEL_CACHE[model] = model_obj
        options = {
            "word_timestamps": True,
            # Long genealogy chapters can poison later 30-second windows when
            # an early spelling error is carried forward. Decode each window
            # independently and keep the known Bible text as stable context.
            "condition_on_previous_text": False,
            "temperature": 0.0,
            "hallucination_silence_threshold": 2.0,
        }
        if language:
            options["language"] = language
        if script_prompt:
            options["initial_prompt"] = script_prompt[:1000]
            options["carry_initial_prompt"] = True

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

        save_cached_timeline(
            wav_path, language, model, word_timeline, script_prompt)
        return word_timeline
    except Exception:
        return None


def _find_verse_boundaries_by_transcription(
        word_timeline: List[Dict],
        verses: Dict[int, str],
        sample_rate: int) -> List[MarkerPlacement]:
    """Monotonically align the known verse script to timestamped ASR words.

    SequenceMatcher supplies reliable token anchors. Missing anchors are
    interpolated between the script and transcript positions, but are marked
    low-confidence so the GUI can require review.
    """
    if not word_timeline or not verses:
        return []

    verse_nums = sorted(verses.keys())
    expected_tokens: List[str] = []
    verse_ranges: Dict[int, Tuple[int, int]] = {}
    for verse_num in verse_nums:
        start = len(expected_tokens)
        expected_tokens.extend(_alignment_tokens(verses[verse_num]))
        verse_ranges[verse_num] = (start, len(expected_tokens))

    transcript_tokens: List[str] = []
    token_to_word: List[int] = []
    for word_index, word_info in enumerate(word_timeline):
        tokens = _alignment_tokens(word_info.get("word", ""))
        for token in tokens:
            transcript_tokens.append(token)
            token_to_word.append(word_index)

    if not expected_tokens or not transcript_tokens:
        return []

    matcher = difflib.SequenceMatcher(
        None, expected_tokens, transcript_tokens, autojunk=False)
    expected_to_transcript: Dict[int, int] = {}
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            expected_to_transcript[block.a + offset] = block.b + offset

    # A timestamped transcript is not automatically a valid alignment. With
    # Assamese, automatic language detection can choose Bengali and produce a
    # fluent-looking transcript with no connection to the loaded Assamese
    # script. Never turn a zero-anchor transcript into plausible-looking
    # evenly distributed "script-interpolated" markers.
    matched_token_count = len(expected_to_transcript)
    minimum_anchor_count = min(
        10, max(3, int(round(len(expected_tokens) * 0.005))))
    alignment_coverage = (
        matched_token_count / float(max(1, len(expected_tokens))))
    if (
            matched_token_count < minimum_anchor_count or
            alignment_coverage < MIN_SCRIPT_ALIGNMENT_COVERAGE):
        return []

    proposed: Dict[int, Tuple[int, float, str]] = {}
    total_expected = max(1, len(expected_tokens) - 1)
    max_transcript = max(0, len(transcript_tokens) - 1)

    for verse_num in verse_nums:
        start, end = verse_ranges[verse_num]
        mapped = [
            expected_to_transcript[i]
            for i in range(start, end)
            if i in expected_to_transcript
        ]
        verse_token_count = max(1, end - start)
        if mapped:
            coverage = len(mapped) / float(verse_token_count)
            confidence = min(0.99, 0.45 + coverage * 0.55)
            proposed[verse_num] = (min(mapped), confidence, "script-align")
        else:
            ratio = start / float(total_expected)
            estimated_index = int(round(ratio * max_transcript))
            proposed[verse_num] = (
                estimated_index, 0.20, "script-interpolated")

    # Enforce strict chronological order even when repeated words create
    # ambiguous matching blocks.
    markers: List[MarkerPlacement] = []
    previous_token_index = -1
    previous_time = -1.0
    for verse_num in verse_nums:
        token_index, confidence, method = proposed[verse_num]
        token_index = max(previous_token_index + 1, token_index)
        token_index = min(token_index, max_transcript)
        word_index = token_to_word[token_index]
        start_time = float(word_timeline[word_index].get("start", 0.0))
        if start_time <= previous_time:
            start_time = previous_time + 0.10
            confidence = min(confidence, 0.20)
            method = "script-interpolated"
        markers.append(MarkerPlacement(
            label="Verse %d" % verse_num,
            sample_offset=int(round(start_time * sample_rate)),
            time_s=start_time,
            confidence=confidence,
            method=method,
        ))
        previous_token_index = token_index
        previous_time = start_time

    return markers


def _fuzzy_token_similarity(left: str, right: str) -> float:
    if left == right:
        return 1.0
    if not left or not right:
        return 0.0
    return difflib.SequenceMatcher(
        None, left, right, autojunk=False).ratio()


def _monotonic_fuzzy_alignment(
        expected: List[str],
        observed: List[str]) -> Dict[int, Tuple[int, float]]:
    """Globally align noisy phonetic word tokens without crossing.

    Meta MMS often merges two genealogy names or drops a short name. A fuzzy
    Needleman-Wunsch alignment preserves chapter order while allowing those
    insertions/deletions; only useful diagonal matches are returned as timing
    anchors.
    """
    if not expected or not observed:
        return {}
    import numpy as np

    rows = len(expected) + 1
    columns = len(observed) + 1
    scores = np.empty((rows, columns), dtype=np.float32)
    trace = np.zeros((rows, columns), dtype=np.uint8)
    skip_expected = -0.65
    skip_observed = -0.35
    scores[0, 0] = 0.0
    for row in range(1, rows):
        scores[row, 0] = scores[row - 1, 0] + skip_expected
        trace[row, 0] = 1
    for column in range(1, columns):
        scores[0, column] = scores[0, column - 1] + skip_observed
        trace[0, column] = 2

    similarities = np.empty(
        (len(expected), len(observed)), dtype=np.float32)
    for row, expected_token in enumerate(expected):
        for column, observed_token in enumerate(observed):
            similarities[row, column] = _fuzzy_token_similarity(
                expected_token, observed_token)

    for row in range(1, rows):
        for column in range(1, columns):
            similarity = float(similarities[row - 1, column - 1])
            diagonal_reward = (
                2.2 if similarity >= 0.999 else
                2.5 * similarity - 1.25)
            candidates = (
                scores[row - 1, column - 1] + diagonal_reward,
                scores[row - 1, column] + skip_expected,
                scores[row, column - 1] + skip_observed,
            )
            choice = max(range(3), key=lambda index: candidates[index])
            scores[row, column] = candidates[choice]
            trace[row, column] = choice

    mapping: Dict[int, Tuple[int, float]] = {}
    row = len(expected)
    column = len(observed)
    while row > 0 or column > 0:
        choice = int(trace[row, column])
        if row > 0 and column > 0 and choice == 0:
            similarity = float(similarities[row - 1, column - 1])
            if similarity >= 0.45:
                mapping[row - 1] = (column - 1, similarity)
            row -= 1
            column -= 1
        elif row > 0 and (column == 0 or choice == 1):
            row -= 1
        else:
            column -= 1
    return mapping


def _find_verse_boundaries_by_mms(
        word_timeline: List[Dict],
        verses: Dict[int, str],
        sample_rate: int,
        duration_s: float
        ) -> Tuple[List[MarkerPlacement], float]:
    """Align Meta MMS Assamese tokens and interpolate only between anchors."""
    if not word_timeline or not verses:
        return [], 0.0

    verse_nums = sorted(verses)
    expected_tokens: List[str] = []
    verse_ranges: Dict[int, Tuple[int, int]] = {}
    for verse_num in verse_nums:
        start = len(expected_tokens)
        expected_tokens.extend(_alignment_tokens(verses[verse_num]))
        verse_ranges[verse_num] = (start, len(expected_tokens))

    observed_tokens: List[str] = []
    observed_to_word: List[int] = []
    for word_index, word in enumerate(word_timeline):
        for token in _alignment_tokens(str(word.get("word", ""))):
            observed_tokens.append(token)
            observed_to_word.append(word_index)
    if not expected_tokens or not observed_tokens:
        return [], 0.0

    mapping = _monotonic_fuzzy_alignment(
        expected_tokens, observed_tokens)
    weighted_matches = sum(value[1] for value in mapping.values())
    alignment_coverage = (
        weighted_matches / float(max(1, len(expected_tokens))))
    if alignment_coverage < MIN_MMS_ALIGNMENT_COVERAGE:
        return [], alignment_coverage

    anchors: Dict[int, Tuple[float, float]] = {}
    token_lengths: Dict[int, int] = {}
    for verse_num in verse_nums:
        start, end = verse_ranges[verse_num]
        token_lengths[verse_num] = max(1, end - start)
        mapped = [
            mapping[index] for index in range(start, end)
            if index in mapping
        ]
        if not mapped:
            continue
        first_observed = min(item[0] for item in mapped)
        word_index = observed_to_word[first_observed]
        time_s = float(word_timeline[word_index].get("start", 0.0))
        local_coverage = len(mapped) / float(token_lengths[verse_num])
        mean_similarity = (
            sum(item[1] for item in mapped) / len(mapped))
        confidence = min(
            0.99, 0.32 + 0.43 * local_coverage +
            0.24 * mean_similarity)
        anchors[verse_num] = (time_s, confidence)

    if not anchors:
        return [], alignment_coverage

    proposed: Dict[int, Tuple[float, float, str]] = {
        number: (value[0], value[1], "mms-ctc-align")
        for number, value in anchors.items()
    }
    anchor_indexes = [
        index for index, number in enumerate(verse_nums)
        if number in anchors]

    # Fill gaps using the amount of scripture between genuine acoustic
    # anchors. This is substantially safer than using a global chapter ratio.
    for position in range(len(anchor_indexes) - 1):
        left_index = anchor_indexes[position]
        right_index = anchor_indexes[position + 1]
        if right_index <= left_index + 1:
            continue
        left_number = verse_nums[left_index]
        right_number = verse_nums[right_index]
        left_time = anchors[left_number][0]
        right_time = anchors[right_number][0]
        span_numbers = verse_nums[left_index:right_index]
        total_weight = sum(token_lengths[number] for number in span_numbers)
        elapsed_weight = token_lengths[left_number]
        for missing_index in range(left_index + 1, right_index):
            number = verse_nums[missing_index]
            fraction = elapsed_weight / float(max(1, total_weight))
            proposed[number] = (
                left_time + (right_time - left_time) * fraction,
                0.30, "mms-ctc-interpolated")
            elapsed_weight += token_lengths[number]

    first_anchor_index = anchor_indexes[0]
    first_anchor_number = verse_nums[first_anchor_index]
    first_anchor_time = anchors[first_anchor_number][0]
    if first_anchor_index:
        leading = verse_nums[:first_anchor_index + 1]
        total_weight = sum(token_lengths[number] for number in leading)
        elapsed = 0
        for number in leading[:-1]:
            proposed[number] = (
                first_anchor_time * elapsed / float(max(1, total_weight)),
                0.25, "mms-ctc-interpolated")
            elapsed += token_lengths[number]

    last_anchor_index = anchor_indexes[-1]
    last_anchor_number = verse_nums[last_anchor_index]
    last_anchor_time = anchors[last_anchor_number][0]
    if last_anchor_index < len(verse_nums) - 1:
        trailing = verse_nums[last_anchor_index:]
        total_weight = sum(token_lengths[number] for number in trailing)
        elapsed = token_lengths[last_anchor_number]
        available = max(0.0, duration_s - last_anchor_time)
        for number in trailing[1:]:
            proposed[number] = (
                last_anchor_time +
                available * elapsed / float(max(1, total_weight)),
                0.25, "mms-ctc-interpolated")
            elapsed += token_lengths[number]

    markers: List[MarkerPlacement] = []
    previous_time = -1.0
    for number in verse_nums:
        time_s, confidence, method = proposed[number]
        if time_s <= previous_time:
            time_s = previous_time + 0.10
            confidence = min(confidence, 0.20)
            method += "+order-repaired"
        markers.append(MarkerPlacement(
            label="Verse %d" % number,
            sample_offset=int(round(time_s * sample_rate)),
            time_s=time_s,
            confidence=confidence,
            method=method))
        previous_time = time_s
    return markers, alignment_coverage


def _alignment_tokens(text: str) -> List[str]:
    """Unicode-safe tokens for Assamese and other supported scripts."""
    from .phonetic import alignment_tokens
    return alignment_tokens(text)


def _find_verse_boundaries_by_pauses(
        pauses: List[Tuple[float, float]],
        expected_verses: int,
        sample_rate: int,
        head_silence_s: float = 2.0,
        duration_s: float = 0.0) -> List[MarkerPlacement]:
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
    if expected_verses <= 0:
        return []

    # Use the end of detected leading silence as the first speech position.
    verse_one_time = head_silence_s
    for start, end in pauses:
        if start <= 0.10 and end <= max(10.0, head_silence_s * 3.0):
            verse_one_time = end
            break

    # Filter out head and tail silence.
    filtered_pauses: List[Tuple[float, float]] = []
    for start, end in pauses:
        if end <= verse_one_time + 0.25:
            continue
        if duration_s > 0 and start >= duration_s - 2.5:
            continue
        filtered_pauses.append((start, end))

    usable_end = max(
        verse_one_time + expected_verses,
        (duration_s - 2.0) if duration_s > 0 else
        (filtered_pauses[-1][1] if filtered_pauses else
         verse_one_time + expected_verses))
    interval = (usable_end - verse_one_time) / float(max(1, expected_verses))
    snap_window = max(1.5, interval * 0.45)
    unused_pause_indexes = set(range(len(filtered_pauses)))
    markers: List[MarkerPlacement] = []
    for verse_index in range(expected_verses):
        verse_num = verse_index + 1
        predicted_time = verse_one_time + verse_index * interval
        boundary_time = predicted_time
        confidence = 0.20
        method = "pause-interpolated"

        if verse_index == 0:
            confidence = 0.55 if verse_one_time != head_silence_s else 0.35
            method = "speech-start"
        elif unused_pause_indexes:
            nearest_index = min(
                unused_pause_indexes,
                key=lambda idx: abs(filtered_pauses[idx][1] - predicted_time))
            start, end = filtered_pauses[nearest_index]
            distance = abs(end - predicted_time)
            if distance <= snap_window:
                boundary_time = end
                pause_duration = end - start
                confidence = min(
                    0.75,
                    0.35 + min(0.25, pause_duration / 2.0) +
                    max(0.0, 0.15 * (1.0 - distance / snap_window)))
                method = "pause-snapped"
                unused_pause_indexes.remove(nearest_index)

        sample_offset = int(boundary_time * sample_rate)
        markers.append(MarkerPlacement(
            label="Verse %d" % verse_num,
            sample_offset=sample_offset,
            time_s=boundary_time,
            confidence=confidence,
            method=method,
        ))

    return markers


def _snap_aligned_markers_to_pauses(
        markers: List[MarkerPlacement],
        pauses: List[Tuple[float, float]],
        sample_rate: int,
        max_distance_s: float = 0.8) -> List[MarkerPlacement]:
    """Refine script-aligned verse starts to nearby speech resumptions."""
    if not markers or not pauses:
        return markers

    pause_ends = [end for start, end in pauses if end - start >= 0.12]
    previous_time = -1.0
    for marker in markers:
        if marker.label == "Verse 1":
            previous_time = marker.time_s
            continue
        candidates = [
            pause_end for pause_end in pause_ends
            if pause_end > previous_time + 0.05
        ]
        if candidates:
            nearest = min(candidates, key=lambda value: abs(value - marker.time_s))
            if abs(nearest - marker.time_s) <= max_distance_s:
                marker.time_s = nearest
                marker.sample_offset = int(round(nearest * sample_rate))
                marker.confidence = min(0.99, marker.confidence + 0.08)
                marker.method += "+pause"
        previous_time = marker.time_s
    return markers


def _find_heading_markers(
        headings, word_timeline: List[Dict],
        verse_markers: List[MarkerPlacement],
        sample_rate: int) -> List[MarkerPlacement]:
    """Align PDF section headings inside their surrounding verse window.

    A heading belongs immediately before ``before_verse``. Exact or partial
    transcript anchors are preferred; otherwise a deliberately
    low-confidence draft is placed before that verse for human review.
    """
    if not headings or not verse_markers:
        return []

    verse_times = {}
    for marker in verse_markers:
        parts = marker.label.split()
        if parts and parts[-1].isdigit():
            verse_times[int(parts[-1])] = marker.time_s

    transcript_tokens: List[str] = []
    token_times: List[float] = []
    for word in word_timeline or []:
        tokens = _alignment_tokens(word.get("word", ""))
        transcript_tokens.extend(tokens)
        token_times.extend(
            [float(word.get("start", 0.0))] * len(tokens))

    grouped = {}
    for heading in headings:
        text = str(getattr(heading, "text", "")).strip()
        before_verse = int(getattr(heading, "before_verse", 1))
        if text and before_verse in verse_times:
            grouped.setdefault(before_verse, []).append(text)

    output: List[MarkerPlacement] = []
    previous_verse_time = 0.0
    for before_verse in sorted(grouped):
        target_time = verse_times[before_verse]
        earlier = [
            time for number, time in verse_times.items()
            if number < before_verse]
        window_start = max(0.0, max(earlier) if earlier else 0.0)
        indexes = [
            index for index, time in enumerate(token_times)
            if window_start <= time <= target_time + 0.20]
        window_tokens = (
            transcript_tokens[indexes[0]:indexes[-1] + 1]
            if indexes else [])

        heading_texts = grouped[before_verse]
        for heading_index, text in enumerate(heading_texts):
            expected = _alignment_tokens(text)
            confidence = 0.20
            method = "heading-interpolated"
            spacing = 0.55 * (len(heading_texts) - heading_index)
            heading_time = max(window_start, target_time - spacing)

            if expected and window_tokens and indexes:
                matcher = difflib.SequenceMatcher(
                    None, expected, window_tokens, autojunk=False)
                blocks = [block for block in matcher.get_matching_blocks()
                          if block.size]
                matched = sum(block.size for block in blocks)
                coverage = matched / float(max(1, len(expected)))
                if blocks and coverage >= 0.45:
                    transcript_index = indexes[0] + min(
                        block.b for block in blocks)
                    heading_time = token_times[transcript_index]
                    confidence = min(0.98, 0.40 + 0.58 * coverage)
                    method = "heading-align"

            output.append(MarkerPlacement(
                label=("Heading" if len(output) == 0 else
                       "Heading %d" % (len(output) + 1)),
                sample_offset=int(round(heading_time * sample_rate)),
                time_s=heading_time,
                confidence=confidence,
                method=method,
            ))
        previous_verse_time = target_time

    return output


def auto_mark_file(wav_path: str, verses: Dict[int, str],
                   language: str = "as", model: str = "large-v3",
                   reader_id: str = "",
                   headings=None,
                   alignment_backend: str = "auto",
                   output_path: Optional[str] = None,
                   correction_memory: Optional[CorrectionMemory] = None,
                   progress_callback=None,
                   marker_preview_callback=None) -> AutoMarkResult:
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
        marker_preview_callback: optional callable(markers) invoked as soon
            as final marker positions are available, before the output WAV is
            written

    Returns:
        AutoMarkResult with the output path and placed markers
    """
    result = AutoMarkResult()
    result.input_path = wav_path
    result.language_used = language or "auto"
    from .mms_pack import MMS_PACK_KEY, is_mms_pack_installed
    use_mms = (
        language == "as" and
        alignment_backend != "pause" and
        is_mms_pack_installed())
    # Whisper large-v3's Assamese language token can produce corrupted
    # mixed-script output for real Assamese narration. Its Bengali acoustic
    # decoder produces coherent Bengali-Assamese script that the phonetic
    # aligner validates against the original Assamese PDF.
    decoder_language = (
        "asm" if use_mms else
        ("bn" if language == "as" else language))
    result.decoder_language_used = decoder_language or "auto"
    result.model_used = (
        "Meta MMS Assamese Precision" if use_mms else model)

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
        progress_callback("analyzing", 0.05)

    # Strategy 1: Prefer the Assamese-specific Meta MMS CTC timeline. Whisper
    # remains the multilingual fallback for other languages.
    markers: List[MarkerPlacement] = []
    word_timeline: List[Dict] = []
    method_used = ""
    mms_completed = False

    use_transcription = alignment_backend != "pause"
    if use_transcription and use_mms:
        if progress_callback:
            progress_callback("loading Meta MMS Assamese", 0.10)
        try:
            from .transcription_cache import (
                load_cached_timeline, save_cached_timeline)
            word_timeline = (
                load_cached_timeline(
                    wav_path, "asm", MMS_PACK_KEY) or [])
            if not word_timeline:
                from .mms_transcriber import transcribe_assamese_mms
                mms_result = transcribe_assamese_mms(
                    wav_path, progress_callback=progress_callback)
                if mms_result.ok:
                    word_timeline = mms_result.words
                    save_cached_timeline(
                        wav_path, "asm", MMS_PACK_KEY, word_timeline)
                else:
                    result.warnings.append(mms_result.error)
            if word_timeline:
                if progress_callback:
                    progress_callback(
                        "aligning Assamese scripture", 0.66)
                markers, result.alignment_coverage = (
                    _find_verse_boundaries_by_mms(
                        word_timeline, verses, sample_rate, duration_s))
                mms_completed = True
                method_used = "mms-ctc-alignment"
                if not markers:
                    result.warnings.append(
                        "Meta MMS/script alignment was only %.1f%% "
                        "(minimum %.0f%%). No precision markers were "
                        "accepted; a pause-based review draft was used." %
                        (result.alignment_coverage * 100,
                         MIN_MMS_ALIGNMENT_COVERAGE * 100))
        except Exception as exc:
            result.warnings.append(
                "Meta MMS Assamese failed; Whisper fallback was attempted: "
                "%s" % exc)

    if (
            use_transcription and not mms_completed and
            _whisper_available()):
        if use_mms:
            decoder_language = "bn"
            result.decoder_language_used = decoder_language
            result.model_used = model
        if progress_callback:
            progress_callback("transcribing", 0.15)

        word_timeline = (
            _transcribe_with_timestamps(
                wav_path, decoder_language, model) or [])
        if word_timeline:
            if progress_callback:
                progress_callback("matching script", 0.65)

            markers = _find_verse_boundaries_by_transcription(
                word_timeline, verses, sample_rate)
            expected_token_count = sum(
                len(_alignment_tokens(text))
                for text in verses.values())
            matcher = difflib.SequenceMatcher(
                None,
                [token for verse_num in sorted(verses)
                 for token in _alignment_tokens(verses[verse_num])],
                [token for word in word_timeline
                 for token in _alignment_tokens(word.get("word", ""))],
                autojunk=False)
            matched_tokens = sum(
                block.size for block in matcher.get_matching_blocks())
            result.alignment_coverage = (
                matched_tokens / float(max(1, expected_token_count)))
            method_used = "script-alignment"
            if (
                    result.alignment_coverage <
                    MIN_SCRIPT_ALIGNMENT_COVERAGE):
                markers = []
                result.warnings.append(
                    "Whisper/script overlap was only %.1f%% (minimum %.0f%%). "
                    "Unreliable transcript anchors were discarded and a "
                    "pause-based review draft was used instead." %
                    (result.alignment_coverage * 100,
                     MIN_SCRIPT_ALIGNMENT_COVERAGE * 100))
            elif not markers:
                result.warnings.append(
                    "Whisper produced a transcript, but it did not match "
                    "the loaded Bible chapter. Check the forced language, "
                    "translation, book/chapter filename, and PDF.")

    # Pause evidence refines aligned boundaries and supplies a complete,
    # explicitly low-confidence draft if transcription is unavailable.
    pauses: List[Tuple[float, float]] = []
    if markers or len(markers) != len(verses):
        if progress_callback:
            progress_callback("detecting pauses", 0.72)

        pauses = _detect_pauses(wav_path, min_pause_s=0.3, threshold_dbfs=-40.0)

    if len(markers) == len(verses):
        markers = _snap_aligned_markers_to_pauses(
            markers, pauses, sample_rate,
            max_distance_s=(
                1.25 if method_used == "mms-ctc-alignment" else 0.8))
    else:
        pause_markers = _find_verse_boundaries_by_pauses(
            pauses, len(verses), sample_rate, duration_s=duration_s)
        markers = pause_markers
        method_used = "pause-draft"

    # Record pause observations for learning.
    for start, end in pauses:
        pause_dur = end - start
        if 0.1 <= pause_dur <= 5.0:
            correction_memory.add_pause_observation(language, pause_dur, reader_id)

    # If still no markers, create evenly spaced markers as last resort
    if not markers and len(verses) > 0:
        if progress_callback:
            progress_callback("estimating draft", 0.72)

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
        method_used = "fallback-draft"
        result.warnings.append(
            "Used evenly-spaced estimation (no Whisper, insufficient pauses detected).")

    # Apply correction memory adjustments
    if correction_memory.has_data(language, reader_id):
        if progress_callback:
            progress_callback("applying corrections", 0.80)

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

    # Corrections and ambiguous repeated words must never change numerical
    # verse order. Repair any crossing before headings are time-sorted.
    previous_verse_time = -1.0
    for marker in markers:
        if marker.time_s <= previous_verse_time:
            marker.time_s = previous_verse_time + 0.10
            marker.sample_offset = int(round(
                marker.time_s * sample_rate))
            marker.confidence = min(marker.confidence, 0.20)
            marker.method += "+order-repaired"
        previous_verse_time = marker.time_s

    # Add Chapter Title marker at the beginning
    chapter_title_time = 0.0
    # Place it right after any head silence
    for marker in markers:
        if marker.time_s > 0:
            # Place chapter title a bit before the first verse
            chapter_title_time = max(0.0, markers[0].time_s - 1.0) if markers else 0.0
            break

    heading_markers = _find_heading_markers(
        headings or [], word_timeline, markers, sample_rate)
    all_markers = [MarkerPlacement(
        label="Chapter Title",
        sample_offset=int(chapter_title_time * sample_rate),
        time_s=chapter_title_time,
        confidence=0.9,
        method="auto",
    )] + heading_markers + markers

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

    if marker_preview_callback:
        try:
            marker_preview_callback(list(all_markers))
        except Exception:
            # A visual preview must never prevent the audio deliverable from
            # being written.
            pass

    if progress_callback:
        progress_callback("writing marked WAV", 0.90)

    # Write output file with markers
    try:
        marker_tuples = [(m.sample_offset, m.label) for m in all_markers]
        write_markers(wav_path, output_path, marker_tuples)
    except Exception as e:
        result.error = "Failed to write output file: %s" % e
        return result

    # Also write an Adobe Audition compatible CSV file alongside the WAV
    try:
        from .csv_markers import write_markers_as_csv
        csv_output = os.path.splitext(output_path)[0] + ".csv"
        csv_tuples = [(m.label, m.time_s) for m in all_markers]
        write_markers_as_csv(csv_output, csv_tuples)
    except Exception:
        result.warnings.append("Could not write CSV marker file.")

    if progress_callback:
        progress_callback("done", 1.0)

    result.markers = all_markers
    result.method_used = method_used
    result.markers_placed = len(all_markers)
    result.headings_placed = len(heading_markers)
    verse_confidences = [
        m.confidence for m in markers + heading_markers]
    result.minimum_confidence = (
        min(verse_confidences) if verse_confidences else 0.0)
    result.needs_review = (
        method_used == "pause-draft" or
        result.minimum_confidence < 0.55 or
        (method_used == "mms-ctc-alignment" and
         result.minimum_confidence < 0.75) or
        any("interpolated" in m.method or "fallback" in m.method
            for m in markers + heading_markers))
    if result.needs_review:
        result.warnings.append(
            "Low-confidence marker(s) require review in the Markers tab "
            "before the file is treated as final.")

    if (
            use_transcription and not use_mms and
            not _whisper_available()):
        result.warnings.append(
            "Whisper not available. Used pause detection only. "
            "Install openai-whisper for better accuracy.")
    if alignment_backend == "pause":
        result.warnings.append(
            "Pause-only backend selected. This output is a draft and must "
            "be calibrated or reviewed.")

    return result


def auto_mark_files(wav_paths: List[str], verses: Dict[int, str],
                    language: str = "as", model: str = "large-v3",
                    reader_id: str = "",
                    headings=None,
                    alignment_backend: str = "auto",
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
            reader_id=reader_id, headings=headings,
            alignment_backend=alignment_backend,
            correction_memory=correction_memory,
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
