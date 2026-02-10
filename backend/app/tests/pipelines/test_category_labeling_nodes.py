"""Unit tests for category labeling Hamilton nodes.

Uses keyword-only method by default for fast execution.
Embedding tests are marked with @pytest.mark.slow.
"""

import polars as pl
import pytest

from app.pipelines.ortps import category_labeling_nodes
from app.pipelines.ortps.validation import CATEGORY_LABELING_CONTRACT


class TestCategoryLabeler:
    def test_creates_instance(self):
        labeler = category_labeling_nodes.category_labeler(
            embedding_model_name="sentence-transformers/all-MiniLM-L6-v2",
            embedding_threshold=0.45,
            embedding_device="cpu",
        )
        assert labeler.similarity_threshold == 0.45
        assert labeler.model_name == "sentence-transformers/all-MiniLM-L6-v2"


class TestDfLabeled:
    def test_keyword_method_adds_columns(self, sample_english_df):
        labeler = category_labeling_nodes.category_labeler(
            embedding_model_name="sentence-transformers/all-MiniLM-L6-v2",
            embedding_threshold=0.45,
            embedding_device="cpu",
        )
        df = category_labeling_nodes.df_labeled(
            df_english=sample_english_df,
            category_labeler=labeler,
            labeling_method="keyword",
            text_col="grievance",
        )

        assert "ortps_category" in df.columns
        assert "ortps_method" in df.columns
        assert "ortps_confidence" in df.columns

    def test_keyword_detects_known_categories(self, sample_english_df):
        labeler = category_labeling_nodes.category_labeler(
            embedding_model_name="sentence-transformers/all-MiniLM-L6-v2",
            embedding_threshold=0.45,
            embedding_device="cpu",
        )
        df = category_labeling_nodes.df_labeled(
            df_english=sample_english_df,
            category_labeler=labeler,
            labeling_method="keyword",
            text_col="grievance",
        )

        categories = df["ortps_category"].drop_nulls().unique().to_list()
        # Should detect at least caste, income, scholarship from fixture data
        assert len(categories) >= 3

    def test_passes_validation_contract(self, sample_english_df):
        labeler = category_labeling_nodes.category_labeler(
            embedding_model_name="sentence-transformers/all-MiniLM-L6-v2",
            embedding_threshold=0.45,
            embedding_device="cpu",
        )
        df = category_labeling_nodes.df_labeled(
            df_english=sample_english_df,
            category_labeler=labeler,
            labeling_method="keyword",
            text_col="grievance",
        )

        violations = CATEGORY_LABELING_CONTRACT.validate(df)
        assert violations == [], f"Validation violations: {violations}"

    @pytest.mark.slow
    def test_hybrid_method(self, sample_english_df):
        """Slow test: loads SentenceTransformer model."""
        labeler = category_labeling_nodes.category_labeler(
            embedding_model_name="sentence-transformers/all-MiniLM-L6-v2",
            embedding_threshold=0.45,
            embedding_device="cpu",
        )
        df = category_labeling_nodes.df_labeled(
            df_english=sample_english_df,
            category_labeler=labeler,
            labeling_method="hybrid",
            text_col="grievance",
        )

        assert "ortps_category" in df.columns
        violations = CATEGORY_LABELING_CONTRACT.validate(df)
        assert violations == []
