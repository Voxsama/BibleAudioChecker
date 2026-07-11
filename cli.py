"""
cli.py — batch-check WAV files from the command line.

Usage:
    python3 -m cli FILE_OR_FOLDER [FILE_OR_FOLDER ...] [--no-loudness] [--json out.json]
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
    ap.add_argument("--no-loudness", action="store_true",
                    help="skip ffmpeg loudness/true-peak checks")
    ap.add_argument("--json", help="write full JSON report to this path")
    ap.add_argument("--config", default=default_config_path(),
                    help="path to config.json")
    args = ap.parse_args(argv)

    cfg = Config.load(args.config)
    wavs = gather_wavs(args.paths)
    if not wavs:
        print("No .wav files found.")
        return 1

    reports = []
    n_pass = 0
    for w in wavs:
        r = check_file(w, cfg, do_loudness=not args.no_loudness)
        reports.append(r)
        print_report(r)
        if r.passed:
            n_pass += 1

    print("\n%d/%d files passed all checks." % (n_pass, len(wavs)))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump([report_to_dict(r) for r in reports], f, indent=2)
        print("Wrote JSON report to %s" % args.json)

    return 0 if n_pass == len(wavs) else 2


if __name__ == "__main__":
    sys.exit(main())
