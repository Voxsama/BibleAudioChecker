"""
script_verify.py — compare transcribed audio segments against expected verse text
from a parsed PDF script.

Uses difflib's SequenceMatcher for fuzzy text comparison that works across all
languages (Indian scripts, Latin, etc.) without needing language-specific NLP.

The verification flow:
  1. Read markers from the WAV to identify verse segment boundaries
  2. Transcribe each verse segment using Whisper (local or API)
  3. Compare each transcription against the expected verse text from the PDF
  4. Report mismatches with similarity scores and details

A verse "matches" if the similarity ratio >= the configured threshold (default 0.6).
Lower thresholds accommodate Whisper's imperfect transcription of Indian languages.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .config import Config
from .transcriber import Transcriber, TranscriptionSegment
from .wav_markers import Marker


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------
@dataclass
class VerseComparison:
    """Comparison result for a single verse."""
    verse_number: int
    expected_text: str           # from PDF script
    transcribed_text: str        # from Whisper
    similarity: float            # 0.0 - 1.0
    passed: bool
    detail: str = ""             # human-readable explanation
    start_s: float = 0.0        # segment start time
    end_s: float = 0.0          # segment end time


@dataclass
class ScriptVerifyResult:
    """Full script verification result for one file."""
    comparisons: List[VerseComparison] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    avg_similarity: float = 0.0
    verses_checked: int = 0
    verses_passed: int = 0
    error: str = ""

    @property
    def ok(self) -> bool:
        if self.error:
            return False
        return len(self.issues) == 0 and self.verses_checked > 0


# ---------------------------------------------------------------------------
# Text normalization for comparison
# ---------------------------------------------------------------------------
def _normalize_text(text: str) -> str:
    """Normalize text for comparison — handles Indian scripts gracefully.

    - Lowercases Latin characters (Indian scripts don't have case)
    - Removes common punctuation but preserves Indic script characters
      (including combining marks like virama, matras, etc.)
    - Normalizes Unicode (NFC form)
    - Collapses whitespace
    """
    if not text:
        return ""

    # Unicode NFC normalization
    text = unicodedata.normalize("NFC", text)

    # Lowercase (only affects Latin characters)
    text = text.lower()

    # Remove only ASCII punctuation and common Unicode punctuation marks,
    # but preserve all script characters (including Indic combining marks
    # which \w incorrectly strips because they are category Mn/Mc).
    # We remove: ASCII punct, dandas, common quote marks, brackets
    text = re.sub(
        r"[\u0000-\u002F\u003A-\u0040\u005B-\u0060\u007B-\u00BF"
        r"\u0964\u0965\u2000-\u206F\u2E00-\u2E7F\u3000-\u303F"
        r"\uFF00-\uFF0F\uFF1A-\uFF20\uFF3B-\uFF40\uFF5B-\uFF65]",
        " ", text)

    # Collapse multiple spaces
    text = re.sub(r"\s+", " ", text).strip()

    return text


def _compute_similarity(text_a: str, text_b: str) -> float:
    """Compute similarity ratio between two texts using SequenceMatcher.

    Works for any language/script since it operates on character sequences.
    """
    norm_a = _normalize_text(text_a)
    norm_b = _normalize_text(text_b)

    if not norm_a and not norm_b:
        return 1.0  # both empty = match
    if not norm_a or not norm_b:
        return 0.0  # one empty = no match

    # Use SequenceMatcher which works on any Unicode string
    return difflib.SequenceMatcher(None, norm_a, norm_b).ratio()


def _word_level_similarity(text_a: str, text_b: str) -> float:
    """Word-level similarity — useful for longer texts where character-level
    matching is too strict."""
    norm_a = _normalize_text(text_a)
    norm_b = _normalize_text(text_b)

    if not norm_a and not norm_b:
        return 1.0
    if not norm_a or not norm_b:
        return 0.0

    words_a = norm_a.split()
    words_b = norm_b.split()

    return difflib.SequenceMatcher(None, words_a, words_b).ratio()


def compute_similarity(text_a: str, text_b: str) -> float:
    """Combined similarity using both character-level and word-level matching.

    Takes the higher of the two scores, since word-level is better for longer
    texts while character-level is better for short phrases.
    """
    char_sim = _compute_similarity(text_a, text_b)
    word_sim = _word_level_similarity(text_a, text_b)
    return max(char_sim, word_sim)


# ---------------------------------------------------------------------------
# Marker-based segment boundaries
# ---------------------------------------------------------------------------
def _get_verse_segments(markers: List[Marker], cfg: Config,
                        file_duration_s: float) -> List[Tuple[float, float, int]]:
    """Extract verse segment boundaries from markers.

    Returns list of (start_s, end_s, verse_number) tuples.
    Each verse segment runs from its marker to the next verse marker (or EOF).
    """
    verse_word = cfg.verse_word.strip().lower()
    verse_re = re.compile(r"^%s\s*0*(\d+)\s*$" % re.escape(verse_word), re.IGNORECASE)

    # Collect verse markers with their timestamps
    verse_markers: List[Tuple[float, int]] = []
    for m in markers:
        label = (m.label or "").strip()
        match = verse_re.match(label)
        if match:
            verse_num = int(match.group(1))
            verse_markers.append((m.seconds, verse_num))

    # Sort by time
    verse_markers.sort(key=lambda x: x[0])

    # Build segments: each verse runs from its marker to the next marker
    segments = []
    for i, (start_s, verse_num) in enumerate(verse_markers):
        if i + 1 < len(verse_markers):
            end_s = verse_markers[i + 1][0]
        else:
            end_s = file_duration_s
        segments.append((start_s, end_s, verse_num))

    return segments


# ---------------------------------------------------------------------------
# Main verification function
# ---------------------------------------------------------------------------
def verify_script(path: str, markers: List[Marker],
                  script_verses: Dict[int, str], cfg: Config) -> ScriptVerifyResult:
    """Verify audio content against expected script text.

    Args:
        path: path to the WAV file
        markers: list of markers read from the WAV
        script_verses: dict of verse_number -> expected text (from PDF)
        cfg: configuration with whisper settings and threshold

    Returns:
        ScriptVerifyResult with per-verse comparisons and overall result
    """
    result = ScriptVerifyResult()

    if not script_verses:
        result.error = "No script verses provided for comparison."
        return result

    if not markers:
        result.error = "No markers in WAV file — cannot determine verse boundaries."
        return result

    # Get file duration
    try:
        from .wavio import read_wav_info
        info = read_wav_info(path)
        duration_s = info.n_frames / float(info.sample_rate) if info.sample_rate > 0 else 0
    except Exception as e:
        result.error = "Could not read WAV info: %s" % e
        return result

    if duration_s <= 0:
        result.error = "WAV file has zero duration."
        return result

    # Get verse segment boundaries from markers
    segments = _get_verse_segments(markers, cfg, duration_s)
    if not segments:
        result.error = "No verse markers found in WAV — cannot segment audio for verification."
        return result

    # Initialize transcriber
    transcriber = Transcriber(
        mode=cfg.whisper_mode,
        model=cfg.whisper_model,
        language=cfg.whisper_language,
        api_key=cfg.openai_api_key,
    )

    if not transcriber.is_available():
        result.error = transcriber.get_availability_message()
        return result

    # Transcribe all verse segments
    try:
        transcriptions = transcriber.transcribe_segments(path, segments)
    except Exception as e:
        result.error = "Transcription failed: %s" % e
        return result

    # Compare each transcription against expected text
    threshold = cfg.script_match_threshold
    total_similarity = 0.0
    checked = 0

    for trans_seg in transcriptions:
        verse_num = trans_seg.verse_number
        expected = script_verses.get(verse_num)

        if expected is None:
            # Verse not in script — can't verify
            continue

        transcribed = trans_seg.text
        similarity = compute_similarity(expected, transcribed)
        passed = similarity >= threshold
        checked += 1
        total_similarity += similarity

        if passed:
            result.verses_passed += 1
            detail = "Match (%.0f%% similar)" % (similarity * 100)
        else:
            detail = "Mismatch (%.0f%% similar)" % (similarity * 100)
            # Add context about what's different
            if not transcribed.strip():
                detail += " — no speech detected in segment"
            else:
                # Show a snippet of expected vs transcribed
                exp_preview = expected[:60] + "..." if len(expected) > 60 else expected
                got_preview = transcribed[:60] + "..." if len(transcribed) > 60 else transcribed
                detail += " — expected: '%s', heard: '%s'" % (exp_preview, got_preview)

            result.issues.append("Verse %d: %s" % (verse_num, detail))

        result.comparisons.append(VerseComparison(
            verse_number=verse_num,
            expected_text=expected,
            transcribed_text=transcribed,
            similarity=similarity,
            passed=passed,
            detail=detail,
            start_s=trans_seg.start_s,
            end_s=trans_seg.end_s,
        ))

    result.verses_checked = checked
    result.avg_similarity = (total_similarity / checked) if checked > 0 else 0.0

    # If we couldn't check any verses, that's an issue
    if checked == 0:
        result.error = ("No verses could be verified — script verse numbers "
                        "don't match the marker verse numbers in the WAV.")

    return result


# ---------------------------------------------------------------------------
# Standalone utility: verify without the full checker pipeline
# ---------------------------------------------------------------------------
def verify_file_against_pdf(wav_path: str, pdf_path: str,
                            cfg: Optional[Config] = None) -> ScriptVerifyResult:
    """Convenience function: verify a WAV file against a PDF script.

    Reads markers from WAV, parses PDF, then runs verification.
    """
    if cfg is None:
        cfg = Config()

    from .wav_markers import read_markers
    from .pdf_parser import parse_pdf

    markers = read_markers(wav_path)
    parsed = parse_pdf(pdf_path)

    if not parsed.ok:
        return ScriptVerifyResult(
            error="Could not parse PDF: %s" % "; ".join(parsed.warnings))

    return verify_script(wav_path, markers, parsed.verses, cfg)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python -m engine.script_verify <file.wav> <script.pdf> [language]")
        sys.exit(1)

    wav = sys.argv[1]
    pdf = sys.argv[2]
    lang = sys.argv[3] if len(sys.argv) > 3 else ""

    cfg = Config()
    if lang:
        cfg.whisper_language = lang

    print("Verifying: %s against %s" % (wav, pdf))
    r = verify_file_against_pdf(wav, pdf, cfg)

    if r.error:
        print("ERROR: %s" % r.error)
        sys.exit(1)

    print("Checked %d verses, %d passed (avg similarity: %.0f%%)" % (
        r.verses_checked, r.verses_passed, r.avg_similarity * 100))

    if r.issues:
        print("\nIssues:")
        for issue in r.issues:
            print("  - %s" % issue)
    else:
        print("\nAll verses match the script!")
