"""Tests for scripts/ortps_topic_analysis.py."""

from __future__ import annotations

from pathlib import Path

import polars as pl


class _SimpleAnalyzer:
    def __init__(self, topic_info: pl.DataFrame, topics: dict[int, list[tuple[str, float]]], n_samples: int):
        self._topic_info = topic_info
        self._topics = topics
        self.n_samples = n_samples
        self.saved_paths = []

    def get_topic_info(self) -> pl.DataFrame:
        return self._topic_info

    def get_topics(self) -> dict[int, list[tuple[str, float]]]:
        return self._topics

    def save_model(self, path: Path) -> None:
        self.saved_paths.append(path)


def test_export_sample_complaints_writes_expected_file(load_script_module, tmp_path):
    module = load_script_module("ortps_topic_analysis.py")

    topic_assignments = pl.DataFrame(
        {
            "id": [10, 11, 12],
            "grievance": ["need caste certificate", "certificate correction", "other issue"],
            "ortps_category": ["Certificates", "Certificates", "Certificates"],
            "topic_id": [0, 0, 1],
        }
    )
    analyzer = _SimpleAnalyzer(
        topic_info=pl.DataFrame({"Topic": [0, 1], "Count": [2, 1], "Name": ["certs", "other"]}),
        topics={0: [("cert", 0.9)], 1: [("other", 0.8)]},
        n_samples=3,
    )

    module.export_sample_complaints(
        df_labeled=topic_assignments,
        topic_assignments=topic_assignments,
        topic_models={"Certificates": analyzer},
        output_dir=tmp_path,
    )

    sample_file = tmp_path / "samples" / "Certificates_samples.txt"
    assert sample_file.exists()
    content = sample_file.read_text(encoding="utf-8")
    assert "ORTPS CATEGORY: Certificates" in content
    assert "TOPIC 0" in content
    assert "Sample 1 (ID:" in content


def test_export_latex_tables_skips_outlier_only_category(load_script_module, tmp_path):
    module = load_script_module("ortps_topic_analysis.py")

    valid = _SimpleAnalyzer(
        topic_info=pl.DataFrame({"Topic": [0, -1], "Count": [5, 1], "Name": ["valid", "outlier"]}),
        topics={0: [("valid", 0.9)]},
        n_samples=6,
    )
    outlier_only = _SimpleAnalyzer(
        topic_info=pl.DataFrame({"Topic": [-1], "Count": [2], "Name": ["outlier"]}),
        topics={-1: []},
        n_samples=2,
    )
    summary = pl.DataFrame(
        {
            "category": ["Certificates", "Land matters"],
            "total_complaints": [6, 2],
            "n_topics": [1, 0],
            "coverage_pct": [83.3, 0.0],
        }
    )

    module.export_latex_tables(
        topic_models={"Certificates": valid, "Land matters": outlier_only},
        topic_summary=summary,
        output_dir=tmp_path,
    )

    assert (tmp_path / "Certificates_topics.tex").exists()
    assert not (tmp_path / "Land_matters_topics.tex").exists()
    assert (tmp_path / "topic_summary.tex").exists()


def test_generate_category_table_escapes_ampersand_and_computes_share(load_script_module):
    module = load_script_module("ortps_topic_analysis.py")

    analyzer = _SimpleAnalyzer(
        topic_info=pl.DataFrame({"Topic": [3], "Count": [2], "Name": ["fallback"]}),
        topics={3: [("land", 0.9), ("mutation", 0.8)]},
        n_samples=4,
    )
    topic_info = pl.DataFrame({"Topic": [3], "Count": [2], "Name": ["ignored"]})

    latex = module.generate_category_table("Land & Matters", topic_info, analyzer)

    assert "\\caption{Land \\& Matters Sub-themes}" in latex
    assert "3 & land, mutation" in latex
    assert "& 50.0 \\\\" in latex


def test_generate_summary_table_has_totals_and_escaped_category(load_script_module):
    module = load_script_module("ortps_topic_analysis.py")
    summary = pl.DataFrame(
        {
            "category": ["Police & Legal", "Certificates"],
            "total_complaints": [30, 20],
            "n_topics": [3, 2],
            "coverage_pct": [80.0, 90.0],
        }
    )

    latex = module.generate_summary_table(summary)
    assert "Police \\& Legal" in latex
    assert "\\textbf{Total} & 50 & 5 & 85.0 \\\\" in latex


def test_main_returns_early_when_single_category_missing(load_script_module, monkeypatch):
    module = load_script_module("ortps_topic_analysis.py")
    monkeypatch.setattr(
        module.pl,
        "read_parquet",
        lambda path: pl.DataFrame({"ortps_category": ["Certificates"], "grievance": ["x"]}),
    )

    def fail_build_driver(*args, **kwargs):
        raise AssertionError("build_driver should not run when category is missing")

    monkeypatch.setattr(module, "build_driver", fail_build_driver)
    module.main(single_category="Ration card")


def test_main_runs_pipeline_exports_and_model_saves(
    load_script_module, monkeypatch, tmp_path
):
    module = load_script_module("ortps_topic_analysis.py")

    source_df = pl.DataFrame(
        {
            "id": [1, 2],
            "grievance": ["land mutation pending", "land document issue"],
            "ortps_category": ["Land & Matters", "Land & Matters"],
        }
    )
    monkeypatch.setattr(module.pl, "read_parquet", lambda path: source_df)

    class FakeTopicConfig:
        def __init__(self):
            self.output_dir = tmp_path / "topics"
            self.model_dir = tmp_path / "models"

        def to_hamilton_inputs(self) -> dict:
            return {"min_text_length": 10}

    monkeypatch.setattr(module, "TopicModelingConfig", FakeTopicConfig)

    analyzer = _SimpleAnalyzer(
        topic_info=pl.DataFrame({"Topic": [0], "Count": [2], "Name": ["land"]}),
        topics={0: [("land", 0.9)]},
        n_samples=2,
    )
    topic_assignments = source_df.with_columns(pl.Series("topic_id", [0, 0], dtype=pl.Int32))
    topic_summary = pl.DataFrame(
        {
            "category": ["Land & Matters"],
            "total_complaints": [2],
            "n_topics": [1],
            "outliers": [0],
            "coverage_pct": [100.0],
        }
    )

    class FakeDriver:
        def execute(self, outputs, inputs):
            assert outputs == ["topic_assignments", "topic_models", "topic_summary"]
            assert "df_labeled" in inputs
            assert "category_labeler" in inputs
            return {
                "topic_assignments": topic_assignments,
                "topic_models": {"Land & Matters": analyzer},
                "topic_summary": topic_summary,
            }

    monkeypatch.setattr(module, "build_driver", lambda *args, **kwargs: FakeDriver())

    export_calls = {"samples": 0, "latex": 0, "parquet": None}
    monkeypatch.setattr(module, "export_sample_complaints", lambda *args, **kwargs: export_calls.__setitem__("samples", 1))
    monkeypatch.setattr(module, "export_latex_tables", lambda *args, **kwargs: export_calls.__setitem__("latex", 1))
    monkeypatch.setattr(
        pl.DataFrame,
        "write_parquet",
        lambda self, path: export_calls.__setitem__("parquet", path),
    )

    module.main(single_category="Land & Matters")

    assert export_calls["samples"] == 1
    assert export_calls["latex"] == 1
    assert str(export_calls["parquet"]).endswith("ortps_topics_results.parquet")
    assert len(analyzer.saved_paths) == 1
    assert analyzer.saved_paths[0].name == "ortps_topics_Land_Matters.safetensors"
