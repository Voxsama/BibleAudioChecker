"""End-to-end mastering and finished-deliverable validation."""

from __future__ import annotations

import os
import tempfile

from engine.mastering import (
    MasteringSettings,
    dependencies_available,
    master_file,
)
from tests.make_test_wav import build_wav


def main():
    if not dependencies_available():
        print("SKIP: optional mastering packages are not installed")
        return 0

    failures = []
    with tempfile.TemporaryDirectory() as root:
        source = os.path.join(root, "Gen_001.wav")
        output = os.path.join(root, "Gen_001_mastered.wav")
        build_wav(
            source, sr=44100, bits=16, n_verses=3,
            head_silence_s=1.0, tail_silence_s=3.0,
            amp=0.18, body_seconds_each=1.2)
        result = master_file(
            source,
            MasteringSettings(
                target_lufs=-18.0,
                lufs_tolerance=0.5,
                true_peak_max=-1.0,
                target_silence_s=2.0,
                target_sample_rate=48000,
                target_bits=24),
            output)

        checks = [
            (result.success and result.validation_passed,
             "finished WAV passes strict validation"),
            (abs(result.output_lufs + 18.0) <= 0.5,
             "independent loudness is within target tolerance"),
            (result.output_peak <= -1.0,
             "independent true peak stays below the ceiling"),
            (abs(result.output_head_silence - 2.0) <= 0.05 and
             abs(result.output_tail_silence - 2.0) <= 0.05,
             "front and back silence are two seconds"),
            (result.output_sample_rate == 48000 and
             result.output_bits == 24,
             "output format is 48 kHz / 24-bit"),
            (result.input_marker_count == result.output_marker_count == 5,
             "all embedded markers are preserved"),
            (os.path.isfile(result.report_path),
             "writes the mastering validation JSON report"),
        ]
        for passed, message in checks:
            print("  [%s] %s" % ("ok  " if passed else "FAIL", message))
            if not passed:
                failures.append(message)

    if failures:
        print("RESULT: %d MASTERING FAILURE(S)" % len(failures))
        return 1
    print("RESULT: MASTERING DELIVERY VALIDATED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
