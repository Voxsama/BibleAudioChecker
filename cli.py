"""
cli.py — batch-check WAV files from the command line.

Usage:
    python3 -m cli FILE_OR_FOLDER [FILE_OR_FOLDER ...] [--no-loudness] [--json out.json]

    # Toggle individual checks off:
    python3 -m cli folder/ --no-format --no-silence
    python3 -m cli folder/ --no-loudness --no-true-peak

    # Only check markers and verses (skip all mastering checks):
    python3 -m cli folder/ --no-format --no-loudness --no-true-peak --no-silence

    # Script verification:
    python3 -m cli folder/ --script script.pdf --language hi
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

from engine.config import Config, default_config_path
from engine.checker import check_file, FileReport


def gather_wavs(paths):
    wavs = []
    for p in paths:
        if os.path.isdir(p):
            wavs += sorted(glob.glob(os.path.join(p, "**", "*.wav"), recursive=True))
        elif p.lower().endswith(".wav"):
            wavs.append(p)
    # de-dup, keep order
    seen, out = set(), []
    for w in wavs:
        if w not in seen:
            seen.add(w); out.append(w)
    return out


def report_to_dict(r: FileReport):
    return {
        "file": r.filename,
        "path": r.path,
        "book": r.book,
        "chapter": r.chapter,
        "expected_verses": r.expected_verses,
        "passed": r.passed,
        "error": r.error,
        "checks": [
            {"name": i.name, "status": i.status, "value": i.value, "detail": i.detail}
            for i in r.items
        ],
    }


def print_report(r: FileReport):
    head = "PASS" if r.passed else "FAIL"
    ident = ""
    if r.book:
        ident = "  [%s %s, expect %s verses]" % (r.book, r.chapter, r.expected_verses)
    print("\n%s  %s%s" % (_c(head), r.filename, ident))
    if r.error:
        print("   ! %s" % r.error)
        return
    for i in r.items:
        mark = "OK " if i.passed else "XX "
        val = (" (%s)" % i.value) if i.value else ""
        print("   %s %-14s%s" % (mark, i.name, val))
        if not i.passed:
            print("        -> %s" % i.detail)


def _c(s):
    return s


def main(argv=None):
    ap = argparse.ArgumentParser(description="Bible Audio Checker (CLI)")
    ap.add_argument("paths", nargs="+", help="WAV files or folders")

    # Legacy flag (kept for backward compatibility)
    ap.add_argument("--no-loudness", action="store_true",
                    help="skip ffmpeg loudness/true-peak checks (legacy flag)")

    # Individual check toggles
    ap.add_argument("--no-format", action="store_true",
                    help="disable format (sample rate / bit depth) check")
    ap.add_argument("--no-lufs", action="store_true",
                    help="disable integrated loudness (LUFS) check")
    ap.add_argument("--no-true-peak", action="store_true",
                    help="disable true peak (dBTP) check")
    ap.add_argument("--no-silence", action="store_true",
                    help="disable head and tail silence checks")
    ap.add_argument("--no-head-silence", action="store_true",
                    help="disable head silence check only")
    ap.add_argument("--no-tail-silence", action="store_true",
                    help="disable tail silence check only")
    ap.add_argument("--no-markers", action="store_true",
                    help="disable marker checks (chapter title, heading, spelling)")
    ap.add_argument("--no-verses", action="store_true",
                    help="disable verse completeness check")

    # Script verification
    ap.add_argument("--script", metavar="PDF_OR_TXT",
                    help="path to a script PDF or text file for verse verification")
    ap.add_argument("--language", metavar="CODE", default="",
                    help="language code for Whisper (e.g. hi, ta, te, kn, ml, bn). Empty=auto-detect")
    ap.add_argument("--whisper-mode", default="local", choices=["local", "api"],
                    help="Whisper mode: 'local' (openai-whisper) or 'api' (OpenAI API)")
    ap.add_argument("--whisper-model", default="medium",
                    help="local Whisper model size (tiny, base, small, medium, large)")

    # Output
    ap.add_argument("--json", help="write full JSON report to this path")
    ap.add_argument("--config", default=default_config_path(),
                    help="path to config.json")

    args = ap.parse_args(argv)

    cfg = Config.load(args.config)

    # Apply CLI toggle overrides to config
    if args.no_format:
        cfg.enable_format = False
    if args.no_loudness or args.no_lufs:
        cfg.enable_loudness = False
    if args.no_loudness or args.no_true_peak:
        cfg.enable_true_peak = False
    if args.no_silence:
        cfg.enable_head_silence = False
        cfg.enable_tail_silence = False
    if args.no_head_silence:
        cfg.enable_head_silence = False
    if args.no_tail_silence:
        cfg.enable_tail_silence = False
    if args.no_markers:
        cfg.enable_markers = False
    if args.no_verses:
        cfg.enable_verses = False

    # Script verification setup
    script_verses = None
    if args.script:
        cfg.enable_script_verification = True
        cfg.whisper_mode = args.whisper_mode
        cfg.whisper_model = args.whisper_model
        if args.language:
            cfg.whisper_language = args.language

        # Parse the script
        try:
            from engine.pdf_parser import parse_pdf, parse_plain_text
            if args.script.lower().endswith(".pdf"):
                result = parse_pdf(args.script)
            else:
                with open(args.script, "r", encoding="utf-8") as f:
                    text = f.read()
                result = parse_plain_text(text)

            if result.ok:
                script_verses = result.verses
                print("Script loaded: %s (%d verses)" % (
                    os.path.basename(args.script), result.total_verses))
                if result.warnings:
                    for w in result.warnings:
                        print("  Warning: %s" % w)
            else:
                print("ERROR: Could not parse script: %s" % "; ".join(result.warnings))
                return 1
        except Exception as e:
            print("ERROR: Failed to load script: %s" % e)
            return 1

    wavs = gather_wavs(args.paths)
    if not wavs:
        print("No .wav files found.")
        return 1

    # Determine if we should attempt loudness checks
    do_loudness = cfg.enable_loudness or cfg.enable_true_peak

    reports = []
    n_pass = 0
    for w in wavs:
        r = check_file(w, cfg, do_loudness=do_loudness,
                       script_verses=script_verses)
        reports.append(r)
        print_report(r)
        if r.passed:
            n_pass += 1

    print("\n%d/%d files passed all checks." % (n_pass, len(wavs)))

    # Check for missing chapters across all files
    from engine.checker import check_missing_chapters
    chapter_reports = check_missing_chapters(reports)
    missing_books = [cr for cr in chapter_reports if not cr.complete]
    if missing_books:
        print("\n" + "=" * 50)
        print("MISSING CHAPTERS:")
        for cr in missing_books:
            print("  %s: missing chapter(s) %s (have %d/%d)" % (
                cr.book, cr.missing_str, len(cr.chapters_found), cr.total_chapters))
            if cr.duplicate_chapters:
                print("    (duplicate files for chapter(s): %s)" %
                      ", ".join(map(str, cr.duplicate_chapters)))
        print("=" * 50)

    if args.json:
        # Include missing chapters info in JSON output
        json_data = {
            "files": [report_to_dict(r) for r in reports],
            "missing_chapters": [
                {"book": cr.book, "total_chapters": cr.total_chapters,
                 "chapters_found": cr.chapters_found,
                 "chapters_missing": cr.chapters_missing,
                 "duplicate_chapters": cr.duplicate_chapters,
                 "complete": cr.complete}
                for cr in chapter_reports
            ] if chapter_reports else []
        }
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2)
        print("Wrote JSON report to %s" % args.json)

    return 0 if (n_pass == len(wavs) and not missing_books) else 2


if __name__ == "__main__":
    sys.exit(main())
