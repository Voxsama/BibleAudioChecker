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
import sys
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


def _missing_pymupdf_message() -> str:
    if getattr(sys, "frozen", False):
        return ("PDF support is missing from this installation. Reinstall "
                "ScriptureSound QC using the complete Windows installer.")
    return "PyMuPDF (fitz) is not installed. Install with: pip install PyMuPDF"


def _check_fitz():
    """Check if PyMuPDF is available."""
    try:
        import fitz  # noqa: F401
        return True
    except ImportError:
        return False


def extract_text_from_pdf(path: str) -> str:
    """Extract all text from a PDF file using PyMuPDF."""
    if not os.path.isfile(path):
        raise FileNotFoundError("PDF file not found: %s" % path)

    try:
        import fitz
    except ImportError:
        raise PDFParseError(_missing_pymupdf_message())

    try:
        doc = fitz.open(path)
    except Exception as e:
        raise PDFParseError("Could not open PDF: %s" % e)

    text_parts = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        # Use "text" mode which preserves reading order and handles
        # multi-column, Indian scripts, RTL, etc.
        text = page.get_text("text")
        if text:
            text_parts.append(text.strip())

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
            warnings=[_missing_pymupdf_message()])

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
