"""
marker_writer.py - write cue points and labl chunks into an existing WAV file.

Creates a new file (never modifies the original). Compatible with Adobe
Audition's marker format:
  * cue chunk with cue points (ID + sample offset)
  * LIST:adtl chunk with labl sub-chunks (text label tied to a cue ID)

Usage:
    from engine.marker_writer import write_markers
    markers = [(0, "Chapter Title"), (48000, "Verse 1"), (96000, "Verse 2")]
    write_markers("input.wav", "output_marked.wav", markers)
"""

from __future__ import annotations

import os
import struct
from typing import List, Tuple

from .wavio import read_wav_info, read_pcm


def write_markers(src_path: str, dst_path: str,
                  markers: List[Tuple[int, str]]) -> None:
    """Write a new WAV file with embedded cue/labl markers.

    Args:
        src_path: path to the source WAV file (not modified)
        dst_path: path to the output WAV file to create
        markers: list of (sample_offset, label_text) tuples, sorted by offset

    The output file preserves the original audio format (sample rate, bit depth,
    channels) and embeds markers in Adobe Audition compatible format.
    """
    if not os.path.isfile(src_path):
        raise FileNotFoundError("Source WAV not found: %s" % src_path)

    info = read_wav_info(src_path)
    if info.data_size <= 0:
        raise ValueError("Source WAV has no audio data: %s" % src_path)

    # Read the full audio data
    audio_data = read_pcm(src_path, info, 0, info.n_frames)

    # Build WAV with markers
    _write_wav_with_markers(
        dst_path, audio_data, info.sample_rate, info.channels,
        info.bits, markers
    )


def _write_wav_with_markers(path: str, audio_bytes: bytes, sample_rate: int,
                            n_channels: int, bits: int,
                            markers: List[Tuple[int, str]]) -> None:
    """Write a complete WAV file with audio data and embedded markers.

    Produces a standard RIFF WAV with:
      - fmt chunk (PCM format)
      - data chunk (raw audio)
      - cue chunk (cue points)
      - LIST:adtl chunk (labels)
    """
    byte_rate = sample_rate * n_channels * (bits // 8)
    block_align = n_channels * (bits // 8)

    # fmt chunk
    fmt_body = struct.pack("<HHIIHH", 1, n_channels, sample_rate,
                           byte_rate, block_align, bits)
    fmt_chunk = b"fmt " + struct.pack("<I", len(fmt_body)) + fmt_body

    # data chunk
    data_chunk = b"data" + struct.pack("<I", len(audio_bytes)) + audio_bytes
    # Pad to word boundary if odd length
    if len(audio_bytes) % 2 == 1:
        data_chunk += b"\x00"

    # cue chunk
    cue_chunk = _build_cue_chunk(markers)

    # LIST:adtl chunk with labl sub-chunks
    list_chunk = _build_adtl_chunk(markers)

    # Assemble RIFF file
    payload = b"WAVE" + fmt_chunk + data_chunk + cue_chunk + list_chunk
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", len(payload)) + payload)


def _build_cue_chunk(markers: List[Tuple[int, str]]) -> bytes:
    """Build a cue chunk with one cue point per marker."""
    if not markers:
        return b""

    cue_points = b""
    for i, (sample_offset, _label) in enumerate(markers, start=1):
        # cue point: ID, position, fccChunk, chunkStart, blockStart, sampleOffset
        cue_points += struct.pack("<II4sIII",
                                  i, sample_offset, b"data", 0, 0, sample_offset)

    cue_body = struct.pack("<I", len(markers)) + cue_points
    return b"cue " + struct.pack("<I", len(cue_body)) + cue_body


def _build_adtl_chunk(markers: List[Tuple[int, str]]) -> bytes:
    """Build a LIST:adtl chunk with labl sub-chunks for each marker."""
    if not markers:
        return b""

    adtl = b"adtl"
    for i, (_offset, label) in enumerate(markers, start=1):
        # labl sub-chunk: cue_id (4 bytes) + null-terminated text
        text = label.encode("utf-8") + b"\x00"
        # Pad to even length
        if len(text) % 2 == 1:
            text += b"\x00"
        labl_body = struct.pack("<I", i) + text
        adtl += b"labl" + struct.pack("<I", len(labl_body)) + labl_body

    return b"LIST" + struct.pack("<I", len(adtl)) + adtl


def generate_output_path(src_path: str) -> str:
    """Generate the output filename with _marked suffix.

    Example: GEN_001.wav -> GEN_001_marked.wav
    """
    base, ext = os.path.splitext(src_path)
    return base + "_marked" + ext


if __name__ == "__main__":
    import sys
    print("marker_writer.py - Write WAV markers (Adobe Audition compatible)")
    print("Usage: from engine.marker_writer import write_markers")
    print("  write_markers('input.wav', 'output.wav', [(0, 'Marker 1'), ...])")
