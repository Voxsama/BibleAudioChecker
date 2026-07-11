"""
silence.py — verify a WAV has ~N seconds of silence at head and tail.

Uses engine.wavio (not the stdlib `wave` module) so it works with 24-bit /
48 kHz EXTENSIBLE-format masters, and reads only the first/last few seconds of
the file rather than loading the whole thing into memory.

"Silent" means the sample peak stays below a dBFS threshold (default -60 dBFS).
We measure the continuous silent run inward from each edge.
"""

from __future__ import annotations

import audioop
from dataclasses import dataclass

from .wavio import read_wav_info, read_pcm


@dataclass
class SilenceResult:
    head_silence_s: float
    tail_silence_s: float
    head_ok: bool
    tail_ok: bool
    expected_s: float
    tolerance_s: float

    @property
    def ok(self) -> bool:
        return self.head_ok and self.tail_ok


def _dbfs_to_amp(dbfs: float, max_amp: float) -> float:
    return (10 ** (dbfs / 20.0)) * max_amp


def _to_mono(raw: bytes, sw: int, ch: int) -> bytes:
    if ch <= 1:
        return raw
    if ch == 2:
        return audioop.tomono(raw, sw, 0.5, 0.5)
    # >2 channels: take channel 0
    block = sw * ch
    out = bytearray()
    for i in range(0, len(raw) - block + 1, block):
        out += raw[i:i + sw]
    return bytes(out)


def _silent_run(mono: bytes, sw: int, sr: int, threshold_amp: float,
                from_end: bool, limit_s: float) -> float:
    """Continuous silence (seconds) measured inward from one edge of `mono`."""
    chunk_frames = max(1, sr // 100)     # 10 ms resolution
    chunk_bytes = chunk_frames * sw
    total = len(mono)
    silent = 0.0
    scanned = 0.0
    pos = total if from_end else 0
    while scanned < limit_s and (pos > 0 if from_end else pos < total):
        if from_end:
            start = max(0, pos - chunk_bytes); block = mono[start:pos]; pos = start
        else:
            end = min(total, pos + chunk_bytes); block = mono[pos:end]; pos = end
        if not block:
            break
        peak = audioop.max(block, sw)
        dur = (len(block) // sw) / float(sr)
        scanned += dur
        if peak <= threshold_amp:
            silent += dur
        else:
            break
    return round(silent, 3)


def check_silence(path: str, expected_s: float = 2.0,
                  tolerance_s: float = 0.5,
                  threshold_dbfs: float = -60.0) -> SilenceResult:
    info = read_wav_info(path)
    sr, sw, ch = info.sample_rate, info.sampwidth, info.channels
    if sr <= 0 or sw <= 0:
        raise ValueError("Unsupported/undecodable WAV format")

    max_amp = float(2 ** (8 * sw - 1))
    threshold_amp = _dbfs_to_amp(threshold_dbfs, max_amp)

    # read a window of ~3x expected from each edge (bounded by file length)
    win_frames = int(min(max(expected_s * 3.0, 1.0), 60.0) * sr)
    win_frames = min(win_frames, info.n_frames)

    head_raw = read_pcm(path, info, 0, win_frames)
    tail_start = max(0, info.n_frames - win_frames)
    tail_raw = read_pcm(path, info, tail_start, win_frames)

    head_mono = _to_mono(head_raw, sw, ch)
    tail_mono = _to_mono(tail_raw, sw, ch)

    head = _silent_run(head_mono, sw, sr, threshold_amp, from_end=False, limit_s=expected_s * 1.5)
    tail = _silent_run(tail_mono, sw, sr, threshold_amp, from_end=True, limit_s=expected_s * 1.5)

    head_ok = abs(head - expected_s) <= tolerance_s + 1e-9
    tail_ok = abs(tail - expected_s) <= tolerance_s + 1e-9
    return SilenceResult(head, tail, head_ok, tail_ok, expected_s, tolerance_s)


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        r = check_silence(p)
        print(p)
        print("  head silence: %.3fs (ok=%s)" % (r.head_silence_s, r.head_ok))
        print("  tail silence: %.3fs (ok=%s)" % (r.tail_silence_s, r.tail_ok))
