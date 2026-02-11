"""
ORTPS analysis Hamilton pipeline.

Architecture note:
    ORTPS modules provide policy/wiring (profiles, labels, category logic) while
    reusable NLP engines live under ``app.pipelines.shared``.

Usage from scripts::

    from app.pipelines.ortps import run_pipeline
    from app.pipelines.ortps.config import OrtpsPipelineConfig

    config = OrtpsPipelineConfig.from_argparse(args)
    result = run_pipeline(raw_df, config)

Usage from notebooks::

    from app.pipelines.ortps import build_ortps_driver

    dr = build_ortps_driver()
    result = dr.execute(["df_labeled__validated"], inputs={...})
"""

from __future__ import annotations

from typing import Any

import polars as pl
from loguru import logger

from app.pipelines._driver import build_driver
from app.pipelines.ortps.config import OrtpsPipelineConfig


def build_ortps_driver():
    """Build Hamilton driver with all ORTPS pipeline modules."""
    from app.pipelines.ortps import (
        category_labeling_nodes,
        lang_detection_nodes,
    )

    return build_driver(lang_detection_nodes, category_labeling_nodes)


def run_pipeline(
    raw_df: pl.DataFrame,
    config: OrtpsPipelineConfig,
) -> dict[str, Any]:
    """
    Run the full ORTPS pipeline (lang detection + category labeling).

    Parameters
    ----------
    raw_df : pl.DataFrame
        Loaded complaints DataFrame.
    config : OrtpsPipelineConfig
        Validated pipeline configuration.

    Returns
    -------
    dict with keys:
        - "df_labeled": pl.DataFrame with all labeling columns
        - "df_with_language": pl.DataFrame with language labels
        - "df_english": pl.DataFrame filtered to English
        - "lang_detection_stats": dict of detection method counts
        - "category_distribution": pl.DataFrame summary
        - "method_distribution": pl.DataFrame summary
    """
    dr = build_ortps_driver()

    inputs = {
        "raw_df": raw_df,
        **config.to_hamilton_inputs(),
    }

    final_vars = [
        "df_labeled__validated",
        "df_with_language__validated",
        "df_english__validated",
        "lang_detection_stats",
        "category_distribution",
        "method_distribution",
    ]

    logger.info("Executing Hamilton ORTPS pipeline...")
    result = dr.execute(final_vars, inputs=inputs)
    logger.info("Hamilton ORTPS pipeline complete.")

    return {
        "df_labeled": result["df_labeled__validated"],
        "df_with_language": result["df_with_language__validated"],
        "df_english": result["df_english__validated"],
        "lang_detection_stats": result["lang_detection_stats"],
        "category_distribution": result["category_distribution"],
        "method_distribution": result["method_distribution"],
    }
