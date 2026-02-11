"""Unit tests for shared two-stage language detection."""

from __future__ import annotations

from app.pipelines.ortps.language_profiles import (
    ENGLISH_LABEL,
    LINGUA_LANGUAGES,
    NON_ENGLISH_LABEL,
    ROMANIZED_MARKER_MIN_HITS,
    ROMANIZED_NON_ENGLISH_MARKERS,
    SCRIPT_FILTER_PATTERN,
    TARGET_LANGUAGE,
)
from app.pipelines.shared.language_detection import TwoStageLanguageDetector


def build_detector(threshold: float = 0.85) -> TwoStageLanguageDetector:
    return TwoStageLanguageDetector(
        confidence_threshold=threshold,
        script_pattern=SCRIPT_FILTER_PATTERN,
        lingua_languages=LINGUA_LANGUAGES,
        target_language=TARGET_LANGUAGE,
        en_label=ENGLISH_LABEL,
        non_en_label=NON_ENGLISH_LABEL,
        non_target_markers=ROMANIZED_NON_ENGLISH_MARKERS,
        marker_min_hits=ROMANIZED_MARKER_MIN_HITS,
    )


def test_detect_batch_expected_labels_and_stats():
    detector = build_detector()
    texts = [
        "Please process my grievance urgently.",
        "ମୋ ନାମ ରାସନ କାର୍ଡ",
        "मेरा राशन कार्ड",
        None,
        "mu mora paribar pain sahayata darkar",
    ]

    labels, stats = detector.detect_batch(texts)

    assert labels[0] == "en"
    assert labels[1] == "non_en"
    assert labels[2] == "non_en"
    assert labels[3] is None
    assert labels[4] == "non_en"

    assert stats == {
        "script_filtered": 2,
        "lingua_high_conf": 1,
        "lingua_low_conf": 1,
        "null": 1,
    }


def test_custom_labels_are_applied():
    detector = TwoStageLanguageDetector(
        confidence_threshold=0.85,
        script_pattern=SCRIPT_FILTER_PATTERN,
        lingua_languages=LINGUA_LANGUAGES,
        target_language=TARGET_LANGUAGE,
        en_label="english",
        non_en_label="other",
    )

    labels, _ = detector.detect_batch(
        ["This is clearly English text.", "मेरा राशन कार्ड"]
    )

    assert labels == ["english", "other"]
