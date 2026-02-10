"""Hamilton nodes for language detection and English text filtering."""

from __future__ import annotations

import polars as pl
from loguru import logger

from app.pipelines.ortps.detectors import ImprovedLanguageDetector
from app.pipelines.ortps.validation import (
    ENGLISH_FILTER_CONTRACT,
    LANG_DETECTION_CONTRACT,
)


def language_detector(lingua_threshold: float) -> ImprovedLanguageDetector:
    """Construct the language detector instance."""
    logger.info(f"Initializing language detector (threshold={lingua_threshold})")
    return ImprovedLanguageDetector(confidence_threshold=lingua_threshold)


def raw_texts(raw_df: pl.DataFrame, text_col: str) -> list[str | None]:
    """Extract raw text list from the input DataFrame."""
    return raw_df[text_col].to_list()


def language_labels_and_stats(
    language_detector: ImprovedLanguageDetector,
    raw_texts: list[str | None],
) -> dict:
    """
    Run batch language detection.

    Returns dict with keys "labels" and "stats".
    """
    labels, stats = language_detector.detect_batch(raw_texts)
    logger.info("Language detection statistics:")
    for method, count in stats.items():
        logger.info(f"  {method}: {count:,}")
    return {"labels": labels, "stats": stats}


def lang_detection_stats(language_labels_and_stats: dict) -> dict[str, int]:
    """Extract the stats dict for downstream logging/validation."""
    return language_labels_and_stats["stats"]


def df_with_language(
    raw_df: pl.DataFrame,
    language_labels_and_stats: dict,
) -> pl.DataFrame:
    """Attach grievance_lang column to the raw DataFrame."""
    labels = language_labels_and_stats["labels"]
    return raw_df.with_columns(pl.Series("grievance_lang", labels))


def df_english(df_with_language: pl.DataFrame) -> pl.DataFrame:
    """Filter to English-only grievances."""
    df_en = df_with_language.filter(pl.col("grievance_lang") == "en")
    total = len(df_with_language)
    en_count = len(df_en)
    logger.info(
        f"English complaints: {en_count:,} / {total:,} "
        f"({en_count / total * 100:.1f}%)"
    )
    return df_en


# ── Validation nodes ─────────────────────────────────────────────────


def df_with_language__validated(df_with_language: pl.DataFrame) -> pl.DataFrame:
    """Validate the language-annotated DataFrame."""
    return LANG_DETECTION_CONTRACT.check_or_warn(
        df_with_language, "lang_detection"
    )


def df_english__validated(df_english: pl.DataFrame) -> pl.DataFrame:
    """Validate the English-filtered DataFrame."""
    return ENGLISH_FILTER_CONTRACT.check_or_warn(
        df_english, "english_filter"
    )
