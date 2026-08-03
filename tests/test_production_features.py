"""Tests for project, calibration, cache, editor, review, and export layers."""

from __future__ import annotations

import os
import hashlib
import tempfile
from pathlib import Path

from engine.calibration import compare_marker_points
from engine.exports import export_marker_bundle
from engine.marker_editor import MarkerEditSession
from engine.pdf_parser import ParsedScriptCollection, ScriptHeading
from engine.project import AudioBibleProject, ProjectPreset
from engine.review import merge_review_items, review_from_language
from engine.script_cache import load_or_parse_pdf
from engine.transcriber import (
    LanguageCandidate, LanguageDetectionResult)
from engine.wav_markers import read_markers
from tests.make_test_wav import build_wav


FAILURES = []


def check(condition, message):
    print("  [%s] %s" % ("ok  " if condition else "FAIL", message))
    if not condition:
        FAILURES.append(message)


def test_project_round_trip(root):
    print("\nProject persistence:")
    path = os.path.join(root, "Assamese.bacproject")
    project = AudioBibleProject(
        name="Assamese IRV",
        project_path=path,
        root_dir=root,
        preset=ProjectPreset(language="as", reader_id="reader-a"))
    project.add_files([
        os.path.join(root, "Gen_001.wav"),
        os.path.join(root, "Mat_001.wav")])
    project.update_file(
        os.path.join(root, "Gen_001.wav"),
        status="review", review_reasons=["low confidence"])
    project.save()
    loaded = AudioBibleProject.load(path)
    check(loaded.name == "Assamese IRV", "restores project identity")
    check(len(loaded.files) == 2, "restores the chapter file list")
    check(loaded.files[0].book == "Genesis", "stores canonical book mapping")
    check(len(loaded.review_files()) == 1, "restores review status")


def test_script_cache(root):
    print("\nScript cache:")
    source = os.path.join(root, "script.pdf")
    with open(source, "wb") as stream:
        stream.write(b"synthetic-pdf")
    calls = []

    def parser(_path):
        calls.append(1)
        return ParsedScriptCollection(
            book_chapters={("Genesis", 1): {1: "text"}},
            book_headings={
                ("Genesis", 1): [
                    ScriptHeading("প্ৰথম দিন", 1)]})

    cache_dir = os.path.join(root, "cache")
    first = load_or_parse_pdf(source, cache_dir=cache_dir, parser=parser)
    second = load_or_parse_pdf(source, cache_dir=cache_dir, parser=parser)
    check(not first.from_cache and second.from_cache,
          "parses once and reuses the persistent cache")
    check(len(calls) == 1, "does not call the parser for a cache hit")
    check(second.collection.book_chapters[
        ("Genesis", 1)][1] == "text", "restores Unicode chapter mappings")
    heading = second.collection.book_headings[("Genesis", 1)][0]
    check(
        heading.text == "প্ৰথম দিন" and heading.before_verse == 1,
        "restores PDF section headings and their following verse")


def test_heading_alignment():
    print("\nPDF heading alignment:")
    from engine.auto_marker import (
        MarkerPlacement, _find_heading_markers)
    timeline = [
        {"word": "প্ৰথম", "start": 1.0, "end": 1.2},
        {"word": "দিন", "start": 1.3, "end": 1.5},
        {"word": "আদিতে", "start": 2.0, "end": 2.3},
    ]
    verses = [MarkerPlacement(
        "Verse 1", 2000, 2.0, 0.9, "script-align")]
    markers = _find_heading_markers(
        [ScriptHeading("প্ৰথম দিন", 1)], timeline, verses, 1000)
    check(len(markers) == 1, "creates a marker for a PDF heading")
    check(
        abs(markers[0].time_s - 1.0) < 0.001,
        "places the heading on its Assamese transcript anchor")
    check(
        markers[0].confidence >= 0.9,
        "reports high confidence for an exact heading match")


def test_cross_script_assamese_alignment():
    print("\nCross-script Assamese alignment:")
    from engine.phonetic import alignment_tokens
    assamese = alignment_tokens("আদম চেথ ইনোচ")
    devanagari = alignment_tokens("आदम छेत इनूस")
    check(
        assamese == devanagari,
        "matches Assamese PDF names to Whisper Devanagari decoding")


