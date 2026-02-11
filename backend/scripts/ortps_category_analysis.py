#!/usr/bin/env python3
"""
ORTPS Category Analysis Pipeline

Analyzes grievance text for ORTPS-related categories:
- Improved language detection (2-stage with tuned threshold)
- Category labeling (expanded ORTPS services) using hybrid approach
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
from pathlib import Path

import pandas as pd
import polars as pl
from loguru import logger

from app.config import directories, load_duckdb
from app.utils import wordcloud


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
        - Index: Category
        - Columns: Multi-index (Fiscal Year, Metric)
        - Values: Properly formatted numbers
    """
    # Convert to pandas for multi-index support
    df_pd = df.to_pandas()

    # Pivot to wide format (transposed: categories as rows, years as columns)
    wide = df_pd.pivot(
        index="ortps_category",
        columns="july_year",
        values=["count", "share_pct"]
    )

    # Reorder multi-index: (year, metric) instead of (metric, year)
    wide = wide.swaplevel(axis=1).sort_index(axis=1)

    # Rename columns for clarity
    wide.columns.names = ["Fiscal Year", "Metric"]
    wide = wide.rename(columns={
        "count": "Count",
        "share_pct": "% of Total"
    }, level=1)

    # Rename index
    wide.index.name = "Category"

    # Sort by count
    wide = wide.sort_values(by=[(year, "Count") for year in sorted(df_pd["july_year"].unique(), reverse=True)], ascending=False)

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
    - Top row: Fiscal Year with \multicolumn
    - Second row: Metric names (Count, % of Total)
    - Index: Category names
    - Data rows: Formatted numbers (counts with commas, percentages with %)

    Parameters
    ----------
    df : pd.DataFrame
        Multi-index DataFrame with (Fiscal Year, Metric) columns and Category index
    output_path : Path
        Output .tex file path
    caption : str
        Table caption
    label : str
        LaTeX label for cross-referencing
    """
    # Fill NaN values with None so they render better
    df = df.fillna("")

    # Escape & characters in index (category names) for LaTeX
    df.index = df.index.str.replace("&", "\\&", regex=False)

    # Create formatters for each column
    # Note: We need to use closures to avoid late binding issues
    def make_percent_formatter():
        return lambda x: f"{x:.2f}\\%" if x != "" else "---"

    def make_count_formatter():
        return lambda x: f"{int(x):,}" if x != "" else "---"

    formatters = {}
    for col in df.columns:
        year, metric = col
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
        # Add cmidrule after the fiscal year header row (first row with multicolumn)
        elif "\\multicolumn" in line and not found_category_row:
            improved_lines.append(line)
            # Add cmidrule for each fiscal year pair of columns (Count, % of Total)
            cmidrules = []
            num_years = len(df.columns) // 2
            for idx in range(num_years):
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


def export_latex_table_long(
    df: pl.DataFrame,
    output_path: Path,
    caption: str = "ORTPS Category Aggregation by Fiscal Year",
    label: str = "tab:ortps_aggregation"
) -> None:
    """
    Export long format DataFrame to LaTeX longtable format.

    Parameters
    ----------
    df : pl.DataFrame
        Long format DataFrame with columns:
        - july_year: Fiscal year
        - ortps_category: Category name
        - count: Number of grievances
        - share_pct: Percentage share
    output_path : Path
        Output .tex file path
    caption : str
        Table caption
    label : str
        LaTeX label for cross-referencing
    """
    # Convert to pandas for to_latex
    df_pd = df.to_pandas()

    # Escape & characters in category names for LaTeX
    df_pd["ortps_category"] = df_pd["ortps_category"].str.replace("&", "\\&", regex=False)

    # Rename columns for display
    df_pd = df_pd.rename(columns={
        "july_year": "Fiscal Year",
        "ortps_category": "Category",
        "count": "Count",
        "share_pct": "Share (\\%)"
    })

    # Select only the columns we want to display
    df_pd = df_pd[["Fiscal Year", "Category", "Count", "Share (\\%)"]]

    # Format the data
    df_pd["Count"] = df_pd["Count"].apply(lambda x: f"{int(x):,}")
    df_pd["Share (\\%)"] = df_pd["Share (\\%)"].apply(lambda x: f"{x:.2f}")

    # Generate LaTeX using longtable for multi-page support
    latex_str = df_pd.to_latex(
        index=False,
        caption=caption,
        label=label,
        position="htbp",
        column_format="lp{7cm}rr",
        escape=False,
        longtable=True
    )

    # Replace \hline with booktabs commands
    latex_str = latex_str.replace("\\hline", "\\toprule", 1)
    latex_str = latex_str.replace("\\hline", "\\midrule", 1)
    latex_str = latex_str.replace("\\hline", "\\bottomrule", 1)

    # Write to file
    with open(output_path, 'w') as f:
        f.write(latex_str)


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

This table presents the aggregation of ORTPS-related grievances by fiscal year (July-June) and category for FY2023 onwards.

\input{fiscal_year_aggregation.tex}

\textbf{Key Findings (FY2023-2025):}
\begin{itemize}
    \item \textbf{Ration Card dominates ORTPS grievances:} Consistently the highest volume category across all fiscal years, with 8,593 complaints (3.13\% of total) in FY2023 growing to 15,052 (3.28\%) in FY2024---a 75\% year-over-year increase. This category alone represents over 3\% of all ORTPS-related grievances.

    \item \textbf{Income Certificate shows dramatic FY2024 surge:} Volume increased 4.6$\times$ from FY2023 to FY2024 (338 $\rightarrow$ 1,542 complaints), with share nearly tripling from 0.12\% to 0.34\%. This sharp discontinuity warrants investigation into potential systemic issues, policy changes, or portal disruptions that emerged in FY2024.

    \item \textbf{Scholarship complaints show sustained growth:} Volume increased 76\% from FY2023 to FY2024 (1,074 $\rightarrow$ 1,895), with share rising from 0.39\% to 0.41\%. This trend suggests increasing demand for scholarship services and growing awareness among beneficiaries.

    \item \textbf{Caste Certificate growth lags overall trends:} While absolute numbers increased 27\% from FY2023 to FY2024 (600 $\rightarrow$ 760), the share declined from 0.22\% to 0.17\%, indicating this service is growing slower than overall ORTPS complaint volume.

    \item \textbf{FY2025 data is partial (incomplete):} All categories show lower absolute counts relative to FY2023 and FY2024, but some percentage shares are elevated (e.g., Scholarship at 0.79\% vs. 0.41\% in FY2024), indicating that data collection for FY2025 is incomplete as the fiscal year is ongoing.
\end{itemize}

\newpage

\section{Exploratory Analysis}

\subsection{Word Cloud Analysis}

The following word clouds visualize the most frequent terms in grievance text for each ORTPS category for FY2023-24 and FY2024-25.

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

        # Add category-specific notes
        if category == "Caste certificate":
            latex_content += r"""\textbf{Note:} Word frequency analysis for FY2023-25 reveals common pain points in Caste Certificate processing. Look for terms related to application status, delays, document requirements, and verification processes. Cross-year comparison can identify persistent bottlenecks versus emerging issues.

