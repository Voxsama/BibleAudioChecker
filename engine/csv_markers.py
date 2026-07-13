"""
csv_markers.py — read and write Adobe Audition marker CSV files.

Adobe Audition exports markers as tab-separated CSV with columns:
  Name, Start, Duration, Time Format, Type, Description

Start format: M:SS.mmm (e.g., "0:11.000", "1:34.750", "12:05.500")

This module:
  - Reads Audition CSV files and returns marker data
  - Writes markers in the exact Audition format
  - Compares CSV markers against WAV embedded markers
"""

from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class CSVMarker:
    """A marker from an Adobe Audition CSV file."""
    name: str
    start_seconds: float
    duration_seconds: float = 0.0
    time_format: str = "decimal"
    marker_type: str = "Cue"
    description: str = ""


def _parse_time(time_str: str) -> float:
    """Parse Audition time format 'M:SS.mmm' or 'MM:SS.mmm' to seconds.

    Examples:
        '0:01.000' -> 1.0
        '0:38.250' -> 38.25
        '1:34.750' -> 94.75
        '12:05.500' -> 725.5
    """
    time_str = time_str.strip()
    # Match M:SS.mmm or MM:SS.mmm or H:MM:SS.mmm
    m = re.match(r"^(\d+):(\d+)\.(\d+)$", time_str)
    if m:
        minutes = int(m.group(1))
        seconds = int(m.group(2))
        millis = m.group(3)
        # Pad or truncate to 3 digits for milliseconds
        millis = millis.ljust(3, '0')[:3]
        return minutes * 60.0 + seconds + int(millis) / 1000.0

    # Try H:MM:SS.mmm
    m = re.match(r"^(\d+):(\d+):(\d+)\.(\d+)$", time_str)
    if m:
        hours = int(m.group(1))
        minutes = int(m.group(2))
        seconds = int(m.group(3))
        millis = m.group(4).ljust(3, '0')[:3]
        return hours * 3600.0 + minutes * 60.0 + seconds + int(millis) / 1000.0

    # Fallback: try float
    try:
        return float(time_str)
    except ValueError:
        return 0.0


