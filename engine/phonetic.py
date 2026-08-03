"""Cross-script phonetic keys for Indic speech-to-script alignment.

Whisper may decode Assamese speech using Devanagari even when ``language=as``
is forced. Bible PDFs normally contain Assamese/Bengali script. Converting
both sides to a deliberately coarse consonant key supplies stable anchors
without changing the text shown to the operator.
"""

from __future__ import annotations

import re
import unicodedata
from typing import List, Optional


_SCRIPT_RANGES = (
    (0x0900, 0x097F, "DEVANAGARI"),
    (0x0980, 0x09FF, "BENGALI"),
    (0x0A00, 0x0A7F, "GURMUKHI"),
    (0x0A80, 0x0AFF, "GUJARATI"),
    (0x0B00, 0x0B7F, "ORIYA"),
    (0x0B80, 0x0BFF, "TAMIL"),
    (0x0C00, 0x0C7F, "TELUGU"),
    (0x0C80, 0x0CFF, "KANNADA"),
    (0x0D00, 0x0D7F, "MALAYALAM"),
)


def _indic_scheme(token: str) -> Optional[str]:
    for character in token:
        codepoint = ord(character)
        for start, end, scheme in _SCRIPT_RANGES:
            if start <= codepoint <= end:
                return scheme
    return None


def _transliterate_indic(token: str, scheme_name: str) -> str:
    try:
        from indic_transliteration import sanscript
        from indic_transliteration.sanscript import transliterate
    except ImportError:
        return token

    # Assamese letters not present in ordinary Bengali are normalized to
    # their closest transliteration equivalents.
    if scheme_name == "BENGALI":
        token = token.replace("\u09f0", "\u09b0")  # ৰ -> র
        token = token.replace("\u09f1", "\u09ac")  # ৱ -> ব
    source_scheme = getattr(sanscript, scheme_name)
    return transliterate(token, source_scheme, sanscript.ITRANS)


def _coarse_phonetic_key(roman: str) -> str:
    key = unicodedata.normalize("NFKD", roman).lower()
    key = re.sub(r"chh|ch", "c", key)
    key = re.sub(r"sh", "s", key)
    key = re.sub(r"([kgcjtdpb])h", r"\1", key)
    key = key.replace("v", "b").replace("w", "b")
    key = key.replace("q", "k").replace("z", "j")
    key = re.sub(r"[^a-z0-9]", "", key)
    if len(key) > 2 and key.endswith("a"):
        key = key[:-1]

    # Consonant skeletons tolerate vowel spelling differences between
    # Assamese and Devanagari decoding (for example ইনোচ / इनूस).
    skeleton = re.sub(r"[aeiou]", "", key).replace("c", "s")
    return skeleton if len(skeleton) >= 2 else key


def alignment_tokens(text: str) -> List[str]:
    normalized = unicodedata.normalize("NFC", text or "").lower()
    cleaned = []
    for character in normalized:
        category = unicodedata.category(character)
        cleaned.append(
            " " if category.startswith(("P", "S")) else character)
    raw_tokens = [
        token for token in
        re.sub(r"\s+", " ", "".join(cleaned)).strip().split(" ")
        if token]

    output = []
    for token in raw_tokens:
        scheme = _indic_scheme(token)
        if scheme:
            output.append(_coarse_phonetic_key(
                _transliterate_indic(token, scheme)))
        else:
            output.append(token)
    return [token for token in output if token]
