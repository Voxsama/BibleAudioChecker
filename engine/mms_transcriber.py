"""Meta MMS Assamese CTC transcription with frame-derived word timestamps."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .mms_pack import is_mms_pack_installed, mms_pack_dir


MMS_SAMPLE_RATE = 16000
MMS_CORE_CHUNK_S = 20.0
MMS_CONTEXT_S = 1.0
MMS_ACOUSTIC_WORD_GAP_S = 0.45
_MODEL_CACHE: Dict[str, Tuple[object, object, object]] = {}


@dataclass
class MMSTranscription:
    words: List[Dict] = field(default_factory=list)
    characters: List[Dict] = field(default_factory=list)
    transcript: str = ""
    mean_token_confidence: float = 0.0
    token_count: int = 0
    error: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.words) and not self.error


def mms_runtime_available() -> bool:
    try:
        import soundfile  # noqa: F401
        import torch  # noqa: F401
        from scipy.signal import resample_poly  # noqa: F401
        from transformers import AutoProcessor, Wav2Vec2ForCTC  # noqa: F401
        return True
    except ImportError:
        return False


def _load_model(root: str):
    cached = _MODEL_CACHE.get(root)
    if cached is not None:
        return cached

    import torch
    from transformers import AutoProcessor, Wav2Vec2ForCTC

    processor = AutoProcessor.from_pretrained(
        root, target_lang="asm", local_files_only=True)
    model = Wav2Vec2ForCTC.from_pretrained(
        root, target_lang="asm", local_files_only=True,
        ignore_mismatched_sizes=True, use_safetensors=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    model.eval()
    cached = (processor, model, device)
    _MODEL_CACHE[root] = cached
    return cached


def _read_resampled_window(
        wav_path: str, start_s: float, end_s: float) -> Tuple[object, float]:
    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly

    with sf.SoundFile(wav_path) as stream:
        sample_rate = int(stream.samplerate)
        start_frame = max(0, int(math.floor(start_s * sample_rate)))
        end_frame = min(
            len(stream), int(math.ceil(end_s * sample_rate)))
        stream.seek(start_frame)
        audio = stream.read(
            max(0, end_frame - start_frame),
            dtype="float32", always_2d=True)
    if audio.size == 0:
        return np.zeros(0, dtype=np.float32), start_frame / float(sample_rate)
    mono = np.mean(audio, axis=1, dtype=np.float32)
    if sample_rate != MMS_SAMPLE_RATE:
        divisor = math.gcd(sample_rate, MMS_SAMPLE_RATE)
        mono = resample_poly(
            mono, MMS_SAMPLE_RATE // divisor,
            sample_rate // divisor).astype(np.float32, copy=False)
    return mono, start_frame / float(sample_rate)


def _duration(wav_path: str) -> float:
    import soundfile as sf
    info = sf.info(wav_path)
    if not info.samplerate:
        return 0.0
    return float(info.frames) / float(info.samplerate)


def transcribe_assamese_mms(
        wav_path: str, pack_root: str = "",
        progress_callback: Optional[Callable[[str, float], None]] = None
        ) -> MMSTranscription:
    """Return a greedy Assamese transcript with CTC frame timestamps.

    Each 20-second core has one second of acoustic context on either side.
    Only frames inside the core are retained, preventing duplicate text while
    avoiding the worst Wav2Vec2 edge effects.
    """
    result = MMSTranscription()
    root = os.path.abspath(pack_root or mms_pack_dir())
    if not os.path.isfile(wav_path):
        result.error = "WAV file not found: %s" % wav_path
        return result
    if not mms_runtime_available():
        result.error = (
            "Meta MMS runtime is unavailable. Install transformers, "
            "safetensors, scipy, and soundfile.")
        return result
    if not is_mms_pack_installed(root):
        result.error = (
            "The Meta MMS Assamese Precision Pack is not installed or has "
            "not passed checksum verification.")
        return result

    try:
        if progress_callback:
            progress_callback("loading Meta MMS Assamese", 0.08)
        processor, model, device = _load_model(root)
        tokenizer = processor.tokenizer
        blank_id = int(
            model.config.pad_token_id
            if model.config.pad_token_id is not None
            else tokenizer.pad_token_id)
        delimiter = tokenizer.word_delimiter_token or "|"
        unknown = tokenizer.unk_token

        import torch

        duration_s = _duration(wav_path)
        if duration_s <= 0:
            result.error = "The WAV file has no readable audio."
            return result
        core_count = max(1, int(math.ceil(
            duration_s / MMS_CORE_CHUNK_S)))
        events: List[Tuple[str, float, float, float]] = []
        previous_id = blank_id

        for core_index in range(core_count):
            core_start = core_index * MMS_CORE_CHUNK_S
            core_end = min(
                duration_s, core_start + MMS_CORE_CHUNK_S)
            window_start = max(0.0, core_start - MMS_CONTEXT_S)
            window_end = min(duration_s, core_end + MMS_CONTEXT_S)
            audio, actual_start = _read_resampled_window(
                wav_path, window_start, window_end)
            if len(audio) == 0:
                continue
            inputs = processor(
                audio, sampling_rate=MMS_SAMPLE_RATE,
                return_tensors="pt")
            input_values = inputs.input_values.to(device)
            attention_mask = getattr(inputs, "attention_mask", None)
            if attention_mask is not None:
                attention_mask = attention_mask.to(device)
            with torch.inference_mode():
                output = model(
                    input_values,
                    attention_mask=attention_mask)
                probabilities = torch.softmax(
                    output.logits[0].float(), dim=-1)
                confidence, token_ids = probabilities.max(dim=-1)
            token_ids = token_ids.cpu().tolist()
            confidence = confidence.cpu().tolist()
            frame_count = max(1, len(token_ids))
            window_duration = len(audio) / float(MMS_SAMPLE_RATE)
            frame_duration = window_duration / float(frame_count)

            for frame_index, token_id in enumerate(token_ids):
                frame_start = (
                    actual_start + frame_index * frame_duration)
                if frame_start < core_start or frame_start >= core_end:
                    continue
                if token_id == blank_id:
                    previous_id = blank_id
                    continue
                if token_id == previous_id:
                    continue
                token = tokenizer.convert_ids_to_tokens(int(token_id))
                previous_id = int(token_id)
                if not token or token == unknown:
                    continue
                events.append((
                    token, frame_start, frame_start + frame_duration,
                    float(confidence[frame_index])))

            if progress_callback:
                fraction = (core_index + 1) / float(core_count)
                progress_callback(
                    "Meta MMS Assamese %d/%d" %
                    (core_index + 1, core_count),
                    0.10 + 0.52 * fraction)

        words: List[Dict] = []
        current_tokens: List[str] = []
        current_confidences: List[float] = []
        word_start = 0.0
        word_end = 0.0
        all_confidences: List[float] = []

        def finish_word() -> None:
            nonlocal current_tokens, current_confidences
            if not current_tokens:
                return
            text = "".join(current_tokens).strip()
            if text:
                words.append({
                    "start": word_start,
                    "end": word_end,
                    "word": text,
                    "confidence": (
                        sum(current_confidences) /
                        max(1, len(current_confidences))),
                    "engine": "meta-mms-asm",
                })
            current_tokens = []
            current_confidences = []

        previous_character_end = 0.0
        for token, start, end, confidence_value in events:
            if (
                    token == delimiter or
                    (current_tokens and
                     start - previous_character_end >=
                     MMS_ACOUSTIC_WORD_GAP_S)):
                finish_word()
                if token == delimiter:
                    previous_character_end = end
                    continue
            if not current_tokens:
                word_start = start
            word_end = end
            current_tokens.append(token)
            current_confidences.append(confidence_value)
            all_confidences.append(confidence_value)
            result.characters.append({
                "character": token,
                "start": start,
                "end": end,
                "confidence": confidence_value,
            })
            previous_character_end = end
        finish_word()

        result.words = words
        result.transcript = " ".join(
            str(word["word"]) for word in words)
        result.token_count = len(all_confidences)
        result.mean_token_confidence = (
            sum(all_confidences) / len(all_confidences)
            if all_confidences else 0.0)
        if not result.words:
            result.error = (
                "Meta MMS did not produce a usable Assamese transcript.")
        return result
    except Exception as exc:
        result.error = "Meta MMS Assamese transcription failed: %s" % exc
        return result
