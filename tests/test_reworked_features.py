"""Regression tests for the v3 GUI-supporting engine changes.

Run:
    python -m tests.test_reworked_features
"""

from __future__ import annotations

import os
import sys
import tempfile
import wave

import numpy as np

from engine.auto_marker import (
    auto_mark_file,
    _find_verse_boundaries_by_pauses,
    _find_verse_boundaries_by_transcription,
)
from engine.mastering import _fix_silence_sides, _measure_silence
from engine.pdf_parser import (
    _is_typographic_heading,
    parse_book_chapters_from_text,
    parse_chapters_from_text,
)
from engine.bible_db import KJV
from engine.languages import (
    INDIAN_LANGUAGES,
    indian_language,
    indian_language_options,
    indian_whisper_codes,
    whisper_language_options,
)


FAILURES = []


def check(condition, message):
    print("  [%s] %s" % ("ok  " if condition else "FAIL", message))
    if not condition:
        FAILURES.append(message)


def test_assamese_script_chapters():
    print("\nAssamese multi-chapter PDF text:")
    text = """অধ্যায় ১
১ আদিতে ঈশ্বৰে আকাশ-মণ্ডল আৰু পৃথিৱী সৃষ্টি কৰিলে।
২ পৃথিৱী আকাৰহীন আৰু শূন্য আছিল।
অধ্যায় ২
১ এইদৰে আকাশ-মণ্ডল আৰু পৃথিৱী সম্পূৰ্ণ হ'ল।
২ সপ্তম দিনত ঈশ্বৰে তেওঁৰ কাৰ্য শেষ কৰিলে।
"""
    chapters = parse_chapters_from_text(text)
    check(sorted(chapters) == [1, 2], "keeps Assamese chapters separate")
    check(sorted(chapters[1]) == [1, 2], "parses Bengali/Assamese verse numerals")
    check(chapters[1][1].startswith("আদিতে"), "preserves Assamese Unicode text")
    check(chapters[2][1].startswith("এইদৰে"), "does not overwrite repeated verse 1")


def test_irvasm_heading_typography():
    print("\nIRV Assamese PDF heading typography:")
    heading = [{
        "text": "section heading",
        "font": "GeetanjaliUni-Bold",
        "size": 12.0,
        "flags": 20,
        "color": 0x231F20,
    }]
    chapter_label = [{
        "text": "1 chapter",
        "font": "GeetanjaliUni-Bold",
        "size": 14.0,
        "flags": 20,
        "color": 0x231F20,
    }]
    verse_line = [
        {
            "text": "1",
            "font": "GeetanjaliUni-Bold",
            "size": 10.0,
            "flags": 20,
            "color": 0x231F20,
        },
        {
            "text": "verse text",
            "font": "GeetanjaliUni",
            "size": 12.0,
            "flags": 4,
            "color": 0x231F20,
        },
    ]
    coloured_bold = [{
        "text": "coloured label",
        "font": "GeetanjaliUni-Bold",
        "size": 12.0,
        "flags": 20,
        "color": 0xCC0000,
    }]
    check(
        _is_typographic_heading("section heading", heading),
        "accepts 12-point bold near-black text as a heading")
    check(
        not _is_typographic_heading("1 chapter", chapter_label),
        "keeps chapter labels separate from section headings")
    check(
        not _is_typographic_heading("1 verse text", verse_line),
        "does not mistake bold verse numbers for headings")
    check(
        not _is_typographic_heading("coloured label", coloured_bold),
        "does not treat coloured bold labels as black headings")


def test_irvasm_number_first_and_full_bible_mapping():
    print("\nIRV Assamese full-Bible structure:")
    compact_bible = []
    for book, expected_chapters in KJV.items():
        for chapter in range(1, len(expected_chapters) + 1):
            if book == "John" and chapter == 5:
                verse_text = (
                    "1\u2009one 2-3\u2009combined range 4\u2009four")
            else:
                verse_text = "1 %s %d verse text" % (book, chapter)
            compact_bible.append(
                "%d অধ্যায়\n%s" % (chapter, verse_text))
    parsed = parse_book_chapters_from_text("\n".join(compact_bible))
    check(len(parsed) == 1189, "maps all 1,189 chapters without collisions")
    check(("Genesis", 1) in parsed, "maps Genesis 1 by book and chapter")
    check(("Matthew", 1) in parsed, "keeps Matthew 1 separate from Genesis 1")
    check(("Revelation", 22) in parsed, "maps the final canonical chapter")
    check(sorted(parsed[("John", 5)]) == [1, 2, 3, 4],
          "expands printed verse ranges without losing a verse number")
    check(parsed[("John", 5)][3] == "",
          "flags the second half of a merged range for interpolation")


