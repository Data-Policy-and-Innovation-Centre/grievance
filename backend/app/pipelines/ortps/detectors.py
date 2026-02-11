"""Backward-compatible ORTPS detector shim over shared language detection."""

from __future__ import annotations

from app.pipelines.ortps.language_profiles import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    ENGLISH_LABEL,
    LINGUA_LANGUAGES,
    NON_ENGLISH_LABEL,
    ROMANIZED_MARKER_MIN_HITS,
    ROMANIZED_NON_ENGLISH_MARKERS,
    SCRIPT_FILTER_PATTERN,
    TARGET_LANGUAGE,
)
from app.pipelines.shared.language_detection import TwoStageLanguageDetector


class ImprovedLanguageDetector(TwoStageLanguageDetector):
    """Compatibility wrapper preserving historical ORTPS detector interface."""

    def __init__(self, confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD):
        super().__init__(
            confidence_threshold=confidence_threshold,
            script_pattern=SCRIPT_FILTER_PATTERN,
            lingua_languages=LINGUA_LANGUAGES,
            target_language=TARGET_LANGUAGE,
            en_label=ENGLISH_LABEL,
            non_en_label=NON_ENGLISH_LABEL,
            non_target_markers=ROMANIZED_NON_ENGLISH_MARKERS,
            marker_min_hits=ROMANIZED_MARKER_MIN_HITS,
        )


__all__ = ["ImprovedLanguageDetector"]
