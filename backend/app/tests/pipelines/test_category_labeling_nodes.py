"""Unit tests for category labeling Hamilton nodes.

Uses keyword-only method by default for fast execution.
Embedding tests are marked with @pytest.mark.slow.
"""

import numpy as np
import polars as pl
import pytest

from app.pipelines.ortps import category_labeling_nodes
from app.pipelines.ortps.labelers import CategoryLabeler
from app.pipelines.ortps.validation import CATEGORY_LABELING_CONTRACT


EXPANDED_KEYWORD_CASES = [
    # Certificates
    ("Certificates", "need caste certificate urgently"),
    ("Certificates", "legal heir certificate required"),
    ("Certificates", "birth certificate issue"),
    ("Certificates", "marriage certificate registration"),
    ("Certificates", "income certificate needed"),
    ("Certificates", "income and asset certificate for ews"),
    # Scholarship
    ("Scholarship", "sanction of scholarship pending"),
    # Ration card
    ("Ration card", "ration card correction requested"),
    # Land matters
    ("Land matters", "please issue certified copy of ror"),
    ("Land matters", "encumbrance certificate for my land"),
    ("Land matters", "certified copy of registered document needed"),
    ("Land matters", "property registration for transfer of immovable property"),
    ("Land matters", "mortgage permission request"),
    ("Land matters", "issue of conveyance deed"),
    ("Land matters", "uncontested mutation case disposal"),
    ("Land matters", "mutation order of leasehold land pending"),
    ("Land matters", "conversion under olr act section 8"),
    ("Land matters", "conversion order of leasehold land required"),
    ("Land matters", "partition of land under olr act section 19"),
    # Building & Construction
    ("Building & Construction", "building plan approval by ulb"),
    ("Building & Construction", "permission for addition/alteration of house"),
    ("Building & Construction", "fire safety certificate required"),
    # Utilities & Connections
    ("Utilities & Connections", "pipe water connection in bmc"),
    ("Utilities & Connections", "new electricity connection for home"),
    # Vehicle Services
    ("Vehicle Services", "certified copy of registration certificate for vehicle"),
    ("Vehicle Services", "transfer of vehicle ownership request"),
    # Police & Legal
    ("Police & Legal", "employee verification request pending"),
    ("Police & Legal", "character verification pending"),
    ("Police & Legal", "copy of fir needed"),
    ("Police & Legal", "trade licence provisional certificate"),
]


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
    def test_hybrid_keeps_row_alignment_when_embedding_updates_subset(self, monkeypatch):
        class FakeModel:
            def encode(self, texts, **kwargs):
                # Works for both complaint texts and category labels.
                return np.zeros((len(texts), 4), dtype=float)

        labeler = CategoryLabeler(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            similarity_threshold=0.99,  # Ensure no embedding matches.
            device="cpu",
        )
        labeler._model = FakeModel()

        # Avoid filesystem writes during test.
        monkeypatch.setattr(labeler, "_save_embeddings_cache", lambda *args, **kwargs: None)
        monkeypatch.setattr(labeler, "_load_embeddings_cache", lambda *args, **kwargs: None)

        df = pl.DataFrame(
            {
                "id": [1, 2, 3, 4],
                "grievance": [
                    "need caste certificate urgently",
                    "this is unrelated text that should stay unlabeled",
                    "another unrelated complaint without category signal",
                    "ration card correction requested",
                ],
            }
        )

        labeled = labeler.label_dataframe(df, text_col="grievance", method="hybrid")

        # Row identity/order must remain unchanged after hybrid merge.
        assert labeled["id"].to_list() == [1, 2, 3, 4]

        by_id = {r["id"]: r for r in labeled.iter_rows(named=True)}
        assert by_id[1]["ortps_category"] == "Certificates"
        assert by_id[1]["ortps_method"] == "keyword"
        assert by_id[4]["ortps_category"] == "Ration card"
        assert by_id[4]["ortps_method"] == "keyword"
        assert by_id[2]["ortps_category"] is None
        assert by_id[3]["ortps_category"] is None

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
        # Should detect multiple categories from fixture data.
        assert len(categories) >= 2

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

    def test_keyword_detects_expanded_categories(self):
        labeler = category_labeling_nodes.category_labeler(
            embedding_model_name="sentence-transformers/all-MiniLM-L6-v2",
            embedding_threshold=0.45,
            embedding_device="cpu",
        )
        df = pl.DataFrame({
            "grievance": [text for _, text in EXPANDED_KEYWORD_CASES],
        })
        labeled = category_labeling_nodes.df_labeled(
            df_english=df,
            category_labeler=labeler,
            labeling_method="keyword",
            text_col="grievance",
        )

        expected = [category for category, _ in EXPANDED_KEYWORD_CASES]
        assert labeled["ortps_category"].to_list() == expected

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


def test_validation_category_set_matches_labeler():
    expected = set(CategoryLabeler.CATEGORY_KEYWORDS.keys())
    spec = next(
        spec for spec in CATEGORY_LABELING_CONTRACT.columns
        if spec.name == "ortps_category"
    )
    assert spec.allowed_values == expected