def test_language_options():
    print("\nAuto-Mark language dropdown:")
    languages = whisper_language_options()
    check(languages.get("as") == "Assamese", "includes Assamese")
    check(all(code in languages for code in (
        "en", "bn", "hi", "ta", "te", "ml", "kn", "mr", "gu", "pa", "ur")),
        "includes major Bible-production languages")
    check(len(languages) >= 90, "provides the full Whisper language set")

    indian = indian_language_options()
    check(len(indian) == 22, "includes all 22 scheduled Indian languages")
    check(indian_language("as").native_name == "অসমীয়া",
          "stores Assamese native-language metadata")
    check(indian_language("brx").name == "Bodo",
          "uses ISO brx for Bodo")
    check("bo" not in INDIAN_LANGUAGES,
          "does not confuse Bodo with Whisper Tibetan code bo")
    check(all(code in languages for code in indian_whisper_codes()),
          "only exposes valid Whisper tokens as forced Indian languages")


def test_assamese_script_alignment():
    print("\nAssamese script-to-audio alignment:")
    verses = {
        1: "আদিতে ঈশ্বৰে আকাশ আৰু পৃথিৱী সৃষ্টি কৰিলে",
        2: "পৃথিৱী আকাৰহীন আৰু শূন্য আছিল",
        3: "ঈশ্বৰে কলে পোহৰ হওক",
    }
    words = [
        {"word": "আদিতে", "start": 2.0, "end": 2.3},
        {"word": "ঈশ্বৰে", "start": 2.3, "end": 2.6},
        {"word": "আকাশ", "start": 2.6, "end": 2.9},
        {"word": "আৰু", "start": 2.9, "end": 3.0},
        {"word": "পৃথিৱী", "start": 3.0, "end": 3.3},
        {"word": "সৃষ্টি", "start": 3.3, "end": 3.6},
        {"word": "কৰিলে", "start": 3.6, "end": 3.9},
        {"word": "পৃথিৱী", "start": 5.0, "end": 5.3},
        {"word": "আকাৰহীন", "start": 5.3, "end": 5.7},
        {"word": "আৰু", "start": 5.7, "end": 5.8},
        {"word": "শূন্য", "start": 5.8, "end": 6.1},
        {"word": "আছিল", "start": 6.1, "end": 6.4},
        {"word": "ঈশ্বৰে", "start": 8.0, "end": 8.3},
        {"word": "কলে", "start": 8.3, "end": 8.5},
        {"word": "পোহৰ", "start": 8.5, "end": 8.8},
        {"word": "হওক", "start": 8.8, "end": 9.0},
    ]
    markers = _find_verse_boundaries_by_transcription(words, verses, 48000)
    check([m.label for m in markers] == ["Verse 1", "Verse 2", "Verse 3"],
          "always returns the complete ordered verse set")
    check([round(m.time_s, 1) for m in markers] == [2.0, 5.0, 8.0],
          "places verse starts at aligned Assamese words")
    check(min(m.confidence for m in markers) >= 0.8,
          "reports high confidence for exact script matches")


def test_sparse_transcript_anchors_are_rejected():
    print("\nLow-overlap transcript rejection:")
    verses = {
        number: "unique%d alpha%d beta%d gamma%d delta%d" %
        (number, number, number, number, number)
        for number in range(1, 21)}
    # Five exact words exceed the former absolute-anchor threshold but cover
    # only 5% of the script, which is unsafe for full-chapter alignment.
    words = [
        {"word": "unique%d" % number,
         "start": float(number * 10), "end": float(number * 10 + 1)}
        for number in (1, 5, 10, 15, 20)]
    markers = _find_verse_boundaries_by_transcription(
        words, verses, 48000)
    check(
        markers == [],
        "rejects sparse name matches instead of clustering missing verses")


