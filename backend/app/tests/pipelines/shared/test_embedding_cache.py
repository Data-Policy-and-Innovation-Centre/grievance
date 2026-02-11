"""Unit tests for shared embedding cache helpers."""

from __future__ import annotations

import numpy as np
import numpy.testing as npt

from app.pipelines.shared.embedding_cache import (
    build_embeddings_cache_path,
    compute_text_hash,
    load_embeddings_cache,
    save_embeddings_cache,
)


def test_compute_text_hash_is_stable():
    texts = ["a", "b", "c"]
    assert compute_text_hash(texts) == compute_text_hash(texts)


def test_save_and_load_embeddings_cache_roundtrip(tmp_path):
    embeddings = np.array([[0.1, 0.2], [0.3, 0.4]])
    text_hash = "abc123"
    model_name = "sentence-transformers/all-MiniLM-L6-v2"

    path = build_embeddings_cache_path(
        model_name=model_name,
        text_hash=text_hash,
        cache_dir=tmp_path,
    )
    save_embeddings_cache(
        cache_path=path,
        embeddings=embeddings,
        metadata={
            "model_name": model_name,
            "text_hash": text_hash,
            "num_texts": 2,
            "embedding_dim": 2,
        },
    )

    loaded = load_embeddings_cache(
        cache_path=path,
        expected_model_name=model_name,
        expected_text_hash=text_hash,
    )
    assert loaded is not None
    npt.assert_allclose(loaded, embeddings)


def test_load_embeddings_cache_returns_none_on_model_mismatch(tmp_path):
    embeddings = np.array([[0.5, 0.6]])
    path = tmp_path / "cache.pkl"
    save_embeddings_cache(
        cache_path=path,
        embeddings=embeddings,
        metadata={
            "model_name": "model_a",
            "text_hash": "hash_a",
            "num_texts": 1,
            "embedding_dim": 2,
        },
    )

    loaded = load_embeddings_cache(
        cache_path=path,
        expected_model_name="model_b",
        expected_text_hash="hash_a",
    )
    assert loaded is None

