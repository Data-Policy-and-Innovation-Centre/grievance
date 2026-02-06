#!/usr/bin/env python3
"""
ORTPS Category Analysis Pipeline

Analyzes grievance text for ORTPS-related categories:
- Improved language detection (2-stage with tuned threshold)
- Category labeling (Caste/Income/Scholarship/Ration Card) using hybrid approach
- Fiscal year aggregation (July-June)
- Word cloud generation per category per FY

Usage:
    python scripts/ortps_category_analysis.py \\
        --db-path data/raw/grievance.db \\
        --output-dir output/ortps_analysis \\
        --labeling-method hybrid \\
        --fiscal-years 2023 2024
"""

from __future__ import annotations

import argparse
import hashlib
import pickle
import re
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
import polars as pl
from loguru import logger
from lingua import Language, LanguageDetectorBuilder
from sentence_transformers import SentenceTransformer

from app.config import directories, load_duckdb
from app.utils import wordcloud


class ImprovedLanguageDetector:
    """
    Improved two-stage language detection with tuned threshold.

    Stage 1: Non-Latin script detection via regex
    Stage 2: Lingua confidence threshold (lowered to 0.85 for better recall)
    """

    def __init__(self, confidence_threshold: float = 0.85):
        """
        Initialize language detector.

        Parameters
        ----------
        confidence_threshold : float
            Minimum confidence for English classification (default: 0.85)
        """
        # Non-Latin script patterns (Odia, Devanagari)
        self.script_re = re.compile(r'[\u0B00-\u0B7F\u0900-\u097F]')

        # Lingua detector with explicit language support
        # Note: Odia is detected via script regex in Stage 1
        self.detector = (
            LanguageDetectorBuilder
            .from_languages(Language.ENGLISH, Language.HINDI)
            .with_minimum_relative_distance(0.2)
            .build()
        )

        self.threshold = confidence_threshold

    def detect_batch(
        self,
        texts: list[str | None]
    ) -> tuple[list[str | None], dict[str, int]]:
        """
        Detect language for batch of texts.

        Parameters
        ----------
        texts : list[str | None]
            List of text strings to classify

        Returns
        -------
        labels : list[str | None]
            Language labels: 'en', 'non_en', or None
        stats : dict[str, int]
            Detection method distribution statistics
        """
        labels = [None] * len(texts)
        stats = {
            "script_filtered": 0,
            "lingua_high_conf": 0,
            "lingua_low_conf": 0,
            "null": 0
        }

        # Stage 1: Script detection
        latin_candidates = []
        for i, t in enumerate(texts):
            if t is None or not str(t).strip():
                stats["null"] += 1
                continue

            s = str(t)
            if self.script_re.search(s):
                labels[i] = 'non_en'
                stats["script_filtered"] += 1
            else:
                latin_candidates.append((i, s))

        if not latin_candidates:
            return labels, stats

        # Stage 2: Lingua batch processing
        idxs, vals = zip(*latin_candidates)
        en_scores = self.detector.compute_language_confidence_in_parallel(
            list(vals), Language.ENGLISH
        )

        for i, score in zip(idxs, en_scores):
            if score >= self.threshold:
                labels[i] = 'en'
                stats["lingua_high_conf"] += 1
            else:
                labels[i] = 'non_en'
                stats["lingua_low_conf"] += 1

        return labels, stats


