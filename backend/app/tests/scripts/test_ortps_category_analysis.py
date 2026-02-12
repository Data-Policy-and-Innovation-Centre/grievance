"""Tests for scripts/ortps_category_analysis.py."""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import pandas as pd
import polars as pl


def _build_main_args(
    output_dir: Path,
    *,
    skip_wordclouds: bool = True,
    generate_latex_wrapper: bool = False,
    sample_size: int | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        db_path=output_dir / "grievance.db",
        output_dir=output_dir,
        labeling_method="hybrid",
        fiscal_years=[2023, 2024],
        lingua_threshold=0.85,
        embedding_threshold=0.45,
        embedding_strategy="label_only",
        keyword_weight=1.0,
        label_weight=0.5,
        skip_wordclouds=skip_wordclouds,
        skip_embeddings=False,
        generate_latex_wrapper=generate_latex_wrapper,
        sample_size=sample_size,
    )


def _build_labeled_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "id": [1, 2, 3, 4],
            "grievance": [
                "need caste certificate urgently",
                "ration card not issued",
                "scholarship amount delayed",
                "land mutation pending",
            ],
            "created_on": [
                dt.datetime(2023, 8, 1),
                dt.datetime(2023, 12, 1),
                dt.datetime(2024, 2, 1),
                dt.datetime(2024, 10, 1),
            ],
            "ortps_category": [
                "Certificates",
                "Ration card",
                "Scholarship",
                "Land matters",
            ],
            "grievance_lang": ["en", "en", "en", "en"],
            "ortps_method": ["keyword", "keyword", "keyword", "keyword"],
            "ortps_confidence": [None, None, None, None],
        }
    )


def _patch_category_main_dependencies(monkeypatch, module, *, load_df: pl.DataFrame, pipeline_df: pl.DataFrame):
    monkeypatch.setattr(module, "load_duckdb", lambda *args, **kwargs: load_df)

    from app.pipelines import ortps as ortps_pkg

    monkeypatch.setattr(
        ortps_pkg,
        "run_pipeline",
        lambda raw_df, config: {"df_labeled": pipeline_df},
    )

    monkeypatch.setattr(module, "format_excel_output", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "export_latex_table", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "export_latex_table_long", lambda *args, **kwargs: None)
    monkeypatch.setattr(pl.DataFrame, "write_parquet", lambda self, path: None)


def test_add_fiscal_year_handles_june_july_boundary(load_script_module):
    module = load_script_module("ortps_category_analysis.py")
    df = pl.DataFrame(
        {
            "created_on": [
                dt.datetime(2023, 6, 30),
                dt.datetime(2023, 7, 1),
                dt.datetime(2024, 1, 15),
            ]
        }
    )

    out = module.add_fiscal_year(df)
    assert out["july_year"].to_list() == [2022, 2023, 2023]


def test_aggregate_by_fiscal_year_counts_and_share(load_script_module):
    module = load_script_module("ortps_category_analysis.py")
    df = pl.DataFrame(
        {
            "july_year": [2023, 2023, 2023, 2023, 2024, 2024],
            "ortps_category": ["A", "A", "B", "C", "A", "B"],
        }
    )

    out = module.aggregate_by_fiscal_year(df, categories=["A", "B"])
    rows = {(r["july_year"], r["ortps_category"]): r for r in out.iter_rows(named=True)}

    assert len(out) == 4
    assert rows[(2023, "A")]["count"] == 2
    assert rows[(2023, "A")]["share_pct"] == 50.0
    assert rows[(2023, "B")]["count"] == 1
    assert rows[(2023, "B")]["share_pct"] == 25.0
    assert rows[(2024, "A")]["share_pct"] == 50.0
    assert rows[(2024, "B")]["share_pct"] == 50.0
    assert all(r["ortps_category"] != "C" for r in out.iter_rows(named=True))


def test_pivot_fiscal_aggregation_shape_columns_and_sort(load_script_module):
    module = load_script_module("ortps_category_analysis.py")
    df = pl.DataFrame(
        {
            "july_year": [2023, 2023, 2024, 2024],
            "ortps_category": ["A", "B", "A", "B"],
            "count": [10, 5, 2, 20],
            "share_pct": [20.0, 10.0, 4.0, 40.0],
        }
    )

    out = module.pivot_fiscal_aggregation(df)

    assert isinstance(out, pd.DataFrame)
    assert out.index.name == "Category"
    assert out.columns.names == ["Fiscal Year", "Metric"]
    assert (2023, "Count") in out.columns
    assert (2024, "% of Total") in out.columns
    assert out.index.to_list()[0] == "B"


