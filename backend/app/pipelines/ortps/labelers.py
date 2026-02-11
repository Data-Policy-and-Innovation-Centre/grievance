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
    - See CATEGORY_KEYWORDS for the full ORTPS service list.
    """

    # Category-specific keywords (case-insensitive), grouped by issue type.
    CATEGORY_KEYWORDS = {
        "Certificates": [
            # Caste certificate
            "caste certificate", "sc certificate", "st certificate",
            "obc certificate", "sebc certificate", "creamy layer",
            "caste validity", "community certificate",
            # Legal Heir Certificate
            "legal heir certificate", "legal heir", "heir certificate",
            "legal heirship",
            # Birth and Death certificate
            "birth certificate", "death certificate",
            "birth and death certificate",
            # Marriage certificate
            "marriage certificate", "marriage registration",
            # Income certificate
            "income certificate", "annual income", "income proof",
            "income verification", "family income",
            # Income & Asset certificate (EWS)
            "income and asset certificate", "income & asset certificate",
            "income asset certificate", "ews certificate",
            "ews income", "ews income certificate",
        ],
        "Scholarship": [
            
            # Scholarship
            "scholarship", "post matric", "pre matric", "oasis",
            "national scholarship", "merit scholarship", "sc scholarship",
            "st scholarship", "minority scholarship",
            "sanction of scholarship",
        ],
        "Ration card": [
            # Ration Card
            "ration card", "food security", "aay card", "bpl card",
            "phh card", "antyodaya", "priority household", "pds card",
        ],
        "Land matters": [
            # Certified copy of RoR
            "certified copy of ror", "ror copy", "ror certified copy",
            "record of rights", "record of rights copy",
            # Encumbrance certificate
            "encumbrance certificate", "ec certificate",
            # Certified copy of registered documents
            "certified copy of registered document",
            "copy of registered document",
            "registered document copy",
            "registered deed copy", "certified copy of deed",
            # Registration of property transfer documents
            "registration of documents", "property registration",
            "document registration", "deed registration",
            "sale deed registration", "transfer of immovable property",
            # Mortgage permission
            "mortgage permission", "permission for mortgage",
            "mortgage noc", "mortgage approval",
            # Conveyance deed
            "conveyance deed", "issue of conveyance",
            "conveyance certificate",
            # Disposal of uncontested mutation cases
            "uncontested mutation", "mutation case disposal",
            "mutation disposal",
            # Mutation order of leasehold land
            "mutation order of leasehold",
            "leasehold mutation order", "leasehold mutation",
            # Conversion of land (OLR Act Sec.8)
            "olr act section 8", "section 8 olr",
            "conversion under olr", "olr section 8",
            # Conversion order of leasehold land
            "conversion order of leasehold",
            "leasehold conversion", "conversion of leasehold land",
            # Partition of land (OLR Act Sec.19)
            "partition of land", "olr act section 19",
            "section 19 olr", "mutual consent partition",
        ],
        "Building & Construction": [
            # Building plan approval
            "building plan approval", "building plan sanction",
            "building plan", "plan approval by ulb",
            "bda approval", "bmc approval", "development authority approval",
            # Permission for addition/alteration
            "addition/alteration", "addition alteration",
            "alteration permission", "addition permission",
            "building alteration",
            # Fire safety recommendation/certificate
            "fire safety recommendation", "fire safety certificate",
            "fire safety noc", "fsr", "fire noc",
        ],
        "Utilities & Connections": [
            # Pipe water connection
            "pipe water connection", "piped water connection",
            "water connection", "bmc water connection",
            "cmc water connection", "bemc water connection",
            # New power connection (non-industrial)
            "new power connection", "new electricity connection",
            "electricity connection", "power connection",
            "non industrial power",
        ],
        "Vehicle Services": [
            # Change of address in driving licence
            "change of address in driving licence",
            "address change in dl", "dl address change",
            "address change driving licence",
            # Driving licence renewal
            "renewal of driving licence", "driving licence renewal",
            "dl renewal", "renew dl",
            # Learner's licence
            "learner's licence", "learner licence",
            "learner license", "ll licence", "ll license",
            "learner's license",
            # Driving licence (general)
            "driving licence", "driving license",
            "issue of driving licence", "dl issue", "dl application",
            # Certified copy of vehicle registration certificate
            "certified copy of registration certificate",
            "registration certificate copy",
            "vehicle registration certificate",
            "vehicle rc", "rc copy", "rc book",
            # Transfer of vehicle ownership
            "transfer of vehicle ownership", "ownership transfer",
            "vehicle ownership transfer", "rc transfer",
            "transfer of ownership of vehicle",
        ],
        "Police & Legal": [
            # Employee verification request
            "employee verification", "employment verification",
            "employee antecedent",
            # Character/Antecedent verification
            "character verification", "antecedent verification",
            "police verification", "antecedent check",
            # Copy of FIR
            "copy of fir", "fir copy", "first information report",
            "fir certified copy",
            # Trade licence
            "trade licence", "trade license",
            "trade licence provisional", "trade licence final",
            "trade license provisional", "trade license final",
            "ulb trade licence",
        ],
    }

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        similarity_threshold: float = 0.45,
        device: str | None = None,
        embedding_strategy: Literal["label_only", "keyword_only", "combined"] = "label_only",
        keyword_weight: float = 1.0,
        label_weight: float = 0.5,
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
        embedding_strategy : {"label_only", "keyword_only", "combined"}
            Strategy for embedding similarity computation
        keyword_weight : float
            Weight for keyword similarity (in combined mode)
        label_weight : float
            Weight for label similarity (in combined mode)
        """
        self.model_name = model_name
        self.similarity_threshold = similarity_threshold
        self.device = device
        self.embedding_strategy = embedding_strategy
        self.keyword_weight = keyword_weight
        self.label_weight = label_weight
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
        method: Literal["keyword", "embedding", "hybrid"] = "hybrid",
        embedding_strategy: Literal["label_only", "keyword_only", "combined"] | None = None,
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
        embedding_strategy : {"label_only", "keyword_only", "combined"}, optional
            Override the instance default embedding strategy

        Returns
        -------
        pl.DataFrame
            DataFrame with new columns:
            - ortps_category: Matched category name
            - ortps_method: Detection method (keyword/embedding/none)
            - ortps_confidence: Similarity score (for embedding matches)
        """
        # Use instance default if not overridden
        if embedding_strategy is None:
            embedding_strategy = self.embedding_strategy

        # Add a stable row key so hybrid embedding merges are key-based, not positional.
        row_idx_col = "__ortps_row_idx__"
        added_row_idx = False
        if method in ["embedding", "hybrid"] and row_idx_col not in df.columns:
            df = df.with_row_index(row_idx_col)
            added_row_idx = True

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
                    df = self._add_embedding_labels(df, df_to_embed, text_col, embedding_strategy)
            else:
                logger.info(f"Running embedding on all {len(df):,} texts")
                df = self._add_embedding_labels(df, df, text_col, embedding_strategy)

        if added_row_idx:
            df = df.drop(row_idx_col)

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

    # TODO: refactor all caching related functions to separate module to avoid duplication and keep labeler focused on labeling logic
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
        text_col: str,
        strategy: Literal["label_only", "keyword_only", "combined"] = "label_only"
    ) -> pl.DataFrame:
        """Embedding similarity for unmatched texts."""
        categories = list(self.CATEGORY_KEYWORDS.keys())

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

        # Compute similarities based on strategy
        if strategy == "label_only":
            similarities, matched_info = self._compute_label_similarities(text_emb, categories)
        elif strategy == "keyword_only":
            similarities, matched_info = self._compute_keyword_similarities(text_emb, categories)
        elif strategy == "combined":
            similarities, matched_info = self._compute_combined_similarities(text_emb, categories)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")

        # Extract max similarities
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
                result = {
                    "category": categories[cat_idx],
                    "method": "embedding",
                    "confidence": float(sim),
                    "matched_keyword": matched_info[i].get("matched_keyword") if strategy != "label_only" else None
                }
                embedding_results.append(result)
            else:
                embedding_results.append({
                    "category": None,
                    "method": None,
                    "confidence": None,
                    "matched_keyword": None
                })

        # Create DataFrame with embedding results
        # Explicitly specify schema to avoid Polars schema inference issues
        # when first rows are all None (above_threshold=False)
        embedding_df = pl.DataFrame(
            embedding_results,
            schema={
                "category": pl.String,
                "method": pl.String,
                "confidence": pl.Float64,
                "matched_keyword": pl.String  # NEW
            }
        ).rename({
            "category": "emb_category",
            "method": "emb_method",
            "confidence": "emb_confidence",
            "matched_keyword": "emb_matched_keyword"
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
        # Check if ortps columns exist (hybrid mode) or need to be created (embedding-only mode)
        has_ortps_cols = "ortps_category" in df_to_embed.columns

        if has_ortps_cols:
            # Hybrid mode: merge with existing ortps columns
            df_to_embed = df_to_embed.with_columns([
                pl.coalesce([pl.col("ortps_category"), pl.col("emb_category")]).alias("ortps_category"),
                pl.coalesce([pl.col("ortps_method"), pl.col("emb_method")]).alias("ortps_method"),
                pl.coalesce([pl.col("ortps_confidence"), pl.col("emb_confidence")]).alias("ortps_confidence"),
                pl.coalesce([pl.col("ortps_matched_keyword"), pl.col("emb_matched_keyword")]).alias("ortps_matched_keyword") if "ortps_matched_keyword" in df_to_embed.columns else pl.col("emb_matched_keyword").alias("ortps_matched_keyword")
            ]).drop(["_embed_idx", "emb_category", "emb_method", "emb_confidence", "emb_matched_keyword"])
        else:
            # Embedding-only mode: just rename emb columns
            df_to_embed = df_to_embed.rename({
                "emb_category": "ortps_category",
                "emb_method": "ortps_method",
                "emb_confidence": "ortps_confidence",
                "emb_matched_keyword": "ortps_matched_keyword"
            }).drop("_embed_idx")

        # Merge back with original DataFrame
        # For rows that were embedded, update their values
        if "ortps_category" not in df.columns:
            df = df.with_columns([
                pl.lit(None).alias("ortps_category"),
                pl.lit(None).alias("ortps_method"),
                pl.lit(None, dtype=pl.Float64).alias("ortps_confidence"),
                pl.lit(None).alias("ortps_matched_keyword")  # NEW
            ])

        # Update rows that were processed; prefer key-based alignment when row key is present.
        if "__ortps_row_idx__" in df.columns and "__ortps_row_idx__" in df_to_embed.columns:
            df = df.update(df_to_embed, on="__ortps_row_idx__")
        else:
            df = df.update(df_to_embed)

        # Log statistics
        matched = above_threshold.sum()
        logger.info(
            f"Embedding matching: {matched:,} texts matched "
            f"({matched/len(texts)*100:.1f}% of processed)"
        )

        return df

    def _compute_keywords_hash(self) -> str:
        """Compute hash of CATEGORY_KEYWORDS dict for cache validation."""
        import json
        keywords_json = json.dumps(self.CATEGORY_KEYWORDS, sort_keys=True)
        return hashlib.md5(keywords_json.encode()).hexdigest()[:8]

    def _get_keyword_embeddings_cache_path(self) -> Path:
        """Get cache file path for keyword embeddings."""
        model_slug = self.model_name.replace("/", "_").replace("-", "_")
        keywords_hash = self._compute_keywords_hash()
        return directories.MODELS / f"ortps_keyword_embeddings_{model_slug}_{keywords_hash}.pkl"

    def _save_keyword_embeddings_cache(self, embeddings: np.ndarray, cache_path: Path):
        """Save keyword embeddings to cache."""
        cache_data = {
            "embeddings": embeddings,
            "model_name": self.model_name,
            "keywords_hash": self._compute_keywords_hash(),
            "num_keywords": len(embeddings),
            "embedding_dim": embeddings.shape[1]
        }
        with open(cache_path, "wb") as f:
            pickle.dump(cache_data, f, protocol=pickle.HIGHEST_PROTOCOL)
        logger.info(f"Saved keyword embeddings to cache: {cache_path.name}")

    def _load_keyword_embeddings_cache(self, cache_path: Path) -> np.ndarray | None:
        """Load keyword embeddings from cache if available."""
        if not cache_path.exists():
            return None

        try:
            with open(cache_path, "rb") as f:
                cache_data = pickle.load(f)

            # Validate cache
            if cache_data["model_name"] != self.model_name:
                logger.warning("Cache model mismatch")
                return None

            if cache_data["keywords_hash"] != self._compute_keywords_hash():
                logger.warning("CATEGORY_KEYWORDS dict changed, cache invalid")
                return None

            logger.info(
                f"Loaded keyword embeddings from cache: {cache_path.name} "
                f"({cache_data['num_keywords']} keywords, dim={cache_data['embedding_dim']})"
            )
            return cache_data["embeddings"]

        except Exception as e:
            logger.warning(f"Failed to load keyword cache: {e}")
            return None

    def _encode_category_keywords(self) -> tuple[np.ndarray, list[tuple[str, str]]]:
        """
        Encode all keywords for all categories.

        Returns
        -------
        keyword_embeddings : np.ndarray
            Shape (total_keywords, embedding_dim), normalized
        keyword_metadata : list[tuple[str, str]]
            List of (category, keyword) tuples, aligned with embedding rows
        """
        # Build flat list of (category, keyword) pairs
        keyword_metadata = []
        keywords_flat = []

        for category, keywords in self.CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                keyword_metadata.append((category, keyword))
                keywords_flat.append(keyword)

        # Check cache
        cache_path = self._get_keyword_embeddings_cache_path()
        cached = self._load_keyword_embeddings_cache(cache_path)
        if cached is not None:
            return cached, keyword_metadata

        # Encode all keywords in one batch
        logger.info(f"Encoding {len(keywords_flat)} keywords for all categories...")
        keyword_emb = self.model.encode(
            keywords_flat,
            normalize_embeddings=True,
            batch_size=256,
            show_progress_bar=True
        )

        # Save to cache
        self._save_keyword_embeddings_cache(keyword_emb, cache_path)

        return keyword_emb, keyword_metadata

    def _compute_label_similarities(
        self,
        text_emb: np.ndarray,
        categories: list[str]
    ) -> tuple[np.ndarray, list[dict]]:
        """Compute similarities using category labels only (current behavior)."""
        logger.info("Computing label-only similarities...")
        category_emb = self.model.encode(
            categories, normalize_embeddings=True, show_progress_bar=False
        )
        similarities = np.dot(text_emb, category_emb.T)  # (N, num_categories)

        # No keyword info for label-only
        matched_info = [{"matched_keyword": None} for _ in range(len(text_emb))]

        return similarities, matched_info

    def _compute_keyword_similarities(
        self,
        text_emb: np.ndarray,
        categories: list[str]
    ) -> tuple[np.ndarray, list[dict]]:
        """
        Compute similarities using keywords only, max-pooled per category.

        Returns
        -------
        similarities : np.ndarray
            Shape (n_texts, n_categories)
            For each text and category, this is the MAX similarity across all keywords in that category
        matched_info : list[dict]
            For each text, the keyword with highest similarity
        """
        logger.info("Computing keyword-only similarities...")

        # Get keyword embeddings and metadata
        keyword_emb, keyword_metadata = self._encode_category_keywords()

        # Compute all text-keyword similarities
        all_sims = np.dot(text_emb, keyword_emb.T)  # (N, num_keywords)

        # Max-pool per category
        similarities = np.zeros((len(text_emb), len(categories)))
        matched_info = []

        for text_idx in range(len(text_emb)):
            text_matched = {"matched_keyword": None}
            max_sim_overall = -1.0

            for cat_idx, category in enumerate(categories):
                # Find all keyword indices for this category
                keyword_indices = [
                    i for i, (cat, kw) in enumerate(keyword_metadata)
                    if cat == category
                ]

                # Max-pool across keywords in this category
                if keyword_indices:
                    cat_sims = all_sims[text_idx, keyword_indices]
                    max_sim = cat_sims.max()
                    best_kw_idx_local = cat_sims.argmax()
                    best_kw_idx_global = keyword_indices[best_kw_idx_local]

                    similarities[text_idx, cat_idx] = max_sim

                    # Track overall best match for this text
                    if max_sim > max_sim_overall:
                        max_sim_overall = max_sim
                        _, best_keyword = keyword_metadata[best_kw_idx_global]
                        text_matched = {"matched_keyword": best_keyword}

            matched_info.append(text_matched)

        # Log top matched keywords
        keyword_counts = {}
        for info in matched_info:
            if info["matched_keyword"]:
                kw = info["matched_keyword"]
                keyword_counts[kw] = keyword_counts.get(kw, 0) + 1

        if keyword_counts:
            top_keywords = sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            logger.info("Top 10 matched keywords:")
            for kw, count in top_keywords:
                logger.info(f"  '{kw}': {count:,}")

        return similarities, matched_info

    def _compute_combined_similarities(
        self,
        text_emb: np.ndarray,
        categories: list[str]
    ) -> tuple[np.ndarray, list[dict]]:
        """Compute weighted combination of label and keyword similarities."""
        logger.info(
            f"Computing combined similarities "
            f"(keyword_weight={self.keyword_weight:.2f}, label_weight={self.label_weight:.2f})"
        )

        # Get both similarity matrices
        label_sims, _ = self._compute_label_similarities(text_emb, categories)
        keyword_sims, matched_info = self._compute_keyword_similarities(text_emb, categories)

        # Weighted fusion
        total_weight = self.keyword_weight + self.label_weight
        if total_weight == 0:
            logger.warning("Both weights are 0, defaulting to keyword_only")
            return keyword_sims, matched_info

        combined = (
            (self.keyword_weight * keyword_sims) +
            (self.label_weight * label_sims)
        ) / total_weight

        return combined, matched_info
