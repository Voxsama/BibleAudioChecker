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


def _build_speech_like(path, sr, input_lufs, seconds=40.0, seed=1,
                       plosives=False):
    """Write narration-like audio: band-limited noise bursts at uneven levels.

    Bursts span 12 dB, one 'quiet verse' sits 10 dB lower still, with short
    gaps and 1 s of digital silence at each end. Scaled to input_lufs.
    plosives=True adds short spikes ~20 dB hot so the limiter must work.
    """
    import numpy as np
    import pyloudnorm as pyln
    from scipy.signal import butter, sosfilt
    from engine.mastering import _write_wav_float

    rng = np.random.default_rng(seed)
    noise = sosfilt(butter(4, [150, 4000], "band", fs=sr, output="sos"),
                    rng.standard_normal(int(seconds * sr)))
    env = np.zeros_like(noise)
    pos, n = int(sr), 0
    end = len(noise) - int(sr)
    while pos < end:
        length = int(rng.uniform(0.3, 0.8) * sr)
        level_db = rng.uniform(-12.0, 0.0) - (10.0 if n == 10 else 0.0)
        env[pos:min(pos + length, end)] = 10 ** (level_db / 20)
        pos += length + int(rng.uniform(0.1, 0.4) * sr)
        n += 1
    audio = noise * env
    if plosives:
        for start in range(int(1.5 * sr), end - sr, int(1.7 * sr)):
            audio[start:start + int(0.004 * sr)] *= 10.0
    lufs = pyln.Meter(sr).integrated_loudness(audio)
    audio *= 10 ** ((input_lufs - lufs) / 20)
    _write_wav_float(path, audio[np.newaxis, :].astype(np.float32), sr, 24)


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
        for input_lufs, plosives in ((-25.0, False), (-40.0, False),
                                     (-8.0, False), (-25.0, True)):
            name = "%d%s" % (-input_lufs, "p" if plosives else "")
            speech = os.path.join(root, "Exo_%s.wav" % name)
            _build_speech_like(speech, 44100, input_lufs, plosives=plosives)
            res = master_file(speech, MasteringSettings(
                target_sample_rate=48000, target_bits=24),
                os.path.join(root, "out_%s.wav" % name))
            label = "speech-like input at %.0f LUFS%s" % (
                input_lufs, " with plosives" if plosives else "")
            checks += [
                (res.success and res.validation_passed,
                 "%s passes strict validation (%s)" % (label, res.error or "ok")),
                (abs(res.output_lufs + 18.0) <= 0.5,
                 "%s lands at -18 +/- 0.5 LUFS (got %.2f)" % (label, res.output_lufs)),
                (res.output_peak <= -1.0,
                 "%s stays at or below -1.0 dBTP (got %.2f)" % (label, res.output_peak)),
                (not any("did not converge" in w for w in res.warnings),
                 "%s loudness converges" % label),
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
