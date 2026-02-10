"""Unit tests for language detection Hamilton nodes."""

import polars as pl
import pytest

from app.pipelines.ortps import lang_detection_nodes
from app.pipelines.ortps.validation import LANG_DETECTION_CONTRACT


class TestLanguageDetector:
    def test_returns_detector_instance(self):
        detector = lang_detection_nodes.language_detector(lingua_threshold=0.85)
        assert detector.threshold == 0.85
        assert hasattr(detector, "detect_batch")

    def test_custom_threshold(self):
        detector = lang_detection_nodes.language_detector(lingua_threshold=0.5)
        assert detector.threshold == 0.5


class TestRawTexts:
    def test_extracts_text_list(self, sample_raw_df):
        texts = lang_detection_nodes.raw_texts(sample_raw_df, text_col="grievance")
        assert isinstance(texts, list)
        assert len(texts) == len(sample_raw_df)

    def test_preserves_nulls(self, sample_raw_df):
        texts = lang_detection_nodes.raw_texts(sample_raw_df, text_col="grievance")
        assert None in texts


class TestLanguageLabelsAndStats:
    def test_returns_dict_with_labels_and_stats(self, sample_raw_df):
        detector = lang_detection_nodes.language_detector(lingua_threshold=0.85)
        texts = lang_detection_nodes.raw_texts(sample_raw_df, text_col="grievance")
        result = lang_detection_nodes.language_labels_and_stats(detector, texts)

        assert "labels" in result
        assert "stats" in result
        assert len(result["labels"]) == len(texts)

    def test_detects_non_latin_scripts(self, sample_raw_df):
        detector = lang_detection_nodes.language_detector(lingua_threshold=0.85)
        texts = lang_detection_nodes.raw_texts(sample_raw_df, text_col="grievance")
        result = lang_detection_nodes.language_labels_and_stats(detector, texts)

        # Odia and Devanagari texts should be "non_en"
        assert result["labels"][3] == "non_en"  # Odia
        assert result["labels"][4] == "non_en"  # Devanagari

    def test_null_text_produces_null_label(self, sample_raw_df):
        detector = lang_detection_nodes.language_detector(lingua_threshold=0.85)
        texts = lang_detection_nodes.raw_texts(sample_raw_df, text_col="grievance")
        result = lang_detection_nodes.language_labels_and_stats(detector, texts)

        assert result["labels"][5] is None  # The null text

    def test_detects_romanized_odia_as_non_english(self):
        df = pl.DataFrame({
            "grievance": ["mu mora paribar pain sahayata darkar"]
        })
        detector = lang_detection_nodes.language_detector(lingua_threshold=0.85)
        texts = lang_detection_nodes.raw_texts(df, text_col="grievance")
        result = lang_detection_nodes.language_labels_and_stats(detector, texts)

        assert result["labels"][0] == "non_en"


class TestDfWithLanguage:
    def test_adds_grievance_lang_column(self, sample_raw_df):
        detector = lang_detection_nodes.language_detector(lingua_threshold=0.85)
        texts = lang_detection_nodes.raw_texts(sample_raw_df, text_col="grievance")
        result = lang_detection_nodes.language_labels_and_stats(detector, texts)
        df = lang_detection_nodes.df_with_language(sample_raw_df, result)

        assert "grievance_lang" in df.columns
        assert len(df) == len(sample_raw_df)

    def test_passes_validation_contract(self, sample_raw_df):
        detector = lang_detection_nodes.language_detector(lingua_threshold=0.85)
        texts = lang_detection_nodes.raw_texts(sample_raw_df, text_col="grievance")
        result = lang_detection_nodes.language_labels_and_stats(detector, texts)
        df = lang_detection_nodes.df_with_language(sample_raw_df, result)

        violations = LANG_DETECTION_CONTRACT.validate(df)
        assert violations == [], f"Validation violations: {violations}"


class TestDfEnglish:
    def test_filters_to_english_only(self, sample_raw_df):
        detector = lang_detection_nodes.language_detector(lingua_threshold=0.85)
        texts = lang_detection_nodes.raw_texts(sample_raw_df, text_col="grievance")
        result = lang_detection_nodes.language_labels_and_stats(detector, texts)
        df_lang = lang_detection_nodes.df_with_language(sample_raw_df, result)
        df_en = lang_detection_nodes.df_english(df_lang)

        assert all(v == "en" for v in df_en["grievance_lang"].to_list())
        assert len(df_en) < len(sample_raw_df)
