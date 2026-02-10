"""BERTopic wrapper for ORTPS grievance theme extraction."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import polars as pl
from bertopic import BERTopic
from hdbscan import HDBSCAN
from loguru import logger
from sklearn.feature_extraction.text import CountVectorizer, ENGLISH_STOP_WORDS
from umap import UMAP

if TYPE_CHECKING:
    pass


# Odisha-specific stopwords for ORTPS grievance analysis
# Filters generic complaint language to surface category-specific themes
ORTPS_STOPWORDS = [
    # Poverty & socioeconomic language
    "poor",
    "family",
    "belongs",
    "belong",
    "bpl",
    "poverty",
    "economic",
    "weaker",
    "section",
    "background",
    "financially",
    "needy",
    "helpless",
    # Petition boilerplate
    "sir",
    "madam",
    "dear",
    "respected",
    "honorable",
    "honourable",
    "humble",
    "humbly",
    "submission",
    "kindly",
    "please",
    "request",
    "pray",
    "appeal",
    "faithfully",
    "obediently",
    "thanking",
    "thanks",
    "yours",
    # Generic administrative terms
    "office",
    "department",
    "district",
    "block",
    "village",
    "panchayat",
    "gram",
    "tahasil",
    "tahsil",
    "govt",
    "government",
    "authority",
    "concerned",
    "officer",
    "collector",
    "bdo",
    "sub",
    "matter",
    "issue",
    "problem",
    "regarding",
    "subject",
    "case",
    "letter",
    "application",
    "form",
    "grievance",
    "complaint",
    "petition",
    "representation",
    "dated",
    "date",
    "reference",
    "ref",
    "copy",
    "enclosed",
    "attachment",
    "document",
    # Generic action verbs
    "give",
    "provide",
    "sanction",
    "approve",
    "allot",
    "allotment",
    "help",
    "assist",
    "resolve",
    "solve",
    "grant",
    "issue",
    "submit",
    "apply",
    "applied",
    "file",
    "filed",
    "visit",
    "visited",
    "check",
    "verify",
    # Common abbreviations
    "pm",
    "pmay",
    "pmgsy",
    "mgnrega",
    "nrega",
    "aay",
    "po",
    "ps",
    "dist",
    "pin",
    "mob",
    "mobile",
    # Odisha place names (major cities/districts)
    "bhubaneswar",
    "cuttack",
    "puri",
    "berhampur",
    "sambalpur",
    "balasore",
    "bhadrak",
    "dhenkanal",
    "angul",
    "bargarh",
    "bolangir",
    "kalahandi",
    "kandhamal",
    "kendrapara",
    "keonjhar",
    "khordha",
    "koraput",
    "malkangiri",
    "mayurbhanj",
    "nabarangpur",
    "nayagarh",
    "nuapada",
    "rayagada",
    "sonepur",
    "sundargarh",
    "odisha",
    "orissa",
    # Generic time references
    "year",
    "month",
    "day",
    "time",
    "ago",
    "since",
    "long",
    "till",
    "until",
]


class TopicAnalyzer:
    """Per-category BERTopic analysis with adaptive parameters.

    Wraps BERTopic with intelligent parameter selection based on data size.
    Uses pre-computed embeddings for efficiency.

    Attributes:
        category: ORTPS category name
        n_samples: Number of documents
        model: Fitted BERTopic instance
    """

    def __init__(
        self,
        category: str,
        n_samples: int,
        random_state: int = 42,
    ):
        """Initialize TopicAnalyzer.

        Args:
            category: ORTPS category name
            n_samples: Number of documents to analyze
            random_state: Random seed for reproducibility
        """
        self.category = category
        self.n_samples = n_samples
        self.random_state = random_state
        self.model: BERTopic | None = None
        self._topics: list[int] | None = None
        self._probs: np.ndarray | None = None

    def _create_model(self) -> BERTopic:
        """Create BERTopic with adaptive parameters based on sample size.

        Returns:
            Configured BERTopic instance
        """
        # Adaptive parameter selection based on data size
        if self.n_samples < 1000:
            min_cluster_size, min_samples = 30, 10
            top_n_words = 12
            n_components = 3  # Reduced for small categories
            # Vectorizer params for small datasets
            min_df = 1  # Very permissive for small categories
            max_df = 1.0  # No upper limit to avoid min_df/max_df conflicts
        elif self.n_samples < 5000:
            min_cluster_size, min_samples = 50, 15
            top_n_words = 10
            n_components = 5
            min_df = 1  # Reduce to 1 to avoid conflicts when few clusters
            max_df = 1.0  # No upper limit to avoid min_df/max_df conflicts
        else:
            min_cluster_size, min_samples = 100, 30
            top_n_words = 10
            n_components = 5
            min_df = 2  # Conservative even for large categories
            max_df = 1.0  # No upper limit to avoid min_df/max_df conflicts

        logger.info(
            f"{self.category}: Using min_cluster_size={min_cluster_size}, "
            f"min_samples={min_samples}, n_components={n_components}, "
            f"min_df={min_df}, max_df={max_df} for n={self.n_samples:,}"
        )

        # UMAP for dimensionality reduction (adaptive components)
        umap_model = UMAP(
            n_neighbors=15,
            n_components=n_components,
            min_dist=0.0,
            metric="cosine",
            random_state=self.random_state,
        )

        # HDBSCAN for clustering
        hdbscan_model = HDBSCAN(
            min_cluster_size=min_cluster_size,
            min_samples=min_samples,
            metric="euclidean",
            cluster_selection_method="eom",
            prediction_data=True,
        )

        # Combine English stopwords with ORTPS-specific stopwords
        stop_words_list = list(set(ENGLISH_STOP_WORDS).union(set(ORTPS_STOPWORDS)))

        # CountVectorizer for c-TF-IDF
        # Improved configuration to filter generic language and capture meaningful phrases
        # Adaptive min_df/max_df based on data size to avoid conflicts
        vectorizer_model = CountVectorizer(
            ngram_range=(1, 3),  # Capture up to 3-word phrases
            token_pattern=r"\b[a-z]{3,}\b",  # Only words >=3 chars, no numbers
            stop_words=stop_words_list,  # Custom Odisha-specific stopwords
            min_df=min_df,  # Adaptive minimum document frequency
            max_df=max_df,  # Adaptive maximum document frequency
        )

        return BERTopic(
            umap_model=umap_model,
            hdbscan_model=hdbscan_model,
            vectorizer_model=vectorizer_model,
            top_n_words=top_n_words,
            n_gram_range=(1, 3),  # Match vectorizer
            calculate_probabilities=(self.n_samples < 5000),
            verbose=True,
        )

    def fit(
        self,
        texts: list[str],
        embeddings: np.ndarray,
    ) -> tuple[list[int], np.ndarray | None]:
        """Fit BERTopic on pre-computed embeddings.

        Args:
            texts: List of complaint texts
            embeddings: Pre-computed sentence embeddings (n_samples, embedding_dim)

        Returns:
            Tuple of (topic_ids, probabilities)
            topic_ids: List of topic assignments (-1 for outliers)
            probabilities: Soft clustering probabilities (None if calculate_probabilities=False)
        """
        if len(texts) != len(embeddings):
            raise ValueError(
                f"Mismatch: {len(texts)} texts but {len(embeddings)} embeddings"
            )

        logger.info(f"{self.category}: Fitting BERTopic on {len(texts):,} documents")

        # Create and fit model
        self.model = self._create_model()
        self._topics, self._probs = self.model.fit_transform(texts, embeddings)

        # Log statistics
        n_topics = len(set(self._topics)) - (1 if -1 in self._topics else 0)
        outlier_rate = (np.array(self._topics) == -1).sum() / len(self._topics)

        logger.info(
            f"{self.category}: Found {n_topics} topics, "
            f"outlier rate: {outlier_rate:.1%}"
        )

        # Reduce outliers if needed
        if outlier_rate > 0.20 and self._probs is not None:
            logger.warning(
                f"{self.category}: High outlier rate ({outlier_rate:.1%}), "
                "attempting reduction..."
            )
            self._topics = self.model.reduce_outliers(
                texts,
                self._topics,
                probabilities=self._probs,
                strategy="probabilities",
                threshold=0.05,
            )
            new_outlier_rate = (np.array(self._topics) == -1).sum() / len(
                self._topics
            )
            logger.info(
                f"{self.category}: Outlier rate after reduction: {new_outlier_rate:.1%}"
            )

        return self._topics, self._probs

    def get_topic_info(self) -> pl.DataFrame:
        """Extract topic information as Polars DataFrame.

        Returns:
            DataFrame with columns: Topic, Count, Name, Representation, etc.
        """
        if self.model is None:
            raise ValueError("Model not fitted yet. Call fit() first.")

        info_df = self.model.get_topic_info()
        return pl.from_pandas(info_df)

    def get_topics(self) -> dict[int, list[tuple[str, float]]]:
        """Get all topics with their top words and scores.

        Returns:
            Dict mapping topic_id -> [(word, score), ...]
        """
        if self.model is None:
            raise ValueError("Model not fitted yet. Call fit() first.")

        return self.model.get_topics()

    def save_model(self, path: Path) -> None:
        """Save BERTopic model to disk.

        Args:
            path: Output path for model file
        """
        if self.model is None:
            raise ValueError("Model not fitted yet. Call fit() first.")

        path.parent.mkdir(parents=True, exist_ok=True)
        self.model.save(str(path), serialization="safetensors")
        logger.info(f"{self.category}: Saved model to {path}")
