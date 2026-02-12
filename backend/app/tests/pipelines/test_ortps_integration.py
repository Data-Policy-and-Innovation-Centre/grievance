"""Integration tests: full Hamilton DAG execution and config validation."""

import polars as pl
import pytest
from pydantic import ValidationError

from app.pipelines import ortps as ortps_pipeline
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

    def test_run_pipeline_wrapper_returns_expected_keys(self, monkeypatch):
        raw_df = pl.DataFrame({"grievance": ["need ration card"], "created_on": [None]})
        labeled_df = pl.DataFrame(
            {
                "grievance": ["need ration card"],
                "grievance_lang": ["en"],
                "ortps_category": ["Ration card"],
                "ortps_method": ["keyword"],
                "ortps_confidence": [None],
            }
        )
        category_dist = pl.DataFrame({"ortps_category": ["Ration card"], "count": [1]})
        method_dist = pl.DataFrame({"ortps_method": ["keyword"], "count": [1]})

        class FakeDriver:
            def execute(self, final_vars, inputs):
                assert "raw_df" in inputs
                assert inputs["raw_df"].equals(raw_df)
                assert "df_labeled__validated" in final_vars
                return {
                    "df_labeled__validated": labeled_df,
                    "df_with_language__validated": labeled_df,
                    "df_english__validated": labeled_df,
                    "lang_detection_stats": {"lingua_high_conf": 1},
                    "category_distribution": category_dist,
                    "method_distribution": method_dist,
                }

        monkeypatch.setattr(ortps_pipeline, "build_ortps_driver", lambda: FakeDriver())
        result = ortps_pipeline.run_pipeline(raw_df, OrtpsPipelineConfig())

        assert set(result.keys()) == {
            "df_labeled",
            "df_with_language",
            "df_english",
            "lang_detection_stats",
            "category_distribution",
            "method_distribution",
        }
        assert result["df_labeled"].equals(labeled_df)
        assert result["category_distribution"].equals(category_dist)


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

    def test_argparse_passes_embedding_strategy_and_weights(self):
        from argparse import Namespace

        args = Namespace(
            db_path=OrtpsPipelineConfig().db_path,
            output_dir=OrtpsPipelineConfig().output_dir,
            sample_size=100,
            lingua_threshold=0.8,
            embedding_threshold=0.4,
            labeling_method="hybrid",
            embedding_strategy="combined",
            keyword_weight=0.6,
            label_weight=0.4,
            fiscal_years=[2024, 2023],  # unsorted on purpose
            skip_wordclouds=True,
            skip_embeddings=False,
            generate_latex_wrapper=True,
        )

        config = OrtpsPipelineConfig.from_argparse(args)
        assert config.labeling.embedding_strategy == "combined"
        assert config.labeling.keyword_weight == 0.6
        assert config.labeling.label_weight == 0.4
        assert config.sample_size == 100
        assert config.fiscal_years == [2023, 2024]

    def test_fiscal_year_validation(self):
        with pytest.raises(ValidationError):
            OrtpsPipelineConfig(fiscal_years=[1900])
