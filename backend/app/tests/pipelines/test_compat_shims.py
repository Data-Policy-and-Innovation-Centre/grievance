"""Tests for backward-compatibility shims in app.pipelines.ortps."""

from __future__ import annotations

from app.pipelines.ortps.analyzers import TopicAnalyzer as ShimTopicAnalyzer
from app.pipelines.ortps.detectors import ImprovedLanguageDetector
from app.pipelines.ortps.topic_profiles import (
    ORTPS_STOPWORDS,
    get_ortps_topic_model_params,
)
from app.pipelines.shared.topic_modeling.bertopic_engine import TopicAnalyzer as SharedTopicAnalyzer


def test_improved_language_detector_shim_defaults_and_labels():
    detector = ImprovedLanguageDetector()
    assert detector.threshold == 0.85

    labels, _ = detector.detect_batch(
        [
            "Please process this complaint quickly and resolve the issue.",
            "मेरा राशन कार्ड",
        ]
    )
    assert labels[1] == "non_en"


def test_topic_analyzer_shim_uses_ortps_profile():
    analyzer = ShimTopicAnalyzer(category="Certificates", n_samples=100)

    assert isinstance(analyzer, SharedTopicAnalyzer)
    assert analyzer.custom_stopwords == ORTPS_STOPWORDS
    assert analyzer.params_resolver is get_ortps_topic_model_params

