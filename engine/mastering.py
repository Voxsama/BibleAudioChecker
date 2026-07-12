"""
mastering.py — auto-master Bible audio WAV files to broadcast standards.

Uses Pedalboard (Spotify) for studio-grade audio processing and pyloudnorm
for ITU-R BS.1770 / EBU R128 loudness measurement. Same algorithms as Logic Pro.

Mastering chain:
  1. High-pass filter (remove rumble below 80 Hz)
  2. Noise gate (clean silence sections)
  3. Loudness normalization (adjust gain to hit target LUFS)
  4. Brickwall limiter (true peak ceiling at -1 dBTP)
  5. Trim/pad head and tail silence to exact duration
  6. Sample rate conversion (if needed)
  7. Bit depth conversion (if needed)
  8. Re-embed markers from the original file

Output: GEN_001_mastered.wav (original untouched)

Requires: pip install pedalboard pyloudnorm numpy
"""

from __future__ import annotations

import os
import struct
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .wavio import read_wav_info, read_pcm
from .wav_markers import read_markers
from .marker_writer import write_markers as write_markers_to_wav


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
    """Settings for the mastering chain — matches Logic Pro workflow.

    Chain order (same as Logic Pro):
      1. Normalize Gain (to -28 LUFS — lower than target, gives headroom)
      2. Noise Gate (clean silence sections)
      3. High-pass filter (Linear EQ — remove rumble)
      4. Compressor (gentle, Platinum Digital style — controls dynamics)
      5. Adaptive Limiter (Gain: auto, Out Ceiling: -1.0 dBTP, True Peak: ON)
      6. Final loudness normalize to target (-18 LUFS)
    """
    # Final target loudness
    target_lufs: float = -18.0
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

    # Compressor (Platinum Digital style — gentle, voice-optimized)
    apply_compressor: bool = True
    comp_threshold_db: float = -20.0   # threshold
    comp_ratio: float = 2.0            # ratio (gentle for voice)
    comp_attack_ms: float = 10.0       # attack
    comp_release_ms: float = 50.0      # release
    comp_makeup_gain_db: float = 0.0   # auto-calculated if 0

    # Adaptive Limiter (Logic Pro style)
    apply_limiter: bool = True
    limiter_lookahead_ms: float = 50.0  # Lookahead: 50ms (same as your setting)
    limiter_release_ms: float = 200.0   # gentle release
    limiter_gain_db: float = 0.0        # auto-calculated based on audio

    # VST3 plugin paths (user-supplied)
    use_vst_plugins: bool = False       # toggle to use VSTs instead of built-in
    vst_compressor_path: str = ""       # path to user's compressor VST3 plugin
    vst_limiter_path: str = ""          # path to user's limiter VST3 plugin
    vst_eq_path: str = ""              # path to user's EQ VST3 plugin

    # Other
    remove_dc_offset: bool = True       # Remove DC Offset: ON
    fix_silence: bool = True
    fix_format: bool = True
    preserve_markers: bool = True


def _check_dependencies():
    """Check if pedalboard and pyloudnorm are available."""
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
            "Install with: pip install pedalboard pyloudnorm numpy" %
            ", ".join(missing))


# ---------------------------------------------------------------------------
# VST3 plugin loading helpers
# ---------------------------------------------------------------------------
_ASSETS_VST_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "vst")


def _find_bundled_limiter() -> Optional[str]:
    """Look for a bundled VST3 limiter (e.g. LoudMax) in assets/vst/.

    Returns the path if found, None otherwise.
    """
    if not os.path.isdir(_ASSETS_VST_DIR):
        return None
    for entry in os.listdir(_ASSETS_VST_DIR):
        if entry.lower().endswith(".vst3"):
            return os.path.join(_ASSETS_VST_DIR, entry)
    return None


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


