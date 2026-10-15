"""
mastering.py — auto-master Bible audio WAV files to broadcast standards.

Uses Pedalboard (Spotify) for audio processing and pyloudnorm for
ITU-R BS.1770 / EBU R128 loudness measurement. The chain follows the
narration workflow used in Logic Pro:

  1. Remove DC offset, downmix to mono, resample to the delivery rate
  2. Pre-normalise to -28 LUFS (headroom for the processors)
  3. Noise gate
  4. EQ: high-pass plus optional low and high shelves
  5. Compressor
  6. Optional ordered VST3 chain
  7. Make-up gain to the target loudness, true-peak limited, re-measured
     until it lands within tolerance
  8. Trim/pad head and tail silence, write at the delivery bit depth,
     re-embed markers, validate the written file independently

Output: GEN_Mastered/GEN_001.wav (original untouched)

Requires: pip install pedalboard pyloudnorm numpy
"""

from __future__ import annotations

import logging
import os
import json
import struct
import tempfile
from dataclasses import asdict, dataclass, field
from typing import List, Optional, Tuple

from .wavio import read_wav_info, read_pcm
from .wav_markers import read_markers
from .marker_writer import write_markers as write_markers_to_wav

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------
@dataclass
class MasteringResult:
    """Result of mastering one file."""
    success: bool = False
    output_path: str = ""
    error: str = ""
    warnings: List[str] = field(default_factory=list)

    # Measurements (before/after)
    input_lufs: float = 0.0
    output_lufs: float = 0.0
    input_peak: float = 0.0
    output_peak: float = 0.0
    gain_applied_db: float = 0.0
    validation_passed: bool = False
    validation_issues: List[str] = field(default_factory=list)
    lufs_error: float = 0.0
    peak_margin: float = 0.0
    output_head_silence: float = 0.0
    output_tail_silence: float = 0.0
    output_sample_rate: int = 0
    output_bits: int = 0
    input_marker_count: int = 0
    output_marker_count: int = 0
    report_path: str = ""

    # What was done
    steps_applied: List[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if not self.success:
            return "FAILED: %s" % self.error
        steps = ", ".join(self.steps_applied) if self.steps_applied else "no changes needed"
        return "OK: %s (%.1f -> %.1f LUFS, peak %.1f dBTP)" % (
            steps, self.input_lufs, self.output_lufs, self.output_peak)


@dataclass
class MasteringSettings:
    """Settings for the mastering chain (order: see the module docstring).

    Make-up gain is never entered by hand: after the compressor the chain
    measures the loudness and applies exactly the gain needed to reach
    target_lufs, limiting true peak to true_peak_max on every pass.
    """
    # Final target loudness
    target_lufs: float = -18.0
    lufs_tolerance: float = 0.5
    strict_validation: bool = True
    true_peak_max: float = -1.0        # Out Ceiling (dBTP) — same as Adaptive Limiter

    # Pre-normalization (Step 1 — normalize to this BEFORE compression)
    pre_normalize_lufs: float = -28.0  # gives headroom for compressor/limiter

    # Silence
    target_silence_s: float = 2.0
    silence_tolerance_s: float = 0.5
    silence_threshold_dbfs: float = -60.0

    # Format
    target_sample_rate: int = 48000
    target_bits: int = 24
    output_mono: bool = True           # output is always mono (input is mono too)

    # Processing options
    apply_highpass: bool = True         # Linear EQ — remove rumble
    highpass_freq: float = 80.0        # Hz

    apply_noise_gate: bool = True
    noise_gate_threshold_db: float = -60.0
    noise_gate_attack_ms: float = 5.0
    noise_gate_release_ms: float = 50.0

    # Shelving EQ (0 dB = flat, filter skipped)
    low_shelf_hz: float = 100.0
    low_shelf_db: float = 0.0
    high_shelf_hz: float = 8000.0
    high_shelf_db: float = 0.0

    # Compressor (gentle, voice-oriented defaults)
    apply_compressor: bool = True
    comp_threshold_db: float = -20.0
    comp_ratio: float = 2.0
    comp_attack_ms: float = 10.0
    comp_release_ms: float = 50.0

    # True-peak limiter
    apply_limiter: bool = True
    limiter_release_ms: float = 200.0

    # Ordered VST3 chain (runs after the compressor, before make-up/limiting)
    use_vst_plugins: bool = False
    vst_chain: List[dict] = field(default_factory=list)

    # Other
    remove_dc_offset: bool = True       # Remove DC Offset: ON
    fix_silence: bool = True
    fix_head_silence: bool = True       # enforce target silence at the front
    fix_tail_silence: bool = True       # enforce target silence at the back
    fix_format: bool = True
    preserve_markers: bool = True


def _check_dependencies():
    """Check if all mastering and true-peak dependencies are available."""
    missing = []
    try:
        import pedalboard  # noqa: F401
    except ImportError:
        missing.append("pedalboard")
    try:
        import pyloudnorm  # noqa: F401
    except ImportError:
        missing.append("pyloudnorm")
    try:
        import numpy  # noqa: F401
    except ImportError:
        missing.append("numpy")
    try:
        import scipy  # noqa: F401
    except ImportError:
        missing.append("scipy")
    return missing


def dependencies_available() -> bool:
    """Check if mastering dependencies are installed."""
    return len(_check_dependencies()) == 0


def get_dependency_message() -> str:
    """Get install instructions for missing dependencies."""
    missing = _check_dependencies()
    if not missing:
        return "All mastering dependencies are installed."
    return ("Missing packages: %s\n"
            "Install with: pip install pedalboard pyloudnorm numpy scipy" %
            ", ".join(missing))


# ---------------------------------------------------------------------------
# VST3 plugin loading helpers
# ---------------------------------------------------------------------------
def _load_vst_plugin(path: str) -> Optional[object]:
    """Attempt to load a VST3 plugin via pedalboard.load_plugin().

    Returns the loaded plugin instance, or None if loading fails.
    """
    if not path or not os.path.exists(path):
        return None
    try:
        import pedalboard
        plugin = pedalboard.load_plugin(path)
        return plugin
    except Exception:
        log.exception("Could not load VST3 plugin %s", path)
        return None


# ---------------------------------------------------------------------------
# Audio I/O helpers
# ---------------------------------------------------------------------------
def _read_audio_as_float(path: str) -> Tuple["np.ndarray", int, int]:
    """Read a WAV file and return as float32 numpy array.

    Returns:
        (audio, sample_rate, original_bits)
        audio shape: (channels, n_samples) — float32, range [-1, 1]
    """
    import numpy as np
    info = read_wav_info(path)
    sr = info.sample_rate
    bits = info.bits
    n_frames = info.n_frames
    channels = info.channels
    sw = info.sampwidth

    # Read raw PCM
    raw = read_pcm(path, info, 0, n_frames)

    # Convert to numpy float32
    if sw == 1:
        # 8-bit unsigned
        arr = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        arr = (arr - 128.0) / 128.0
    elif sw == 2:
        # 16-bit signed
        arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        arr = arr / 32768.0
    elif sw == 3:
        # 24-bit signed — convert manually
        n_samples = len(raw) // 3
        arr = np.zeros(n_samples, dtype=np.float32)
        for i in range(n_samples):
            b = raw[i*3:(i+1)*3]
            val = b[0] | (b[1] << 8) | (b[2] << 16)
            if val & 0x800000:
                val -= 0x1000000
            arr[i] = val / 8388608.0
    elif sw == 4:
        # 32-bit signed
        arr = np.frombuffer(raw, dtype=np.int32).astype(np.float32)
        arr = arr / 2147483648.0
    else:
        raise ValueError("Unsupported sample width: %d" % sw)

    # Reshape to (channels, n_samples) for pedalboard
    arr = arr.reshape(-1, channels).T

    return arr, sr, bits


def _write_wav_float(path: str, audio: "np.ndarray", sample_rate: int, bits: int):
    """Write a float32 numpy array as a WAV file.

    audio shape: (channels, n_samples)
    """
    import numpy as np
    channels = audio.shape[0]
    n_samples = audio.shape[1]
    sw = max(1, bits // 8)

    # Clip to [-1, 1]
    audio = np.clip(audio, -1.0, 1.0)

    # Convert float to integer samples
    if sw == 1:
        int_audio = ((audio + 1.0) * 128.0).astype(np.uint8)
        raw = int_audio.T.flatten().tobytes()
    elif sw == 2:
        int_audio = (audio * 32767.0).astype(np.int16)
        raw = int_audio.T.flatten().tobytes()
    elif sw == 3:
        # 24-bit: pack manually
        int_audio = (audio * 8388607.0).astype(np.int32)
        flat = int_audio.T.flatten()
        raw_parts = []
        for val in flat:
            v = int(val)
            if v < 0:
                v += 0x1000000
            raw_parts.append(struct.pack("<I", v & 0xFFFFFF)[:3])
        raw = b"".join(raw_parts)
    elif sw == 4:
        int_audio = (audio * 2147483647.0).astype(np.int32)
        raw = int_audio.T.flatten().tobytes()
    else:
        raise ValueError("Unsupported bit depth: %d" % bits)

    # Write WAV file
    byte_rate = sample_rate * channels * sw
    block_align = channels * sw
    data_size = len(raw)
    file_size = 36 + data_size

    with open(path, "wb") as f:
        # RIFF header
        f.write(b"RIFF")
        f.write(struct.pack("<I", file_size))
        f.write(b"WAVE")
        # fmt chunk
        f.write(b"fmt ")
        f.write(struct.pack("<I", 16))
        f.write(struct.pack("<HHIIHH", 1, channels, sample_rate,
                            byte_rate, block_align, bits))
        # data chunk
        f.write(b"data")
        f.write(struct.pack("<I", data_size))
        f.write(raw)


def _resample_audio(
        audio: "np.ndarray", source_rate: int,
        target_rate: int) -> "np.ndarray":
    """Change the actual sample count while preserving audio duration."""
    import math
    import numpy as np
    from scipy.signal import resample_poly

    if source_rate == target_rate:
        return audio
    divisor = math.gcd(int(source_rate), int(target_rate))
    up = int(target_rate) // divisor
    down = int(source_rate) // divisor
    channels = [
        resample_poly(channel, up=up, down=down).astype(np.float32)
        for channel in audio]
    expected_length = int(round(
        audio.shape[1] * target_rate / float(source_rate)))
    output = np.zeros(
        (audio.shape[0], expected_length), dtype=np.float32)
    for index, channel in enumerate(channels):
        copy_length = min(expected_length, len(channel))
        output[index, :copy_length] = channel[:copy_length]
    return output


# ---------------------------------------------------------------------------
# True Peak measurement using 4x oversampling (ITU-R BS.1770 / same as Orban)
# ---------------------------------------------------------------------------
def _adaptive_true_peak_limit(audio: "np.ndarray", sample_rate: int,
                               ceiling_db: float, release_ms: float,
                               lookahead_ms: float = 5.0) -> "np.ndarray":
    """Look-ahead true-peak limiter: only turns down what would cross the ceiling.

    1. Upsample 4x and take each sample's reconstructed peak (inter-sample
       peaks included), giving the gain each sample needs: min(1, ceiling/peak).
    2. Hold that gain from lookahead_ms before a peak to release_ms after it,
       then smooth the edges over lookahead_ms so there are no clicks.
    The smoothing window sits inside the hold window, so every peak still
    gets at least the reduction it needs. Material below the ceiling is left
    untouched (no make-up gain, no compression).
    """
    import numpy as np
    from scipy.ndimage import minimum_filter1d, uniform_filter1d
    from scipy.signal import resample_poly

    channels, n = audio.shape
    if n == 0:
        return audio
    ceiling = 10.0 ** (ceiling_db / 20.0)
    up = np.abs(resample_poly(audio, 4, 1, axis=1))[:, :n * 4]
    if up.shape[1] < n * 4:
        up = np.pad(up, ((0, 0), (0, n * 4 - up.shape[1])))
    peak = up.reshape(channels, n, 4).max(axis=2).max(axis=0)
    need = np.minimum(1.0, ceiling / np.maximum(peak, 1e-12))
    if need.min() >= 1.0:
        return audio

    look = max(1, int(sample_rate * lookahead_ms / 1000.0))
    hold = max(look, int(sample_rate * release_ms / 1000.0))
    if (look + hold) % 2:
        hold += 1
    half = (look + hold) // 2
    # held[i] = min(need[i - hold : i + look + 1])
    padded = np.concatenate([np.ones(hold), need, np.ones(look)])
    held = minimum_filter1d(padded, size=look + hold + 1)[half:half + n]
    gain = uniform_filter1d(held, size=look if look % 2 else look + 1,
                            mode="nearest")
    return (audio * gain[np.newaxis, :]).astype(np.float32)


def _measure_true_peak_oversampled(audio: "np.ndarray", sample_rate: int) -> float:
    """Measure true peak using 4x oversampling (ITU-R BS.1770-4 compliant).

    This is the same method Orban uses for "Highest Reconstructed Peak Level".
    It interpolates between samples to find inter-sample peaks that exceed
    the actual sample values.

    Returns the peak as a linear value (not dB).
    """
    import numpy as np
    from scipy.signal import resample_poly

    # 4x upsample using polyphase filter (ITU-R BS.1770 spec)
    try:
        upsampled = resample_poly(audio.flatten(), up=4, down=1)
        true_peak = np.max(np.abs(upsampled))
    except Exception:
        log.exception("True-peak oversampling failed; using sample peak")
        true_peak = np.max(np.abs(audio))

    return float(true_peak)


def _limit_true_peak(audio: "np.ndarray", sample_rate: int, ceiling_db: float,
                     release_ms: float, result) -> "np.ndarray":
    """Limit so the reconstructed (4x oversampled) peak is <= ceiling_db.

    Gain changes between samples can let a reconstructed peak creep a hair
    over the internal ceiling, so the result is re-measured and the limiter
    re-run with a slightly lower internal ceiling until it is safe.
    """
    import numpy as np
    tp_db = 0.0
    out = audio
    for attempt in (1, 2, 3):
        out = _adaptive_true_peak_limit(
            audio, sample_rate, ceiling_db - 0.1 * attempt, release_ms)
        peak = _measure_true_peak_oversampled(out, sample_rate)
        tp_db = 20.0 * np.log10(peak) if peak > 0 else -120.0
        if tp_db <= ceiling_db:
            return out
    result.warnings.append(
        "True peak %.2f dBTP is still above the %.1f dBTP ceiling after limiting."
        % (tp_db, ceiling_db))
    return out


def _converge_to_target(audio: "np.ndarray", sample_rate: int,
                        settings: "MasteringSettings", result,
                        max_passes: int = 4) -> "np.ndarray":
    """Make-up gain to target LUFS, true-peak limit, re-measure, repeat.

    Limiting removes some loudness, so a single gain step undershoots. Each
    pass measures the integrated loudness and applies the exact difference.
    """
    tol = settings.lufs_tolerance / 2.0
    total_db = 0.0
    passes = 0
    err = 0.0
    for i in range(max_passes):
        lufs, _ = _measure_loudness(audio, sample_rate)
        if lufs <= -120.0:
            return audio  # digital silence: nothing to normalise
        err = settings.target_lufs - lufs
        if i > 0 and abs(err) <= tol:
            break
        audio = audio * (10.0 ** (err / 20.0))
        total_db += err
        passes += 1
        if settings.apply_limiter:
            audio = _limit_true_peak(audio, sample_rate, settings.true_peak_max,
                                     settings.limiter_release_ms, result)
        err = None  # re-measured on the next pass
    if err is None:
        lufs, _ = _measure_loudness(audio, sample_rate)
        err = settings.target_lufs - lufs
    result.gain_applied_db = total_db
    if settings.apply_limiter:
        result.steps_applied.append(
            "make-up gain %+.1f dB, true-peak limiter %.1f dBTP (%d pass%s)" % (
                total_db, settings.true_peak_max, passes,
                "" if passes == 1 else "es"))
    else:
        result.steps_applied.append("make-up gain %+.1f dB" % total_db)
    if abs(err) > tol:
        result.warnings.append(
            "Loudness did not converge: %.1f LU from target after %d passes. "
            "The material may be too dense for %.1f LUFS at %.1f dBTP; "
            "try more compression." % (
                -err, passes, settings.target_lufs, settings.true_peak_max))
    return audio


# ---------------------------------------------------------------------------
# Loudness measurement (pyloudnorm)
# ---------------------------------------------------------------------------
def _measure_loudness(audio: "np.ndarray", sample_rate: int) -> Tuple[float, float]:
    """Measure integrated loudness (LUFS) and true peak (dBTP).

    Returns (lufs, true_peak_db)
    """
    import numpy as np
    import pyloudnorm as pyln

    # pyloudnorm expects (n_samples, channels)
    audio_t = audio.T

    meter = pyln.Meter(sample_rate)
    lufs = meter.integrated_loudness(audio_t)

    peak_linear = _measure_true_peak_oversampled(audio, sample_rate)
    if peak_linear > 0:
        true_peak_db = 20.0 * np.log10(peak_linear)
    else:
        true_peak_db = -120.0

    return float(lufs), float(true_peak_db)


# ---------------------------------------------------------------------------
# Silence detection and manipulation
# ---------------------------------------------------------------------------
def _measure_silence(audio: "np.ndarray", sample_rate: int,
                     threshold_dbfs: float = -60.0) -> Tuple[float, float]:
    """Measure head and tail silence duration.

    Returns (head_silence_s, tail_silence_s)
    """
    import numpy as np
    # Convert to mono for silence detection
    if audio.shape[0] > 1:
        mono = np.mean(audio, axis=0)
    else:
        mono = audio[0]

    threshold_linear = 10.0 ** (threshold_dbfs / 20.0)
    n_samples = len(mono)

    # Head silence
    head_samples = 0
    for i in range(n_samples):
        if abs(mono[i]) > threshold_linear:
            break
        head_samples = i + 1

    # Tail silence
    tail_samples = 0
    for i in range(n_samples - 1, -1, -1):
        if abs(mono[i]) > threshold_linear:
            break
        tail_samples = n_samples - i

    head_s = head_samples / float(sample_rate)
    tail_s = tail_samples / float(sample_rate)
    return head_s, tail_s


def _fix_silence(audio: "np.ndarray", sample_rate: int,
                 target_s: float, threshold_dbfs: float) -> "np.ndarray":
    """Trim or pad head and tail silence to target duration.

    Returns new audio array with correct silence.
    """
    result, _delta = _fix_silence_sides(
        audio, sample_rate, target_s, threshold_dbfs,
        fix_head=True, fix_tail=True)
    return result


def _fix_silence_sides(audio: "np.ndarray", sample_rate: int,
                       target_s: float, threshold_dbfs: float,
                       fix_head: bool = True,
                       fix_tail: bool = True) -> Tuple["np.ndarray", int]:
    """Trim/pad selected edges and return the content timing transform.

    The returned integer is the number of samples by which content-relative
    markers must move. A positive value means head padding was added; a
    negative value means head silence was trimmed. Tail-only edits return 0.
    """
    import numpy as np
    channels = audio.shape[0]
    threshold_linear = 10.0 ** (threshold_dbfs / 20.0)

    # Find first non-silent sample (head)
    if channels > 1:
        mono = np.mean(audio, axis=0)
    else:
        mono = audio[0]

    n_samples = len(mono)
    head_end = 0
    for i in range(n_samples):
        if abs(mono[i]) > threshold_linear:
            head_end = i
            break

    # Find last non-silent sample (tail)
    tail_start = n_samples
    for i in range(n_samples - 1, -1, -1):
        if abs(mono[i]) > threshold_linear:
            tail_start = i + 1
            break

    # Extract the content (non-silent audio).
    content = audio[:, head_end:tail_start]

    # Create or preserve each edge independently.
    target_samples = int(target_s * sample_rate)
    if fix_head:
        head_audio = np.zeros((channels, target_samples), dtype=np.float32)
        marker_delta_samples = target_samples - head_end
    else:
        head_audio = audio[:, :head_end]
        marker_delta_samples = 0

    if fix_tail:
        tail_audio = np.zeros((channels, target_samples), dtype=np.float32)
    else:
        tail_audio = audio[:, tail_start:]

    result = np.concatenate([head_audio, content, tail_audio], axis=1)
    return result, marker_delta_samples


# ---------------------------------------------------------------------------
# The mastering chain
# ---------------------------------------------------------------------------
def _write_mastering_report(
        result: MasteringResult, settings: MasteringSettings) -> None:
    """Write a machine-readable audit report beside the mastered WAV."""
    if not result.output_path:
        return
    destination = os.path.splitext(result.output_path)[0] + ".mastering.json"
    payload = {
        "version": 1,
        "output_path": os.path.abspath(result.output_path),
        "settings": asdict(settings),
        "result": asdict(result),
    }
    payload["result"]["report_path"] = destination
    def json_default(value):
        if hasattr(value, "item"):
            return value.item()
        raise TypeError(
            "Object of type %s is not JSON serializable" %
            type(value).__name__)

    with open(destination, "w", encoding="utf-8") as stream:
        json.dump(
            payload, stream, indent=2, ensure_ascii=False,
            default=json_default)
    result.report_path = destination


def _validate_mastered_output(
        result: MasteringResult, settings: MasteringSettings,
        original_marker_count: int) -> None:
    """Independently reopen and verify the finished deliverable."""
    issues: List[str] = []
    output_info = read_wav_info(result.output_path)
    result.output_sample_rate = output_info.sample_rate
    result.output_bits = output_info.bits
    result.input_marker_count = original_marker_count

    output_audio, output_sr, _bits = _read_audio_as_float(
        result.output_path)
    head_s, tail_s = _measure_silence(
        output_audio, output_sr, settings.silence_threshold_dbfs)
    result.output_head_silence = head_s
    result.output_tail_silence = tail_s

    # ffmpeg EBU R128 is deliberately separate from the in-memory mastering
    # measurement. Fall back to the in-memory values only when unavailable.
    try:
        from .loudness import measure_loudness
        measured = measure_loudness(
            result.output_path,
            target_lufs=settings.target_lufs,
            lufs_tol=settings.lufs_tolerance,
            true_peak_max=settings.true_peak_max)
        if measured.integrated_lufs is not None:
            result.output_lufs = measured.integrated_lufs
        if measured.true_peak_dbtp is not None:
            result.output_peak = measured.true_peak_dbtp
    except Exception as exc:
        result.warnings.append(
            "Independent ffmpeg loudness validation was unavailable: %s" %
            exc)

    result.lufs_error = result.output_lufs - settings.target_lufs
    result.peak_margin = settings.true_peak_max - result.output_peak
    if abs(result.lufs_error) > settings.lufs_tolerance + 1e-9:
        issues.append(
            "loudness %.1f LUFS is outside target %.1f +/- %.1f" %
            (result.output_lufs, settings.target_lufs,
             settings.lufs_tolerance))
    if result.output_peak > settings.true_peak_max + 1e-9:
        issues.append(
            "true peak %.1f dBTP exceeds %.1f dBTP" %
            (result.output_peak, settings.true_peak_max))

    if settings.fix_format:
        if output_info.sample_rate != settings.target_sample_rate:
            issues.append(
                "sample rate is %d Hz, expected %d Hz" %
                (output_info.sample_rate, settings.target_sample_rate))
        if output_info.bits != settings.target_bits:
            issues.append(
                "bit depth is %d-bit, expected %d-bit" %
                (output_info.bits, settings.target_bits))
    if settings.output_mono and output_info.channels != 1:
        issues.append(
            "output has %d channels, expected mono" % output_info.channels)

    if settings.fix_silence and settings.fix_head_silence:
        if abs(head_s - settings.target_silence_s) > (
                settings.silence_tolerance_s + 1e-9):
            issues.append(
                "front silence %.2fs is outside %.2fs +/- %.2fs" %
                (head_s, settings.target_silence_s,
                 settings.silence_tolerance_s))
    if settings.fix_silence and settings.fix_tail_silence:
        if abs(tail_s - settings.target_silence_s) > (
                settings.silence_tolerance_s + 1e-9):
            issues.append(
                "back silence %.2fs is outside %.2fs +/- %.2fs" %
                (tail_s, settings.target_silence_s,
                 settings.silence_tolerance_s))

    try:
        result.output_marker_count = len(read_markers(result.output_path))
    except Exception:
        log.exception("Could not read markers from %s", result.output_path)
        result.output_marker_count = 0
    if (settings.preserve_markers and original_marker_count and
            result.output_marker_count != original_marker_count):
        issues.append(
            "preserved %d of %d input markers" %
            (result.output_marker_count, original_marker_count))

    result.validation_issues = issues
    result.validation_passed = not issues


def master_file(path: str, settings: Optional[MasteringSettings] = None,
                output_path: Optional[str] = None,
                progress_callback=None) -> MasteringResult:
    """Master a single WAV file according to the given settings.

    Args:
        path: input WAV file path
        settings: mastering settings (uses defaults if None)
        output_path: output path (default: input_mastered.wav)
        progress_callback: optional callable(stage: str, progress: float)

    Returns:
        MasteringResult with success/error info and measurements
    """
    if settings is None:
        settings = MasteringSettings()

    result = MasteringResult()

    # Check dependencies
    missing = _check_dependencies()
    if missing:
        result.error = ("Missing packages: %s. "
                        "Install with: pip install pedalboard pyloudnorm numpy scipy" %
                        ", ".join(missing))
        return result

    import pedalboard as pb
    import numpy as np

    # Output path
    if not output_path:
        output_path = generate_output_path(path)
    result.output_path = output_path

    try:
        # --- Read audio ---
        if progress_callback:
            progress_callback("reading", 0.05)

        audio, sr, original_bits = _read_audio_as_float(path)
        input_sample_rate = sr
        marker_time_shift_s = 0.0
        channels = audio.shape[0]

        # --- Read markers (to re-embed later) ---
        original_markers = []
        if settings.preserve_markers:
            try:
                markers = read_markers(path)
                original_markers = [(m.sample_offset, m.label) for m in markers]
            except Exception:
                result.warnings.append("Could not read markers from original file.")
        result.input_marker_count = len(original_markers)

        # --- Measure input ---
        if progress_callback:
            progress_callback("measuring", 0.1)

        input_lufs, input_peak = _measure_loudness(audio, sr)
        result.input_lufs = input_lufs
        result.input_peak = input_peak

        # --- DC offset ---
        if settings.remove_dc_offset:
            dc = np.mean(audio)
            if abs(dc) > 1e-6:
                audio = audio - dc
                result.steps_applied.append("DC offset removed")

        # --- Mono ---
        if settings.output_mono and audio.shape[0] > 1:
            audio = np.mean(audio, axis=0, keepdims=True)
            result.steps_applied.append("mono")

        # --- Resample first: everything peak-critical runs at the final rate ---
        target_sr = settings.target_sample_rate
        if settings.fix_format and sr != target_sr:
            if progress_callback:
                progress_callback("resampling", 0.12)
            audio = _resample_audio(audio, sr, target_sr)
            sr = target_sr
            result.steps_applied.append("resample %dHz" % target_sr)
            # Marker offsets are recalculated from time when the output is
            # written, after all timeline and sample-rate changes.

        # --- Pre-normalise (headroom for the processors) ---
        if progress_callback:
            progress_callback("pre-normalizing", 0.15)
        current_lufs, _ = _measure_loudness(audio, sr)
        if current_lufs > -120.0:
            pre_gain_db = settings.pre_normalize_lufs - current_lufs
            audio = audio * (10.0 ** (pre_gain_db / 20.0))
            result.steps_applied.append("pre-normalize to %.0f LUFS (%+.1f dB)" % (
                settings.pre_normalize_lufs, pre_gain_db))

        # --- Noise gate ---
        if settings.apply_noise_gate:
            if progress_callback:
                progress_callback("noise gate", 0.2)
            audio = pb.Pedalboard([pb.NoiseGate(
                threshold_db=settings.noise_gate_threshold_db,
                attack_ms=settings.noise_gate_attack_ms,
                release_ms=settings.noise_gate_release_ms,
            )])(audio, sr)
            result.steps_applied.append(
                "noise gate %.0f dB" % settings.noise_gate_threshold_db)

        # --- EQ: high-pass + optional shelves ---
        eq = []
        if settings.apply_highpass and settings.highpass_freq > 0:
            eq.append(pb.HighpassFilter(cutoff_frequency_hz=settings.highpass_freq))
            result.steps_applied.append("high-pass %d Hz" % int(settings.highpass_freq))
        if settings.low_shelf_db:
            eq.append(pb.LowShelfFilter(cutoff_frequency_hz=settings.low_shelf_hz,
                                        gain_db=settings.low_shelf_db))
            result.steps_applied.append("low shelf %d Hz %+.1f dB" % (
                int(settings.low_shelf_hz), settings.low_shelf_db))
        if settings.high_shelf_db:
            eq.append(pb.HighShelfFilter(cutoff_frequency_hz=settings.high_shelf_hz,
                                         gain_db=settings.high_shelf_db))
            result.steps_applied.append("high shelf %d Hz %+.1f dB" % (
                int(settings.high_shelf_hz), settings.high_shelf_db))
        if eq:
            if progress_callback:
                progress_callback("EQ", 0.25)
            audio = pb.Pedalboard(eq)(audio, sr)

        # --- Compressor (make-up gain comes from the loudness step below) ---
        if settings.apply_compressor:
            if progress_callback:
                progress_callback("compressor", 0.35)
            audio = pb.Pedalboard([pb.Compressor(
                threshold_db=settings.comp_threshold_db,
                ratio=settings.comp_ratio,
                attack_ms=settings.comp_attack_ms,
                release_ms=settings.comp_release_ms,
            )])(audio, sr)
            result.steps_applied.append("compressor %.0f dB %.1f:1" % (
                settings.comp_threshold_db, settings.comp_ratio))

        # --- Ordered custom VST chain ---
        # Make-up gain, limiting and validation still run after this chain so
        # plugin output cannot bypass the delivery targets.
        if settings.use_vst_plugins and settings.vst_chain:
            if progress_callback:
                progress_callback("custom VST chain", 0.44)
            for slot in settings.vst_chain:
                plugin_path = str(slot.get("path", ""))
                plugin_name = str(
                    slot.get("name") or os.path.basename(plugin_path))
                if not plugin_path:
                    continue
                plugin = _load_vst_plugin(plugin_path)
                if plugin is None:
                    result.warnings.append(
                        "Could not load VST plugin: %s" % plugin_name)
                    continue
                try:
                    audio = plugin(audio, sr)
                    result.steps_applied.append("VST: %s" % plugin_name)
                except Exception as exc:
                    result.warnings.append(
                        "VST %s failed: %s" % (plugin_name, exc))

        # --- Make-up gain + true-peak limiter, converged to target ---
        if progress_callback:
            progress_callback("loudness + limiter", 0.5)
        audio = _converge_to_target(audio, sr, settings, result)

        # --- Fix silence (trim/pad) ---
        if settings.fix_silence and (
                settings.fix_head_silence or settings.fix_tail_silence):
            if progress_callback:
                progress_callback("fixing silence", 0.65)

            head_s, tail_s = _measure_silence(audio, sr, settings.silence_threshold_dbfs)
            needs_fix = (
                settings.fix_head_silence and
                abs(head_s - settings.target_silence_s) > settings.silence_tolerance_s
            ) or (
                settings.fix_tail_silence and
                abs(tail_s - settings.target_silence_s) > settings.silence_tolerance_s
            )

            if needs_fix:
                audio, marker_delta_samples = _fix_silence_sides(
                    audio, sr, settings.target_silence_s,
                    settings.silence_threshold_dbfs,
                    fix_head=settings.fix_head_silence,
                    fix_tail=settings.fix_tail_silence)
                marker_time_shift_s = marker_delta_samples / float(sr)
                sides = []
                if settings.fix_head_silence:
                    sides.append("front")
                if settings.fix_tail_silence:
                    sides.append("back")
                result.steps_applied.append(
                    "%s silence %.1fs" %
                    ("+".join(sides), settings.target_silence_s))

        # --- Bit depth ---
        target_bits = settings.target_bits
        if settings.fix_format and original_bits != target_bits:
            result.steps_applied.append("bit depth %d" % target_bits)
        else:
            target_bits = original_bits

        # --- Measure output ---
        if progress_callback:
            progress_callback("measuring output", 0.85)

        output_lufs, output_peak = _measure_loudness(audio, sr)
        result.output_lufs = output_lufs
        result.output_peak = output_peak

        # --- Write output ---
        if progress_callback:
            progress_callback("writing", 0.9)

        if settings.preserve_markers and original_markers:
            # Write audio first, then embed markers
            tmp_path = output_path + ".tmp.wav"
            _write_wav_float(tmp_path, audio, sr, target_bits)

            # Recalculate marker positions using the input sample rate and the
            # exact head trim/pad transform. Tail edits do not move markers.
            adjusted_markers = []
            for sample_offset, label in original_markers:
                original_time = sample_offset / float(input_sample_rate)
                adjusted_time = max(0.0, original_time + marker_time_shift_s)
                new_offset = int(round(adjusted_time * sr))
                # Only keep markers that fit within the new file
                if 0 <= new_offset < audio.shape[1]:
                    adjusted_markers.append((new_offset, label))

            if adjusted_markers:
                write_markers_to_wav(tmp_path, output_path, adjusted_markers)
                os.remove(tmp_path)
            else:
                os.rename(tmp_path, output_path)
        else:
            _write_wav_float(output_path, audio, sr, target_bits)

        if progress_callback:
            progress_callback("validating deliverable", 0.96)
        _validate_mastered_output(
            result, settings, len(original_markers))
        result.success = (
            result.validation_passed or not settings.strict_validation)
        if not result.validation_passed:
            result.error = (
                "Post-master validation failed: " +
                "; ".join(result.validation_issues))
            result.warnings.append(
                "The output was kept for inspection but is not approved.")
        _write_mastering_report(result, settings)

        if progress_callback:
            progress_callback("done", 1.0)

    except Exception as e:
        result.success = False
        result.error = str(e)
        try:
            _write_mastering_report(result, settings)
        except Exception:
            log.exception("Could not write the mastering report")

    return result


def generate_output_path(src_path: str) -> str:
    """Generate the output path for a mastered file.

    Keeps the original filename, places it in a folder named like:
      GEN_Mastered/  (based on the book abbreviation from the filename)

    Examples:
      GEN_001.wav -> GEN_Mastered/GEN_001.wav
      PSA_119.wav -> PSA_Mastered/PSA_119.wav
      Mat_024.wav -> Mat_Mastered/Mat_024.wav
      unknown.wav -> Mastered/unknown.wav
    """
    import re
    src_dir = os.path.dirname(src_path)
    filename = os.path.basename(src_path)

    # Extract the book abbreviation from filename (e.g., "GEN" from "GEN_001.wav")
    m = re.match(r"^([A-Za-z0-9]+?)[\s_\-\.]", filename)
    if m:
        book_abbrev = m.group(1)
        folder_name = "%s_Mastered" % book_abbrev
    else:
        folder_name = "Mastered"

    output_dir = os.path.join(src_dir, folder_name)
    os.makedirs(output_dir, exist_ok=True)
    return os.path.join(output_dir, filename)


# ---------------------------------------------------------------------------
# Batch mastering
# ---------------------------------------------------------------------------
def master_files(paths: List[str], settings: Optional[MasteringSettings] = None,
                 progress_callback=None) -> List[MasteringResult]:
    """Master multiple WAV files.

    Args:
        paths: list of input WAV file paths
        settings: mastering settings
        progress_callback: optional callable(file_index: int, total: int, filename: str)

    Returns:
        List of MasteringResult, one per file
    """
    results = []
    total = len(paths)
    for i, path in enumerate(paths):
        if progress_callback:
            progress_callback(i + 1, total, os.path.basename(path))
        r = master_file(path, settings)
        results.append(r)
    return results


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m engine.mastering <file.wav> [file2.wav ...]")
        print()
        print("Dependencies: %s" % get_dependency_message())
        sys.exit(1)

    if not dependencies_available():
        print("ERROR: %s" % get_dependency_message())
        sys.exit(1)

    settings = MasteringSettings()
    for path in sys.argv[1:]:
        print("Mastering: %s" % path)
        result = master_file(path, settings)
        if result.success:
            print("  OK: %s" % result.summary)
            print("  Output: %s" % result.output_path)
        else:
            print("  FAILED: %s" % result.error)
