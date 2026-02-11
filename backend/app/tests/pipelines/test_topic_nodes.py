"""Unit tests for ORTPS topic nodes."""

from __future__ import annotations

import numpy as np
import polars as pl

from app.pipelines.ortps import topic_nodes


class DummyEncoder:
    def encode(self, texts, normalize_embeddings=True, batch_size=256, show_progress_bar=True):
        return np.ones((len(texts), 4))


class DummyLabeler:
    """Mimics only the public surface needed by topic_nodes.cached_embeddings."""

    model_name = "dummy/model"
    model = DummyEncoder()


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