class CategoryLabeler:
    """
    Hybrid category labeling: keyword matching + embedding similarity.

    Categories:
    - Caste certificate
    - Income certificate
    - Scholarship
    - Ration Card
    """

    # Category-specific keywords (case-insensitive)
    CATEGORY_KEYWORDS = {
        "Caste certificate": [
            "caste certificate", "sc certificate", "st certificate",
            "obc certificate", "sebc certificate", "creamy layer",
            "caste validity", "community certificate"
        ],
        "Income certificate": [
            "income certificate", "annual income", "income proof",
            "income verification", "family income"
        ],
        "Scholarship": [
            "scholarship", "post matric", "pre matric", "oasis",
            "national scholarship", "merit scholarship", "sc scholarship",
            "st scholarship", "minority scholarship"
        ],
        "Ration Card": [
            "ration card", "food security", "aay card", "bpl card",
            "phh card", "antyodaya", "priority household", "pds card"
        ]
    }

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        similarity_threshold: float = 0.45,
        device: str | None = None
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
        """
        self.model_name = model_name
        self.similarity_threshold = similarity_threshold
        self.device = device
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
        method: Literal["keyword", "embedding", "hybrid"] = "hybrid"
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

        Returns
        -------
        pl.DataFrame
            DataFrame with new columns:
            - ortps_category: Matched category name
            - ortps_method: Detection method (keyword/embedding/none)
            - ortps_confidence: Similarity score (for embedding matches)
        """
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
                    df = self._add_embedding_labels(df, df_to_embed, text_col)
            else:
                logger.info(f"Running embedding on all {len(df):,} texts")
                df = self._add_embedding_labels(df, df, text_col)

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
        text_col: str
    ) -> pl.DataFrame:
        """Embedding similarity for unmatched texts."""
        # Encode category labels
        categories = list(self.CATEGORY_KEYWORDS.keys())
        logger.info("Encoding category labels...")
        category_emb = self.model.encode(
            categories,
            normalize_embeddings=True,
            show_progress_bar=False
        )

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

        # Compute similarities
        similarities = np.dot(text_emb, category_emb.T)  # (N, 4)
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
                embedding_results.append({
                    "category": categories[cat_idx],
                    "method": "embedding",
                    "confidence": float(sim)
                })
            else:
                embedding_results.append({
                    "category": None,
                    "method": None,
                    "confidence": None
                })

        # Create DataFrame with embedding results
        embedding_df = pl.DataFrame(embedding_results).rename({
            "category": "emb_category",
            "method": "emb_method",
            "confidence": "emb_confidence"
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
        df_to_embed = df_to_embed.with_columns([
            pl.coalesce([pl.col("ortps_category"), pl.col("emb_category")]).alias("ortps_category"),
            pl.coalesce([pl.col("ortps_method"), pl.col("emb_method")]).alias("ortps_method"),
            pl.coalesce([pl.col("ortps_confidence"), pl.col("emb_confidence")]).alias("ortps_confidence")
        ]).drop(["_embed_idx", "emb_category", "emb_method", "emb_confidence"])

        # Merge back with original DataFrame
        # For rows that were embedded, update their values
        if "ortps_category" not in df.columns:
            df = df.with_columns([
                pl.lit(None).alias("ortps_category"),
                pl.lit(None).alias("ortps_method"),
                pl.lit(None, dtype=pl.Float64).alias("ortps_confidence")
            ])

        # Update rows that were processed
        df = df.update(df_to_embed)

        # Log statistics
        matched = above_threshold.sum()
        logger.info(
            f"Embedding matching: {matched:,} texts matched "
            f"({matched/len(texts)*100:.1f}% of processed)"
        )

        return df


def add_fiscal_year(
    df: pl.DataFrame,
    date_col: str = "created_on"
) -> pl.DataFrame:
    """
    Add fiscal year column (July-June).

    Examples:
        - 2023-08-15 → FY 2023-24 (july_year=2023)
        - 2024-06-30 → FY 2023-24 (july_year=2023)
        - 2024-07-01 → FY 2024-25 (july_year=2024)

    Parameters
    ----------
    df : pl.DataFrame
        Input DataFrame with date column
    date_col : str
        Name of date column

    Returns
    -------
    pl.DataFrame
        DataFrame with added july_year column
    """
    return df.with_columns([
        pl.when(pl.col(date_col).dt.month() >= 7)
        .then(pl.col(date_col).dt.year())
        .otherwise(pl.col(date_col).dt.year() - 1)
        .alias("july_year")
    ])


def aggregate_by_fiscal_year(
    df: pl.DataFrame,
    categories: list[str]
) -> pl.DataFrame:
    """
    Aggregate counts and percentages per fiscal year per category.

    Parameters
    ----------
    df : pl.DataFrame
        Input DataFrame with july_year and ortps_category columns
    categories : list[str]
        List of categories to include

    Returns
    -------
    pl.DataFrame
        Aggregation table with columns:
        - july_year: Fiscal year
        - ortps_category: Category name
        - count: Number of grievances
        - total_year: Total grievances that year
        - share_pct: Percentage share
    """
    # Total complaints per year
    year_totals = (
        df.group_by("july_year")
        .len()
        .rename({"len": "total_year"})
    )

    # Category counts per year
    category_counts = (
        df.group_by(["july_year", "ortps_category"])
        .len()
        .rename({"len": "count"})
        .filter(pl.col("ortps_category").is_in(categories))
    )

    # Join and calculate shares
    result = (
        category_counts
        .join(year_totals, on="july_year", how="left")
        .with_columns([
            (pl.col("count") / pl.col("total_year") * 100)
            .round(2)
            .alias("share_pct")
        ])
        .sort(["july_year", "ortps_category"])
    )

    return result


def pivot_fiscal_aggregation(df: pl.DataFrame) -> pd.DataFrame:
    """
    Convert aggregation to wide format with multi-index columns.

    Parameters
    ----------
    df : pl.DataFrame
        Long format aggregation table

    Returns
    -------
    pd.DataFrame
        Wide format DataFrame with:
        - Index: Fiscal Year (no commas)
        - Columns: Multi-index (Category, Metric)
        - Values: Properly formatted numbers
    """
    # Convert to pandas for multi-index support
    df_pd = df.to_pandas()

    # Pivot to wide format
    wide = df_pd.pivot(
        index="july_year",
        columns="ortps_category",
        values=["count", "share_pct"]
    )

    # Reorder multi-index: (category, metric) instead of (metric, category)
    wide = wide.swaplevel(axis=1).sort_index(axis=1)

    # Rename columns for clarity
    wide.columns.names = ["Category", "Metric"]
    wide = wide.rename(columns={
        "count": "Count",
        "share_pct": "% of Total"
    }, level=1)

    # Rename index
    wide.index.name = "Fiscal Year"

    return wide


def format_excel_output(
    df: pd.DataFrame,
    output_path: Path
) -> None:
    """
    Export DataFrame to Excel with proper formatting.

    Parameters
    ----------
    df : pd.DataFrame
        Multi-index DataFrame to export
    output_path : Path
        Output Excel file path
    """
    # Create Excel writer with xlsxwriter engine
    with pd.ExcelWriter(output_path, engine='xlsxwriter') as writer:
        # Write DataFrame
        df.to_excel(writer, sheet_name='ORTPS Analysis')

        # Get workbook and worksheet
        workbook = writer.book
        worksheet = writer.sheets['ORTPS Analysis']

        # Define formats
        percent_format = workbook.add_format({
            'num_format': '0.0"%"',
            'align': 'right'
        })

        count_format = workbook.add_format({
            'num_format': '#,##0',
            'align': 'right'
        })

        year_format = workbook.add_format({
            'num_format': '0',  # No commas for years
            'align': 'center',
            'bold': True
        })

        header_format = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'border': 1
        })

        # Apply year format to index column (column A)
        for row_idx in range(3, 3 + len(df)):  # Start after headers
            worksheet.write(row_idx, 0, df.index[row_idx - 3], year_format)

        # Apply formatting to data columns
        for col_idx, (category, metric) in enumerate(df.columns, start=1):
            if metric == "% of Total":
                # Apply percentage format
                # Note: data is already in percentage form (2.74 means 2.74%)
                for row_idx in range(3, 3 + len(df)):
                    cell_value = df.iloc[row_idx - 3, col_idx - 1]
                    if pd.notna(cell_value):
                        worksheet.write(row_idx, col_idx, cell_value, percent_format)
            else:  # Count
                # Apply count format
                for row_idx in range(3, 3 + len(df)):
                    cell_value = df.iloc[row_idx - 3, col_idx - 1]
                    if pd.notna(cell_value):
                        worksheet.write(row_idx, col_idx, int(cell_value), count_format)

        # Auto-adjust column widths
        for i, col in enumerate(df.columns):
            max_len = max(
                len(str(col[0])),  # Category name
                len(str(col[1])),  # Metric name
                12  # Minimum width
            )
            worksheet.set_column(i + 1, i + 1, max_len + 2)

        # Set index column width
        worksheet.set_column(0, 0, 12)


