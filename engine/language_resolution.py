"""Resolve closely related Whisper language guesses with script evidence."""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

from .transcriber import LanguageDetectionResult


ASSAMESE_DISTINCTIVE = frozenset(("ৰ", "ৱ"))


def assamese_script_evidence(text: str) -> Optional[dict]:
    """Return strong Assamese evidence from Bengali-Assamese script text.

    Bengali and Assamese share a Unicode block, but Assamese uses distinctive
    letters such as RA WITH MIDDLE DIAGONAL (ৰ) and RA WITH LOWER DIAGONAL
    (ৱ). Requiring repeated evidence avoids changing a language based on a
    stray glyph.
    """
    value = text or ""
    bengali_block_count = sum(
        1 for character in value if "\u0980" <= character <= "\u09ff")
    distinctive_count = sum(
        1 for character in value if character in ASSAMESE_DISTINCTIVE)
    distinctive_types = {
        character for character in value
        if character in ASSAMESE_DISTINCTIVE}
    if bengali_block_count < 20:
        return None
    if distinctive_count < 2 and len(distinctive_types) < 2:
        return None
    ratio = distinctive_count / float(max(1, bengali_block_count))
    confidence = min(0.99, 0.90 + min(0.09, ratio * 3.0))
    return {
        "code": "as",
        "name": "Assamese",
        "confidence": confidence,
        "distinctive_count": distinctive_count,
        "characters": "".join(sorted(distinctive_types)),
    }


def resolve_language_with_script(
        detection: LanguageDetectionResult,
        script_text: str) -> LanguageDetectionResult:
    """Combine raw audio detection with high-specificity script evidence."""
    if detection is None or detection.error:
        return detection
    evidence = assamese_script_evidence(script_text)
    if not evidence:
        return detection

    raw_code = detection.raw_language or detection.language
    raw_name = detection.raw_language_name or detection.language_name
    raw_confidence = (
        detection.raw_confidence
        if detection.raw_language else detection.confidence)
    detail = (
        "The loaded PDF chapter contains %d Assamese-specific character(s) "
        "(%s)." %
        (evidence["distinctive_count"],
         evidence["characters"] or "ৰ/ৱ"))

    if raw_code in ("as", "bn"):
        return replace(
            detection,
            language="as",
            language_name="Assamese",
            confidence=max(
                float(evidence["confidence"]),
                float(detection.confidence)),
            raw_language=raw_code,
            raw_language_name=raw_name,
            raw_confidence=float(raw_confidence),
            resolution_source="script-confirmed",
            resolution_note=(
                detail + " Whisper commonly groups Assamese speech with "
                "closely related Bengali."),
        )

    return replace(
        detection,
        raw_language=raw_code,
        raw_language_name=raw_name,
        raw_confidence=float(raw_confidence),
        resolution_source="script-conflict",
        resolution_note=(
            detail + " The audio model instead detected %s; verify that the "
            "selected audio and PDF belong to the same language." %
            (raw_name or raw_code or "another language")),
    )
