"""
bible_db.py — KJV (Protestant, 66-book) versification: verses-per-chapter for
every chapter, plus a flexible filename parser that maps names like
"Gen_001", "GEN_001", "1Sa_005", "Ps_119" to (book, chapter, expected_verses).

The verse counts are the standard King James Version chapter/verse totals.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# KJV verses-per-chapter. Each entry: canonical book name -> list of ints
# (index 0 = chapter 1). Standard KJV versification.
# ---------------------------------------------------------------------------
KJV: "Dict[str, List[int]]" = {
    "Genesis": [31,25,24,26,32,22,24,22,29,32,32,20,18,24,21,16,27,33,38,18,34,24,20,67,34,35,46,22,35,43,55,32,20,31,29,43,36,30,23,23,57,38,34,34,28,34,31,22,33,26],
    "Exodus": [22,25,22,31,23,30,25,32,35,29,10,51,22,31,27,36,16,27,25,26,36,31,33,18,40,37,21,43,46,38,18,35,23,35,35,38,29,31,43,38],
    "Leviticus": [17,16,17,35,19,30,38,36,24,20,47,8,59,57,33,34,16,30,37,27,24,33,44,23,55,46,34],
    "Numbers": [54,34,51,49,31,27,89,26,23,36,35,16,33,45,41,50,13,32,22,29,35,41,30,25,18,65,23,31,40,16,54,42,56,29,34,13],
    "Deuteronomy": [46,37,29,49,33,25,26,20,29,22,32,32,18,29,23,22,20,22,21,20,23,30,25,22,19,19,26,68,29,20,30,52,29,12],
    "Joshua": [18,24,17,24,15,27,26,35,27,43,23,24,33,15,63,10,18,28,51,9,45,34,16,33],
    "Judges": [36,23,31,24,31,40,25,35,57,18,40,15,25,20,20,31,13,31,30,48,25],
    "Ruth": [22,23,18,22],
    "1 Samuel": [28,36,21,22,12,21,17,22,27,27,15,25,23,52,35,23,58,30,24,42,15,23,29,22,44,25,12,25,11,31,13],
    "2 Samuel": [27,32,39,12,25,23,29,18,13,19,27,31,39,33,37,23,29,33,43,26,22,51,39,25],
    "1 Kings": [53,46,28,34,18,38,51,66,28,29,43,33,34,31,34,34,24,46,21,43,29,53],
    "2 Kings": [18,25,27,44,27,33,20,29,37,36,21,21,25,29,38,20,41,37,37,21,26,20,37,20,30],
    "1 Chronicles": [54,55,24,43,26,81,40,40,44,14,47,40,14,17,29,43,27,17,19,8,30,19,32,31,31,32,34,21,30],
    "2 Chronicles": [17,18,17,22,14,42,22,18,31,19,23,16,22,15,19,14,19,34,11,37,20,12,21,27,28,23,9,27,36,27,21,33,25,33,27,23],
    "Ezra": [11,70,13,24,17,22,28,36,15,44],
    "Nehemiah": [11,20,32,23,19,19,73,18,38,39,36,47,31],
    "Esther": [22,23,15,17,14,14,10,17,32,3],
    "Job": [22,13,26,21,27,30,21,22,35,22,20,25,28,22,35,22,16,21,29,29,34,30,17,25,6,14,23,28,25,31,40,22,33,37,16,33,24,41,30,24,34,17],
    "Psalms": [6,12,8,8,12,10,17,9,20,18,7,8,6,7,5,11,15,50,14,9,13,31,6,10,22,12,14,9,11,12,24,11,22,22,28,12,40,22,13,17,13,11,5,26,17,11,9,14,20,23,19,9,6,7,23,13,11,11,17,12,8,12,11,10,13,20,7,35,36,5,24,20,28,23,10,12,20,72,13,19,16,8,18,12,13,17,7,18,52,17,16,15,5,23,11,13,12,9,9,5,8,28,22,35,45,48,43,13,31,7,10,10,9,8,18,19,2,29,176,7,8,9,4,8,5,6,5,6,8,8,3,18,3,3,21,26,9,8,24,13,10,7,12,15,21,10,20,14,9,6],
    "Proverbs": [33,22,35,27,23,35,27,36,18,32,31,28,25,35,33,33,28,24,29,30,31,29,35,34,28,28,27,28,27,33,31],
    "Ecclesiastes": [18,26,22,16,20,12,29,17,18,20,10,14],
    "Song of Solomon": [17,17,11,16,16,13,13,14],
    "Isaiah": [31,22,26,6,30,13,25,22,21,34,16,6,22,32,9,14,14,7,25,6,17,25,18,23,12,21,13,29,24,33,9,20,24,17,10,22,38,22,8,31,29,25,28,28,25,13,15,22,26,11,23,15,12,17,13,12,21,14,21,22,11,12,19,12,25,24],
    "Jeremiah": [19,37,25,31,31,30,34,22,26,25,23,17,27,22,21,21,27,23,15,18,14,30,40,10,38,24,22,17,32,24,40,44,26,22,19,32,21,28,18,16,18,22,13,30,5,28,7,47,39,46,64,34],
    "Lamentations": [22,22,66,22,22],
    "Ezekiel": [28,10,27,17,17,14,27,18,11,22,25,28,23,23,8,63,24,32,14,49,32,31,49,27,17,21,36,26,21,26,18,32,33,31,15,38,28,23,29,49,26,20,27,31,25,24,23,35],
    "Daniel": [21,49,30,37,31,28,28,27,27,21,45,13],
    "Hosea": [11,23,5,19,15,11,16,14,17,15,12,14,16,9],
    "Joel": [20,32,21],
    "Amos": [15,16,15,13,27,14,17,14,15],
    "Obadiah": [21],
    "Jonah": [17,10,10,11],
    "Micah": [16,13,12,13,15,16,20],
    "Nahum": [15,13,19],
    "Habakkuk": [17,20,19],
    "Zephaniah": [18,15,20],
    "Haggai": [15,23],
    "Zechariah": [21,13,10,14,11,15,14,23,17,12,17,14,9,21],
    "Malachi": [14,17,18,6],
    "Matthew": [25,23,17,25,48,34,29,34,38,42,30,50,58,36,39,28,27,35,30,34,46,46,39,51,46,75,66,20],
    "Mark": [45,28,35,41,43,56,37,38,50,52,33,44,37,72,47,20],
    "Luke": [80,52,38,44,39,49,50,56,62,42,54,59,35,35,32,31,37,43,48,47,38,71,56,53],
    "John": [51,25,36,54,47,71,53,59,41,42,57,50,38,31,27,33,26,40,42,31,25],
    "Acts": [26,47,26,37,42,15,60,40,43,48,30,25,52,28,41,40,34,28,41,38,40,30,35,27,27,32,44,31],
    "Romans": [32,29,31,25,21,23,25,39,33,21,36,21,14,23,33,27],
    "1 Corinthians": [31,16,23,21,13,20,40,13,27,33,34,31,13,40,58,24],
    "2 Corinthians": [24,17,18,18,21,18,16,24,15,18,33,21,14],
    "Galatians": [24,21,29,31,26,18],
    "Ephesians": [23,22,21,32,33,24],
    "Philippians": [30,30,21,23],
    "Colossians": [29,23,25,18],
    "1 Thessalonians": [10,20,13,18,28],
    "2 Thessalonians": [12,17,18],
    "1 Timothy": [20,15,16,16,25,21],
    "2 Timothy": [18,26,17,22],
    "Titus": [16,15,15],
    "Philemon": [25],
    "Hebrews": [14,18,19,16,14,20,28,13,28,39,40,29,25],
    "James": [27,26,18,17,20],
    "1 Peter": [25,25,22,19,14],
    "2 Peter": [21,22,18],
    "1 John": [10,29,24,21,21],
    "2 John": [13],
    "3 John": [14],
    "Jude": [25],
    "Revelation": [20,29,22,11,14,17,17,13,21,11,19,17,18,20,8,21,18,24,21,15,27,21],
}

# ---------------------------------------------------------------------------
# Aliases: many spellings/abbreviations -> canonical book name.
# Keys are stored lowercase with spaces removed.
# ---------------------------------------------------------------------------
_ALIASES: "Dict[str, str]" = {}


def _add_aliases(canonical: str, names):
    for n in names:
        _ALIASES[n.lower().replace(" ", "")] = canonical


_add_aliases("Genesis", ["Genesis", "Gen", "Ge", "Gn"])
_add_aliases("Exodus", ["Exodus", "Exo", "Exod", "Ex"])
_add_aliases("Leviticus", ["Leviticus", "Lev", "Lv"])
_add_aliases("Numbers", ["Numbers", "Num", "Nu", "Nm", "Nb"])
_add_aliases("Deuteronomy", ["Deuteronomy", "Deu", "Deut", "Dt"])
_add_aliases("Joshua", ["Joshua", "Jos", "Josh", "Jsh"])
_add_aliases("Judges", ["Judges", "Jdg", "Judg", "Jg"])
_add_aliases("Ruth", ["Ruth", "Rut", "Rth", "Ru"])
_add_aliases("1 Samuel", ["1Samuel", "1Sam", "1Sa", "1Sm", "1S", "ISam", "1stSamuel"])
_add_aliases("2 Samuel", ["2Samuel", "2Sam", "2Sa", "2Sm", "2S", "IISam", "2ndSamuel"])
_add_aliases("1 Kings", ["1Kings", "1Kgs", "1Ki", "1Kin", "1K", "IKgs"])
_add_aliases("2 Kings", ["2Kings", "2Kgs", "2Ki", "2Kin", "2K", "IIKgs"])
_add_aliases("1 Chronicles", ["1Chronicles", "1Chron", "1Chr", "1Ch", "1Cr"])
_add_aliases("2 Chronicles", ["2Chronicles", "2Chron", "2Chr", "2Ch", "2Cr"])
_add_aliases("Ezra", ["Ezra", "Ezr", "Ez"])
_add_aliases("Nehemiah", ["Nehemiah", "Neh", "Ne"])
_add_aliases("Esther", ["Esther", "Est", "Esth", "Es"])
_add_aliases("Job", ["Job", "Jb"])
_add_aliases("Psalms", ["Psalms", "Psalm", "Psa", "Ps", "Pslm", "Psm", "Pss"])
_add_aliases("Proverbs", ["Proverbs", "Prov", "Pro", "Prv", "Pr"])
_add_aliases("Ecclesiastes", ["Ecclesiastes", "Eccl", "Ecc", "Ec", "Qoh"])
_add_aliases("Song of Solomon", ["SongofSolomon", "Song", "Sng", "SoS", "SS", "Canticles", "Cant"])
_add_aliases("Isaiah", ["Isaiah", "Isa", "Is"])
_add_aliases("Jeremiah", ["Jeremiah", "Jer", "Je", "Jr"])
_add_aliases("Lamentations", ["Lamentations", "Lam", "La"])
_add_aliases("Ezekiel", ["Ezekiel", "Ezek", "Eze", "Ezk"])
_add_aliases("Daniel", ["Daniel", "Dan", "Dn", "Da"])
_add_aliases("Hosea", ["Hosea", "Hos", "Ho"])
_add_aliases("Joel", ["Joel", "Joe", "Jl"])
_add_aliases("Amos", ["Amos", "Amo", "Am"])
_add_aliases("Obadiah", ["Obadiah", "Oba", "Obad", "Ob"])
_add_aliases("Jonah", ["Jonah", "Jon", "Jnh"])
_add_aliases("Micah", ["Micah", "Mic", "Mc"])
_add_aliases("Nahum", ["Nahum", "Nah", "Na"])
_add_aliases("Habakkuk", ["Habakkuk", "Hab", "Hb"])
_add_aliases("Zephaniah", ["Zephaniah", "Zeph", "Zep", "Zp"])
_add_aliases("Haggai", ["Haggai", "Hag", "Hg"])
_add_aliases("Zechariah", ["Zechariah", "Zech", "Zec", "Zc"])
_add_aliases("Malachi", ["Malachi", "Mal", "Ml"])
_add_aliases("Matthew", ["Matthew", "Matt", "Mat", "Mt"])
_add_aliases("Mark", ["Mark", "Mar", "Mrk", "Mk", "Mr"])
_add_aliases("Luke", ["Luke", "Luk", "Lk", "Lu"])
_add_aliases("John", ["John", "Joh", "Jhn", "Jn"])
_add_aliases("Acts", ["Acts", "Act", "Ac"])
_add_aliases("Romans", ["Romans", "Rom", "Ro", "Rm"])
_add_aliases("1 Corinthians", ["1Corinthians", "1Cor", "1Co", "1C"])
_add_aliases("2 Corinthians", ["2Corinthians", "2Cor", "2Co", "2C"])
_add_aliases("Galatians", ["Galatians", "Gal", "Ga"])
_add_aliases("Ephesians", ["Ephesians", "Eph", "Ephes"])
_add_aliases("Philippians", ["Philippians", "Phil", "Php", "Pp"])
_add_aliases("Colossians", ["Colossians", "Col", "Co"])
_add_aliases("1 Thessalonians", ["1Thessalonians", "1Thess", "1Thes", "1Th"])
_add_aliases("2 Thessalonians", ["2Thessalonians", "2Thess", "2Thes", "2Th"])
_add_aliases("1 Timothy", ["1Timothy", "1Tim", "1Ti", "1Tm"])
_add_aliases("2 Timothy", ["2Timothy", "2Tim", "2Ti", "2Tm"])
_add_aliases("Titus", ["Titus", "Tit", "Ti"])
_add_aliases("Philemon", ["Philemon", "Phlm", "Phm", "Pm"])
_add_aliases("Hebrews", ["Hebrews", "Heb"])
_add_aliases("James", ["James", "Jas", "Jam", "Jm"])
_add_aliases("1 Peter", ["1Peter", "1Pet", "1Pe", "1Pt", "1P"])
_add_aliases("2 Peter", ["2Peter", "2Pet", "2Pe", "2Pt", "2P"])
_add_aliases("1 John", ["1John", "1Jn", "1Jo", "1Jhn", "1J"])
_add_aliases("2 John", ["2John", "2Jn", "2Jo", "2Jhn", "2J"])
_add_aliases("3 John", ["3John", "3Jn", "3Jo", "3Jhn", "3J"])
_add_aliases("Jude", ["Jude", "Jud", "Jd"])
_add_aliases("Revelation", ["Revelation", "Rev", "Re", "Rv", "Apocalypse"])


@dataclass
class BookChapter:
    book: str
    chapter: int
    expected_verses: int


def num_chapters(book: str) -> int:
    return len(KJV.get(book, []))


def expected_verses(book: str, chapter: int) -> Optional[int]:
    chapters = KJV.get(book)
    if not chapters or chapter < 1 or chapter > len(chapters):
        return None
    return chapters[chapter - 1]


# filename like  Gen_001,  GEN_001,  1Sa_005,  Ps-119,  Psalm 023, 1John_1
_PARSE_RE = re.compile(
    r"""^\s*
        (?P<book>(?:[1-3]\s*)?[A-Za-z]+(?:\s*[A-Za-z]+)*?)   # optional leading 1-3 + letters
        [\s_\-\.]+
        (?P<chap>\d+)
        \s*$""",
    re.VERBOSE,
)


def parse_filename(name: str) -> Optional[BookChapter]:
    """Parse a base filename (with or without extension) into BookChapter.

    Returns None if the book can't be recognised or chapter is out of range.
    Handles: Gen_001, GEN_001, 1Sa_005, Ps_119, 1John_1, "Song_008", etc.
    """
    base = os.path.splitext(os.path.basename(name))[0]
    m = _PARSE_RE.match(base)
    if not m:
        # try a fallback: split on last separator group
        m2 = re.match(r"^(?P<book>.+?)[\s_\-\.]+(?P<chap>\d+)\s*$", base)
        if not m2:
            return None
        m = m2
    book_token = m.group("book")
    chap = int(m.group("chap"))
    key = book_token.lower().replace(" ", "").replace("_", "")
    canonical = _ALIASES.get(key)
    if canonical is None:
        return None
    ev = expected_verses(canonical, chap)
    if ev is None:
        return None
    return BookChapter(canonical, chap, ev)


def total_verses() -> int:
    return sum(sum(ch) for ch in KJV.values())


def total_chapters() -> int:
    return sum(len(ch) for ch in KJV.values())


if __name__ == "__main__":
    print("Books:", len(KJV), "| chapters:", total_chapters(), "| verses:", total_verses())
    for t in ["Gen_001", "GEN_050", "1Sa_005", "Ps_119", "1John_1", "Rev_022", "Xyz_009", "Gen_099"]:
        print("%-10s -> %s" % (t, parse_filename(t)))