def export_latex_table(
    df: pd.DataFrame,
    output_path: Path,
    caption: str = "ORTPS Category Aggregation by Fiscal Year",
    label: str = "tab:ortps_aggregation"
) -> None:
    r"""
    Export multi-index DataFrame to LaTeX booktabs format.

    Handles multi-index columns with proper formatting:
    - Top row: Category names with \multicolumn
    - Second row: Metric names (Count, % of Total)
    - Data rows: Formatted numbers (counts with commas, percentages with %)

    Parameters
    ----------
    df : pd.DataFrame
        Multi-index DataFrame with (Category, Metric) columns
    output_path : Path
        Output .tex file path
    caption : str
        Table caption
    label : str
        LaTeX label for cross-referencing
    """
    # Fill NaN values with None so they render better
    df = df.fillna("")

    # Create formatters for each column
    # Note: We need to use closures to avoid late binding issues
    def make_percent_formatter():
        return lambda x: f"{x:.2f}\\%" if x != "" else "---"

    def make_count_formatter():
        return lambda x: f"{int(x):,}" if x != "" else "---"

    formatters = {}
    for col in df.columns:
        category, metric = col
        if metric == "% of Total":
            formatters[col] = make_percent_formatter()
        else:  # Count
            formatters[col] = make_count_formatter()

    # Generate base LaTeX table
    latex_str = df.to_latex(
        column_format="l" + "r" * len(df.columns),
        formatters=formatters,
        escape=False,  # Don't escape % signs we added
        multicolumn=True,
        multicolumn_format="c",
        caption=caption,
        label=label,
        position="htbp"
    )

    # Post-process to improve formatting
    lines = latex_str.split("\n")
    improved_lines = []
    found_category_row = False

    for i, line in enumerate(lines):
        # Replace \hline with booktabs commands
        if "\\hline" in line:
            if i < 5:  # Top rules (before header)
                improved_lines.append("\\toprule")
            elif i + 1 < len(lines) and "\\end{tabular}" in lines[i + 1]:
                improved_lines.append("\\bottomrule")
            else:
                improved_lines.append("\\midrule")
        # Add cmidrule after the category header row (first row with multicolumn)
        elif "\\multicolumn" in line and not found_category_row:
            improved_lines.append(line)
            # Add cmidrule for each category pair of columns
            cmidrules = []
            num_categories = len(df.columns) // 2
            for idx in range(num_categories):
                start_col = 2 + idx * 2
                end_col = start_col + 1
                cmidrules.append(f"\\cmidrule(lr){{{start_col}-{end_col}}}")
            improved_lines.append(" ".join(cmidrules))
            found_category_row = True
        # Wrap tabular in resizebox for auto-sizing
        elif "\\begin{tabular}" in line:
            improved_lines.append("\\resizebox{\\textwidth}{!}{%")
            improved_lines.append(line)
        elif "\\end{tabular}" in line:
            improved_lines.append(line)
            improved_lines.append("}")
        else:
            improved_lines.append(line)

    # Write to file
    with open(output_path, 'w') as f:
        f.write("\n".join(improved_lines))


