"""Unit tests for shared BERTopic engine wrapper."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import pytest

from app.pipelines.shared.topic_modeling.bertopic_engine import (
    TopicAnalyzer,
    TopicModelParams,
    default_topic_model_params,
)


class FakeBERTopicModel:
    def __init__(self):
        self.reduced_called = False
        self.saved = None

    def fit_transform(self, texts, embeddings):
        return [0, -1, 1], np.array([[0.9], [0.1], [0.8]])

    def reduce_outliers(self, texts, topics, probabilities, strategy, threshold):
        self.reduced_called = True
        return [0, 0, 1]

    def get_topic_info(self):
        return pd.DataFrame(
            {
                "Topic": [0, 1, -1],
                "Count": [2, 1, 0],
                "Name": ["topic_0", "topic_1", "outlier"],
            }
        )

    def get_topics(self):
        return {
            0: [("topic", 0.8)],
            1: [("model", 0.7)],
        }

    def save(self, path, serialization):
        self.saved = (path, serialization)


class FakeBERTopicCtor:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def test_default_topic_model_params_are_adaptive():
    small = default_topic_model_params(500)
    medium = default_topic_model_params(2000)
    large = default_topic_model_params(8000)

    assert (small.min_cluster_size, small.min_samples, small.n_components) == (30, 10, 3)
    assert (medium.min_cluster_size, medium.min_samples, medium.n_components) == (50, 15, 5)
    assert (large.min_cluster_size, large.min_samples, large.n_components) == (100, 30, 5)
    assert large.calculate_probabilities is False


def test_topic_analyzer_fit_accessors_and_save(monkeypatch, tmp_path):
    analyzer = TopicAnalyzer(
        category="Test",
        n_samples=3,
        custom_stopwords=["custom"],
        params_resolver=lambda _: TopicModelParams(
            min_cluster_size=2,
            min_samples=1,
            top_n_words=5,
            n_components=2,
            min_df=1,
            max_df=1.0,
            calculate_probabilities=True,
        ),
    )
    fake_model = FakeBERTopicModel()
    monkeypatch.setattr(analyzer, "_create_model", lambda: fake_model)

    topics, probs = analyzer.fit(
        texts=["a", "b", "c"],
        embeddings=np.array([[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]),
    )
    assert topics == [0, 0, 1]
    assert probs is not None
    assert fake_model.reduced_called is True

    info = analyzer.get_topic_info()
    assert isinstance(info, pl.DataFrame)
    assert "Topic" in info.columns
    assert analyzer.get_topics()[0][0][0] == "topic"

    model_path = tmp_path / "models" / "test_model"
    analyzer.save_model(model_path)
    assert fake_model.saved == (str(model_path), "safetensors")


def test_topic_analyzer_rejects_mismatched_lengths():
    analyzer = TopicAnalyzer(category="Test", n_samples=1)
    with pytest.raises(ValueError):
        analyzer.fit(["one", "two"], np.array([[0.1, 0.2]]))


def test_topic_analyzer_tiny_sample_falls_back_to_outliers():
    analyzer = TopicAnalyzer(category="Tiny", n_samples=2)
    topics, probs = analyzer.fit(
        texts=["a", "b"],
        embeddings=np.array([[0.1, 0.2], [0.3, 0.4]]),
    )

    assert topics == [-1, -1]
    assert probs is None

    info = analyzer.get_topic_info()
    assert info["Topic"].to_list() == [-1]
    assert info["Count"].to_list() == [2]


def test_create_model_adjusts_umap_params_for_small_samples(monkeypatch):
    captured = {}

    class FakeUMAP:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    class FakeHDBSCAN:
        def __init__(self, **kwargs):
            captured["min_cluster_size"] = kwargs["min_cluster_size"]
            captured["min_samples"] = kwargs["min_samples"]

    monkeypatch.setattr(
        "app.pipelines.shared.topic_modeling.bertopic_engine.UMAP",
        FakeUMAP,
    )
    monkeypatch.setattr(
        "app.pipelines.shared.topic_modeling.bertopic_engine.HDBSCAN",
        FakeHDBSCAN,
    )
    monkeypatch.setattr(
        "app.pipelines.shared.topic_modeling.bertopic_engine.BERTopic",
        FakeBERTopicCtor,
    )

    analyzer = TopicAnalyzer(
        category="Small",
        n_samples=4,
        params_resolver=lambda _: TopicModelParams(
            min_cluster_size=30,
            min_samples=10,
            top_n_words=12,
            n_components=3,
            min_df=1,
            max_df=1.0,
            calculate_probabilities=True,
        ),
    )
    model = analyzer._create_model()

    assert captured["n_neighbors"] == 3
    assert captured["n_components"] == 2
    assert captured["min_cluster_size"] == 4
    assert captured["min_samples"] == 4
    assert isinstance(model, FakeBERTopicCtor)


def test_accessors_raise_before_fit():
    analyzer = TopicAnalyzer(category="Unfitted", n_samples=10)

    with pytest.raises(ValueError, match="Model not fitted yet"):
        analyzer.get_topic_info()
    with pytest.raises(ValueError, match="Model not fitted yet"):
        analyzer.get_topics()
    with pytest.raises(ValueError, match="Model not fitted yet"):
        analyzer.save_model(Path("unused"))


def test_tiny_sample_fallback_save_writes_outlier_only_marker(tmp_path):
    analyzer = TopicAnalyzer(category="Tiny", n_samples=2)
    analyzer.fit(
        texts=["a", "b"],
        embeddings=np.array([[0.1, 0.2], [0.3, 0.4]]),
    )

    model_path = tmp_path / "tiny_model.safetensors"
    analyzer.save_model(model_path)

    assert model_path.exists()
    content = model_path.read_text(encoding="utf-8")
    assert "outlier_only" in content