"""
        elif category == "Income certificate":
            latex_content += r"""\textbf{Note:} Given the 4.6$\times$ spike in FY2024 (Table \ref{tab:ortps_aggregation}), compare word clouds across years to identify new terms or increased frequency of specific issues that may explain this surge. Pay attention to portal-related terminology or policy changes.

"""
        elif category == "Scholarship":
            latex_content += r"""\textbf{Note:} Scholarship complaints show consistent 76\% growth from FY2023-24. Word clouds may reveal seasonal patterns (academic calendar dependencies), common delays in disbursement, or eligibility verification issues. Terms related to deadlines and urgency are likely prominent.

"""
        elif category == "Ration Card":
            latex_content += r"""\textbf{Note:} As the dominant ORTPS category with 75\% FY2023-24 growth, Ration Card word clouds are critical for understanding systemic service delivery challenges. Expect high frequency of terms related to updates, corrections, additions/deletions of members, and digitization issues (e.g., Aadhaar linking).

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
        "--embedding-strategy",
        choices=["label_only", "keyword_only", "combined"],
        default="label_only",
        help="Strategy for embedding similarity (default: label_only for backward compatibility)"
    )
    parser.add_argument(
        "--keyword-weight",
        type=float,
        default=1.0,
        help="Weight for keyword similarity in combined mode (default: 1.0)"
    )
    parser.add_argument(
        "--label-weight",
        type=float,
        default=0.5,
        help="Weight for label similarity in combined mode (default: 0.5)"
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
        "--generate-latex-wrapper",
        action="store_true",
        help="Generate LaTeX wrapper document (default: skip)"
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help="Sample size for testing (None = full dataset)"
    )

    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Validate config with Pydantic
    from app.pipelines.ortps.config import OrtpsPipelineConfig
    from app.pipelines.ortps import run_pipeline

    config = OrtpsPipelineConfig.from_argparse(args)

    # Set up logging
    log_file = args.output_dir / "ortps_analysis.log"
    logger.add(log_file, rotation="10 MB", level="INFO")
    logger.info("=" * 80)
    logger.info("ORTPS Category Analysis Pipeline")
    logger.info("=" * 80)
    logger.info(f"Configuration:")
    logger.info(f"  Database: {config.db_path}")
    logger.info(f"  Output: {config.output_dir}")
    logger.info(f"  Labeling method: {config.labeling.labeling_method}")
    if config.skip_embeddings:
        logger.info(f"  Mode: FAST (embeddings skipped)")
    logger.info(f"  Fiscal years: {config.fiscal_years}")
    logger.info(f"  Lingua threshold: {config.lang.lingua_threshold}")
    logger.info(f"  Embedding threshold: {config.labeling.embedding_threshold}")

    # 1. Load data
    logger.info("=" * 80)
    logger.info("Step 1: Loading complaints from database")
    logger.info("=" * 80)
    df = load_duckdb(config.db_path, output_format="polars")
    logger.info(f"Loaded {len(df):,} complaints")

    # Sample if requested
    if config.sample_size is not None:
        logger.info(f"Sampling {config.sample_size:,} complaints for testing")
        df = df.sample(n=min(config.sample_size, len(df)), seed=42)
        logger.info(f"Sample size: {len(df):,}")

    # 2-4. Language detection + English filtering + Category labeling (Hamilton)
    logger.info("=" * 80)
    logger.info("Steps 2-4: Running Hamilton pipeline (lang detection + labeling)")
    logger.info("=" * 80)
    result = run_pipeline(df, config)
    df_en = result["df_labeled"]

    # 5. Fiscal year aggregation
    logger.info("=" * 80)
    logger.info("Step 5: Adding fiscal year column")
    logger.info("=" * 80)
    df_en = add_fiscal_year(df_en, date_col="created_on")

    # Year distribution (before filtering)
    year_dist = df_en["july_year"].value_counts().sort("july_year")
    logger.info("Fiscal year distribution (all years in database):")
    for row in year_dist.iter_rows(named=True):
        year = row["july_year"]
        count = row["count"]
        logger.info(f"  FY {year}-{year+1}: {count:,}")

    # Filter to FY2023 onwards only
    logger.info("=" * 80)
    logger.info("Step 5b: Filtering to FY2023 onwards and before FY2025")
    logger.info("=" * 80)
    df_en = df_en.filter((pl.col("july_year") >= 2023) & (pl.col("july_year") < 2025))
    logger.info(f"Complaints after filtering to FY2023-FY2024: {len(df_en):,}")

    categories = (
        df_en["ortps_category"]
        .drop_nulls()
        .unique()
        .sort()
        .to_list()
    )

    # Year distribution (after filtering)
    year_dist_filtered = df_en["july_year"].value_counts().sort("july_year")
    logger.info("Fiscal year distribution (filtered to FY2023+):")
    for row in year_dist_filtered.iter_rows(named=True):
        year = row["july_year"]
        count = row["count"]
        logger.info(f"  FY {year}-{year+1}: {count:,}")

    logger.info("=" * 80)
    logger.info("Step 6: Aggregating by fiscal year")
    logger.info("=" * 80)
    agg_df = aggregate_by_fiscal_year(df_en, categories)

    # Save aggregation tables
    csv_long_path = config.output_dir / "fiscal_year_aggregation.csv"
    agg_df.write_csv(csv_long_path)
    logger.info(f"Saved: {csv_long_path.name}")

    # Pivot and format wide table
    pivot_df = pivot_fiscal_aggregation(agg_df)

    # Save Excel with formatting
    excel_path = config.output_dir / "fiscal_year_aggregation_wide.xlsx"
    format_excel_output(pivot_df, excel_path)
    logger.info(f"Saved: {excel_path.name}")

    # Save CSV version (without special formatting)
    csv_wide_path = config.output_dir / "fiscal_year_aggregation_wide.csv"
    pivot_df.to_csv(csv_wide_path)
    logger.info(f"Saved: {csv_wide_path.name}")

    # Save LaTeX version (wide format - for reference)
    latex_wide_path = config.output_dir / "fiscal_year_aggregation_wide.tex"
    export_latex_table(pivot_df, latex_wide_path)
    logger.info(f"Saved: {latex_wide_path.name}")

    # Save LaTeX version (long format - for main document)
    latex_long_path = config.output_dir / "fiscal_year_aggregation_long.tex"
    export_latex_table_long(agg_df, latex_long_path)
    logger.info(f"Saved: {latex_long_path.name}")

    # Create LaTeX wrapper document (only if requested)
    if config.generate_latex_wrapper:
        create_latex_wrapper(
            output_dir=config.output_dir,
            categories=categories,
            fiscal_years=config.fiscal_years
        )
        logger.info(f"Created LaTeX wrapper: ortps_analysis.tex")
    else:
        logger.info("Skipping LaTeX wrapper generation (use --generate-latex-wrapper to create)")

    # Display aggregation summary
    logger.info("Aggregation summary:")
    logger.info(f"\n{agg_df}")

    # 6. Word clouds
    if not config.skip_wordclouds:
        logger.info("=" * 80)
        logger.info("Step 7: Generating word clouds")
        logger.info("=" * 80)
        wordcloud_paths = generate_fiscal_wordclouds(
            df_en,
            categories=categories,
            fiscal_years=config.fiscal_years,
            output_dir=config.output_dir / "wordclouds",
            text_col="grievance"
        )
        logger.info(f"Generated {len(wordcloud_paths)} word clouds")
    else:
        logger.info("Skipping word cloud generation (--skip-wordclouds)")

    # 7. Save labeled dataset
    logger.info("=" * 80)
    logger.info("Step 8: Saving labeled dataset")
    logger.info("=" * 80)
    output_parquet = (
        directories.INTERIM / "grievance_complaints_ortps_labelled_fy2023.parquet"
    )
    df_en.write_parquet(output_parquet)
    logger.info(f"Saved: {output_parquet} ({len(df_en):,} rows)")

    # Final summary
    logger.info("=" * 80)
    logger.info("Pipeline complete!")
    logger.info("=" * 80)
    logger.info(f"Output directory: {config.output_dir}")
    logger.info(f"Total English complaints: {len(df_en):,}")
    labeled_count = df_en.filter(pl.col("ortps_category").is_not_null()).shape[0]
    logger.info(
        f"Labeled with ORTPS category: {labeled_count:,} "
        f"({labeled_count/len(df_en)*100:.1f}%)"
    )


if __name__ == "__main__":
    main()