def create_latex_wrapper(
    output_dir: Path,
    categories: list[str],
    fiscal_years: list[int]
) -> None:
    """
    Create main LaTeX wrapper document for ORTPS analysis.

    Generates a complete LaTeX document with:
    - Title page, TOC, list of tables/figures
    - Main Exhibits section with aggregation table
    - Exploratory section with word cloud subfigures

    Parameters
    ----------
    output_dir : Path
        Directory containing analysis outputs
    categories : list[str]
        List of ORTPS categories
    fiscal_years : list[int]
        List of fiscal year start years
    """
    # Map category names for display
    category_display = {
        "Caste certificate": "Caste Certificate",
        "Income certificate": "Income Certificate",
        "Ration Card": "Ration Card",
        "Scholarship": "Scholarship"
    }

    # Start building LaTeX content
    latex_content = r"""\documentclass[11pt,a4paper]{article}

% Packages
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{booktabs}
\usepackage{graphicx}
\usepackage{subcaption}
\usepackage[margin=1in]{geometry}
\usepackage{hyperref}
\usepackage{longtable}
\usepackage{pdflscape}

% Title information
\title{ORTPS Analysis}
\author{Data, Policy and Innovation Centre}
\date{\today}

\begin{document}

\maketitle
\tableofcontents
\newpage

\listoftables
\listoffigures
\newpage

\section{Main Exhibits}

\subsection{Fiscal Year Aggregation}

This table presents the aggregation of ORTPS-related grievances by fiscal year (July-June) and category.

\begin{landscape}
\input{fiscal_year_aggregation_wide.tex}
\end{landscape}

\newpage

\section{Exploratory Analysis}

\subsection{Word Cloud Analysis}

The following word clouds visualize the most frequent terms in grievance text for each ORTPS category across fiscal years.

"""

    # Generate figure blocks for each category
    for category in categories:
        display_name = category_display.get(category, category)
        # Clean category name for file paths (replace spaces with underscores)
        file_category = category.replace(" ", "_")

        latex_content += f"""% {display_name}
\\begin{{figure}}[htbp]
\\centering
"""

        # Add subfigures for each fiscal year
        for i, year in enumerate(fiscal_years):
            next_year = year + 1
            img_path = f"wordclouds/{file_category}_FY{year}_{next_year}.png"

            # Check if this is the last subfigure in the row
            hfill = "\\hfill\n" if i < len(fiscal_years) - 1 else "\n"

            latex_content += f"""\\begin{{subfigure}}[b]{{0.48\\textwidth}}
    \\centering
    \\includegraphics[width=\\textwidth]{{{img_path}}}
    \\caption{{FY {year}-{str(next_year)[2:]}}}
    \\label{{fig:{file_category.lower()}_{year}}}
\\end{{subfigure}}
{hfill}"""

        # Clean label for figure
        fig_label = file_category.lower()

        latex_content += f"""\\caption{{{display_name} Grievances}}
\\label{{fig:{fig_label}}}
\\end{{figure}}

"""

    latex_content += r"""\end{document}
"""

    # Write to file
    wrapper_path = output_dir / "ortps_analysis.tex"
    with open(wrapper_path, 'w') as f:
        f.write(latex_content)


