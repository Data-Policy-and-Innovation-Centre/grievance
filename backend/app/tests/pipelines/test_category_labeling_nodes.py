"""Unit tests for category labeling Hamilton nodes.

Uses keyword-only method by default for fast execution.
Embedding tests are marked with @pytest.mark.slow.
"""

import polars as pl
import pytest

from app.pipelines.ortps import category_labeling_nodes
from app.pipelines.ortps.labelers import CategoryLabeler
from app.pipelines.ortps.validation import CATEGORY_LABELING_CONTRACT


EXPANDED_KEYWORD_CASES = [
    # Revenue - Certificates
    ("Revenue - Certificates", "need caste certificate urgently"),
    ("Revenue - Certificates", "legal heir certificate required"),
    ("Revenue - Certificates", "income certificate needed"),
    ("Revenue - Certificates", "income and asset certificate for ews"),
    # Revenue - Land
    ("Revenue - Land", "please issue certified copy of ror"),
    ("Revenue - Land", "encumbrance certificate for my land"),
    ("Revenue - Land", "uncontested mutation case disposal"),
    ("Revenue - Land", "mutation order of leasehold land pending"),
    ("Revenue - Land", "conversion under olr act section 8"),
    ("Revenue - Land", "conversion order of leasehold land required"),
    ("Revenue - Land", "partition of land under olr act section 19"),
    # Registration & Stamps
    ("Registration & Stamps", "certified copy of registered document needed"),
    ("Registration & Stamps", "property registration for transfer of immovable property"),
    # Transport - Driving Licence
    ("Transport - Driving Licence", "change of address in driving licence"),
    ("Transport - Driving Licence", "renewal of driving licence pending"),
    ("Transport - Driving Licence", "apply for learner's licence"),
    ("Transport - Driving Licence", "issue of driving licence"),
    # Transport - Vehicle
    ("Transport - Vehicle", "certified copy of registration certificate for vehicle"),
    ("Transport - Vehicle", "transfer of vehicle ownership request"),
    # Police
    ("Police", "employee verification request pending"),
    ("Police", "character verification pending"),
    ("Police", "copy of fir needed"),
    # Municipal - Building
    ("Municipal - Building", "building plan approval by ulb"),
    ("Municipal - Building", "permission for addition/alteration of house"),
    ("Municipal - Building", "fire safety certificate required"),
    ("Municipal - Building", "mortgage permission request"),
    ("Municipal - Building", "issue of conveyance deed"),
    # Municipal - Civic
    ("Municipal - Civic", "birth certificate issue"),
    ("Municipal - Civic", "marriage certificate registration"),
    ("Municipal - Civic", "trade licence provisional certificate"),
    # Welfare
    ("Welfare", "sanction of scholarship pending"),
    ("Welfare", "ration card correction requested"),
    # Utilities
    ("Utilities", "pipe water connection in bmc"),
    ("Utilities", "new electricity connection for home"),
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
        # Should detect at least Revenue-Certificates, Welfare from fixture data
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
