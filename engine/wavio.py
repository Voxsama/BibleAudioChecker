"""
wavio.py — minimal, dependency-free RIFF/WAVE reader used by the engine.

Why this exists instead of the stdlib `wave` module: real 24-bit / 48 kHz
masters are frequently written as WAVE_FORMAT_EXTENSIBLE (format tag 0xFFFE),
which Python's `wave` module refuses to open. This reader handles plain PCM
(tag 1), IEEE float (tag 3), and EXTENSIBLE (0xFFFE, real format taken from the
SubFormat GUID) at any bit depth.

It also records the byte offset/size of the `data` chunk *without reading it*,
so callers can read just the first/last few seconds of a large file instead of
loading hundreds of megabytes into memory.
"""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class WavInfo:
    audio_format: int = 1        # 1=PCM, 3=float (resolved from EXTENSIBLE)
    channels: int = 0
    sample_rate: int = 0
    bits: int = 0                # bits per sample
    sampwidth: int = 0           # bytes per sample (per channel)
    data_offset: int = 0         # byte offset of PCM data in the file
    data_size: int = 0           # length of the data chunk in bytes
    n_frames: int = 0            # number of sample frames
    chunks: Dict[str, bytes] = field(default_factory=dict)  # e.g. 'cue ', 'LIST:adtl'


def read_wav_info(path: str) -> WavInfo:
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    info = WavInfo()
    with open(path, "rb") as f:
        riff = f.read(12)
        if len(riff) < 12 or riff[0:4] != b"RIFF" or riff[8:12] != b"WAVE":
            raise ValueError("Not a RIFF/WAVE file: %s" % path)
        while True:
            header = f.read(8)
            if len(header) < 8:
                break
            chunk_id = header[0:4]
            (size,) = struct.unpack("<I", header[4:8])
            if chunk_id == b"data":
                info.data_offset = f.tell()
                info.data_size = size
                f.seek(size, os.SEEK_CUR)          # skip the audio, don't load it
            elif chunk_id == b"fmt ":
                body = f.read(size)
                _parse_fmt(body, info)
            elif chunk_id == b"cue ":
                info.chunks["cue "] = f.read(size)
            elif chunk_id == b"LIST":
                body = f.read(size)
                if len(body) >= 4:
                    info.chunks["LIST:" + body[0:4].decode("latin-1")] = body
            else:
                f.seek(size, os.SEEK_CUR)
            if size % 2 == 1:                       # word alignment pad byte
                f.seek(1, os.SEEK_CUR)

    if info.sampwidth and info.channels:
        info.n_frames = info.data_size // (info.sampwidth * info.channels)
    return info


def _parse_fmt(body: bytes, info: WavInfo) -> None:
    if len(body) < 16:
        raise ValueError("fmt chunk too short")
    (fmt_tag, channels, rate, _byte_rate, _block_align, bits) = \
        struct.unpack("<HHIIHH", body[0:16])
    if fmt_tag == 0xFFFE and len(body) >= 40:
        # EXTENSIBLE: the real format is the first 2 bytes of the SubFormat GUID
        (sub_tag,) = struct.unpack("<H", body[24:26])
        fmt_tag = sub_tag
    info.audio_format = fmt_tag
    info.channels = channels
    info.sample_rate = rate
    info.bits = bits
    info.sampwidth = max(1, bits // 8)


def read_pcm(path: str, info: WavInfo, start_frame: int, n_frames: int) -> bytes:
    """Read n_frames sample frames starting at start_frame from the data chunk."""
    block = info.sampwidth * info.channels
    if block <= 0:
        return b""
    start_frame = max(0, min(start_frame, info.n_frames))
    n_frames = max(0, min(n_frames, info.n_frames - start_frame))
    with open(path, "rb") as f:
        f.seek(info.data_offset + start_frame * block)
        return f.read(n_frames * block)
