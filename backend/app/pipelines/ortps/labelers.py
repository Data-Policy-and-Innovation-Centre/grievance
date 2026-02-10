"""Category labeling utilities for ORTPS pipeline."""

from __future__ import annotations

import hashlib
import pickle
from pathlib import Path
from typing import Literal

import numpy as np
import polars as pl
from loguru import logger
from sentence_transformers import SentenceTransformer

from app.config import directories


class CategoryLabeler:
    """
    Hybrid category labeling: keyword matching + embedding similarity.

    Categories:
    - Caste certificate
    - Income certificate
    - Scholarship
    - Ration Card
    """

    # Category-specific keywords (case-insensitive)
    CATEGORY_KEYWORDS = {
        "Caste certificate": [
            "caste certificate", "sc certificate", "st certificate",
            "obc certificate", "sebc certificate", "creamy layer",
            "caste validity", "community certificate"
        ],
        "Income certificate": [
            "income certificate", "annual income", "income proof",
            "income verification", "family income"
        ],
        "Scholarship": [
            "scholarship", "post matric", "pre matric", "oasis",
            "national scholarship", "merit scholarship", "sc scholarship",
            "st scholarship", "minority scholarship"
        ],
        "Ration Card": [
            "ration card", "food security", "aay card", "bpl card",
            "phh card", "antyodaya", "priority household", "pds card"
        ]
    }

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        similarity_threshold: float = 0.45,
        device: str | None = None
    ):
        """
        Initialize category labeler.

        Parameters
        ----------
        model_name : str
            SentenceTransformer model name
        similarity_threshold : float
            Minimum cosine similarity for embedding match
        device : str | None
            Device for model ("mps", "cuda", "cpu", or None for auto)
        """
        self.model_name = model_name
        self.similarity_threshold = similarity_threshold
        self.device = device
        self._model = None  # Lazy loading

    @property
    def model(self):
        """Lazy load the SentenceTransformer model."""
        if self._model is None:
            # Auto-detect device if not specified
            device = self.device
            if device is None:
                import torch
                if torch.backends.mps.is_available():
                    device = "mps"
                elif torch.cuda.is_available():
                    device = "cuda"
                else:
                    device = "cpu"

            logger.info(f"Loading SentenceTransformer on device: {device}")
            self._model = SentenceTransformer(self.model_name, device=device)

        return self._model

    def label_dataframe(
        self,
        df: pl.DataFrame,
        text_col: str = "grievance",
        method: Literal["keyword", "embedding", "hybrid"] = "hybrid"
    ) -> pl.DataFrame:
        """
        Add category label columns to DataFrame.

        Parameters
        ----------
        df : pl.DataFrame
            Input DataFrame with text column
        text_col : str
            Name of text column to analyze
        method : {"keyword", "embedding", "hybrid"}
            Labeling method to use

        Returns
        -------
        pl.DataFrame
            DataFrame with new columns:
            - ortps_category: Matched category name
            - ortps_method: Detection method (keyword/embedding/none)
            - ortps_confidence: Similarity score (for embedding matches)
        """
        if method in ["keyword", "hybrid"]:
            df = self._add_keyword_labels(df, text_col)

        if method in ["embedding", "hybrid"]:
            # Only embed texts without keyword matches
            if method == "hybrid":
                mask = pl.col("ortps_category").is_null()
                df_to_embed = df.filter(mask)

                if len(df_to_embed) > 0:
                    logger.info(
                        f"Running embedding on {len(df_to_embed):,} "
                        f"unmatched texts ({len(df_to_embed)/len(df)*100:.1f}%)"
                    )
                    df = self._add_embedding_labels(df, df_to_embed, text_col)
            else:
                logger.info(f"Running embedding on all {len(df):,} texts")
                df = self._add_embedding_labels(df, df, text_col)

        return df

    def _add_keyword_labels(
        self,
        df: pl.DataFrame,
        text_col: str
    ) -> pl.DataFrame:
        """Pattern matching using Polars expressions."""
        # Create conditions for each category
        conditions = []
        for category, keywords in self.CATEGORY_KEYWORDS.items():
            # Combine all keywords for this category with OR
            keyword_conditions = [
                pl.col(text_col).str.to_lowercase().str.contains(kw.lower())
                for kw in keywords
            ]

            # Start with first condition
            combined = keyword_conditions[0]
            for cond in keyword_conditions[1:]:
                combined = combined | cond

            conditions.append((combined, category))

        # Build cascading when/then/otherwise chain
        category_expr = pl.lit(None)
        for condition, category in reversed(conditions):
            category_expr = pl.when(condition).then(pl.lit(category)).otherwise(category_expr)

        # Add columns
        df = df.with_columns([
            category_expr.alias("ortps_category"),
            pl.when(category_expr.is_not_null())
            .then(pl.lit("keyword"))
            .otherwise(None)
            .alias("ortps_method"),
            pl.lit(None, dtype=pl.Float64).alias("ortps_confidence")
        ])

        # Log statistics
        matched = df.filter(pl.col("ortps_method") == "keyword")
        logger.info(
            f"Keyword matching: {len(matched):,} texts matched "
            f"({len(matched)/len(df)*100:.1f}%)"
        )

        return df

    def _compute_text_hash(self, texts: list[str]) -> str:
        """Compute hash of texts for cache validation."""
        # Sample first 1000 texts for efficient hashing
        sample = texts[:min(1000, len(texts))]
        text_str = "||".join(str(t) for t in sample)
        return hashlib.md5(text_str.encode()).hexdigest()

    def _get_cache_path(self, text_hash: str) -> Path:
        """Get cache file path in directories.MODELS."""
        # Include model name in cache filename
        model_slug = self.model_name.replace("/", "_").replace("-", "_")
        return directories.MODELS / f"ortps_embeddings_{model_slug}_{text_hash}.pkl"

    def _save_embeddings_cache(
        self,
        embeddings: np.ndarray,
        texts: list[str],
        text_hash: str
    ):
        """Save embeddings to cache."""
        cache_path = self._get_cache_path(text_hash)
        cache_data = {
            "embeddings": embeddings,
            "model_name": self.model_name,
            "text_hash": text_hash,
            "num_texts": len(texts),
            "embedding_dim": embeddings.shape[1]
        }
        with open(cache_path, "wb") as f:
            pickle.dump(cache_data, f, protocol=pickle.HIGHEST_PROTOCOL)
        logger.info(f"Saved embeddings to cache: {cache_path.name}")

    def _load_embeddings_cache(self, text_hash: str) -> np.ndarray | None:
        """Load embeddings from cache if available."""
        cache_path = self._get_cache_path(text_hash)
        if not cache_path.exists():
            return None

        try:
            with open(cache_path, "rb") as f:
                cache_data = pickle.load(f)

            # Validate cache
            if cache_data["model_name"] != self.model_name:
                logger.warning(
                    f"Cache model mismatch: {cache_data['model_name']} != {self.model_name}"
                )
                return None

            if cache_data["text_hash"] != text_hash:
                logger.warning("Cache hash mismatch")
                return None

            logger.info(
                f"Loaded embeddings from cache: {cache_path.name} "
                f"({cache_data['num_texts']:,} texts, dim={cache_data['embedding_dim']})"
            )
            return cache_data["embeddings"]

        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
            return None

    def _add_embedding_labels(
        self,
        df: pl.DataFrame,
        df_to_embed: pl.DataFrame,
        text_col: str
    ) -> pl.DataFrame:
        """Embedding similarity for unmatched texts."""
        # Encode category labels
        categories = list(self.CATEGORY_KEYWORDS.keys())
        logger.info("Encoding category labels...")
        category_emb = self.model.encode(
            categories,
            normalize_embeddings=True,
            show_progress_bar=False
        )

        # Get texts and compute hash
        texts = df_to_embed[text_col].to_list()
        text_hash = self._compute_text_hash(texts)

        # Try to load from cache
        text_emb = self._load_embeddings_cache(text_hash)

        if text_emb is None:
            # Encode texts in batches
            logger.info(f"Encoding {len(texts):,} texts (not in cache)...")
            text_emb = self.model.encode(
                texts,
                normalize_embeddings=True,
                batch_size=256,
                show_progress_bar=True
            )
            # Save to cache
            self._save_embeddings_cache(text_emb, texts, text_hash)
        else:
            logger.info(f"Using cached embeddings for {len(texts):,} texts")

        # Compute similarities
        similarities = np.dot(text_emb, category_emb.T)  # (N, 4)
        max_sims = similarities.max(axis=1)
        max_indices = similarities.argmax(axis=1)

        # Filter by threshold
        above_threshold = max_sims >= self.similarity_threshold

        # Create mapping for above-threshold matches
        embedding_results = []
        for i, (sim, cat_idx, above_thresh) in enumerate(
            zip(max_sims, max_indices, above_threshold)
        ):
            if above_thresh:
                embedding_results.append({
                    "category": categories[cat_idx],
                    "method": "embedding",
                    "confidence": float(sim)
                })
            else:
                embedding_results.append({
                    "category": None,
                    "method": None,
                    "confidence": None
                })

        # Create DataFrame with embedding results
        embedding_df = pl.DataFrame(embedding_results).rename({
            "category": "emb_category",
            "method": "emb_method",
            "confidence": "emb_confidence"
        })

        # Join back to df_to_embed
        df_to_embed = df_to_embed.with_columns(
            pl.int_range(0, pl.len()).alias("_embed_idx")
        )
        embedding_df = embedding_df.with_columns(
            pl.int_range(0, pl.len()).alias("_embed_idx")
        )
        df_to_embed = df_to_embed.join(embedding_df, on="_embed_idx", how="left")

        # Update original columns
        df_to_embed = df_to_embed.with_columns([
            pl.coalesce([pl.col("ortps_category"), pl.col("emb_category")]).alias("ortps_category"),
            pl.coalesce([pl.col("ortps_method"), pl.col("emb_method")]).alias("ortps_method"),
            pl.coalesce([pl.col("ortps_confidence"), pl.col("emb_confidence")]).alias("ortps_confidence")
        ]).drop(["_embed_idx", "emb_category", "emb_method", "emb_confidence"])

        # Merge back with original DataFrame
        # For rows that were embedded, update their values
        if "ortps_category" not in df.columns:
            df = df.with_columns([
                pl.lit(None).alias("ortps_category"),
                pl.lit(None).alias("ortps_method"),
                pl.lit(None, dtype=pl.Float64).alias("ortps_confidence")
            ])

        # Update rows that were processed
        df = df.update(df_to_embed)

        # Log statistics
        matched = above_threshold.sum()
        logger.info(
            f"Embedding matching: {matched:,} texts matched "
            f"({matched/len(texts)*100:.1f}% of processed)"
        )

        return df
