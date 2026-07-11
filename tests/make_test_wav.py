"""
make_test_wav.py — generate synthetic WAVs with embedded cue markers + labels,
silence at head/tail. Supports 16- or 24-bit and any sample rate so we can test
the engine at the real 48 kHz / 24-bit spec. Pure stdlib.
"""
from __future__ import annotations

import math
import struct
import sys


def _pack_sample(v: float, bits: int) -> bytes:
    v = max(-1.0, min(1.0, v))
    if bits == 16:
        return struct.pack("<h", int(v * 32767))
    if bits == 24:
        return int(round(v * 8388607)).to_bytes(3, "little", signed=True)
    raise ValueError("bits must be 16 or 24")


def _tone(n, sr, freq, amp, bits):
    out = bytearray()
    for i in range(n):
        out += _pack_sample(amp * math.sin(2 * math.pi * freq * i / sr), bits)
    return bytes(out)


def _silence(n, bits):
    return b"\x00" * (n * (bits // 8))


def build_wav(path, sr=44100, n_verses=5, head_silence_s=2.0, tail_silence_s=2.0,
              amp=0.5, labels=None, drop_marker=None, body_seconds_each=0.5,
              bits=16):
    head = int(head_silence_s * sr)
    tail = int(tail_silence_s * sr)
    seg = int(body_seconds_each * sr)
    if labels is None:
        labels = ["Chapter Title", "Heading"] + ["Verse %d" % i for i in range(1, n_verses + 1)]

    audio = bytearray()
    audio += _silence(head, bits)
    markers = []
    cursor = head
    for idx, name in enumerate(labels):
        if drop_marker is not None and idx == drop_marker:
            audio += _tone(seg, sr, 220.0, amp, bits); cursor += seg; continue
        markers.append((cursor, name))
        audio += _tone(seg, sr, 200.0 + idx * 10, amp, bits)
        cursor += seg
    audio += _silence(tail, bits)

    _write_wav_with_cues(path, bytes(audio), sr, markers, bits=bits, n_channels=1)
    return markers


def _write_wav_with_cues(path, audio_bytes, sr, markers, bits=16, n_channels=1):
    byte_rate = sr * n_channels * bits // 8
    block_align = n_channels * bits // 8
    fmt_body = struct.pack("<HHIIHH", 1, n_channels, sr, byte_rate, block_align, bits)
    fmt_chunk = b"fmt " + struct.pack("<I", len(fmt_body)) + fmt_body

    data_chunk = b"data" + struct.pack("<I", len(audio_bytes)) + audio_bytes
    if len(audio_bytes) % 2 == 1:
        data_chunk += b"\x00"

    cue_points = b""
    for i, (offset, _name) in enumerate(markers, start=1):
        cue_points += struct.pack("<II4sIII", i, offset, b"data", 0, 0, offset)
    cue_body = struct.pack("<I", len(markers)) + cue_points
    cue_chunk = b"cue " + struct.pack("<I", len(cue_body)) + cue_body

    adtl = b"adtl"
    for i, (_offset, name) in enumerate(markers, start=1):
        text = name.encode("utf-8") + b"\x00"
        if len(text) % 2 == 1:
            text += b"\x00"
        labl_body = struct.pack("<I", i) + text
        adtl += b"labl" + struct.pack("<I", len(labl_body)) + labl_body
    list_chunk = b"LIST" + struct.pack("<I", len(adtl)) + adtl

    payload = b"WAVE" + fmt_chunk + data_chunk + cue_chunk + list_chunk
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", len(payload)) + payload)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "test.wav"
    m = build_wav(out, sr=48000, bits=24, n_verses=5)
    print("wrote", out, "48k/24bit with", len(m), "markers")
