"""
wav_markers.py — read embedded markers (cue points) and their labels from a WAV
file, using engine.wavio for header parsing (so 24-bit / EXTENSIBLE files work).

Adobe Audition stores markers in a RIFF WAV using:
  * a 'cue ' chunk   -> list of cue points (ID + sample offset)
  * an 'adtl' LIST chunk with:
        'labl' sub-chunks  -> a text label tied to a cue ID
        'ltxt' sub-chunks  -> a labelled region (cue ID + length in samples)

Returns markers sorted by time, with label text attached. Stdlib only.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Dict, List

from .wavio import read_wav_info


@dataclass
class Marker:
    cue_id: int
    sample_offset: int
    label: str = ""
    length_samples: int = 0
    sample_rate: int = 44100

    @property
    def seconds(self) -> float:
        return self.sample_offset / float(self.sample_rate) if self.sample_rate > 0 else 0.0

    @property
    def is_region(self) -> bool:
        return self.length_samples > 0


def _parse_cue(body: bytes) -> Dict[int, int]:
    result: Dict[int, int] = {}
    if len(body) < 4:
        return result
    (count,) = struct.unpack("<I", body[0:4])
    off = 4
    for _ in range(count):
        if off + 24 > len(body):
            break
        (cue_id, position, _dchunk, _cstart, _bstart, sample_offset) = \
            struct.unpack("<II4sIII", body[off:off + 24])
        result[cue_id] = sample_offset if sample_offset else position
        off += 24
    return result


def _parse_adtl(body: bytes) -> Dict[int, dict]:
    info: Dict[int, dict] = {}
    if len(body) < 4:
        return info
    off = 4  # skip 'adtl'
    while off + 8 <= len(body):
        sub_id = body[off:off + 4]
        (sub_size,) = struct.unpack("<I", body[off + 4:off + 8])
        sub_body = body[off + 8:off + 8 + sub_size]
        if sub_id in (b"labl", b"note"):
            if len(sub_body) >= 4:
                (cue_id,) = struct.unpack("<I", sub_body[0:4])
                text = _decode_text(sub_body[4:])
                entry = info.setdefault(cue_id, {"label": "", "length": 0})
                if sub_id == b"labl" or not entry["label"]:
                    entry["label"] = text
        elif sub_id == b"ltxt":
            if len(sub_body) >= 8:
                (cue_id, length) = struct.unpack("<II", sub_body[0:8])
                text = _decode_text(sub_body[20:]) if len(sub_body) > 20 else ""
                entry = info.setdefault(cue_id, {"label": "", "length": 0})
                entry["length"] = length
                if text and not entry["label"]:
                    entry["label"] = text
        off += 8 + sub_size
        if sub_size % 2 == 1:
            off += 1
    return info


def _decode_text(raw: bytes) -> str:
    if not raw:
        return ""
    nul = raw.find(b"\x00")
    if nul != -1:
        raw = raw[:nul]
    for enc in ("utf-8", "latin-1"):
        try:
            return raw.decode(enc).strip()
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", "replace").strip()


def read_markers(path: str) -> List[Marker]:
    """Read all markers from a WAV, sorted by time. [] if no cue chunk."""
    info = read_wav_info(path)
    sample_rate = info.sample_rate or 44100
    cue_body = info.chunks.get("cue ")
    if not cue_body:
        return []
    cues = _parse_cue(cue_body)
    adtl = _parse_adtl(info.chunks.get("LIST:adtl", b""))

    markers: List[Marker] = []
    for cue_id, sample_offset in cues.items():
        meta = adtl.get(cue_id, {})
        markers.append(Marker(cue_id, sample_offset, meta.get("label", ""),
                              meta.get("length", 0), sample_rate))
    markers.sort(key=lambda m: (m.sample_offset, m.cue_id))
    return markers


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        print("== %s ==" % p)
        for m in read_markers(p):
            kind = "region" if m.is_region else "point"
            print("  %8.3fs  %-20s  [%s]" % (m.seconds, m.label, kind))