def test_script_aware_assamese_language_resolution():
    print("\nScript-aware Assamese language detection:")
    from engine.language_resolution import resolve_language_with_script

    raw = LanguageDetectionResult(
        language="bn", language_name="Bengali", confidence=0.81,
        candidates=[
            LanguageCandidate("bn", "Bengali", 0.81),
            LanguageCandidate("ne", "Nepali", 0.05),
            LanguageCandidate("si", "Sinhala", 0.02),
        ])
    assamese_script = (
        "আদিতে ঈশ্বৰে আকাশ-মণ্ডল আৰু পৃথিৱী সৃষ্টি কৰিলে। "
        "তেওঁ পৃথিৱীৰ সকলো বস্তু দেখিলে আৰু তেওঁৰ বাক্য কলে।")
    resolved = resolve_language_with_script(raw, assamese_script)
    check(
        resolved.language == "as" and
        resolved.language_name == "Assamese",
        "resolves Bengali acoustic confusion using Assamese PDF letters")
    check(
        resolved.raw_language == "bn" and
        abs(resolved.raw_confidence - 0.81) < 0.0001,
        "retains the raw Whisper result for transparent reporting")
    check(
        resolved.resolution_source == "script-confirmed",
        "labels the result as script-confirmed")

    unrelated = LanguageDetectionResult(
        language="en", language_name="English", confidence=0.90)
    conflict = resolve_language_with_script(
        unrelated, assamese_script)
    check(
        conflict.language == "en" and
        conflict.resolution_source == "script-conflict",
        "warns instead of overriding an unrelated audio language")


def test_model_pack_download(root):
    print("\nIn-app AI model packs:")
    from engine.model_packs import (
        ModelPack, _download_pack, available_model_packs, format_bytes,
        verify_file)
    source_dir = os.path.join(root, "model-source")
    cache_dir = os.path.join(root, "model-cache")
    os.makedirs(source_dir)
    source = os.path.join(source_dir, "test-model.pt")
    payload = (b"multilingual-model-pack" * 65536)
    with open(source, "wb") as stream:
        stream.write(payload)
    checksum = hashlib.sha256(payload).hexdigest()
    pack = ModelPack(
        key="test", display_name="Test model",
        description="Local download test",
        approx_bytes=len(payload),
        url=Path(source).as_uri(),
        sha256=checksum,
        filename="test-model.pt")
    progress = []
    result = _download_pack(
        pack, cache_dir,
        progress_callback=lambda stage, done, total, elapsed:
        progress.append((stage, done, total)))
    check(result.verified, "checksum-verifies an in-app model download")
    check(
        verify_file(result.path, checksum),
        "atomically installs the verified model pack")
    check(
        any(stage == "downloading" for stage, _done, _total in progress) and
        any(stage == "verifying" for stage, _done, _total in progress),
        "reports download and verification progress")
    keys = {item.key for item in available_model_packs()}
    check(
        {"medium", "large-v3", "turbo",
         "mms-1b-all-asm"}.issubset(keys),
        "lists Whisper packs and Meta MMS Assamese Precision")
    check(
        format_bytes(75 * 1024**2) == "75.00 MB" and
        format_bytes(1530 * 1024**2) == "1.49 GB" and
        format_bytes(3100 * 1024**2) == "3.03 GB",
        "displays model downloads in the correct MB/GB units")


def test_mms_monotonic_alignment():
    print("\nMeta MMS Assamese CTC alignment:")
    from engine.auto_marker import _find_verse_boundaries_by_mms

    timeline = [
        {"word": "chapter", "start": 0.5, "end": 0.9},
        {"word": "adam", "start": 2.0, "end": 2.4},
        {"word": "seth", "start": 3.0, "end": 3.4},
        {"word": "enosh", "start": 5.0, "end": 5.4},
        {"word": "cainan", "start": 8.0, "end": 8.4},
    ]
    verses = {
        1: "adam seth",
        2: "enosh",
        3: "cainan",
    }
    markers, coverage = _find_verse_boundaries_by_mms(
        timeline, verses, 1000, 10.0)
    check(
        coverage > 0.95,
        "rejects the extra heading while matching the complete script")
    check(
        [round(marker.time_s, 1) for marker in markers] ==
        [2.0, 5.0, 8.0],
        "places every verse on a direct monotonic CTC anchor")
    check(
        all(marker.method == "mms-ctc-align" for marker in markers),
        "identifies direct MMS anchors separately from interpolation")


