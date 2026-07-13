"""
test_engine.py — automated verification of the checking engine, run at the real
48 kHz / 24-bit spec. Builds synthetic WAVs (correct + deliberately broken) and
asserts the checker flags exactly the right things.

Run:  python3 -m tests.test_engine
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.config import Config
from engine.checker import check_file
from engine import bible_db
from engine.loudness import ffmpeg_available
from engine.wavio import read_wav_info, read_pcm
from tests.make_test_wav import build_wav, _write_wav_with_cues

TMP = tempfile.mkdtemp(prefix="bac_test_")
FAILS = []
SR = 48000
BITS = 24


def check(cond, msg):
    print("  [%s] %s" % ("ok  " if cond else "FAIL", msg))
    if not cond:
        FAILS.append(msg)


def item(report, name):
    for i in report.items:
        if i.name == name:
            return i
    return None


def normalize(src, dst, markers, I=-18, TP=-1.0):
    """loudnorm to target as 24-bit, then re-embed markers (loudnorm strips cues)."""
    tmp = dst + ".norm.wav"
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-i", src, "-af", "loudnorm=I=%s:TP=%s:LRA=11" % (I, TP),
                    "-ar", str(SR), "-ac", "1", "-c:a", "pcm_s24le", tmp], check=True)
    info = read_wav_info(tmp)
    frames = read_pcm(tmp, info, 0, info.n_frames)
    _write_wav_with_cues(dst, frames, info.sample_rate, markers,
                         bits=info.bits, n_channels=info.channels)
    os.remove(tmp)


def build_named(name, labels, have_ff, cfg, I=-18, head=2.0, tail=2.0):
    raw = os.path.join(TMP, "raw_" + name)
    if labels:
        m = build_wav(raw, sr=SR, bits=BITS, labels=labels,
                      body_seconds_each=0.2, head_silence_s=head, tail_silence_s=tail)
    else:  # a file with NO markers
        build_wav(raw, sr=SR, bits=BITS, labels=["x"], body_seconds_each=0.2,
                  head_silence_s=head, tail_silence_s=tail)
        m = []
        info = read_wav_info(raw)
        _write_wav_with_cues(os.path.join(TMP, name),
                             read_pcm(raw, info, 0, info.n_frames), SR, [],
                             bits=BITS, n_channels=1)
        return check_file(os.path.join(TMP, name), cfg)
    dst = os.path.join(TMP, name)
    if have_ff:
        normalize(raw, dst, m, I=I)
    else:
        os.rename(raw, dst)
    return check_file(dst, cfg)


def main():
    cfg = Config()
    have_ff = ffmpeg_available()
    print("ffmpeg:", have_ff, "| spec: %d Hz / %d-bit" % (SR, BITS))

    print("\nDatabase:")
    check(len(bible_db.KJV) == 66, "66 books")
    check(bible_db.total_chapters() == 1189, "1189 chapters")
    check(bible_db.total_verses() == 31103, "31103 verses (ESV)")
    check(bible_db.parse_filename("Gen_001").expected_verses == 31, "Gen 1 -> 31")
    check(bible_db.parse_filename("Ps_119").expected_verses == 176, "Ps 119 -> 176")

    print("\nGood file (Gen_001, 31 verses, 48k/24bit):")
    labels = ["Chapter Title", "Heading"] + ["Verse %d" % i for i in range(1, 32)]
    r = build_named("Gen_001.wav", labels, have_ff, cfg)
    fmt = read_wav_info(os.path.join(TMP, "Gen_001.wav"))
    check(fmt.sample_rate == SR and fmt.bits == BITS, "file really is %dHz/%dbit" % (SR, BITS))
    check(r.book == "Genesis" and r.chapter == 1, "identified as Genesis 1")
    check(item(r, "Verses").passed, "verses complete (31/31)")
    check(item(r, "Head Silence").passed, "head silence OK")
    check(item(r, "Tail Silence").passed, "tail silence OK")
    if have_ff:
        check(item(r, "Loudness").passed, "loudness within target")
        check(item(r, "True Peak").passed, "true peak under ceiling")
        check(r.passed, "OVERALL PASS")

    print("\nMissing verses (Gen_001 missing 5,17-19):")
    labels_m = ["Chapter Title", "Heading"] + \
        ["Verse %d" % i for i in range(1, 32) if i not in (5, 17, 18, 19)]
    r = build_named("Gen_001.wav", labels_m, have_ff, cfg)
    vi = item(r, "Verses")
    check(not vi.passed, "verses flagged incomplete")
    check("5" in vi.detail and "17-19" in vi.detail, "reports missing 5, 17-19 (%s)" % vi.detail)

    print("\nMisspelled marker + wrong loudness + short tail (Jon_001):")
    labels = ["Chapter Title", "Heading"] + ["Verse %d" % i for i in range(1, 17)] + ["Vers 17"]
    r = build_named("Jon_001.wav", labels, have_ff, cfg, I=-14, tail=0.4)
    check(r.book == "Jonah", "identified as Jonah")
    sp = item(r, "Marker Spelling")
    check(sp is not None and not sp.passed, "misspelled 'Vers 17' flagged")
    check(not item(r, "Verses").passed, "verse 17 counted missing")
    check(not item(r, "Tail Silence").passed, "short tail silence flagged")
    if have_ff:
        check(not item(r, "Loudness").passed, "wrong loudness (-14) flagged")

    print("\nNo markers:")
    r = build_named("Oba_001.wav", [], have_ff, cfg)
    mk = item(r, "Markers")
    check(mk is not None and not mk.passed, "no-markers flagged")

    print("\n" + "=" * 50)
    if FAILS:
        print("RESULT: %d assertion(s) FAILED" % len(FAILS))
        for f in FAILS:
            print("   - " + f)
        return 1
    print("RESULT: ALL ASSERTIONS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