def test_generate_fiscal_wordclouds_skips_empty_and_saves_expected_names(
    load_script_module, monkeypatch, tmp_path
):
    module = load_script_module("ortps_category_analysis.py")
    calls = []
    saved_paths = []

    class FakeWordCloud:
        def __init__(self, label: str):
            self.label = label

        def to_file(self, output_path: str):
            saved_paths.append(Path(output_path))

    def fake_wordcloud(df_subset, column, custom_stopwords):
        calls.append(
            {
                "rows": len(df_subset),
                "column": column,
                "custom_stopwords": custom_stopwords,
            }
        )
        return FakeWordCloud("ok")

    monkeypatch.setattr(module, "wordcloud", fake_wordcloud)

    df = pl.DataFrame(
        {
            "july_year": [2023],
            "ortps_category": ["Certificates"],
            "grievance": ["certificate status pending"],
        }
    )
    out = module.generate_fiscal_wordclouds(
        df,
        categories=["Certificates", "Ration card"],
        fiscal_years=[2023],
        output_dir=tmp_path / "wordclouds",
        text_col="grievance",
    )

    assert len(calls) == 1
    assert calls[0]["rows"] == 1
    assert calls[0]["column"] == "grievance"
    assert "certificates" in calls[0]["custom_stopwords"]
    assert "certificate" in calls[0]["custom_stopwords"]
    assert "card" in calls[0]["custom_stopwords"]

    assert set(out.keys()) == {("Certificates", 2023)}
    assert saved_paths[0].name == "Certificates_FY2023_2024.png"


def test_main_skips_wordcloud_generation(load_script_module, monkeypatch, tmp_path):
    module = load_script_module("ortps_category_analysis.py")
    args = _build_main_args(tmp_path / "out", skip_wordclouds=True)
    monkeypatch.setattr(module.argparse.ArgumentParser, "parse_args", lambda self: args)

    _patch_category_main_dependencies(
        monkeypatch,
        module,
        load_df=pl.DataFrame({"grievance": ["a"]}),
        pipeline_df=_build_labeled_df(),
    )

    calls = {"wordcloud": 0}
    monkeypatch.setattr(
        module,
        "generate_fiscal_wordclouds",
        lambda *a, **k: calls.__setitem__("wordcloud", calls["wordcloud"] + 1) or {},
    )
    monkeypatch.setattr(module, "create_latex_wrapper", lambda *args, **kwargs: None)

    module.main()
    assert calls["wordcloud"] == 0


def test_main_runs_wordclouds_and_wrapper_when_enabled(
    load_script_module, monkeypatch, tmp_path
):
    module = load_script_module("ortps_category_analysis.py")
    out_dir = tmp_path / "out"
    args = _build_main_args(out_dir, skip_wordclouds=False, generate_latex_wrapper=True)
    monkeypatch.setattr(module.argparse.ArgumentParser, "parse_args", lambda self: args)

    _patch_category_main_dependencies(
        monkeypatch,
        module,
        load_df=pl.DataFrame({"grievance": ["a"]}),
        pipeline_df=_build_labeled_df(),
    )

    wrapper_calls = {"count": 0}
    wordcloud_calls = {"count": 0, "output_dir": None}

    def fake_wrapper(output_dir, categories, fiscal_years):
        wrapper_calls["count"] += 1
        assert output_dir == out_dir
        assert fiscal_years == [2023, 2024]
        assert len(categories) > 0

    def fake_wordclouds(*args, **kwargs):
        wordcloud_calls["count"] += 1
        wordcloud_calls["output_dir"] = kwargs["output_dir"]
        return {("Certificates", 2023): out_dir / "wordclouds" / "Certificates_FY2023_2024.png"}

    monkeypatch.setattr(module, "create_latex_wrapper", fake_wrapper)
    monkeypatch.setattr(module, "generate_fiscal_wordclouds", fake_wordclouds)

    module.main()

    assert wrapper_calls["count"] == 1
    assert wordcloud_calls["count"] == 1
    assert wordcloud_calls["output_dir"] == out_dir / "wordclouds"


def test_main_applies_sample_size_before_pipeline(load_script_module, monkeypatch, tmp_path):
    module = load_script_module("ortps_category_analysis.py")
    args = _build_main_args(tmp_path / "out", sample_size=2, skip_wordclouds=True)
    monkeypatch.setattr(module.argparse.ArgumentParser, "parse_args", lambda self: args)

    load_df = pl.DataFrame(
        {
            "id": [1, 2, 3, 4, 5],
            "grievance": ["a", "b", "c", "d", "e"],
        }
    )
    pipeline_df = _build_labeled_df()

    from app.pipelines import ortps as ortps_pkg

    captured = {"input_len": None}

    def fake_run_pipeline(raw_df, config):
        captured["input_len"] = len(raw_df)
        return {"df_labeled": pipeline_df}

    monkeypatch.setattr(module, "load_duckdb", lambda *args, **kwargs: load_df)
    monkeypatch.setattr(ortps_pkg, "run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(module, "format_excel_output", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "export_latex_table", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "export_latex_table_long", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "create_latex_wrapper", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "generate_fiscal_wordclouds", lambda *args, **kwargs: {})
    monkeypatch.setattr(pl.DataFrame, "write_parquet", lambda self, path: None)

    module.main()
    assert captured["input_len"] == 2