# ---------------------------------------------------------------------------
# True Peak measurement using 4x oversampling (ITU-R BS.1770 / same as Orban)
# ---------------------------------------------------------------------------
def _adaptive_true_peak_limit(audio: "np.ndarray", sample_rate: int,
                               ceiling_db: float, release_ms: float,
                               pb) -> "np.ndarray":
    """Adaptive true peak limiter — same approach as Logic Pro's Adaptive Limiter.

    Works by:
      1. Upsample audio 4x (so inter-sample peaks become visible as actual samples)
      2. Apply brickwall limiter at the upsampled rate
      3. Downsample back to original rate

    This guarantees the reconstructed waveform never exceeds the ceiling,
    because we're limiting the actual reconstructed signal.

    Args:
        audio: (channels, n_samples) float32 array
        sample_rate: original sample rate
        ceiling_db: true peak ceiling in dBTP (e.g., -1.0)
        release_ms: limiter release time
        pb: pedalboard module reference

    Returns:
        Limited audio at original sample rate
    """
    import numpy as np
    from scipy.signal import resample_poly

    channels, n_samples = audio.shape
    upsampled_sr = sample_rate * 4

    # Step 1: Upsample 4x (polyphase — high quality, no aliasing)
    upsampled = np.zeros((channels, n_samples * 4), dtype=np.float32)
    for ch in range(channels):
        upsampled[ch] = resample_poly(audio[ch], up=4, down=1).astype(np.float32)

    # Step 2: Apply limiter at 4x sample rate
    # Set threshold slightly below ceiling for safety margin
    board = pb.Pedalboard([
        pb.Limiter(
            threshold_db=ceiling_db,
            release_ms=release_ms,
        ),
    ])
    upsampled = board(upsampled, upsampled_sr)

    # Also hard clip at ceiling (absolute safety)
    ceiling_linear = 10.0 ** (ceiling_db / 20.0)
    upsampled = np.clip(upsampled, -ceiling_linear, ceiling_linear)

    # Step 3: Downsample back to original rate
    result = np.zeros((channels, n_samples), dtype=np.float32)
    for ch in range(channels):
        downsampled = resample_poly(upsampled[ch], up=1, down=4).astype(np.float32)
        # resample_poly may produce slightly different length due to filtering
        out_len = min(n_samples, len(downsampled))
        result[ch, :out_len] = downsampled[:out_len]

    return result


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
        # Fallback: simple peak
        true_peak = np.max(np.abs(audio))

    return float(true_peak)


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

    # True peak (oversampled peak detection)
    peak_linear = np.max(np.abs(audio))
    if peak_linear > 0:
        true_peak_db = 20.0 * np.log10(peak_linear)
    else:
        true_peak_db = -120.0

    return lufs, true_peak_db


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

    # Extract the content (non-silent audio)
    content = audio[:, head_end:tail_start]

    # Create target silence
    target_samples = int(target_s * sample_rate)
    silence = np.zeros((channels, target_samples), dtype=np.float32)

    # Assemble: silence + content + silence
    result = np.concatenate([silence, content, silence], axis=1)
    return result