def test_transcription_cache(root):
    print("\nWhisper transcript cache:")
    from engine.transcription_cache import (
        load_cached_timeline, save_cached_timeline)

    audio = os.path.join(root, "cache-source.wav")
    cache_dir = os.path.join(root, "transcript-cache")
    with open(audio, "wb") as stream:
        stream.write(b"audio-version-one")
    words = [
        {"start": 1.0, "end": 1.5, "word": "আদম"},
        {"start": 1.5, "end": 2.0, "word": "ছেত"},
    ]
    save_cached_timeline(
        audio, "bn", "large-v3", words, cache_dir=cache_dir)
    check(
        load_cached_timeline(
            audio, "bn", "large-v3",
            cache_dir=cache_dir) == words,
        "reuses a cached word timeline without rerunning Whisper")
    with open(audio, "ab") as stream:
        stream.write(b"-changed")
    check(
        load_cached_timeline(
            audio, "bn", "large-v3",
            cache_dir=cache_dir) is None,
        "invalidates the cache when the audio changes")


def test_marker_editor_and_learning(root):
    print("\nMarker editing:")
    source = os.path.join(root, "Gen_001.wav")
    output = os.path.join(root, "Gen_001_edited.wav")
    build_wav(source, sr=8000, bits=16, n_verses=3)
    session = MarkerEditSession(source)
    verse_index = next(
        index for index, marker in enumerate(session.markers)
        if marker.label == "Verse 1")
    original = session.time_s(verse_index)
    moved_index = session.move(verse_index, original + 0.25)
    check(abs(session.time_s(moved_index) - original - 0.25) < 0.001,
          "moves a marker to an exact time")
    check(session.undo(), "supports undo")
    check(session.redo(), "supports redo")
    session.save(output)
    saved = read_markers(output)
    verse = next(marker for marker in saved if marker.label == "Verse 1")
    check(abs(verse.seconds - original - 0.25) < 0.001,
          "writes a non-destructive edited WAV")


def test_calibration():
    print("\nCalibration metrics:")
    automatic = [
        ("Verse 1", 2.10), ("Verse 2", 5.40), ("Verse 3", 8.20)]
    reference = [
        ("Verse 1", 2.00), ("Verse 2", 5.00), ("Verse 3", 8.00)]
    result = compare_marker_points(automatic, reference, threshold_s=0.25)
    check(len(result.matched) == 3, "matches markers by normalized label")
    check(abs(result.median_error_s - 0.2) < 0.0001,
          "calculates median absolute timing error")
    check(result.worst_error_s >= 0.39, "calculates worst-case error")
    check(0.0 < result.pass_rate < 1.0, "calculates threshold pass rate")


def test_exports_and_review(root):
    print("\nExports and review queue:")
    output_dir = os.path.join(root, "exports")
    outputs = export_marker_bundle(
        output_dir, os.path.join(root, "Gen_001.wav"),
        [("Chapter Title", 1.0), ("Verse 1", 2.0)],
        {"project": "Assamese IRV"})
    check(len(outputs) == 4 and all(os.path.isfile(path) for path in outputs),
          "writes JSON, REAPER CSV, CUE, and iXML sidecar files")
    detection = LanguageDetectionResult(
        language="as", language_name="Assamese", confidence=0.45)
    review = merge_review_items(
        review_from_language("Gen_001.wav", detection))
    check(len(review) == 1 and review[0].category == "Language",
          "adds uncertain language detection to the review queue")


def main():
    with tempfile.TemporaryDirectory() as root:
        test_project_round_trip(root)
        test_script_cache(root)
        test_marker_editor_and_learning(root)
        test_exports_and_review(root)
        test_model_pack_download(root)
        test_transcription_cache(root)
    test_calibration()
    test_heading_alignment()
    test_cross_script_assamese_alignment()
    test_script_aware_assamese_language_resolution()
    test_mms_monotonic_alignment()

    print("\n" + "=" * 58)
    if FAILURES:
        print("RESULT: %d failure(s)" % len(FAILURES))
        for failure in FAILURES:
            print("  - " + failure)
        return 1
    print("RESULT: ALL PRODUCTION FEATURE TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