def test_pause_fallback_completeness():
    print("\nPause fallback:")
    markers = _find_verse_boundaries_by_pauses(
        [(0.0, 2.0), (4.5, 5.0), (7.5, 8.0)],
        expected_verses=3,
        sample_rate=48000,
        duration_s=12.0,
    )
    check([m.label for m in markers] == ["Verse 1", "Verse 2", "Verse 3"],
          "pause draft includes Verse 1 and every expected verse")
    check(all(markers[i].time_s < markers[i + 1].time_s
              for i in range(len(markers) - 1)),
          "pause draft remains chronological")


def test_independent_silence_edges():
    print("\nIndependent silence repair:")
    sample_rate = 1000
    audio = np.concatenate([
        np.zeros((1, 1000), dtype=np.float32),
        np.ones((1, 2000), dtype=np.float32) * 0.2,
        np.zeros((1, 1000), dtype=np.float32),
    ], axis=1)

    front_fixed, delta = _fix_silence_sides(
        audio, sample_rate, 2.0, -60.0,
        fix_head=True, fix_tail=False)
    front, back = _measure_silence(front_fixed, sample_rate, -60.0)
    check(abs(front - 2.0) < 0.001, "front-only mode applies two seconds at front")
    check(abs(back - 1.0) < 0.001, "front-only mode preserves back silence")
    check(delta == 1000, "front padding returns exact +1 second marker transform")

    back_fixed, delta = _fix_silence_sides(
        audio, sample_rate, 2.0, -60.0,
        fix_head=False, fix_tail=True)
    front, back = _measure_silence(back_fixed, sample_rate, -60.0)
    check(abs(front - 1.0) < 0.001, "back-only mode preserves front silence")
    check(abs(back - 2.0) < 0.001, "back-only mode applies two seconds at back")
    check(delta == 0, "back-only edit does not move markers")


def test_live_automark_callbacks():
    print("\nLive Auto-Mark feedback:")
    with tempfile.TemporaryDirectory() as root:
        source = os.path.join(root, "Gen_001.wav")
        sample_rate = 8000
        # Two speech regions separated by pauses. The pause backend avoids
        # loading Whisper, so this remains a fast deterministic regression.
        audio = np.concatenate([
            np.zeros(sample_rate, dtype=np.int16),
            np.full(sample_rate, 4000, dtype=np.int16),
            np.zeros(sample_rate // 2, dtype=np.int16),
            np.full(sample_rate, 4000, dtype=np.int16),
            np.zeros(sample_rate, dtype=np.int16),
        ])
        with wave.open(source, "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(sample_rate)
            stream.writeframes(audio.tobytes())

        stages = []
        previews = []
        result = auto_mark_file(
            source, {1: "one", 2: "two"},
            alignment_backend="pause",
            progress_callback=lambda stage, fraction:
                stages.append((stage, fraction)),
            marker_preview_callback=lambda markers:
                previews.append(list(markers)))
        check(result.ok, "creates a complete pause-backed marker draft")
        check(result.needs_review, "keeps every pause-only result as a draft")
        check(
            bool(previews) and
            [marker.label for marker in previews[0]] ==
            ["Chapter Title", "Verse 1", "Verse 2"],
            "publishes accurate marker positions before file writing")
        check(
            any(stage == "writing marked WAV" for stage, _ in stages) and
            stages[-1] == ("done", 1.0),
            "publishes stage progress through completion")


def main():
    test_assamese_script_chapters()
    test_irvasm_heading_typography()
    test_irvasm_number_first_and_full_bible_mapping()
    test_language_options()
    test_assamese_script_alignment()
    test_sparse_transcript_anchors_are_rejected()
    test_pause_fallback_completeness()
    test_independent_silence_edges()
    test_live_automark_callbacks()

    print("\n" + "=" * 56)
    if FAILURES:
        print("RESULT: %d failure(s)" % len(FAILURES))
        for failure in FAILURES:
            print("  - " + failure)
        return 1
    print("RESULT: ALL REWORKED FEATURE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
