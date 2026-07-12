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
def check_file(path: str, cfg: Config, do_loudness: bool = True,
               script_verses: Optional[dict] = None) -> FileReport:
    """Check a single WAV file against configured standards.

    Args:
        path: path to the WAV file
        cfg: configuration with thresholds and toggle flags
        do_loudness: whether ffmpeg loudness checks are available
        script_verses: optional dict mapping verse number (int) -> verse text (str)
                       for script verification. Only used if cfg.enable_script_verification.
    """
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
    if cfg.enable_format and cfg.check_format:
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
        if cfg.enable_loudness:
            try:
                lr = measure_loudness(path, cfg.target_lufs, cfg.lufs_tolerance,
                                      cfg.true_peak_max)
                lufs_txt = ("%.1f LUFS" % lr.integrated_lufs) if lr.integrated_lufs is not None else "n/a"
                report.add(CheckItem(
                    "Loudness", lr.lufs_ok,
                    "Target %.1f LUFS +/- %.1f; measured %s" % (
                        cfg.target_lufs, cfg.lufs_tolerance, lufs_txt),
                    lufs_txt))
            except Exception as e:
                report.add(CheckItem("Loudness", False, "Measurement failed: %s" % e))

        if cfg.enable_true_peak:
            try:
                if not cfg.enable_loudness:
                    # Need to run measurement if loudness was skipped
                    lr = measure_loudness(path, cfg.target_lufs, cfg.lufs_tolerance,
                                          cfg.true_peak_max)
                peak_txt = ("%.1f dBTP" % lr.true_peak_dbtp) if lr.true_peak_dbtp is not None else "n/a"
                report.add(CheckItem(
                    "True Peak", lr.peak_ok,
                    "Ceiling %.1f dBTP; measured %s" % (cfg.true_peak_max, peak_txt),
                    peak_txt))
            except Exception as e:
                report.add(CheckItem("True Peak", False, "Measurement failed: %s" % e))
    elif do_loudness and (cfg.enable_loudness or cfg.enable_true_peak):
        report.add(CheckItem("Loudness", False,
                             "ffmpeg not found - cannot measure loudness/true peak"))

    # === Silence ===
    if cfg.enable_head_silence or cfg.enable_tail_silence:
        try:
            sr = check_silence(path, cfg.silence_seconds, cfg.silence_tolerance,
                               cfg.silence_threshold_dbfs)
            if cfg.enable_head_silence:
                report.add(CheckItem(
                    "Head Silence", sr.head_ok,
                    "Expected %.1fs +/- %.1fs; measured %.2fs" % (
                        cfg.silence_seconds, cfg.silence_tolerance, sr.head_silence_s),
                    "%.2fs" % sr.head_silence_s))
            if cfg.enable_tail_silence:
                report.add(CheckItem(
                    "Tail Silence", sr.tail_ok,
                    "Expected %.1fs +/- %.1fs; measured %.2fs" % (
                        cfg.silence_seconds, cfg.silence_tolerance, sr.tail_silence_s),
                    "%.2fs" % sr.tail_silence_s))
        except Exception as e:
            report.add(CheckItem("Silence", False, "Silence check failed: %s" % e))

    # === Markers present at all ===
    if cfg.enable_markers or cfg.enable_verses:
        if not markers:
            if cfg.enable_markers:
                report.add(CheckItem("Markers", False,
                                     "No markers found in the WAV file."))
            return report

        cm = classify_markers(markers, cfg)

        if cfg.enable_markers:
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
        if cfg.enable_verses:
            _check_verses(report, cm, cfg)

    # === Script verification ===
    if cfg.enable_script_verification and script_verses:
        try:
            from .script_verify import verify_script
            sv_result = verify_script(path, markers, script_verses, cfg)
            if sv_result.error:
                report.add(CheckItem(
                    "Script Match", False,
                    "Script verification error: %s" % sv_result.error,
                    "error"))
            elif sv_result.ok:
                report.add(CheckItem(
                    "Script Match", True,
                    "All verse segments match the script (avg similarity: %.0f%%)." %
                    (sv_result.avg_similarity * 100),
                    "%.0f%%" % (sv_result.avg_similarity * 100)))
            else:
                mismatches = "; ".join(sv_result.issues[:5])
                if len(sv_result.issues) > 5:
                    mismatches += " (+%d more)" % (len(sv_result.issues) - 5)
                report.add(CheckItem(
                    "Script Match", False,
                    "Script mismatches found: " + mismatches,
                    "%d issues" % len(sv_result.issues)))
        except ImportError:
            report.add(CheckItem("Script Match", False,
                                 "Script verification dependencies not installed (whisper/PyMuPDF)."))
        except Exception as e:
            report.add(CheckItem("Script Match", False,
                                 "Script verification failed: %s" % e))

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


# ---------------------------------------------------------------------------
# Batch-level check: missing chapters across loaded files
# ---------------------------------------------------------------------------
@dataclass
class MissingChapterReport:
    """Report of missing chapters for a book."""
    book: str
    total_chapters: int            # expected (e.g. 28 for Matthew)
    chapters_found: List[int]      # chapters present in loaded files
    chapters_missing: List[int]    # chapters not found
    duplicate_chapters: List[int]  # chapters with multiple files

    @property
    def complete(self) -> bool:
        return len(self.chapters_missing) == 0

    @property
    def missing_str(self) -> str:
        """Human-readable missing chapters string (e.g. '5, 17-19, 24')."""
        return _rngs(self.chapters_missing)

    @property
    def summary(self) -> str:
        if self.complete:
            return "%s: all %d chapters present." % (self.book, self.total_chapters)
        return "%s: missing chapter(s) %s (have %d/%d)." % (
            self.book, self.missing_str, len(self.chapters_found), self.total_chapters)


def check_missing_chapters(reports: List[FileReport]) -> List[MissingChapterReport]:
    """Check for missing chapters across a batch of file reports.

    Groups files by book, then for each book checks which chapters are present
    vs the expected total from the KJV database.

    Args:
        reports: list of FileReport objects from check_file()

    Returns:
        List of MissingChapterReport for each book that has at least one file.
        Books with all chapters present are included (complete=True).
        Only books recognised by the DB are checked.
    """
    # Group chapters by book
    book_chapters: dict = {}  # book_name -> list of chapter numbers found
    for r in reports:
        if r.book and r.chapter:
            if r.book not in book_chapters:
                book_chapters[r.book] = []
            book_chapters[r.book].append(r.chapter)

    results = []
    for book, chapters in sorted(book_chapters.items()):
        total = bible_db.num_chapters(book)
        if total <= 0:
            continue

        found_set = set(chapters)
        expected_set = set(range(1, total + 1))
        missing = sorted(expected_set - found_set)

        # Check for duplicate chapters (same chapter appearing multiple times)
        seen = set()
        duplicates = []
        for ch in chapters:
            if ch in seen and ch not in duplicates:
                duplicates.append(ch)
            seen.add(ch)

        results.append(MissingChapterReport(
            book=book,
            total_chapters=total,
            chapters_found=sorted(found_set),
            chapters_missing=missing,
            duplicate_chapters=sorted(duplicates),
        ))

    return results