def generate_fiscal_wordclouds(
    df: pl.DataFrame,
    categories: list[str],
    fiscal_years: list[int],
    output_dir: Path,
    text_col: str = "grievance"
) -> dict[tuple[str, int], Path]:
    """
    Generate word clouds for each category × fiscal year combination.

    Parameters
    ----------
    df : pl.DataFrame
        Input DataFrame with july_year and ortps_category columns
    categories : list[str]
        List of categories
    fiscal_years : list[int]
        List of fiscal year start years (e.g., [2023, 2024])
    output_dir : Path
        Directory to save word cloud images
    text_col : str
        Name of text column

    Returns
    -------
    dict[tuple[str, int], Path]
        Mapping of (category, fiscal_year) to saved image path
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    saved_paths = {}

    for fy in fiscal_years:
        for category in categories:
            # Filter data
            df_subset = df.filter(
                (pl.col("july_year") == fy) &
                (pl.col("ortps_category") == category)
            )

            if len(df_subset) == 0:
                logger.warning(f"No data for {category} in FY {fy}-{fy+1}")
                continue

            logger.info(
                f"Generating wordcloud for {category} FY {fy}-{fy+1} "
                f"({len(df_subset):,} texts)"
            )

            # Custom stopwords (category name words)
            category_words = category.lower().split()
            custom_stopwords = category_words + ["certificate", "card"]

            # Generate wordcloud
            wc = wordcloud(
                df_subset,
                column=text_col,
                custom_stopwords=custom_stopwords
            )

            # Save to file
            output_path = output_dir / f"{category.replace(' ', '_')}_FY{fy}_{fy+1}.png"
            wc.to_file(str(output_path))

            saved_paths[(category, fy)] = output_path
            logger.info(f"Saved: {output_path.name}")

    return saved_paths


def main():
    """Main pipeline function."""
    parser = argparse.ArgumentParser(
        description="ORTPS category analysis pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=directories.RAW_DATA / "grievance.db",
        help="Path to SQLite database"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=directories.OUTPUT / "ortps_analysis",
        help="Output directory for results"
    )
    parser.add_argument(
        "--labeling-method",
        choices=["keyword", "embedding", "hybrid"],
        default="hybrid",
        help="Category labeling method"
    )
    parser.add_argument(
        "--fiscal-years",
        nargs="+",
        type=int,
        default=[2023, 2024],
        help="FY start years (e.g., 2023 for FY 2023-24)"
    )
    parser.add_argument(
        "--lingua-threshold",
        type=float,
        default=0.85,
        help="Language confidence threshold"
    )
    parser.add_argument(
        "--embedding-threshold",
        type=float,
        default=0.45,
        help="Category similarity threshold"
    )
    parser.add_argument(
        "--skip-wordclouds",
        action="store_true",
        help="Skip word cloud generation"
    )
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="Skip embedding computation, use keyword matching only (fast mode, ~5 min)"
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help="Sample size for testing (None = full dataset)"
    )

    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Handle --skip-embeddings flag
    if args.skip_embeddings:
        if args.labeling_method != "keyword":
            logger.warning(
                f"--skip-embeddings flag set, overriding "
                f"--labeling-method {args.labeling_method} → keyword"
            )
        args.labeling_method = "keyword"

    # Set up logging
    log_file = args.output_dir / "ortps_analysis.log"
    logger.add(log_file, rotation="10 MB", level="INFO")
    logger.info("=" * 80)
    logger.info("ORTPS Category Analysis Pipeline")
    logger.info("=" * 80)
    logger.info(f"Configuration:")
    logger.info(f"  Database: {args.db_path}")
    logger.info(f"  Output: {args.output_dir}")
    logger.info(f"  Labeling method: {args.labeling_method}")
    if args.skip_embeddings:
        logger.info(f"  Mode: FAST (embeddings skipped)")
    logger.info(f"  Fiscal years: {args.fiscal_years}")
    logger.info(f"  Lingua threshold: {args.lingua_threshold}")
    logger.info(f"  Embedding threshold: {args.embedding_threshold}")

    # 1. Load data
    logger.info("=" * 80)
    logger.info("Step 1: Loading complaints from database")
    logger.info("=" * 80)
    df = load_duckdb(args.db_path, output_format="polars")
    logger.info(f"Loaded {len(df):,} complaints")

    # Sample if requested
    if args.sample_size is not None:
        logger.info(f"Sampling {args.sample_size:,} complaints for testing")
        df = df.sample(n=min(args.sample_size, len(df)), seed=42)
        logger.info(f"Sample size: {len(df):,}")

    # 2. Language detection
    logger.info("=" * 80)
    logger.info("Step 2: Detecting language (2-stage improved)")
    logger.info("=" * 80)
    detector = ImprovedLanguageDetector(confidence_threshold=args.lingua_threshold)
    labels, stats = detector.detect_batch(df["grievance"].to_list())
    df = df.with_columns(pl.Series("grievance_lang", labels))

    logger.info("Language detection statistics:")
    for method, count in stats.items():
        logger.info(f"  {method}: {count:,} ({count/len(df)*100:.2f}%)")

    # Distribution
    lang_dist = df["grievance_lang"].value_counts().sort("grievance_lang")
    logger.info("Language distribution:")
    for row in lang_dist.iter_rows(named=True):
        lang = row["grievance_lang"]
        count = row["count"]
        logger.info(f"  {lang}: {count:,} ({count/len(df)*100:.2f}%)")

    # 3. Filter to English
    logger.info("=" * 80)
    logger.info("Step 3: Filtering to English complaints")
    logger.info("=" * 80)
    df_en = df.filter(pl.col("grievance_lang") == "en")
    logger.info(
        f"English complaints: {len(df_en):,} ({len(df_en)/len(df)*100:.1f}%)"
    )

    # 4. Category labeling
    logger.info("=" * 80)
    logger.info(f"Step 4: Labeling categories ({args.labeling_method} method)")
    if args.labeling_method == "keyword":
        logger.info("Using keyword-only matching (embeddings skipped - FAST MODE)")
    logger.info("=" * 80)
    labeler = CategoryLabeler(similarity_threshold=args.embedding_threshold)
    df_en = labeler.label_dataframe(df_en, method=args.labeling_method)

    # Category distribution
    categories = ["Caste certificate", "Income certificate", "Scholarship", "Ration Card"]
    category_dist = (
        df_en["ortps_category"]
        .value_counts()
        .sort("ortps_category")
    )
    logger.info("Category distribution:")
    for row in category_dist.iter_rows(named=True):
        cat = row["ortps_category"]
        count = row["count"]
        logger.info(f"  {cat}: {count:,} ({count/len(df_en)*100:.2f}%)")

    # Method distribution
    method_dist = df_en["ortps_method"].value_counts().sort("ortps_method")
    logger.info("Labeling method distribution:")
    for row in method_dist.iter_rows(named=True):
        method = row["ortps_method"]
        count = row["count"]
        logger.info(f"  {method}: {count:,} ({count/len(df_en)*100:.2f}%)")

    # 5. Fiscal year aggregation
    logger.info("=" * 80)
    logger.info("Step 5: Adding fiscal year column")
    logger.info("=" * 80)
    df_en = add_fiscal_year(df_en, date_col="created_on")

    # Year distribution
    year_dist = df_en["july_year"].value_counts().sort("july_year")
    logger.info("Fiscal year distribution:")
    for row in year_dist.iter_rows(named=True):
        year = row["july_year"]
        count = row["count"]
        logger.info(f"  FY {year}-{year+1}: {count:,}")

    logger.info("=" * 80)
    logger.info("Step 6: Aggregating by fiscal year")
    logger.info("=" * 80)
    agg_df = aggregate_by_fiscal_year(df_en, categories)

    # Save aggregation tables
    csv_long_path = args.output_dir / "fiscal_year_aggregation.csv"
    agg_df.write_csv(csv_long_path)
    logger.info(f"Saved: {csv_long_path.name}")

    # Pivot and format wide table
    pivot_df = pivot_fiscal_aggregation(agg_df)

    # Save Excel with formatting
    excel_path = args.output_dir / "fiscal_year_aggregation_wide.xlsx"
    format_excel_output(pivot_df, excel_path)
    logger.info(f"Saved: {excel_path.name}")

    # Save CSV version (without special formatting)
    csv_wide_path = args.output_dir / "fiscal_year_aggregation_wide.csv"
    pivot_df.to_csv(csv_wide_path)
    logger.info(f"Saved: {csv_wide_path.name}")

    # Save LaTeX version
    latex_path = args.output_dir / "fiscal_year_aggregation_wide.tex"
    export_latex_table(pivot_df, latex_path)
    logger.info(f"Saved: {latex_path.name}")

    # Create LaTeX wrapper document
    create_latex_wrapper(
        output_dir=args.output_dir,
        categories=categories,
        fiscal_years=args.fiscal_years
    )
    logger.info(f"Created LaTeX wrapper: ortps_analysis.tex")

    # Display aggregation summary
    logger.info("Aggregation summary:")
    logger.info(f"\n{agg_df}")

    # 6. Word clouds
    if not args.skip_wordclouds:
        logger.info("=" * 80)
        logger.info("Step 7: Generating word clouds")
        logger.info("=" * 80)
        wordcloud_paths = generate_fiscal_wordclouds(
            df_en,
            categories=categories,
            fiscal_years=args.fiscal_years,
            output_dir=args.output_dir / "wordclouds",
            text_col="grievance"
        )
        logger.info(f"Generated {len(wordcloud_paths)} word clouds")
    else:
        logger.info("Skipping word cloud generation (--skip-wordclouds)")

    # 7. Save labeled dataset
    logger.info("=" * 80)
    logger.info("Step 8: Saving labeled dataset")
    logger.info("=" * 80)
    output_parquet = args.output_dir / "complaints_labeled.parquet"
    df_en.write_parquet(output_parquet)
    logger.info(f"Saved: {output_parquet.name} ({len(df_en):,} rows)")

    # Final summary
    logger.info("=" * 80)
    logger.info("Pipeline complete!")
    logger.info("=" * 80)
    logger.info(f"Output directory: {args.output_dir}")
    logger.info(f"Total English complaints: {len(df_en):,}")
    labeled_count = df_en.filter(pl.col("ortps_category").is_not_null()).shape[0]
    logger.info(
        f"Labeled with ORTPS category: {labeled_count:,} "
        f"({labeled_count/len(df_en)*100:.1f}%)"
    )


if __name__ == "__main__":
    main()
