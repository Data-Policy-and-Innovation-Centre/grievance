"""ORTPS Category Crosstab Analysis.

Creates crosstab tables mapping ORTPS issue categories to departments and subcategories.

Usage:
    uv run python scripts/ortps_crosstab_analysis.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import polars as pl
from loguru import logger

from app.config import directories


def load_ortps_labeled_data() -> pl.DataFrame:
    """Load ORTPS-labeled grievances from parquet.

    Returns
    -------
    pl.DataFrame
        DataFrame filtered to ORTPS-labeled grievances only
    """
    parquet_path = directories.INTERIM / "grievance_complaints_ortps_labelled_fy2023.parquet"
    logger.info(f"Loading data from {parquet_path}")

    df = pl.read_parquet(parquet_path)

    # Filter to ORTPS-labeled only
    df_ortps = df.filter(pl.col("ortps_category").is_not_null())

    logger.info(
        f"Loaded {len(df_ortps):,} ORTPS-labeled grievances "
        f"({len(df_ortps)/len(df)*100:.1f}% of total)"
    )

    return df_ortps


def create_department_crosstab(df: pl.DataFrame) -> pl.DataFrame:
    """Create ORTPS categories (rows) × Departments (cols) crosstab.

    Parameters
    ----------
    df : pl.DataFrame
        DataFrame with ortps_category and dept columns

    Returns
    -------
    pl.DataFrame
        Crosstab with counts and share percentages
    """
    # Count by ORTPS category × Department
    dept_counts = (
        df.filter(pl.col("dept").is_not_null())
        .group_by(["ortps_category", "dept"])
        .len()
        .rename({"len": "count"})
    )

    # Calculate row totals (total per ORTPS category)
    dept_totals = dept_counts.group_by("ortps_category").agg(
        pl.col("count").sum().alias("total")
    )

    # Join and calculate shares
    dept_with_shares = (
        dept_counts.join(dept_totals, on="ortps_category", how="left").with_columns(
            [(pl.col("count") / pl.col("total") * 100).round(2).alias("share_pct")]
        )
    )

    logger.info(f"Department crosstab: {dept_counts['ortps_category'].n_unique()} ORTPS categories × {dept_counts['dept'].n_unique()} departments")

    return dept_with_shares


def create_subcategory_crosstab(df: pl.DataFrame) -> pl.DataFrame:
    """Create ORTPS categories (rows) × Subcategories (cols) crosstab.

    Parameters
    ----------
    df : pl.DataFrame
        DataFrame with ortps_category and subcategory columns

    Returns
    -------
    pl.DataFrame
        Crosstab with counts and share percentages
    """
    # Count by ORTPS category × Subcategory
    subcat_counts = (
        df.filter(pl.col("subcategory").is_not_null())
        .group_by(["ortps_category", "subcategory"])
        .len()
        .rename({"len": "count"})
    )

    # Calculate row totals (total per ORTPS category)
    subcat_totals = subcat_counts.group_by("ortps_category").agg(
        pl.col("count").sum().alias("total")
    )

    # Join and calculate shares
    subcat_with_shares = (
        subcat_counts.join(subcat_totals, on="ortps_category", how="left").with_columns(
            [(pl.col("count") / pl.col("total") * 100).round(2).alias("share_pct")]
        )
    )

    logger.info(f"Subcategory crosstab: {subcat_counts['ortps_category'].n_unique()} ORTPS categories × {subcat_counts['subcategory'].n_unique()} subcategories")

    return subcat_with_shares


def get_top_subcategories(df: pl.DataFrame, n: int = 20) -> list[str]:
    """Get top N subcategories by count of ORTPS-labeled grievances.

    Parameters
    ----------
    df : pl.DataFrame
        DataFrame with subcategory column
    n : int
        Number of top subcategories to return

    Returns
    -------
    list[str]
        Top N subcategory names
    """
    top_subcats = (
        df.filter(pl.col("subcategory").is_not_null())
        .group_by("subcategory")
        .len()
        .sort("len", descending=True)
        .head(n)["subcategory"]
        .to_list()
    )

    logger.info(f"Selected top {n} subcategories")
    return top_subcats


def get_top_departments(df: pl.DataFrame, n: int = 15) -> list[str]:
    """Get top N departments by count of ORTPS-labeled grievances.

    Parameters
    ----------
    df : pl.DataFrame
        DataFrame with dept column
    n : int
        Number of top departments to return

    Returns
    -------
    list[str]
        Top N department names
    """
    top_depts = (
        df.filter(pl.col("dept").is_not_null())
        .group_by("dept")
        .len()
        .sort("len", descending=True)
        .head(n)["dept"]
        .to_list()
    )

    logger.info(f"Selected top {n} departments")
    return top_depts


def create_summary_stats(
    dept_crosstab: pl.DataFrame, subcat_crosstab: pl.DataFrame
) -> pl.DataFrame:
    """Create summary statistics table.

    Parameters
    ----------
    dept_crosstab : pl.DataFrame
        Department crosstab
    subcat_crosstab : pl.DataFrame
        Subcategory crosstab

    Returns
    -------
    pl.DataFrame
        Summary statistics
    """
    # Aggregate by ORTPS category
    dept_summary = (
        dept_crosstab.group_by("ortps_category")
        .agg([pl.col("count").sum().alias("total_grievances_dept")])
    )

    subcat_summary = (
        subcat_crosstab.group_by("ortps_category")
        .agg([pl.col("count").sum().alias("total_grievances_subcat")])
    )

    summary = dept_summary.join(subcat_summary, on="ortps_category", how="full")

    logger.info("Created summary statistics")
    return summary


def export_crosstabs_to_excel(
    dept_crosstab: pl.DataFrame,
    subcat_crosstab_top20: pl.DataFrame,
    subcat_crosstab_full: pl.DataFrame,
    summary: pl.DataFrame,
    output_path: Path,
) -> None:
    """Export crosstabs to multi-sheet Excel workbook.

    Parameters
    ----------
    dept_crosstab : pl.DataFrame
        Department crosstab (long format)
    subcat_crosstab_top20 : pl.DataFrame
        Top 20 subcategory crosstab (long format)
    subcat_crosstab_full : pl.DataFrame
        Full subcategory crosstab (long format)
    summary : pl.DataFrame
        Summary statistics
    output_path : Path
        Output file path
    """
    # Pivot to wide format for readability
    dept_wide = (
        dept_crosstab.pivot(
            index="ortps_category",
            on="dept",
            values=["count", "share_pct"],
            aggregate_function="first",
        )
        .sort("ortps_category")
    )

    subcat_wide_top20 = (
        subcat_crosstab_top20.pivot(
            index="ortps_category",
            on="subcategory",
            values=["count", "share_pct"],
            aggregate_function="first",
        )
        .sort("ortps_category")
    )

    subcat_wide_full = (
        subcat_crosstab_full.pivot(
            index="ortps_category",
            on="subcategory",
            values=["count", "share_pct"],
            aggregate_function="first",
        )
        .sort("ortps_category")
    )

    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        # Sheet 1: Departments (all)
        dept_wide.to_pandas().to_excel(
            writer, sheet_name="ORTPS x Departments", index=True
        )

        # Sheet 2: Top 20 Subcategories
        subcat_wide_top20.to_pandas().to_excel(
            writer, sheet_name="ORTPS x Top20 Subcategories", index=True
        )

        # Sheet 3: All Subcategories (reference)
        subcat_wide_full.to_pandas().to_excel(
            writer, sheet_name="ORTPS x All Subcategories", index=True
        )

        # Sheet 4: Summary stats
        summary.to_pandas().to_excel(writer, sheet_name="Summary", index=False)

        # Format columns
        for sheet_name in writer.sheets:
            worksheet = writer.sheets[sheet_name]
            worksheet.set_column("A:A", 35)  # ORTPS category column width
            worksheet.set_column("B:ZZ", 14)  # Data column widths

    logger.info(f"Exported Excel workbook to {output_path}")


def export_csv_long(
    dept_crosstab: pl.DataFrame,
    subcat_crosstab: pl.DataFrame,
    output_dir: Path,
) -> None:
    """Export crosstabs to CSV in long format.

    Parameters
    ----------
    dept_crosstab : pl.DataFrame
        Department crosstab
    subcat_crosstab : pl.DataFrame
        Subcategory crosstab
    output_dir : Path
        Output directory
    """
    dept_csv_path = output_dir / "ortps_dept_crosstab.csv"
    subcat_csv_path = output_dir / "ortps_subcat_crosstab.csv"

    dept_crosstab.write_csv(dept_csv_path)
    subcat_crosstab.write_csv(subcat_csv_path)

    logger.info(f"Exported department crosstab CSV to {dept_csv_path}")
    logger.info(f"Exported subcategory crosstab CSV to {subcat_csv_path}")


def export_latex_table(
    df: pl.DataFrame, output_path: Path, caption: str, label: str
) -> None:
    """Export to LaTeX table using booktabs package.

    Parameters
    ----------
    df : pl.DataFrame
        DataFrame in wide format (ortps_category as index)
    output_path : Path
        Output file path
    caption : str
        Table caption
    label : str
        LaTeX label
    """
    # Convert to pandas for to_latex method
    df_pd = df.to_pandas()

    # Generate LaTeX string
    latex_str = df_pd.to_latex(
        index=True,
        caption=caption,
        label=label,
        position="htbp",
        column_format="l" + "r" * len(df_pd.columns),
        float_format="%.1f",
        escape=False,
    )

    # Add booktabs formatting
    latex_str = latex_str.replace("\\toprule", "\\toprule\n")
    latex_str = latex_str.replace("\\midrule", "\\midrule\n")
    latex_str = latex_str.replace("\\bottomrule", "\\bottomrule\n")

    output_path.write_text(latex_str)
    logger.info(f"Exported LaTeX table to {output_path}")


def main() -> None:
    """Main execution function."""
    # Setup output directory
    output_dir = directories.OUTPUT / "ortps_analysis"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Starting ORTPS crosstab analysis...")

    # Load data
    df = load_ortps_labeled_data()

    # Create crosstabs
    logger.info("Creating department crosstab...")
    dept_crosstab = create_department_crosstab(df)

    logger.info("Creating subcategory crosstabs...")
    subcat_crosstab_full = create_subcategory_crosstab(df)

    # Get top N for focused views
    top_20_subcats = get_top_subcategories(df, n=20)
    subcat_crosstab_top20 = subcat_crosstab_full.filter(
        pl.col("subcategory").is_in(top_20_subcats)
    )

    top_15_depts = get_top_departments(df, n=15)
    dept_crosstab_top15 = dept_crosstab.filter(pl.col("dept").is_in(top_15_depts))

    # Create summary stats
    logger.info("Creating summary statistics...")
    summary = create_summary_stats(dept_crosstab, subcat_crosstab_full)

    # Export to Excel
    logger.info("Exporting to Excel...")
    export_crosstabs_to_excel(
        dept_crosstab,
        subcat_crosstab_top20,
        subcat_crosstab_full,
        summary,
        output_dir / "ortps_crosstab_analysis.xlsx",
    )

    # Export to CSV (long format)
    logger.info("Exporting CSV (long format)...")
    export_csv_long(dept_crosstab, subcat_crosstab_full, output_dir)

    # Export to LaTeX (top-N only)
    logger.info("Exporting LaTeX tables...")

    # Pivot top-N crosstabs to wide format for LaTeX
    dept_wide_top15 = dept_crosstab_top15.pivot(
        index="ortps_category",
        on="dept",
        values="count",
        aggregate_function="first",
    ).sort("ortps_category")

    subcat_wide_top20 = subcat_crosstab_top20.pivot(
        index="ortps_category",
        on="subcategory",
        values="count",
        aggregate_function="first",
    ).sort("ortps_category")

    export_latex_table(
        dept_wide_top15,
        output_dir / "ortps_dept_top15.tex",
        caption="ORTPS Categories × Top 15 Departments (by count)",
        label="tab:ortps_dept_top15",
    )

    export_latex_table(
        subcat_wide_top20,
        output_dir / "ortps_subcat_top20.tex",
        caption="ORTPS Categories × Top 20 Subcategories (by count)",
        label="tab:ortps_subcat_top20",
    )

    logger.info(f"Analysis complete. Outputs saved to {output_dir}")
    logger.info(f"\nGenerated files:")
    logger.info(f"  - ortps_crosstab_analysis.xlsx (multi-sheet workbook)")
    logger.info(f"  - ortps_dept_crosstab.csv (long format)")
    logger.info(f"  - ortps_subcat_crosstab.csv (long format)")
    logger.info(f"  - ortps_dept_top15.tex (LaTeX table)")
    logger.info(f"  - ortps_subcat_top20.tex (LaTeX table)")


if __name__ == "__main__":
    main()
