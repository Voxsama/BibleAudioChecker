"""
checker.py — orchestrates all checks for one WAV file and produces a structured,
human-readable report.

Checks performed:
  1. Loudness    : integrated LUFS within target +/- tol
  2. True peak   : <= configured ceiling (dBTP)
  3. Head silence: ~N s of silence at the start
  4. Tail silence: ~N s of silence at the end
  5. Markers     : classify each marker into Chapter Title / Heading / Verse N;
                   validate marker spelling; verify the verse markers are
                   exactly 1..expected_verses with none missing/extra/duplicate.

Marker classification (literal-word scheme):
  * "Chapter Title" (case-insensitive, trimmed)  -> chapter title
  * "Heading"                                     -> heading
  * "Verse <n>"                                   -> verse number <n>
  * anything else                                 -> flagged as an unknown /
                                                     misspelled marker
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

from .config import Config
from . import bible_db
from .wav_markers import read_markers, Marker
from .silence import check_silence
from .loudness import measure_loudness, ffmpeg_available
from .wavio import read_wav_info


# ---------------------------------------------------------------------------
# Result data structures
# ---------------------------------------------------------------------------
@dataclass
class CheckItem:
    name: str            # e.g. "Loudness", "True Peak", "Verses"
    passed: bool
    detail: str          # human readable explanation (esp. on failure)
    value: str = ""      # measured value, short

    @property
    def status(self) -> str:
        return "PASS" if self.passed else "FAIL"


@dataclass
class FileReport:
    path: str
    filename: str
    book: Optional[str] = None
    chapter: Optional[int] = None
    expected_verses: Optional[int] = None
    items: List[CheckItem] = field(default_factory=list)
    error: Optional[str] = None      # hard error (couldn't read file etc.)

    @property
    def passed(self) -> bool:
        if self.error:
            return False
        return all(i.passed for i in self.items)

    @property
    def n_fails(self) -> int:
        return sum(1 for i in self.items if not i.passed)

    def add(self, item: CheckItem):
        self.items.append(item)


# ---------------------------------------------------------------------------
# Marker classification
# ---------------------------------------------------------------------------
@dataclass
class ClassifiedMarkers:
    chapter_titles: List[Marker]
    headings: List[Marker]
    verses: List[tuple]              # (verse_number:int, Marker)
    unknown: List[Marker]            # unrecognised / misspelled labels
    malformed_verse: List[Marker]    # look like a verse but number unreadable


def classify_markers(markers: List[Marker], cfg: Config) -> ClassifiedMarkers:
    ct_name = cfg.chapter_title_name.strip().lower()
    hd_name = cfg.heading_name.strip().lower()
    verse_word = cfg.verse_word.strip().lower()

    chapter_titles, headings, verses, unknown, malformed = [], [], [], [], []
    # "Verse 12", "Verse12", "Verse  003" -> capture number
    verse_re = re.compile(r"^%s\s*0*(\d+)\s*$" % re.escape(verse_word), re.IGNORECASE)
    # looser: starts with the verse word but number missing/garbled
    verse_loose = re.compile(r"^%s\b" % re.escape(verse_word), re.IGNORECASE)

    for m in markers:
        label = (m.label or "").strip()
        low = label.lower()
        if low == ct_name:
            chapter_titles.append(m)
        elif low == hd_name:
            headings.append(m)
        else:
            mm = verse_re.match(label)
            if mm:
                verses.append((int(mm.group(1)), m))
            elif verse_loose.match(label):
                malformed.append(m)
            else:
                unknown.append(m)
    return ClassifiedMarkers(chapter_titles, headings, verses, unknown, malformed)


# ---------------------------------------------------------------------------
# The main entry point
# ---------------------------------------------------------------------------
def check_file(path: str, cfg: Config, do_loudness: bool = True) -> FileReport:
    filename = os.path.basename(path)
    report = FileReport(path=path, filename=filename)

    # --- identify book/chapter from filename ---
    bc = bible_db.parse_filename(filename)
    if bc:
        report.book = bc.book
        report.chapter = bc.chapter
        report.expected_verses = bc.expected_verses

    # --- read markers ---
    try:
        markers = read_markers(path)
    except Exception as e:  # unreadable / not a wav
        report.error = "Could not read WAV: %s" % e
        return report

    # === Format (sample rate / bit depth) ===
    if cfg.check_format:
        try:
            _info = read_wav_info(path)
            fmt_txt = "%gk/%d-bit" % (_info.sample_rate / 1000.0, _info.bits)
            fmt_ok = (_info.sample_rate == cfg.expected_sample_rate
                      and _info.bits == cfg.expected_bits)
            report.add(CheckItem(
                "Format", fmt_ok,
                "Expected %d Hz / %d-bit; file is %d Hz / %d-bit" % (
                    cfg.expected_sample_rate, cfg.expected_bits,
                    _info.sample_rate, _info.bits),
                fmt_txt))
        except Exception as e:
            report.add(CheckItem("Format", False, "Could not read WAV format: %s" % e))

    # === Loudness + true peak ===
    if do_loudness and ffmpeg_available():
        try:
            lr = measure_loudness(path, cfg.target_lufs, cfg.lufs_tolerance,
                                  cfg.true_peak_max)
            lufs_txt = ("%.1f LUFS" % lr.integrated_lufs) if lr.integrated_lufs is not None else "n/a"
            report.add(CheckItem(
                "Loudness", lr.lufs_ok,
                "Target %.1f LUFS +/- %.1f; measured %s" % (
                    cfg.target_lufs, cfg.lufs_tolerance, lufs_txt),
                lufs_txt))
            peak_txt = ("%.1f dBTP" % lr.true_peak_dbtp) if lr.true_peak_dbtp is not None else "n/a"
            report.add(CheckItem(
                "True Peak", lr.peak_ok,
                "Ceiling %.1f dBTP; measured %s" % (cfg.true_peak_max, peak_txt),
                peak_txt))
        except Exception as e:
            report.add(CheckItem("Loudness", False, "Measurement failed: %s" % e))
    elif do_loudness:
        report.add(CheckItem("Loudness", False,
                             "ffmpeg not found - cannot measure loudness/true peak"))

    # === Silence ===
    try:
        sr = check_silence(path, cfg.silence_seconds, cfg.silence_tolerance,
                           cfg.silence_threshold_dbfs)
        report.add(CheckItem(
            "Head Silence", sr.head_ok,
            "Expected %.1fs +/- %.1fs; measured %.2fs" % (
                cfg.silence_seconds, cfg.silence_tolerance, sr.head_silence_s),
            "%.2fs" % sr.head_silence_s))
        report.add(CheckItem(
            "Tail Silence", sr.tail_ok,
            "Expected %.1fs +/- %.1fs; measured %.2fs" % (
                cfg.silence_seconds, cfg.silence_tolerance, sr.tail_silence_s),
            "%.2fs" % sr.tail_silence_s))
    except Exception as e:
        report.add(CheckItem("Silence", False, "Silence check failed: %s" % e))

    # === Markers present at all ===
    if not markers:
        report.add(CheckItem("Markers", False,
                             "No markers found in the WAV file."))
        return report

    cm = classify_markers(markers, cfg)

    # --- Chapter title ---
    if cfg.require_chapter_title:
        if len(cm.chapter_titles) == 1:
            report.add(CheckItem("Chapter Title", True, "Present.", "1"))
        elif len(cm.chapter_titles) == 0:
            report.add(CheckItem("Chapter Title", False,
                                 "Missing '%s' marker." % cfg.chapter_title_name))
        else:
            report.add(CheckItem("Chapter Title", False,
                                 "Found %d '%s' markers (expected 1)." % (
                                     len(cm.chapter_titles), cfg.chapter_title_name)))

    # --- Heading (optional) ---
    if cfg.require_heading and len(cm.headings) == 0:
        report.add(CheckItem("Heading", False,
                             "Missing '%s' marker." % cfg.heading_name))

    # --- Misspelled / unknown markers ---
    if cfg.strict_verse_spelling and (cm.unknown or cm.malformed_verse):
        bad = []
        for m in cm.malformed_verse:
            bad.append("'%s' @ %s (verse number unreadable)" % (m.label, _ts(m)))
        for m in cm.unknown:
            bad.append("'%s' @ %s (unrecognised marker name)" % (m.label, _ts(m)))
        report.add(CheckItem("Marker Spelling", False,
                             "Markers not matching expected names: " + "; ".join(bad),
                             "%d bad" % len(bad)))

    # --- Verse count / completeness ---
    _check_verses(report, cm, cfg)

    return report


def _ts(m: Marker) -> str:
    s = m.seconds
    return "%d:%05.2f" % (int(s // 60), s % 60)


def _check_verses(report: FileReport, cm: ClassifiedMarkers, cfg: Config):
    verse_numbers = [n for (n, _m) in cm.verses]
    found = set(verse_numbers)
    n_found = len(cm.verses)

    if report.expected_verses is None:
        # Can't validate against DB (unknown filename); still report duplicates.
        dupes = _dupes(verse_numbers)
        detail = "Found %d verse markers. Book/chapter not recognised from filename, so expected count is unknown." % n_found
        passed = True
        if dupes:
            detail += " Duplicate verse numbers: %s." % ", ".join(map(str, dupes))
            passed = False
        report.add(CheckItem("Verses", passed, detail, "%d found" % n_found))
        return

    expected = report.expected_verses
    expected_set = set(range(1, expected + 1))
    missing = sorted(expected_set - found)
    extra = sorted(n for n in found if n < 1 or n > expected)
    dupes = _dupes(verse_numbers)

    problems = []
    if missing:
        problems.append("missing verse(s): %s" % _rngs(missing))
    if extra:
        problems.append("unexpected verse number(s): %s" % ", ".join(map(str, extra)))
    if dupes:
        problems.append("duplicate verse number(s): %s" % ", ".join(map(str, dupes)))

    passed = not problems
    if passed:
        detail = "All %d verses present (Verse 1..%d), no missing/extra/duplicates." % (expected, expected)
    else:
        detail = "%s %d/%d — " % (report.book, report.chapter, expected) if report.book else ""
        detail = "Expected %d verses (%s %d). " % (expected, report.book, report.chapter) + "; ".join(problems) + "."
    report.add(CheckItem("Verses", passed, detail,
                         "%d/%d" % (n_found, expected)))


def _dupes(nums):
    seen, dup = set(), []
    for n in nums:
        if n in seen and n not in dup:
            dup.append(n)
        seen.add(n)
    return sorted(dup)


def _rngs(nums):
    """Compress [3,4,5,9] -> '3-5, 9' for readable missing-verse lists."""
    if not nums:
        return ""
    nums = sorted(nums)
    out = []
    start = prev = nums[0]
    for n in nums[1:]:
        if n == prev + 1:
            prev = n
            continue
        out.append("%d" % start if start == prev else "%d-%d" % (start, prev))
        start = prev = n
    out.append("%d" % start if start == prev else "%d-%d" % (start, prev))
    return ", ".join(out)
