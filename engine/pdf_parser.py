"""
pdf_parser.py — extract verse text from a PDF Bible script.

Supports common Bible PDF formats:
  * Numbered verses: "1 In the beginning God created..." or "1. In the beginning..."
  * Superscript-style: where verse numbers appear as standalone tokens
  * Chapter headings like "Chapter 1" or "Genesis 1" are skipped

Uses PyMuPDF (fitz) for PDF text extraction — handles multi-column layouts,
Indian language scripts (Devanagari, Tamil, Telugu, etc.), and Unicode text.

Returns a dict mapping verse_number (int) -> verse_text (str) for a given
chapter, or for the entire PDF if no chapter filtering is requested.
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class ParsedScript:
    """Result of parsing a Bible script PDF."""
    verses: Dict[int, str]           # verse_number -> verse text
    book: str = ""                   # detected book name (if any)
    chapter: int = 0                 # detected chapter number (if any)
    total_verses: int = 0            # number of verses found
    raw_text: str = ""               # full extracted text (for debugging)
    warnings: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.verses) > 0


class PDFParseError(RuntimeError):
    pass


@dataclass
class ScriptHeading:
    """A section heading read before a particular verse."""
    text: str
    before_verse: int


@dataclass
class ParsedScriptCollection:
    """A PDF/text script separated into chapter-specific verse dictionaries."""
    chapters: Dict[int, Dict[int, str]] = field(default_factory=dict)
    book_chapters: Dict[Tuple[str, int], Dict[int, str]] = field(
        default_factory=dict)
    headings: Dict[int, List[ScriptHeading]] = field(default_factory=dict)
    book_headings: Dict[Tuple[str, int], List[ScriptHeading]] = field(
        default_factory=dict)
    raw_text: str = ""
    warnings: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        source = self.book_chapters or self.chapters
        return any(bool(verses) for verses in source.values())

    @property
    def total_chapters(self) -> int:
        source = self.book_chapters or self.chapters
        return len([key for key, verses in source.items() if verses])

    @property
    def total_verses(self) -> int:
        source = self.book_chapters or self.chapters
        return sum(len(verses) for verses in source.values())

    @property
    def total_books(self) -> int:
        return len({book for book, _chapter in self.book_chapters})

    @property
    def total_headings(self) -> int:
        source = self.book_headings or self.headings
        return sum(len(headings) for headings in source.values())


def _check_fitz():
    """Check if PyMuPDF is available."""
    try:
        import fitz  # noqa: F401
        return True
    except ImportError:
        return False


def _is_neutral_dark_pdf_color(color: int) -> bool:
    """Return True for black and near-black PDF text colours.

    PyMuPDF exposes an sRGB integer. The IRV Assamese PDF uses #231f20
    instead of literal #000000, so checking for zero alone would miss its
    printed black text. Requiring low channel values with little colour cast
    excludes coloured bold labels.
    """
    value = int(color or 0) & 0xFFFFFF
    channels = (
        (value >> 16) & 0xFF,
        (value >> 8) & 0xFF,
        value & 0xFF,
    )
    return max(channels) <= 96 and max(channels) - min(channels) <= 24


def _is_typographic_heading(text: str, spans) -> bool:
    """Recognize a section heading from PDF typography, not its wording."""
    substantive = [
        span for span in spans
        if span.get("text", "").strip()]
    if not substantive or _chapter_number_from_line(text) > 0:
        return False
    all_bold = all(
        ("bold" in span.get("font", "").lower())
        or (int(span.get("flags", 0)) & 16)
        for span in substantive)
    all_dark = all(
        _is_neutral_dark_pdf_color(span.get("color", 0))
        for span in substantive)
    body_sized = max(
        float(span.get("size", 0.0))
        for span in substantive) >= 11.0
    return all_bold and all_dark and body_sized


def extract_text_from_pdf(path: str) -> str:
    """Extract all text from a PDF file using PyMuPDF."""
    if not os.path.isfile(path):
        raise FileNotFoundError("PDF file not found: %s" % path)

    try:
        import fitz
    except ImportError:
        raise PDFParseError(
            "PyMuPDF (fitz) is not installed. Install with: pip install PyMuPDF")

    try:
        doc = fitz.open(path)
    except Exception as e:
        raise PDFParseError("Could not open PDF: %s" % e)

    text_parts = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        # Preserve reading order while tagging typographically bold section
        # headings. IRV Assamese uses 12-point bold for headings, 14-point bold
        # for chapter labels, and regular 12-point body text.
        page_lines = []
        page_dict = page.get_text("dict")
        for block in page_dict.get("blocks", []):
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                text = "".join(
                    span.get("text", "") for span in spans).strip()
                if not text:
                    continue
                if _is_typographic_heading(text, spans):
                    page_lines.append("[[HEADING]]" + text)
                else:
                    page_lines.append(text)
        if page_lines:
            text_parts.append("\n".join(page_lines))

    doc.close()
    return "\n".join(text_parts)


# ---------------------------------------------------------------------------
# Verse number detection patterns
# ---------------------------------------------------------------------------

# Pattern 1: "1 In the beginning..." or "1. In the beginning..."
# Handles Devanagari numerals (०-९), standard digits, with optional dot/colon
_VERSE_NUM_PATTERN = re.compile(
    r"""
    (?:^|\n)\s*                      # start of line or after newline
    (?P<num>\d+|[०-९]+|[੦-੯]+|[૦-૯]+|[୦-୯]+|[௦-௯]+|[౦-౯]+|[೦-೯]+|[൦-൯]+|[০-৯]+)
    \s*[.\:)}\]]*\s*                 # optional separator (dot, colon, bracket)
    (?P<text>\S.+?)                   # verse text (at least one non-space char)
    (?=\n\s*(?:\d+|[०-९]+|[੦-੯]+|[૦-૯]+|[୦-୯]+|[௦-௯]+|[౦-౯]+|[೦-೯]+|[൦-൯]+|[০-৯]+)\s*[.\:)}\]]*\s*\S|\Z)  # lookahead for next verse or end
    """,
    re.VERBOSE | re.DOTALL
)

# Simpler line-by-line pattern for fallback
_VERSE_LINE_RE = re.compile(
    r"^\s*(\d+|[०-९]+|[੦-੯]+|[૦-૯]+|[୦-୯]+|[௦-௯]+|[౦-౯]+|[೦-೯]+|[൦-൯]+|[০-৯]+)"
    r"\s*[.\:)}\]]*\s*(.+)",
    re.MULTILINE
)

# Chapter heading patterns to skip
_CHAPTER_HEADING_RE = re.compile(
    r"^\s*(chapter|अध्याय|அதிகாரம்|అధ్యాయము|ಅಧ್ಯಾಯ|അദ്ധ്യായം|অধ্যায়|ਅਧਿਆਇ|અધ્યાય|ଅଧ୍ୟାୟ)\s*\d+",
    re.IGNORECASE | re.MULTILINE
)


def _convert_indic_numeral(s: str) -> int:
    """Convert Indic numeral string to integer."""
    # Mapping of Indic digit ranges to 0-9
    indic_ranges = [
        ("०१२३४५६७८९", "Devanagari"),    # Hindi/Marathi/Sanskrit
        ("੦੧੨੩੪੫੬੭੮੯", "Gurmukhi"),     # Punjabi
        ("૦૧૨૩૪૫૬૭૮૯", "Gujarati"),
        ("୦୧୨୩୪୫୬୭୮୯", "Odia"),
        ("௦௧௨௩௪௫௬௭௮௯", "Tamil"),
        ("౦౧౨౩౪౫౬౭౮౯", "Telugu"),
        ("೦೧೨೩೪೫೬೭೮೯", "Kannada"),
        ("൦൧൨൩൪൫൬൭൮൯", "Malayalam"),
        ("০১২৩৪৫৬৭৮৯", "Bengali/Assamese"),
    ]

    # Check if it's a regular digit
    if s.isdigit():
        return int(s)

    # Try each Indic numeral system
    for digits, _name in indic_ranges:
        if any(ch in digits for ch in s):
            result = ""
            for ch in s:
                idx = digits.find(ch)
                if idx >= 0:
                    result += str(idx)
                else:
                    # might be a mixed string, just try int
                    break
            if result:
                try:
                    return int(result)
                except ValueError:
                    continue

    # Last resort
    try:
        return int(s)
    except ValueError:
        return -1


def parse_verses_from_text(text: str) -> Dict[int, str]:
    """Parse verse numbers and text from extracted PDF text.

    Tries multiple strategies:
    1. Multi-line verse detection (handles verses spanning multiple lines)
    2. Line-by-line detection (simpler, for cleanly formatted PDFs)
    """
    if not text or not text.strip():
        return {}

    # Remove common chapter headings
    cleaned = _CHAPTER_HEADING_RE.sub("", text)

    # Strategy 1: Line-by-line (most reliable for well-formatted scripts)
    verses: Dict[int, str] = {}
    lines = cleaned.split("\n")

    current_verse_num = -1
    current_verse_text = []

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            # Blank line — might be paragraph break within a verse
            if current_verse_num > 0 and current_verse_text:
                current_verse_text.append("")
            continue

        # Try to match a verse number at the start of this line
        m = re.match(
            r"^\s*(\d+|[०-९]+|[੦-੯]+|[૦-૯]+|[୦-୯]+|[௦-௯]+|[౦-౯]+|[೦-೯]+|[൦-൯]+|[০-৯]+)"
            r"\s*[.\:)}\]]*\s*(.*)",
            line_stripped
        )

        if m:
            num_str = m.group(1)
            rest = m.group(2).strip()
            num = _convert_indic_numeral(num_str)

            if num > 0:
                # Save previous verse
                if current_verse_num > 0 and current_verse_text:
                    verses[current_verse_num] = " ".join(
                        t for t in current_verse_text if t).strip()

                # Start new verse
                current_verse_num = num
                current_verse_text = [rest] if rest else []
                continue

        # Continuation of current verse
        if current_verse_num > 0:
            current_verse_text.append(line_stripped)

    # Save last verse
    if current_verse_num > 0 and current_verse_text:
        verses[current_verse_num] = " ".join(
            t for t in current_verse_text if t).strip()

    return verses


def parse_pdf(path: str, chapter: Optional[int] = None) -> ParsedScript:
    """Parse a Bible script PDF and extract verses.

    Args:
        path: path to the PDF file
        chapter: optional chapter number to filter (if PDF contains multiple chapters)

    Returns:
        ParsedScript with verse_number -> verse_text mapping
    """
    if not _check_fitz():
        return ParsedScript(
            verses={},
            warnings=["PyMuPDF not installed. Install with: pip install PyMuPDF"])

    raw_text = extract_text_from_pdf(path)
    verses = parse_verses_from_text(raw_text)

    warnings = []
    if not verses:
        warnings.append("No verses could be extracted from the PDF. "
                        "Check that verse numbers are present in the text.")

    # If verses are numbered sequentially starting from 1, we're good.
    # If they jump around, warn.
    if verses:
        nums = sorted(verses.keys())
        if nums[0] != 1:
            warnings.append("First verse number is %d (expected 1)." % nums[0])
        # Check for gaps
        expected_set = set(range(nums[0], nums[-1] + 1))
        missing = expected_set - set(nums)
        if missing:
            warnings.append("Missing verse numbers in PDF: %s" %
                            ", ".join(map(str, sorted(missing)[:10])))

    return ParsedScript(
        verses=verses,
        chapter=chapter or 0,
        total_verses=len(verses),
        raw_text=raw_text,
        warnings=warnings,
    )


def parse_plain_text(text: str) -> ParsedScript:
    """Parse verse text from a plain text string (for non-PDF inputs)."""
    verses = parse_verses_from_text(text)
    warnings = []
    if not verses:
        warnings.append("No verses could be extracted from the text.")
    return ParsedScript(
        verses=verses,
        total_verses=len(verses),
        raw_text=text,
        warnings=warnings,
    )


# Chapter headings commonly found in English and Assamese/Bengali Bible PDFs.
# Assamese uses the Bengali digit block, which _convert_indic_numeral handles.
_CHAPTER_WORD = r"(?:chapter|chap\.?|অধ্যায়|অধ্যায়)"
_CHAPTER_NUMBER = r"(\d+|[০-৯]+)"
_CHAPTER_LINE_RE = re.compile(
    r"^\s*(?:" +
    _CHAPTER_WORD + r"\s*" + _CHAPTER_NUMBER +
    r"|" + _CHAPTER_NUMBER + r"\s*" + _CHAPTER_WORD +
    r")\s*[:.\-–—]?\s*$",
    re.IGNORECASE,
)

_VERSE_AT_LINE_START_RE = re.compile(
    r"^\s*(\d+|[०-९]+|[੦-੯]+|[૦-૯]+|[୦-୯]+|[௦-௯]+|"
    r"[౦-౯]+|[೦-೯]+|[൦-൯]+|[০-৯]+)"
    r"\s*[.\:)}\]]*\s*(.*)$"
)

_FOOTNOTE_LINE_RE = re.compile(r"^[a-z]\s+\d+:\d+\s+", re.IGNORECASE)
_HEADING_PREFIX = "[[HEADING]]"
_VERSE_INLINE_RE = re.compile(
    r"(?<![\d:])"
    r"(\d{1,3}|[०-९]+|[੦-੯]+|[૦-૯]+|[୦-୯]+|[௦-௯]+|"
    r"[౦-౯]+|[೦-೯]+|[൦-൯]+|[০-৯]+)"
    r"(?:[-–—]"
    r"(\d{1,3}|[०-९]+|[੦-੯]+|[૦-૯]+|[୦-୯]+|[௦-௯]+|"
    r"[౦-౯]+|[೦-೯]+|[൦-൯]+|[০-৯]+))?"
    r"[\u2009\u202f\t]"
)


def _clean_pdf_text(text: str) -> str:
    """Remove extraction artifacts without changing Assamese letters."""
    cleaned = []
    for char in text or "":
        if char == "\ufffd":
            continue
        if char in "\n\t":
            cleaned.append(char)
            continue
        if unicodedata.category(char).startswith("C"):
            continue
        cleaned.append(char)
    return "".join(cleaned)


def _chapter_number_from_line(line: str) -> int:
    match = _CHAPTER_LINE_RE.match(line)
    if not match:
        return -1
    number = match.group(1) or match.group(2)
    return _convert_indic_numeral(number)


def _parse_chapter_lines(
        lines: List[str],
        heading_sink: Optional[List[ScriptHeading]] = None
        ) -> Dict[int, str]:
    """Parse one chapter section and reject page numbers/footnote headers."""
    filtered_lines: List[str] = []
    heading_positions: List[Tuple[int, str]] = []
    joined_length = 0
    for raw_line in lines:
        line = _clean_pdf_text(raw_line).strip()
        if not line:
            continue
        if line.isdigit() or _FOOTNOTE_LINE_RE.match(line):
            continue
        if line.startswith(_HEADING_PREFIX):
            heading_text = line[len(_HEADING_PREFIX):].strip()
            if heading_text:
                heading_positions.append((joined_length, heading_text))
            continue
        filtered_lines.append(line)
        joined_length += len(line) + 1

    # IRV Assamese places verse numbers inline and follows them with U+2009
    # THIN SPACE. Preserve only a strict Verse 1, Verse 2, ... sequence so
    # printed page numbers and chapter:verse references cannot become markers.
    joined = "\n".join(filtered_lines)
    accepted: List[Tuple[List[int], int, int]] = []
    expected_number = 1
    for match in _VERSE_INLINE_RE.finditer(joined):
        range_start = _convert_indic_numeral(match.group(1))
        range_end = (
            _convert_indic_numeral(match.group(2))
            if match.group(2) else range_start)
        if (range_start == expected_number and
                range_end >= range_start and range_end - range_start <= 10):
            verse_numbers = list(range(range_start, range_end + 1))
            accepted.append((verse_numbers, match.start(), match.end()))
            expected_number = range_end + 1

    if accepted:
        inline_verses: Dict[int, str] = {}
        for index, (verse_numbers, _start, content_start) in enumerate(accepted):
            content_end = (
                accepted[index + 1][1]
                if index + 1 < len(accepted) else len(joined))
            verse_text = joined[content_start:content_end].strip()
            # A printed range (for example 3-4) has one combined text block.
            # Keep the text on the first verse and a blank placeholder on the
            # remaining verse(s), which makes Auto-Mark interpolate them and
            # require manual review instead of inventing a false word match.
            inline_verses[verse_numbers[0]] = verse_text
            for verse_number in verse_numbers[1:]:
                inline_verses[verse_number] = ""
        if inline_verses:
            if heading_sink is not None:
                for position, text in heading_positions:
                    following = next(
                        (numbers[0] for numbers, marker_start, _marker_end
                         in accepted if marker_start >= position),
                        max(inline_verses) + 1)
                    heading_sink.append(ScriptHeading(
                        text=text, before_verse=following))
            return inline_verses

    # Fallback for scripts that put one verse number at each line start.
    verses: Dict[int, str] = {}
    current_verse = -1
    current_text: List[str] = []

    def save_current() -> None:
        nonlocal current_verse, current_text
        if current_verse > 0:
            verse_text = " ".join(
                part for part in current_text if part).strip()
            if verse_text:
                verses[current_verse] = verse_text
        current_verse = -1
        current_text = []

    pending_headings = iter(heading_positions)
    # Plain-text fallback cannot retain exact character positions after line
    # filtering; headings are attached to the next verse when possible.
    fallback_headings = [
        ScriptHeading(text=text, before_verse=1)
        for _position, text in pending_headings]
    for line in filtered_lines:
        verse_match = _VERSE_AT_LINE_START_RE.match(line)
        if verse_match:
            verse_number = _convert_indic_numeral(verse_match.group(1))
            rest = verse_match.group(2).strip()
            # A standalone number is normally a printed page number.
            if verse_number > 0 and rest:
                save_current()
                current_verse = verse_number
                current_text = [rest]
                continue

        if current_verse > 0:
            current_text.append(line)

    save_current()
    if heading_sink is not None:
        for heading in fallback_headings:
            heading.before_verse = min(
                (number for number in verses if number >= heading.before_verse),
                default=max(verses, default=0) + 1)
            heading_sink.append(heading)
    return verses


def parse_book_chapters_from_text(
        text: str,
        headings_out: Optional[
            Dict[Tuple[str, int], List[ScriptHeading]]] = None
        ) -> Dict[Tuple[str, int], Dict[int, str]]:
    """Recognize a complete 66-book Bible by its canonical chapter sequence.

    IRV Assamese uses headings such as ``1 অধ্যায়``. Each reset to chapter 1
    begins the next canonical book. This inference is enabled only when all 66
    runs exactly match the chapter counts in the built-in Bible database.
    """
    from .bible_db import KJV

    cleaned_text = _clean_pdf_text(text)
    lines = cleaned_text.splitlines()
    headings: List[Tuple[int, int]] = []
    for line_index, line in enumerate(lines):
        chapter = _chapter_number_from_line(line.strip())
        if chapter > 0:
            headings.append((line_index, chapter))

    if not headings:
        return {}

    runs: List[List[int]] = []
    for _line_index, chapter in headings:
        if chapter == 1:
            runs.append([])
        if not runs:
            return {}
        runs[-1].append(chapter)

    book_order = list(KJV.keys())
    if len(runs) != len(book_order):
        return {}
    for book, run in zip(book_order, runs):
        expected = list(range(1, len(KJV[book]) + 1))
        if run != expected:
            return {}

    result: Dict[Tuple[str, int], Dict[int, str]] = {}
    book_index = -1
    for heading_index, (line_index, chapter) in enumerate(headings):
        if chapter == 1:
            book_index += 1
        end_line = (
            headings[heading_index + 1][0]
            if heading_index + 1 < len(headings) else len(lines))
        chapter_headings: List[ScriptHeading] = []
        verses = _parse_chapter_lines(
            lines[line_index + 1:end_line], chapter_headings)
        if verses:
            key = (book_order[book_index], chapter)
            result[key] = verses
            if headings_out is not None and chapter_headings:
                headings_out[key] = chapter_headings
    return result


def parse_chapters_from_text(
        text: str,
        headings_out: Optional[Dict[int, List[ScriptHeading]]] = None
        ) -> Dict[int, Dict[int, str]]:
    """Parse a script without allowing repeated verse numbers to overwrite.

    Chapter 0 represents a single chapter whose number was not present in the
    text. The GUI can safely associate that script with one selected WAV.
    """
    if not text or not text.strip():
        return {}

    lines = _clean_pdf_text(text).splitlines()
    chapter_starts: List[Tuple[int, int]] = []
    for index, raw_line in enumerate(lines):
        chapter_number = _chapter_number_from_line(raw_line.strip())
        if chapter_number > 0:
            chapter_starts.append((index, chapter_number))

    if not chapter_starts:
        verses = _parse_chapter_lines(lines)
        return {0: verses} if verses else {}

    chapters: Dict[int, Dict[int, str]] = {}
    for position, (start, chapter) in enumerate(chapter_starts):
        end = (
            chapter_starts[position + 1][0]
            if position + 1 < len(chapter_starts) else len(lines))
        chapter_headings: List[ScriptHeading] = []
        verses = _parse_chapter_lines(
            lines[start + 1:end], chapter_headings)
        if verses:
            chapters[chapter] = verses
            if headings_out is not None and chapter_headings:
                headings_out[chapter] = chapter_headings
    return chapters


def parse_pdf_chapters(path: str) -> ParsedScriptCollection:
    """Extract a PDF into book/chapter-aware or chapter-only mappings."""
    if not _check_fitz():
        return ParsedScriptCollection(
            chapters={},
            warnings=["PyMuPDF not installed. Install with: pip install PyMuPDF"])

    raw_text = extract_text_from_pdf(path)
    book_headings: Dict[
        Tuple[str, int], List[ScriptHeading]] = {}
    headings: Dict[int, List[ScriptHeading]] = {}
    book_chapters = parse_book_chapters_from_text(
        raw_text, book_headings)
    chapters = (
        {} if book_chapters else
        parse_chapters_from_text(raw_text, headings))
    warnings = []
    if book_chapters:
        warnings.append(
            "Recognized a complete 66-book Bible; WAVs will be matched by "
            "both book and chapter.")
    elif not chapters:
        warnings.append(
            "No chapter/verse structure could be extracted from the PDF.")
    elif 0 in chapters and len(chapters) > 1:
        warnings.append(
            "Some verses appeared before the first recognized chapter heading.")
    return ParsedScriptCollection(
        chapters=chapters, book_chapters=book_chapters,
        headings=headings, book_headings=book_headings,
        raw_text=raw_text, warnings=warnings)


def parse_text_chapters(text: str) -> ParsedScriptCollection:
    """Plain-text equivalent of parse_pdf_chapters()."""
    book_headings: Dict[
        Tuple[str, int], List[ScriptHeading]] = {}
    headings: Dict[int, List[ScriptHeading]] = {}
    book_chapters = parse_book_chapters_from_text(
        text, book_headings)
    chapters = (
        {} if book_chapters else
        parse_chapters_from_text(text, headings))
    warnings = []
    if book_chapters:
        warnings.append(
            "Recognized a complete 66-book Bible; WAVs will be matched by "
            "both book and chapter.")
    elif not chapters:
        warnings.append(
            "No chapter/verse structure could be extracted from the text.")
    return ParsedScriptCollection(
        chapters=chapters, book_chapters=book_chapters,
        headings=headings, book_headings=book_headings,
        raw_text=text, warnings=warnings)


# ---------------------------------------------------------------------------
# Indian language names for UI
# ---------------------------------------------------------------------------
INDIAN_LANGUAGES = {
    "hi": "Hindi (हिन्दी)",
    "ta": "Tamil (தமிழ்)",
    "te": "Telugu (తెలుగు)",
    "kn": "Kannada (ಕನ್ನಡ)",
    "ml": "Malayalam (മലയാളം)",
    "bn": "Bengali (বাংলা)",
    "mr": "Marathi (मराठी)",
    "gu": "Gujarati (ગુજરાતી)",
    "pa": "Punjabi (ਪੰਜਾਬੀ)",
    "ur": "Urdu (اردو)",
    "or": "Odia (ଓଡ଼ିଆ)",
    "as": "Assamese (অসমীয়া)",
    "mai": "Maithili (मैथिली)",
    "sa": "Sanskrit (संस्कृतम्)",
    "ks": "Kashmiri (कॉशुर)",
    "ne": "Nepali (नेपाली)",
    "sd": "Sindhi (سنڌي)",
    "kok": "Konkani (कोंकणी)",
    "doi": "Dogri (डोगरी)",
    "mni": "Manipuri (মৈতৈলোন্)",
    "sat": "Santali (ᱥᱟᱱᱛᱟᱲᱤ)",
    "bo": "Bodo (बड़ो)",
    "en": "English",
}


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m engine.pdf_parser <script.pdf>")
        sys.exit(1)
    result = parse_pdf(sys.argv[1])
    print("Verses found: %d" % result.total_verses)
    if result.warnings:
        print("Warnings:")
        for w in result.warnings:
            print("  - %s" % w)
    print()
    for num in sorted(result.verses.keys())[:10]:
        txt = result.verses[num]
        preview = txt[:80] + "..." if len(txt) > 80 else txt
        print("  %3d: %s" % (num, preview))
    if result.total_verses > 10:
        print("  ... (%d more)" % (result.total_verses - 10))