def _format_time(seconds: float) -> str:
    """Format seconds to Audition time format 'M:SS.mmm'.

    Examples:
        1.0 -> '0:01.000'
        38.25 -> '0:38.250'
        94.75 -> '1:34.750'
        725.5 -> '12:05.500'
    """
    minutes = int(seconds // 60)
    secs = seconds - minutes * 60
    return "%d:%06.3f" % (minutes, secs)


def read_csv_markers(path: str) -> List[CSVMarker]:
    """Read markers from an Adobe Audition CSV file.

    The file is tab-separated with a BOM header:
      Name\tStart\tDuration\tTime Format\tType\tDescription

    Returns list of CSVMarker sorted by time.
    """
    if not os.path.isfile(path):
        return []

    markers = []
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                name = row.get("Name", "").strip()
                start_str = row.get("Start", "0:00.000").strip()
                dur_str = row.get("Duration", "0:00.000").strip()
                time_fmt = row.get("Time Format", "decimal").strip()
                mtype = row.get("Type", "Cue").strip()
                desc = row.get("Description", "").strip()

                if not name:
                    continue

                markers.append(CSVMarker(
                    name=name,
                    start_seconds=_parse_time(start_str),
                    duration_seconds=_parse_time(dur_str),
                    time_format=time_fmt,
                    marker_type=mtype,
                    description=desc,
                ))
    except Exception:
        return []

    markers.sort(key=lambda m: m.start_seconds)
    return markers


def write_csv_markers(path: str, markers: List[CSVMarker]) -> None:
    """Write markers as an Adobe Audition compatible CSV file.

    Output is tab-separated with BOM, exactly matching Audition's export format.
    """
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        f.write("Name\tStart\tDuration\tTime Format\tType\tDescription\n")
        for m in markers:
            f.write("%s\t%s\t%s\t%s\t%s\t%s\n" % (
                m.name,
                _format_time(m.start_seconds),
                _format_time(m.duration_seconds),
                m.time_format,
                m.marker_type,
                m.description,
            ))


def write_markers_as_csv(path: str, marker_tuples: List[Tuple[str, float]]) -> None:
    """Convenience: write (name, seconds) tuples as Audition CSV.

    Args:
        path: output CSV path
        marker_tuples: list of (marker_name, time_in_seconds)
    """
    markers = [CSVMarker(name=name, start_seconds=secs) for name, secs in marker_tuples]
    write_csv_markers(path, markers)


def find_csv_for_wav(wav_path: str) -> Optional[str]:
    """Find a matching CSV file for a WAV file (same name, .csv extension).

    e.g., /path/to/2CO-001.wav -> /path/to/2CO-001.csv (if exists)
    """
    base = os.path.splitext(wav_path)[0]
    csv_path = base + ".csv"
    if os.path.isfile(csv_path):
        return csv_path
    # Try uppercase
    csv_path_upper = base + ".CSV"
    if os.path.isfile(csv_path_upper):
        return csv_path_upper
    return None


@dataclass
class MarkerComparison:
    """Result of comparing CSV markers vs WAV embedded markers."""
    csv_count: int = 0
    wav_count: int = 0
    matched: int = 0
    mismatched: List[str] = None  # list of mismatch descriptions
    csv_only: List[str] = None   # markers in CSV but not WAV
    wav_only: List[str] = None   # markers in WAV but not CSV

    def __post_init__(self):
        if self.mismatched is None:
            self.mismatched = []
        if self.csv_only is None:
            self.csv_only = []
        if self.wav_only is None:
            self.wav_only = []

    @property
    def ok(self) -> bool:
        return (not self.mismatched and not self.csv_only and not self.wav_only
                and self.csv_count > 0)

    @property
    def summary(self) -> str:
        if self.csv_count == 0:
            return "No CSV file found"
        if self.ok:
            return "All %d markers match" % self.matched
        parts = []
        if self.mismatched:
            parts.append("%d mismatched" % len(self.mismatched))
        if self.csv_only:
            parts.append("%d in CSV only" % len(self.csv_only))
        if self.wav_only:
            parts.append("%d in WAV only" % len(self.wav_only))
        return "; ".join(parts)


def compare_markers(wav_markers, csv_markers: List[CSVMarker],
                    time_tolerance_s: float = 0.5) -> MarkerComparison:
    """Compare WAV embedded markers against CSV markers.

    Args:
        wav_markers: list of Marker objects from wav_markers.read_markers()
        csv_markers: list of CSVMarker from read_csv_markers()
        time_tolerance_s: how close times must be to count as matching (seconds)

    Returns:
        MarkerComparison with match/mismatch details
    """
    result = MarkerComparison(
        csv_count=len(csv_markers),
        wav_count=len(wav_markers),
    )

    if not csv_markers:
        return result

    # Build lookup by name for CSV markers
    csv_by_name: Dict[str, CSVMarker] = {}
    for cm in csv_markers:
        csv_by_name[cm.name.strip().lower()] = cm

    # Build lookup by name for WAV markers
    wav_by_name: Dict[str, object] = {}
    for wm in wav_markers:
        label = (wm.label or "").strip().lower()
        wav_by_name[label] = wm

    # Check each CSV marker against WAV
    csv_names = set()
    for cm in csv_markers:
        name_lower = cm.name.strip().lower()
        csv_names.add(name_lower)
        wm = wav_by_name.get(name_lower)
        if wm is None:
            result.csv_only.append(cm.name)
        else:
            # Check time matches
            time_diff = abs(wm.seconds - cm.start_seconds)
            if time_diff <= time_tolerance_s:
                result.matched += 1
            else:
                result.mismatched.append(
                    "'%s': CSV=%.2fs, WAV=%.2fs (diff=%.2fs)" % (
                        cm.name, cm.start_seconds, wm.seconds, time_diff))

    # Check for WAV markers not in CSV
    for wm in wav_markers:
        label = (wm.label or "").strip().lower()
        if label and label not in csv_names:
            result.wav_only.append(wm.label)

    return result


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m engine.csv_markers <file.csv>")
        sys.exit(1)

    markers = read_csv_markers(sys.argv[1])
    print("Markers found: %d" % len(markers))
    for m in markers:
        print("  %s  %s" % (_format_time(m.start_seconds), m.name))
