"""Integration tests: full Hamilton DAG execution and config validation."""

import polars as pl
import pytest
from pydantic import ValidationError

from app.pipelines.ortps import build_ortps_driver
from app.pipelines.ortps.config import OrtpsPipelineConfig


class TestFullPipeline:
    def test_full_dag_keyword_only(self, sample_raw_df, default_hamilton_inputs):
        dr = build_ortps_driver()

        inputs = {
            "raw_df": sample_raw_df,
            **default_hamilton_inputs,
        }

        result = dr.execute(
            ["df_labeled__validated", "lang_detection_stats"],
            inputs=inputs,
        )

        df = result["df_labeled__validated"]
        assert isinstance(df, pl.DataFrame)
        assert "ortps_category" in df.columns
        assert "grievance_lang" in df.columns

    def test_dag_lists_expected_nodes(self):
        dr = build_ortps_driver()
        available = dr.list_available_variables()
        node_names = {v.name for v in available}

        assert "df_labeled" in node_names
        assert "df_english" in node_names
        assert "df_with_language" in node_names
        assert "language_detector" in node_names
        assert "category_labeler" in node_names
        assert "df_labeled__validated" in node_names
        assert "df_english__validated" in node_names
        assert "df_with_language__validated" in node_names


class TestConfigValidation:
    def test_valid_config(self):
        config = OrtpsPipelineConfig()
        inputs = config.to_hamilton_inputs()
        assert inputs["lingua_threshold"] == 0.85
        assert inputs["embedding_threshold"] == 0.45

    def test_threshold_out_of_range(self):
        with pytest.raises(ValidationError):
            OrtpsPipelineConfig(
                lang={"lingua_threshold": 1.5}
            )

    def test_invalid_labeling_method(self):
        with pytest.raises(ValidationError):
            OrtpsPipelineConfig(
                labeling={"labeling_method": "magic"}
            )

    def test_skip_embeddings_overrides_method(self):
        """Verify from_argparse with skip_embeddings forces keyword method."""
        from argparse import Namespace

        args = Namespace(
            db_path=OrtpsPipelineConfig().db_path,
            output_dir=OrtpsPipelineConfig().output_dir,
            sample_size=None,
            lingua_threshold=0.85,
            embedding_threshold=0.45,
            labeling_method="hybrid",
            fiscal_years=[2023, 2024],
            skip_wordclouds=False,
            skip_embeddings=True,
            generate_latex_wrapper=False,
        )
        config = OrtpsPipelineConfig.from_argparse(args)
        assert config.labeling.labeling_method == "keyword"

    def test_fiscal_year_validation(self):
        with pytest.raises(ValidationError):
            OrtpsPipelineConfig(fiscal_years=[1900])
