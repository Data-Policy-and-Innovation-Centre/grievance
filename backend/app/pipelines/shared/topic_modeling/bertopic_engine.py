"""Shared BERTopic analysis engine with injectable policy profiles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

import numpy as np
import pandas as pd
import polars as pl
from bertopic import BERTopic
from hdbscan import HDBSCAN
from loguru import logger
from sklearn.feature_extraction.text import CountVectorizer, ENGLISH_STOP_WORDS
from umap import UMAP


@dataclass(frozen=True)
class TopicModelParams:
    """BERTopic parameter bundle resolved from a profile."""

    min_cluster_size: int
    min_samples: int
    top_n_words: int
    n_components: int
    min_df: int
    max_df: float
    ngram_range: tuple[int, int] = (1, 3)
    token_pattern: str = r"\b[a-z]{3,}\b"
    calculate_probabilities: bool = True


def default_topic_model_params(n_samples: int) -> TopicModelParams:
    """Default adaptive parameters based on dataset size."""
    if n_samples < 1000:
        return TopicModelParams(
            min_cluster_size=30,
            min_samples=10,
            top_n_words=12,
            n_components=3,
            min_df=1,
            max_df=1.0,
            calculate_probabilities=True,
        )

    if n_samples < 5000:
        return TopicModelParams(
            min_cluster_size=50,
            min_samples=15,
            top_n_words=10,
            n_components=5,
            min_df=1,
            max_df=1.0,
            calculate_probabilities=True,
        )

    return TopicModelParams(
        min_cluster_size=100,
        min_samples=30,
        top_n_words=10,
        n_components=5,
        min_df=2,
        max_df=1.0,
        calculate_probabilities=False,
    )


class TopicAnalyzer:
    """
    Generic per-category BERTopic analysis with profile-driven configuration.

    The caller supplies custom stopwords and a parameter resolver to make this
    class reusable across domain-specific pipelines.
    """

    def __init__(
        self,
        category: str,
        n_samples: int,
        random_state: int = 42,
        custom_stopwords: Sequence[str] | None = None,
        params_resolver: Callable[[int], TopicModelParams] = default_topic_model_params,
    ) -> None:
        self.category = category
        self.n_samples = n_samples
        self.random_state = random_state
        self.custom_stopwords = list(custom_stopwords or [])
        self.params_resolver = params_resolver

        self.model: BERTopic | None = None
        self._topics: list[int] | None = None
        self._probs: np.ndarray | None = None

    class _OutlierOnlyModel:
        """Minimal model-like object for tiny samples where BERTopic is unstable."""

        def __init__(self, n_texts: int) -> None:
            self.n_texts = n_texts

        def get_topic_info(self) -> pd.DataFrame:
            return pd.DataFrame(
                {
                    "Topic": [-1],
                    "Count": [self.n_texts],
                    "Name": ["outlier"],
                }
            )

        def get_topics(self) -> dict[int, list[tuple[str, float]]]:
            return {-1: []}

        def save(self, path: str, serialization: str = "safetensors") -> None:
            Path(path).write_text(
                f"{{\"fallback\":\"outlier_only\",\"n_texts\":{self.n_texts},"
                f"\"serialization\":\"{serialization}\"}}"
            )

    def _create_model(self) -> BERTopic:
        """Create BERTopic model instance from resolved parameters."""
        params = self.params_resolver(self.n_samples)
        n_neighbors = min(15, max(2, self.n_samples - 1))
        n_components = min(params.n_components, max(1, self.n_samples - 2))
        min_cluster_size = min(params.min_cluster_size, self.n_samples)
        min_samples = min(params.min_samples, self.n_samples)

        logger.info(
            f"{self.category}: Using min_cluster_size={params.min_cluster_size}, "
            f"min_samples={params.min_samples}, n_components={params.n_components}, "
            f"min_df={params.min_df}, max_df={params.max_df} for n={self.n_samples:,}"
        )
        if n_components != params.n_components or n_neighbors != 15:
            logger.info(
                f"{self.category}: Adjusted UMAP settings for small sample size "
                f"(n_neighbors={n_neighbors}, n_components={n_components})"
            )
        if (
            min_cluster_size != params.min_cluster_size
            or min_samples != params.min_samples
        ):
            logger.info(
                f"{self.category}: Adjusted HDBSCAN settings for small sample size "
                f"(min_cluster_size={min_cluster_size}, min_samples={min_samples})"
            )

        umap_model = UMAP(
            n_neighbors=n_neighbors,
            n_components=n_components,
            min_dist=0.0,
            metric="cosine",
            random_state=self.random_state,
        )

        hdbscan_model = HDBSCAN(
            min_cluster_size=min_cluster_size,
            min_samples=min_samples,
            metric="euclidean",
            cluster_selection_method="eom",
            prediction_data=True,
        )

        stop_words_list = list(set(ENGLISH_STOP_WORDS).union(set(self.custom_stopwords)))

        vectorizer_model = CountVectorizer(
            ngram_range=params.ngram_range,
            token_pattern=params.token_pattern,
            stop_words=stop_words_list,
            min_df=params.min_df,
            max_df=params.max_df,
        )

        return BERTopic(
            umap_model=umap_model,
            hdbscan_model=hdbscan_model,
            vectorizer_model=vectorizer_model,
            top_n_words=params.top_n_words,
            n_gram_range=params.ngram_range,
            calculate_probabilities=params.calculate_probabilities,
            verbose=True,
        )

    def fit(
        self,
        texts: list[str],
        embeddings: np.ndarray,
    ) -> tuple[list[int], np.ndarray | None]:
        """Fit BERTopic model on supplied texts + precomputed embeddings."""
        if len(texts) != len(embeddings):
            raise ValueError(
                f"Mismatch: {len(texts)} texts but {len(embeddings)} embeddings"
            )
        if len(texts) < 3:
            logger.warning(
                f"{self.category}: Too few documents ({len(texts)}) for BERTopic; "
                "assigning outlier topic only."
            )
            self.model = self._OutlierOnlyModel(len(texts))  # type: ignore[assignment]
            self._topics = [-1 for _ in texts]
            self._probs = None
            return self._topics, self._probs

        logger.info(f"{self.category}: Fitting BERTopic on {len(texts):,} documents")

        self.model = self._create_model()
        self._topics, self._probs = self.model.fit_transform(texts, embeddings)

        n_topics = len(set(self._topics)) - (1 if -1 in self._topics else 0)
        outlier_rate = (np.array(self._topics) == -1).sum() / len(self._topics)

        logger.info(
            f"{self.category}: Found {n_topics} topics, outlier rate: {outlier_rate:.1%}"
        )

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
        """Return BERTopic topic info as Polars DataFrame."""
        if self.model is None:
            raise ValueError("Model not fitted yet. Call fit() first.")
        return pl.from_pandas(self.model.get_topic_info())

    def get_topics(self) -> dict[int, list[tuple[str, float]]]:
        """Return mapping topic_id -> [(word, score), ...]."""
        if self.model is None:
            raise ValueError("Model not fitted yet. Call fit() first.")
        return self.model.get_topics()

    def save_model(self, path: Path) -> None:
        """Persist fitted BERTopic model to disk."""
        if self.model is None:
            raise ValueError("Model not fitted yet. Call fit() first.")

        path.parent.mkdir(parents=True, exist_ok=True)
        self.model.save(str(path), serialization="safetensors")
        logger.info(f"{self.category}: Saved model to {path}")
