"""
waveform.py — extract a compact min/max peak envelope from a WAV for drawing an
Audition-style waveform, plus the marker positions to overlay on it.

Streams the audio in one pass (downmixing to mono) and buckets it into ~N
columns of (min, max) peaks normalised to -1.0..1.0, so even a long 24-bit
master is summarised cheaply without loading it all at once.
"""

from __future__ import annotations

import audioop
from dataclasses import dataclass, field
from typing import List, Tuple

from .wavio import read_wav_info, WavInfo
from .wav_markers import read_markers


@dataclass
class WaveformData:
    peaks: List[Tuple[float, float]] = field(default_factory=list)  # (min,max) per column, -1..1
    duration_s: float = 0.0
    sample_rate: int = 0
    channels: int = 0
    bits: int = 0
    markers: list = field(default_factory=list)   # list of (seconds, label)

    @property
    def ok(self) -> bool:
        return bool(self.peaks) and self.duration_s > 0


def _to_mono(raw: bytes, sw: int, ch: int) -> bytes:
    if ch <= 1:
        return raw
    if ch == 2:
        return audioop.tomono(raw, sw, 0.5, 0.5)
    block = sw * ch
    out = bytearray()
    for i in range(0, len(raw) - block + 1, block):
        out += raw[i:i + sw]
    return bytes(out)


def extract_waveform(path: str, columns: int = 1400) -> WaveformData:
    info: WavInfo = read_wav_info(path)
    sr, sw, ch = info.sample_rate, info.sampwidth, info.channels
    data = WaveformData(sample_rate=sr, channels=ch, bits=info.bits)
    if sr <= 0 or sw <= 0 or info.n_frames <= 0:
        return data

    data.duration_s = info.n_frames / float(sr)
    max_amp = float(2 ** (8 * sw - 1))
    bucket = max(1, info.n_frames // max(1, columns))
    block = sw * ch
    read_bytes = bucket * block

    peaks: List[Tuple[float, float]] = []
    with open(path, "rb") as f:
        f.seek(info.data_offset)
        remaining = info.data_size
        while remaining > 0 and len(peaks) < columns:
            chunk = f.read(min(read_bytes, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            # trim to whole frames
            usable = (len(chunk) // block) * block
            if usable <= 0:
                continue
            mono = _to_mono(chunk[:usable], sw, ch)
            try:
                mn, mx = audioop.minmax(mono, sw)
            except audioop.error:
                mn, mx = 0, 0
            peaks.append((mn / max_amp, mx / max_amp))
    data.peaks = peaks

    try:
        data.markers = [(m.seconds, m.label) for m in read_markers(path)]
    except Exception:
        data.markers = []
    return data


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        w = extract_waveform(p)
        print(p)
        print("  dur %.2fs  %d Hz  %d-bit  %d cols  %d markers" % (
            w.duration_s, w.sample_rate, w.bits, len(w.peaks), len(w.markers)))
        if w.peaks:
            lo = min(p[0] for p in w.peaks); hi = max(p[1] for p in w.peaks)
            print("  peak range: %.3f .. %.3f" % (lo, hi))
