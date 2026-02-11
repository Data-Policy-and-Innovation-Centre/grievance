"""Backward-compatible ORTPS BERTopic analyzer shim over shared engine."""

from __future__ import annotations

from app.pipelines.ortps.topic_profiles import (
    ORTPS_STOPWORDS,
    get_ortps_topic_model_params,
)
from app.pipelines.shared.topic_modeling.bertopic_engine import TopicAnalyzer as SharedTopicAnalyzer


class TopicAnalyzer(SharedTopicAnalyzer):
    """Compatibility wrapper preserving historical ORTPS TopicAnalyzer import path."""

    def __init__(
        self,
        category: str,
        n_samples: int,
        random_state: int = 42,
    ) -> None:
        super().__init__(
            category=category,
            n_samples=n_samples,
            random_state=random_state,
            custom_stopwords=ORTPS_STOPWORDS,
            params_resolver=get_ortps_topic_model_params,
        )


__all__ = ["TopicAnalyzer", "ORTPS_STOPWORDS"]

