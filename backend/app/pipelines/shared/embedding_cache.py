"""Shared helpers for sentence-embedding cache read/write operations."""

from __future__ import annotations

import hashlib
import pickle
from pathlib import Path
from typing import Any

import numpy as np
from loguru import logger

from app.config import directories


def compute_text_hash(texts: list[str], sample_size: int = 1000) -> str:
    """Compute deterministic hash from up to `sample_size` leading texts."""
    sample = texts[:min(sample_size, len(texts))]
    text_str = "||".join(str(text) for text in sample)
    return hashlib.md5(text_str.encode()).hexdigest()


def build_embeddings_cache_path(
    model_name: str,
    text_hash: str,
    cache_dir: Path | None = None,
    prefix: str = "ortps_embeddings",
) -> Path:
    """Build cache path using the same naming scheme as existing ORTPS cache files."""
    target_dir = cache_dir or directories.MODELS
    model_slug = model_name.replace("/", "_").replace("-", "_")
    return target_dir / f"{prefix}_{model_slug}_{text_hash}.pkl"


def save_embeddings_cache(
    cache_path: Path,
    embeddings: np.ndarray,
    metadata: dict[str, Any],
) -> None:
    """Persist embeddings and metadata to a pickle file."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_data = {"embeddings": embeddings, **metadata}
    with open(cache_path, "wb") as file:
        pickle.dump(cache_data, file, protocol=pickle.HIGHEST_PROTOCOL)
    logger.info(f"Saved embeddings to cache: {cache_path.name}")


def load_embeddings_cache(
    cache_path: Path,
    expected_model_name: str | None = None,
    expected_text_hash: str | None = None,
) -> np.ndarray | None:
    """Load embeddings from cache if present and metadata checks pass."""
    if not cache_path.exists():
        return None

    try:
        with open(cache_path, "rb") as file:
            cache_data = pickle.load(file)

        if (
            expected_model_name is not None and
            cache_data.get("model_name") != expected_model_name
        ):
            logger.warning(
                f"Cache model mismatch: {cache_data.get('model_name')} != {expected_model_name}"
            )
            return None

        if (
            expected_text_hash is not None and
            cache_data.get("text_hash") != expected_text_hash
        ):
            logger.warning("Cache hash mismatch")
            return None

        logger.info(
            "Loaded embeddings from cache: "
            f"{cache_path.name} ({cache_data.get('num_texts', 0):,} texts, "
            f"dim={cache_data.get('embedding_dim', 'unknown')})"
        )
        return cache_data["embeddings"]

    except Exception as exc:  # pragma: no cover - defensive logging path
        logger.warning(f"Failed to load cache: {exc}")
        return None

