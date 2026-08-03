"""Non-destructive marker editing, snapping, undo/redo, and learning."""

from __future__ import annotations

import audioop
import copy
import math
import os
import re
import struct
from dataclasses import dataclass
from typing import List, Optional

from .correction_memory import CorrectionMemory
from .marker_writer import write_markers
from .wavio import read_pcm, read_wav_info
from .wav_markers import read_markers


@dataclass
class EditableMarker:
    label: str
    sample_offset: int
    original_sample_offset: int
    confidence: float = 1.0
    method: str = "embedded"


class MarkerEditSession:
    def __init__(self, wav_path: str):
        self.wav_path = os.path.abspath(wav_path)
        self.info = read_wav_info(self.wav_path)
        self.markers = [
            EditableMarker(
                label=marker.label,
                sample_offset=marker.sample_offset,
                original_sample_offset=marker.sample_offset)
            for marker in read_markers(self.wav_path)
        ]
        self.markers.sort(key=lambda marker: marker.sample_offset)
        self._undo: List[List[EditableMarker]] = []
        self._redo: List[List[EditableMarker]] = []

    @property
    def duration_s(self) -> float:
        return self.info.n_frames / float(self.info.sample_rate)

    def time_s(self, index: int) -> float:
        return self.markers[index].sample_offset / float(self.info.sample_rate)

    def _snapshot(self) -> None:
        self._undo.append(copy.deepcopy(self.markers))
        if len(self._undo) > 100:
            self._undo = self._undo[-100:]
        self._redo = []

    def move(self, index: int, time_s: float) -> int:
        self._snapshot()
        marker = self.markers[index]
        marker.sample_offset = max(
            0, min(self.info.n_frames - 1,
                   int(round(time_s * self.info.sample_rate))))
        marker.method = "manual"
        marker.confidence = 1.0
        self.markers.sort(key=lambda item: item.sample_offset)
        return self.markers.index(marker)

    def rename(self, index: int, label: str) -> None:
        if not label.strip():
            raise ValueError("Marker label cannot be empty.")
        self._snapshot()
        self.markers[index].label = label.strip()
        self.markers[index].method = "manual"

    def add(self, label: str, time_s: float) -> int:
        self._snapshot()
        offset = max(
            0, min(self.info.n_frames - 1,
                   int(round(time_s * self.info.sample_rate))))
        marker = EditableMarker(
            label=label.strip() or "Marker",
            sample_offset=offset,
            original_sample_offset=offset,
            method="manual")
        self.markers.append(marker)
        self.markers.sort(key=lambda item: item.sample_offset)
        return self.markers.index(marker)

    def delete(self, index: int) -> None:
        self._snapshot()
        self.markers.pop(index)

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(copy.deepcopy(self.markers))
        self.markers = self._undo.pop()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(copy.deepcopy(self.markers))
        self.markers = self._redo.pop()
        return True

    def nearest_marker(self, time_s: float, maximum_distance_s: float = 0.5
                       ) -> Optional[int]:
        if not self.markers:
            return None
        index = min(
            range(len(self.markers)),
            key=lambda item: abs(self.time_s(item) - time_s))
        if abs(self.time_s(index) - time_s) > maximum_distance_s:
            return None
        return index

    def snap_to_speech_onset(
            self, index: int, search_s: float = 0.8,
            threshold_dbfs: float = -40.0) -> int:
        """Move a marker to the nearest quiet-to-speech transition."""
        center = self.time_s(index)
        sr = self.info.sample_rate
        chunk_frames = max(1, int(sr * 0.01))
        start_frame = max(0, int((center - search_s) * sr))
        end_frame = min(self.info.n_frames, int((center + search_s) * sr))
        max_amp = float(2 ** (8 * self.info.sampwidth - 1))
        threshold = max_amp * (10.0 ** (threshold_dbfs / 20.0))
        transitions = []
        was_quiet = True
        frame = start_frame
        while frame < end_frame:
            count = min(chunk_frames, end_frame - frame)
            raw = read_pcm(self.wav_path, self.info, frame, count)
            if self.info.channels == 2:
                raw = audioop.tomono(raw, self.info.sampwidth, 0.5, 0.5)
            peak = audioop.max(raw, self.info.sampwidth) if raw else 0
            quiet = peak <= threshold
            if was_quiet and not quiet:
                transitions.append(frame / float(sr))
            was_quiet = quiet
            frame += count
        if not transitions:
            return index
        target = min(transitions, key=lambda value: abs(value - center))
        return self.move(index, target)

    def snap_to_zero_crossing(
            self, index: int, search_ms: float = 20.0) -> int:
        """Move to the lowest-amplitude mono sample near the current marker."""
        sr = self.info.sample_rate
        center_frame = self.markers[index].sample_offset
        radius = max(1, int(sr * search_ms / 1000.0))
        start = max(0, center_frame - radius)
        end = min(self.info.n_frames, center_frame + radius + 1)
        raw = read_pcm(self.wav_path, self.info, start, end - start)
        sw = self.info.sampwidth
        channels = self.info.channels
        if channels == 2:
            raw = audioop.tomono(raw, sw, 0.5, 0.5)
            channels = 1
        if channels > 1:
            # First channel is sufficient for locating a safe edit point.
            block = sw * channels
            raw = b"".join(
                raw[offset:offset + sw]
                for offset in range(0, len(raw) - block + 1, block))

        best_frame = center_frame
        best_value = float("inf")
        frame_count = len(raw) // sw
        for local_frame in range(frame_count):
            chunk = raw[local_frame * sw:(local_frame + 1) * sw]
            value = abs(_decode_sample(chunk, sw))
            if value < best_value:
                best_value = value
                best_frame = start + local_frame
                if value == 0:
                    break
        return self.move(index, best_frame / float(sr))

    def save(self, output_path: str, language: str = "",
             reader_id: str = "",
             correction_memory: Optional[CorrectionMemory] = None) -> str:
        output_path = os.path.abspath(output_path)
        tuples = [(marker.sample_offset, marker.label)
                  for marker in self.markers]
        write_markers(self.wav_path, output_path, tuples)

        memory = correction_memory
        if memory is None and language:
            memory = CorrectionMemory()
        if memory is not None:
            verse_re = re.compile(r"^verse\s*(\d+)$", re.IGNORECASE)
            for marker in self.markers:
                if marker.sample_offset == marker.original_sample_offset:
                    continue
                match = verse_re.match(marker.label.strip())
                if not match:
                    continue
                memory.add_correction(
                    language=language,
                    verse_number=int(match.group(1)),
                    expected_time=marker.original_sample_offset /
                    float(self.info.sample_rate),
                    corrected_time=marker.sample_offset /
                    float(self.info.sample_rate),
                    reader_id=reader_id,
                )
        return output_path


def _decode_sample(raw: bytes, sample_width: int) -> int:
    if sample_width == 1:
        return raw[0] - 128
    if sample_width == 2:
        return struct.unpack("<h", raw)[0]
    if sample_width == 3:
        value = raw[0] | raw[1] << 8 | raw[2] << 16
        return value - 0x1000000 if value & 0x800000 else value
    if sample_width == 4:
        return struct.unpack("<i", raw)[0]
    return 0

