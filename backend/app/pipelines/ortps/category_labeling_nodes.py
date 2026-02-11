"""Hamilton nodes for ORTPS category labeling (keyword + embedding hybrid)."""

from __future__ import annotations

from typing import Literal

import polars as pl
from loguru import logger

from app.pipelines.ortps.labelers import CategoryLabeler
from app.pipelines.ortps.validation import CATEGORY_LABELING_CONTRACT


def category_labeler(
    embedding_model_name: str,
    embedding_threshold: float,
    embedding_device: str | None,
    embedding_strategy: Literal["label_only", "keyword_only", "combined"] = "label_only",
    keyword_weight: float = 1.0,
    label_weight: float = 0.5,
) -> CategoryLabeler:
    """Construct the CategoryLabeler instance."""
    logger.info(
        f"Initializing CategoryLabeler "
        f"(model={embedding_model_name}, threshold={embedding_threshold}, "
        f"device={embedding_device}, strategy={embedding_strategy})"
    )
    return CategoryLabeler(
        model_name=embedding_model_name,
        similarity_threshold=embedding_threshold,
        device=embedding_device,
        embedding_strategy=embedding_strategy,
        keyword_weight=keyword_weight,
        label_weight=label_weight,
    )


def df_labeled(
    df_english: pl.DataFrame,
    category_labeler: CategoryLabeler,
    labeling_method: Literal["keyword", "embedding", "hybrid"],
    text_col: str = "grievance",
    embedding_strategy: Literal["label_only", "keyword_only", "combined"] = "label_only",
) -> pl.DataFrame:
    """Apply category labels to the English-filtered DataFrame."""
    logger.info(
        f"Running category labeling "
        f"(method={labeling_method}, embedding_strategy={embedding_strategy})"
    )
    return category_labeler.label_dataframe(
        df_english,
        text_col=text_col,
        method=labeling_method,
        embedding_strategy=embedding_strategy,
    )


def category_distribution(df_labeled: pl.DataFrame) -> pl.DataFrame:
    """Compute category value counts for logging and validation."""
    dist = df_labeled["ortps_category"].value_counts().sort("ortps_category")
    logger.info("Category distribution:")
    for row in dist.iter_rows(named=True):
        cat = row["ortps_category"]
        count = row["count"]
        logger.info(f"  {cat}: {count:,}")
    return dist


def method_distribution(df_labeled: pl.DataFrame) -> pl.DataFrame:
    """Compute labeling method value counts."""
    dist = df_labeled["ortps_method"].value_counts().sort("ortps_method")
    logger.info("Labeling method distribution:")
    for row in dist.iter_rows(named=True):
        method = row["ortps_method"]
        count = row["count"]
        logger.info(f"  {method}: {count:,}")
    return dist


# ── Validation node ──────────────────────────────────────────────────


def df_labeled__validated(df_labeled: pl.DataFrame) -> pl.DataFrame:
    """Validate the category-labeled DataFrame."""
    return CATEGORY_LABELING_CONTRACT.check_or_warn(
        df_labeled, "category_labeling"
    )
