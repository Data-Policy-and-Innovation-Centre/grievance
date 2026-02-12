"""Unit tests for ORTPS topic nodes."""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from app.pipelines.ortps import topic_nodes


class DummyEncoder:
    def encode(self, texts, normalize_embeddings=True, batch_size=256, show_progress_bar=True):
        return np.ones((len(texts), 4))


class DummyLabeler:
    """Mimics only the public surface needed by topic_nodes.cached_embeddings."""

    model_name = "dummy/model"
    model = DummyEncoder()


def test_filtered_data_keeps_only_labeled_and_min_length():
    df = pl.DataFrame(
        {
            "grievance": [
                "x" * 60,        # keep
                "short text",    # too short
                "y" * 70,        # category null -> drop
            ],
            "ortps_category": ["Certificates", "Ration card", None],
        }
    )

    out = topic_nodes.filtered_data(df, min_text_length=50)
    assert len(out) == 1
    assert out["ortps_category"].to_list() == ["Certificates"]


def test_category_splits_returns_per_category_frames():
    df = pl.DataFrame(
        {
            "grievance": ["a" * 60, "b" * 60, "c" * 60],
            "ortps_category": ["Certificates", "Ration card", "Certificates"],
        }
    )

    splits = topic_nodes.category_splits(df)
    assert set(splits.keys()) == {"Certificates", "Ration card"}
    assert len(splits["Certificates"]) == 2
    assert len(splits["Ration card"]) == 1


def test_cached_embeddings_uses_public_labeler_surface(monkeypatch, tmp_path):
    category_splits = {
        "Certificates": pl.DataFrame(
            {
                "grievance": [
                    "Need caste certificate quickly",
                    "Birth certificate correction pending",
                ]
            }
        )
    }

    monkeypatch.setattr(
        topic_nodes,
        "build_embeddings_cache_path",
        lambda model_name, text_hash: tmp_path / f"{model_name.replace('/', '_')}_{text_hash}.pkl",
    )

    embeddings = topic_nodes.cached_embeddings(category_splits, DummyLabeler())
    assert "Certificates" in embeddings
    assert embeddings["Certificates"].shape == (2, 4)


def test_topic_models_wires_ortps_profile_into_analyzer(monkeypatch):
    created = []

    class FakeAnalyzer:
        def __init__(self, category, n_samples, custom_stopwords, params_resolver):
            self.category = category
            self.n_samples = n_samples
            self.custom_stopwords = custom_stopwords
            self.params_resolver = params_resolver
            self.fit_called_with = None
            created.append(self)

        def fit(self, texts, embeddings):
            self.fit_called_with = (texts, embeddings)
            return [0 for _ in texts], None

    monkeypatch.setattr(topic_nodes, "TopicAnalyzer", FakeAnalyzer)

    splits = {
        "Certificates": pl.DataFrame({"grievance": ["need caste certificate", "income certificate"]}),
        "Ration card": pl.DataFrame({"grievance": ["ration card not issued"]}),
    }
    embeddings = {
        "Certificates": np.ones((2, 4)),
        "Ration card": np.ones((1, 4)),
    }

    models = topic_nodes.topic_models(splits, embeddings)

    assert set(models.keys()) == {"Certificates", "Ration card"}
    assert len(created) == 2
    assert created[0].custom_stopwords == topic_nodes.ORTPS_STOPWORDS
    assert created[0].params_resolver is topic_nodes.get_ortps_topic_model_params
    assert created[0].fit_called_with[0] == ["need caste certificate", "income certificate"]
    assert created[1].fit_called_with[0] == ["ration card not issued"]


def test_topic_assignments_combines_with_topic_ids():
    class FakeAnalyzer:
        def __init__(self, topics):
            self._topics = topics

    splits = {
        "Certificates": pl.DataFrame({"id": [1, 2], "grievance": ["a", "b"], "ortps_category": ["Certificates", "Certificates"]}),
        "Ration card": pl.DataFrame({"id": [3], "grievance": ["c"], "ortps_category": ["Ration card"]}),
    }
    models = {
        "Certificates": FakeAnalyzer([10, 11]),
        "Ration card": FakeAnalyzer([20]),
    }

    out = topic_nodes.topic_assignments(splits, models).sort("id")
    assert out["topic_id"].to_list() == [10, 11, 20]


def test_topic_assignments_raises_when_model_not_fitted():
    class FakeAnalyzer:
        _topics = None

    splits = {
        "Certificates": pl.DataFrame({"id": [1], "grievance": ["a"], "ortps_category": ["Certificates"]}),
    }
    models = {"Certificates": FakeAnalyzer()}

    with pytest.raises(ValueError, match="Model not fitted"):
        topic_nodes.topic_assignments(splits, models)


def test_topic_summary_computes_topics_outliers_and_coverage():
    class FakeAnalyzer:
        def __init__(self, topics):
            self._topics = topics

    models = {
        "Certificates": FakeAnalyzer([0, 0, -1, 1]),   # 2 valid topics, 1 outlier
        "Ration card": FakeAnalyzer([-1, -1]),         # 0 valid topics, 2 outliers
    }

    out = topic_nodes.topic_summary(models).sort("category")
    rows = {r["category"]: r for r in out.iter_rows(named=True)}

    assert rows["Certificates"]["n_topics"] == 2
    assert rows["Certificates"]["outliers"] == 1
    assert rows["Certificates"]["coverage_pct"] == 75.0

    assert rows["Ration card"]["n_topics"] == 0
    assert rows["Ration card"]["outliers"] == 2
    assert rows["Ration card"]["coverage_pct"] == 0.0
