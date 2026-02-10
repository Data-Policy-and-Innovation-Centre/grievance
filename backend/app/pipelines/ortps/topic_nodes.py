"""Hamilton nodes for BERTopic topic modeling."""

from __future__ import annotations

import numpy as np
import polars as pl
from loguru import logger

from app.pipelines.ortps.analyzers import TopicAnalyzer
from app.pipelines.ortps.labelers import CategoryLabeler


def filtered_data(
    df_labeled: pl.DataFrame,
    min_text_length: int = 50,
) -> pl.DataFrame:
    """Filter to ORTPS-labeled complaints with sufficient text.

    Args:
        df_labeled: Input DataFrame with ortps_category column
        min_text_length: Minimum character length for grievance text

    Returns:
        Filtered DataFrame
    """
    df = df_labeled.filter(pl.col("ortps_category").is_not_null())

    # Filter short texts
    df = df.with_columns(
        pl.col("grievance").str.len_chars().alias("_text_len")
    ).filter(pl.col("_text_len") >= min_text_length).drop("_text_len")

    logger.info(f"Filtered to {len(df):,} ORTPS-labeled complaints (>={min_text_length} chars)")

    return df


def category_splits(filtered_data: pl.DataFrame) -> dict[str, pl.DataFrame]:
    """Split DataFrame by ORTPS category.

    Args:
        filtered_data: Filtered DataFrame with ortps_category column

    Returns:
        Dict mapping category name -> DataFrame
    """
    categories = filtered_data["ortps_category"].unique().sort().to_list()
    splits = {}

    for cat in categories:
        df_cat = filtered_data.filter(pl.col("ortps_category") == cat)
        splits[cat] = df_cat
        logger.info(f"  {cat}: {len(df_cat):,} complaints")

    return splits


def cached_embeddings(
    category_splits: dict[str, pl.DataFrame],
    category_labeler: CategoryLabeler,
) -> dict[str, np.ndarray]:
    """Load or compute embeddings for each category.

    Reuses CategoryLabeler's embedding cache for efficiency.

    Args:
        category_splits: Dict of category -> DataFrame
        category_labeler: CategoryLabeler instance with embedding cache

    Returns:
        Dict mapping category name -> embeddings array
    """
    embeddings_dict = {}

    for cat, df_cat in category_splits.items():
        texts = df_cat["grievance"].to_list()

        # Try to load from cache
        text_hash = category_labeler._compute_text_hash(texts)
        emb = category_labeler._load_embeddings_cache(text_hash)

        if emb is None:
            logger.info(f"{cat}: No cache found, computing embeddings...")
            emb = category_labeler.model.encode(
                texts,
                normalize_embeddings=True,
                batch_size=256,
                show_progress_bar=True,
            )
            # Save to cache for future use
            category_labeler._save_embeddings_cache(emb, texts, text_hash)
        else:
            logger.info(f"{cat}: Loaded embeddings from cache")

        embeddings_dict[cat] = emb

    return embeddings_dict


def topic_models(
    category_splits: dict[str, pl.DataFrame],
    cached_embeddings: dict[str, np.ndarray],
) -> dict[str, TopicAnalyzer]:
    """Fit BERTopic model for each category.

    Args:
        category_splits: Dict of category -> DataFrame
        cached_embeddings: Dict of category -> embeddings

    Returns:
        Dict mapping category name -> fitted TopicAnalyzer
    """
    models = {}

    for cat, df_cat in category_splits.items():
        texts = df_cat["grievance"].to_list()
        emb = cached_embeddings[cat]

        # Create and fit analyzer
        analyzer = TopicAnalyzer(cat, len(texts))
        analyzer.fit(texts, emb)

        models[cat] = analyzer

    return models


def topic_assignments(
    category_splits: dict[str, pl.DataFrame],
    topic_models: dict[str, TopicAnalyzer],
) -> pl.DataFrame:
    """Combine all category DataFrames with topic assignments.

    Args:
        category_splits: Dict of category -> DataFrame
        topic_models: Dict of category -> fitted TopicAnalyzer

    Returns:
        Combined DataFrame with topic_id column added
    """
    dfs = []

    for cat, df_cat in category_splits.items():
        analyzer = topic_models[cat]

        if analyzer._topics is None:
            raise ValueError(f"{cat}: Model not fitted")

        # Add topic assignments
        df_with_topics = df_cat.with_columns(
            pl.Series("topic_id", analyzer._topics, dtype=pl.Int32)
        )
        dfs.append(df_with_topics)

    result = pl.concat(dfs)
    logger.info(f"Combined {len(result):,} complaints with topic assignments")

    return result


def topic_summary(
    topic_models: dict[str, TopicAnalyzer],
) -> pl.DataFrame:
    """Create cross-category summary statistics.

    Args:
        topic_models: Dict of category -> fitted TopicAnalyzer

    Returns:
        DataFrame with summary stats per category
    """
    rows = []

    for cat, analyzer in topic_models.items():
        if analyzer._topics is None:
            continue

        n_topics = len(set(analyzer._topics)) - (1 if -1 in analyzer._topics else 0)
        outlier_count = (np.array(analyzer._topics) == -1).sum()
        total_count = len(analyzer._topics)
        coverage_pct = (total_count - outlier_count) / total_count * 100

        rows.append({
            "category": cat,
            "total_complaints": total_count,
            "n_topics": n_topics,
            "outliers": outlier_count,
            "coverage_pct": round(coverage_pct, 1),
        })

    return pl.DataFrame(rows)
