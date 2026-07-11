"""
loudness.py — measure integrated loudness (LUFS) and true peak (dBTP) with
ffmpeg's EBU R128 meter (the `ebur128` filter with peak='true').

ffmpeg's ebur128 implements ITU-R BS.1770 / EBU R128, the same standard the
Orban Loudness Meter reports as "Integrated Loudness (LUFS)" and true peak.
Values track Orban closely (typically within a few tenths of a LU).

Requires an ffmpeg binary (on PATH, bundled next to the app, or pointed to by
the BAC_FFMPEG environment variable).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional


class FFmpegNotFound(RuntimeError):
    pass


def find_ffmpeg() -> Optional[str]:
    """Locate an ffmpeg binary.

    Search order (so a packaged .exe/.app can ship ffmpeg alongside it):
      1. BAC_FFMPEG environment variable (explicit override)
      2. a copy bundled by PyInstaller (sys._MEIPASS)
      3. next to the running executable / this source file
      4. ffmpeg on the system PATH
    """
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"

    env = os.environ.get("BAC_FFMPEG")
    if env and os.path.isfile(env):
        return env

    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, exe))
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(sys.executable)), exe))
    here = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(here, exe))
    candidates.append(os.path.join(os.path.dirname(here), exe))

    for c in candidates:
        if os.path.isfile(c):
            return c
    return shutil.which("ffmpeg")


@dataclass
class LoudnessResult:
    integrated_lufs: Optional[float]
    true_peak_dbtp: Optional[float]
    lufs_ok: bool
    peak_ok: bool
    raw_summary: str = ""

    @property
    def ok(self) -> bool:
        return self.lufs_ok and self.peak_ok


def ffmpeg_available() -> bool:
    return find_ffmpeg() is not None


def _run_ebur128(path: str) -> str:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise FFmpegNotFound(
            "ffmpeg was not found. Install ffmpeg (or place ffmpeg.exe next to "
            "the app) and try again."
        )
    cmd = [ffmpeg, "-nostats", "-hide_banner", "-i", path,
           "-af", "ebur128=peak=true:framelog=verbose", "-f", "null", "-"]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True)
    return proc.stderr


_I_RE = re.compile(r"I:\s*(-?\d+(?:\.\d+)?)\s*LUFS")
_PEAK_RE = re.compile(r"Peak:\s*(-?\d+(?:\.\d+)?)\s*dBFS")


def _parse_summary(stderr_text: str):
    integrated = None
    true_peak = None
    i_matches = _I_RE.findall(stderr_text)
    if i_matches:
        integrated = float(i_matches[-1])
    p_matches = _PEAK_RE.findall(stderr_text)
    if p_matches:
        true_peak = max(float(x) for x in p_matches)
    return integrated, true_peak


def measure_loudness(path: str, target_lufs: float = -18.0,
                     lufs_tol: float = 0.5,
                     true_peak_max: float = -1.0) -> LoudnessResult:
    stderr_text = _run_ebur128(path)
    integrated, true_peak = _parse_summary(stderr_text)
    lufs_ok = (integrated is not None) and abs(integrated - target_lufs) <= lufs_tol + 1e-9
    peak_ok = (true_peak is not None) and true_peak <= true_peak_max + 1e-9
    tail = "\n".join(stderr_text.strip().splitlines()[-12:])
    return LoudnessResult(integrated, true_peak, lufs_ok, peak_ok, tail)


if __name__ == "__main__":
    for p in sys.argv[1:]:
        r = measure_loudness(p)
        print(p)
        print("  integrated: %s LUFS  (ok=%s)" % (r.integrated_lufs, r.lufs_ok))
        print("  true peak : %s dBTP  (ok=%s)" % (r.true_peak_dbtp, r.peak_ok))