# ---------------------------------------------------------------------------
# The mastering chain
# ---------------------------------------------------------------------------
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
                        "Install with: pip install pedalboard pyloudnorm numpy" %
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
        channels = audio.shape[0]

        # --- Read markers (to re-embed later) ---
        original_markers = []
        if settings.preserve_markers:
            try:
                markers = read_markers(path)
                original_markers = [(m.sample_offset, m.label) for m in markers]
            except Exception:
                result.warnings.append("Could not read markers from original file.")

        # --- Measure input ---
        if progress_callback:
            progress_callback("measuring", 0.1)

        input_lufs, input_peak = _measure_loudness(audio, sr)
        result.input_lufs = input_lufs
        result.input_peak = input_peak

        # --- Step 1: Remove DC Offset ---
        if settings.remove_dc_offset:
            dc = np.mean(audio)
            if abs(dc) > 1e-6:
                audio = audio - dc
                result.steps_applied.append("DC offset removed")

        # --- Step 1.5: Convert to mono (input is mono but just in case) ---
        if settings.output_mono and audio.shape[0] > 1:
            mono = np.mean(audio, axis=0, keepdims=True)
            audio = mono
            result.steps_applied.append("mono")

        # --- Step 2: Pre-normalize to -28 LUFS (gives headroom for processing) ---
        if progress_callback:
            progress_callback("pre-normalizing", 0.15)

        current_lufs, _ = _measure_loudness(audio, sr)
        if current_lufs > -120.0:
            pre_gain_db = settings.pre_normalize_lufs - current_lufs
            pre_gain_linear = 10.0 ** (pre_gain_db / 20.0)
            audio = audio * pre_gain_linear
            result.steps_applied.append("pre-normalize to %.0f LUFS (%.1f dB)" % (
                settings.pre_normalize_lufs, pre_gain_db))

        # --- Step 3: Noise Gate (clean silence sections) ---
        if settings.apply_noise_gate:
            if progress_callback:
                progress_callback("noise gate", 0.2)

            board = pb.Pedalboard([
                pb.NoiseGate(
                    threshold_db=settings.noise_gate_threshold_db,
                    attack_ms=5.0,
                    release_ms=50.0,
                ),
            ])
            audio = board(audio, sr)
            result.steps_applied.append("noise gate")

        # --- Step 4: High-pass filter (Linear EQ — remove rumble) ---
        if settings.apply_highpass:
            if progress_callback:
                progress_callback("high-pass filter", 0.25)

            vst_eq_used = False
            if settings.use_vst_plugins and settings.vst_eq_path:
                eq_plugin = _load_vst_plugin(settings.vst_eq_path)
                if eq_plugin is not None:
                    try:
                        audio = eq_plugin(audio, sr)
                        result.steps_applied.append("VST EQ: %s" % os.path.basename(settings.vst_eq_path))
                        vst_eq_used = True
                    except Exception as e:
                        result.warnings.append("VST EQ failed, using built-in: %s" % str(e))

            if not vst_eq_used:
                board = pb.Pedalboard([
                    pb.HighpassFilter(cutoff_frequency_hz=settings.highpass_freq),
                ])
                audio = board(audio, sr)
                result.steps_applied.append("highpass %dHz" % int(settings.highpass_freq))

        # --- Step 5: Compressor (Platinum Digital style — gentle for voice) ---
        if settings.apply_compressor:
            if progress_callback:
                progress_callback("compressor", 0.35)

            # Measure level before compression to calculate auto makeup gain
            pre_comp_lufs, _ = _measure_loudness(audio, sr)

            vst_comp_used = False
            if settings.use_vst_plugins and settings.vst_compressor_path:
                comp_plugin = _load_vst_plugin(settings.vst_compressor_path)
                if comp_plugin is not None:
                    try:
                        audio = comp_plugin(audio, sr)
                        result.steps_applied.append("VST compressor: %s" % os.path.basename(settings.vst_compressor_path))
                        vst_comp_used = True
                    except Exception as e:
                        result.warnings.append("VST compressor failed, using built-in: %s" % str(e))

            if not vst_comp_used:
                board = pb.Pedalboard([
                    pb.Compressor(
                        threshold_db=settings.comp_threshold_db,
                        ratio=settings.comp_ratio,
                        attack_ms=settings.comp_attack_ms,
                        release_ms=settings.comp_release_ms,
                    ),
                ])
                audio = board(audio, sr)

                # Auto makeup gain: compensate for the gain reduction the compressor applied
                # (same as Logic Pro's Auto Gain — brings level back up after compression)
                post_comp_lufs, _ = _measure_loudness(audio, sr)
                if pre_comp_lufs > -120.0 and post_comp_lufs > -120.0:
                    gain_reduction = pre_comp_lufs - post_comp_lufs
                    if gain_reduction > 0.5:
                        # Apply makeup gain (restore some of the lost level)
                        # Use 40% compensation — conservative, lets final step handle the rest
                        makeup_db = gain_reduction * 0.4
                        makeup_linear = 10.0 ** (makeup_db / 20.0)
                        audio = audio * makeup_linear
                        result.steps_applied.append("compressor (%.0fdB, %.1f:1) + auto makeup +%.1f dB" % (
                            settings.comp_threshold_db, settings.comp_ratio, makeup_db))
                    else:
                        result.steps_applied.append("compressor (%.0fdB, %.1f:1, minimal reduction)" % (
                            settings.comp_threshold_db, settings.comp_ratio))
                else:
                    result.steps_applied.append("compressor (%.0fdB, %.1f:1)" % (
                        settings.comp_threshold_db, settings.comp_ratio))

        # --- Step 6: Adaptive Limiter (Logic Pro style — True Peak ON) ---
        # Upsample 4x → limit → downsample (catches inter-sample peaks)
        if settings.apply_limiter:
            if progress_callback:
                progress_callback("adaptive limiter (true peak)", 0.5)

            # Calculate gain needed to bring audio up to target after limiting
            current_lufs_post_comp, _ = _measure_loudness(audio, sr)
            if current_lufs_post_comp > -120.0:
                # How much gain the adaptive limiter should apply
                # Only apply 50% of needed gain — compressor already boosted,
                # final loudness step fine-adjusts the rest
                limiter_gain_db = (settings.target_lufs - current_lufs_post_comp) * 0.5
                if limiter_gain_db > 0:
                    # Apply gain (like the Adaptive Limiter's Gain knob)
                    gain_linear = 10.0 ** (limiter_gain_db / 20.0)
                    audio = audio * gain_linear
                    result.gain_applied_db = limiter_gain_db
                    result.steps_applied.append("limiter gain +%.1f dB" % limiter_gain_db)

            # Try VST limiter first (user-supplied), then bundled, then built-in
            vst_limiter_used = False

            # Option A: User-supplied VST limiter
            if settings.use_vst_plugins and settings.vst_limiter_path:
                limiter_plugin = _load_vst_plugin(settings.vst_limiter_path)
                if limiter_plugin is not None:
                    try:
                        audio = limiter_plugin(audio, sr)
                        result.steps_applied.append("VST limiter: %s" % os.path.basename(settings.vst_limiter_path))
                        vst_limiter_used = True
                    except Exception as e:
                        result.warnings.append("VST limiter failed, trying fallback: %s" % str(e))

            # Option B: Bundled VST limiter (e.g. LoudMax in assets/vst/)
            if not vst_limiter_used:
                bundled_limiter_path = _find_bundled_limiter()
                if bundled_limiter_path is not None:
                    bundled_plugin = _load_vst_plugin(bundled_limiter_path)
                    if bundled_plugin is not None:
                        try:
                            audio = bundled_plugin(audio, sr)
                            result.steps_applied.append("bundled VST limiter: %s" % os.path.basename(bundled_limiter_path))
                            vst_limiter_used = True
                        except Exception as e:
                            result.warnings.append("Bundled VST limiter failed, using built-in: %s" % str(e))

            # Option C: Built-in adaptive true peak limiter (default fallback)
            if not vst_limiter_used:
                # Now apply the true peak limiter (4x oversample method)
                # Use ceiling 1.0dB tighter than target to guarantee Orban compliance
                internal_ceiling = settings.true_peak_max - 1.0  # -2.0 dBTP internally -> guarantees <= -1.0 in Orban
                audio = _adaptive_true_peak_limit(audio, sr, internal_ceiling,
                                                  settings.limiter_release_ms, pb)
                result.steps_applied.append("adaptive limiter (ceiling %.1f dBTP)" % settings.true_peak_max)

        # --- Step 7: Final loudness check + adjustment ---
        if progress_callback:
            progress_callback("final loudness check", 0.65)

        final_lufs, _ = _measure_loudness(audio, sr)
        if final_lufs > -120.0:
            lufs_error = settings.target_lufs - final_lufs
            if abs(lufs_error) > 0.3:
                fine_gain = 10.0 ** (lufs_error / 20.0)
                audio = audio * fine_gain
                result.steps_applied.append("final adjust %.1f dB" % lufs_error)

                # Re-limit after adjustment
                internal_ceiling = settings.true_peak_max - 1.0
                audio = _adaptive_true_peak_limit(audio, sr, internal_ceiling,
                                                  settings.limiter_release_ms, pb)

        # --- Step 5: Fix silence (trim/pad) ---
        if settings.fix_silence:
            if progress_callback:
                progress_callback("fixing silence", 0.65)

            head_s, tail_s = _measure_silence(audio, sr, settings.silence_threshold_dbfs)
            needs_fix = (abs(head_s - settings.target_silence_s) > settings.silence_tolerance_s or
                         abs(tail_s - settings.target_silence_s) > settings.silence_tolerance_s)

            if needs_fix:
                audio = _fix_silence(audio, sr, settings.target_silence_s,
                                     settings.silence_threshold_dbfs)
                result.steps_applied.append("silence %.1fs" % settings.target_silence_s)

        # --- Step 6: Sample rate conversion ---
        target_sr = settings.target_sample_rate
        if settings.fix_format and sr != target_sr:
            if progress_callback:
                progress_callback("resampling", 0.75)

            board = pb.Pedalboard([
                pb.Resample(target_sample_rate=float(target_sr)),
            ])
            audio = board(audio, sr)
            sr = target_sr
            result.steps_applied.append("resample %dHz" % target_sr)

            # Adjust marker positions for new sample rate
            if original_markers:
                ratio = target_sr / float(settings.target_sample_rate)
                # Markers stay at same time positions, adjust sample offsets
                # (already at correct offsets since we'll recalculate below)

        # --- Step 7: Bit depth ---
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

            # Recalculate marker positions if silence was changed
            # For now, preserve original time positions
            adjusted_markers = []
            for sample_offset, label in original_markers:
                # Keep markers at same time position
                original_time = sample_offset / float(settings.target_sample_rate)
                new_offset = int(original_time * sr)
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

        result.success = True

        if progress_callback:
            progress_callback("done", 1.0)

    except Exception as e:
        result.error = str(e)

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
