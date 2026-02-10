"""ORTPS Topic Modeling Analysis Script.

Runs BERTopic on ORTPS-labeled complaints to discover sub-themes within each category.

Usage:
    uv run python scripts/ortps_topic_analysis.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

import polars as pl
from loguru import logger

from app.config import directories
from app.pipelines._driver import build_driver
from app.pipelines.ortps import topic_nodes
from app.pipelines.ortps.analyzers import TopicAnalyzer
from app.pipelines.ortps.labelers import CategoryLabeler
from app.pipelines.ortps.topic_config import TopicModelingConfig


def export_sample_complaints(
    df_labeled: pl.DataFrame,
    topic_assignments: pl.DataFrame,
    topic_models: dict[str, TopicAnalyzer],
    output_dir: Path,
) -> None:
    """Export sample complaints for each category and topic.

    Args:
        df_labeled: Original labeled DataFrame
        topic_assignments: DataFrame with topic_id column
        topic_models: Dict of category -> TopicAnalyzer
        output_dir: Output directory for sample files
    """
    samples_dir = output_dir / "samples"
    samples_dir.mkdir(parents=True, exist_ok=True)

    for category, analyzer in topic_models.items():
        # Get complaints for this category
        cat_df = topic_assignments.filter(pl.col("ortps_category") == category)

        if len(cat_df) == 0:
            continue

        # Safe filename
        safe_name = category.replace(" & ", "_and_").replace(" ", "_").replace("&", "and")
        output_file = samples_dir / f"{safe_name}_samples.txt"

        # Get topic info
        topic_info = analyzer.get_topic_info().filter(pl.col("Topic") != -1)

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(f"ORTPS CATEGORY: {category}\n")
            f.write(f"Total complaints: {len(cat_df)}\n")
            f.write(f"Topics found: {len(topic_info)}\n")
            f.write("=" * 80 + "\n\n")

            # Export samples per topic
            for row in topic_info.iter_rows(named=True):
                topic_id = row["Topic"]
                topic_count = row["Count"]

                # Get complaints for this topic
                topic_complaints = cat_df.filter(pl.col("topic_id") == topic_id)

                # Sample up to 5 complaints per topic
                n_samples = min(5, len(topic_complaints))
                samples = topic_complaints.select(["id", "grievance"]).sample(
                    n=n_samples, seed=42
                )

                f.write(f"TOPIC {topic_id} ({topic_count} complaints)\n")
                f.write(f"Keywords: {row['Name']}\n")
                f.write("-" * 80 + "\n\n")

                for i, sample_row in enumerate(samples.iter_rows(named=True), 1):
                    f.write(f"Sample {i} (ID: {sample_row['id']})\n")
                    f.write(sample_row["grievance"])
                    f.write("\n\n" + "~" * 80 + "\n\n")

                f.write("=" * 80 + "\n\n")

        logger.info(f"✓ Exported {safe_name}_samples.txt")


def export_latex_tables(
    topic_models: dict[str, TopicAnalyzer],
    topic_summary: pl.DataFrame,
    output_dir: Path,
) -> None:
    """Generate LaTeX tables for topics.

    Args:
        topic_models: Dict of category -> fitted TopicAnalyzer
        topic_summary: Cross-category summary statistics
        output_dir: Output directory for LaTeX files
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Per-category tables
    for category, analyzer in topic_models.items():
        topic_info = analyzer.get_topic_info()

        # Filter out outlier topic (-1)
        topic_info_filtered = topic_info.filter(pl.col("Topic") != -1)

        if len(topic_info_filtered) == 0:
            logger.warning(f"{category}: No valid topics found, skipping LaTeX export")
            continue

        # Generate table
        latex_table = generate_category_table(category, topic_info_filtered, analyzer)

        # Save
        safe_name = category.replace(" & ", "_").replace(" ", "_").replace("&", "and")
        table_path = output_dir / f"{safe_name}_topics.tex"
        table_path.write_text(latex_table)
        logger.info(f"Exported {category} table to {table_path.name}")

    # Cross-category summary
    summary_table = generate_summary_table(topic_summary)
    summary_path = output_dir / "topic_summary.tex"
    summary_path.write_text(summary_table)
    logger.info(f"Exported summary table to {summary_path.name}")


def generate_category_table(
    category: str,
    topic_info: pl.DataFrame,
    analyzer: TopicAnalyzer,
) -> str:
    """Generate LaTeX table for a single category.

    Args:
        category: Category name
        topic_info: Topic info DataFrame
        analyzer: Fitted TopicAnalyzer

    Returns:
        LaTeX table string
    """
    # Escape LaTeX special characters in category name
    cat_escaped = category.replace("&", "\\&")

    # Get topics dict
    topics_dict = analyzer.get_topics()

    lines = []
    lines.append("\\begin{table}[htbp]")
    lines.append("\\centering")
    lines.append(f"\\caption{{{cat_escaped} Sub-themes}}")
    label = category.replace(" & ", "_").replace(" ", "_").replace("&", "and")
    lines.append(f"\\label{{tab:topics_{label}}}")
    lines.append("\\begin{tabular}{rlp{7cm}r}")
    lines.append("\\toprule")
    lines.append("Topic ID & Top Keywords & Count & Share (\\%) \\\\")
    lines.append("\\midrule")

    # Sort by count descending
    topic_info_sorted = topic_info.sort("Count", descending=True)

    for row in topic_info_sorted.iter_rows(named=True):
        topic_id = row["Topic"]

        # Get top words
        if topic_id in topics_dict:
            top_words = topics_dict[topic_id][:10]  # Top 10 words
            keywords = ", ".join([word for word, _ in top_words])
        else:
            keywords = row["Name"]  # Fallback to Name column

        count = row["Count"]

        # Calculate share
        total = analyzer.n_samples
        share_pct = (count / total) * 100

        lines.append(f"{topic_id} & {keywords} & {count:,} & {share_pct:.1f} \\\\")

    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    lines.append("\\end{table}")

    return "\n".join(lines)


def generate_summary_table(topic_summary: pl.DataFrame) -> str:
    """Generate cross-category summary LaTeX table.

    Args:
        topic_summary: Summary statistics DataFrame

    Returns:
        LaTeX table string
    """
    lines = []
    lines.append("\\begin{table}[htbp]")
    lines.append("\\centering")
    lines.append("\\caption{Topic Modeling Coverage Across ORTPS Categories}")
    lines.append("\\label{tab:topic_summary}")
    lines.append("\\begin{tabular}{lrrr}")
    lines.append("\\toprule")
    lines.append("Category & Complaints & Topics & Coverage (\\%) \\\\")
    lines.append("\\midrule")

    # Sort by total complaints descending
    summary_sorted = topic_summary.sort("total_complaints", descending=True)

    for row in summary_sorted.iter_rows(named=True):
        cat_escaped = row["category"].replace("&", "\\&")
        lines.append(
            f"{cat_escaped} & {row['total_complaints']:,} & "
            f"{row['n_topics']} & {row['coverage_pct']:.1f} \\\\"
        )

    # Add total row
    total_complaints = topic_summary["total_complaints"].sum()
    total_topics = topic_summary["n_topics"].sum()
    avg_coverage = topic_summary["coverage_pct"].mean()

    lines.append("\\midrule")
    lines.append(
        f"\\textbf{{Total}} & {total_complaints:,} & "
        f"{total_topics} & {avg_coverage:.1f} \\\\"
    )

    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    lines.append("\\end{table}")

    return "\n".join(lines)


def main(
    single_category: str | None = None,
) -> None:
    """Main execution function.

    Args:
        single_category: Optional category name to analyze (for testing)
    """
    logger.info("Starting ORTPS topic modeling analysis...")

    # Load data
    parquet_path = directories.INTERIM / "grievance_complaints_ortps_labelled_fy2023.parquet"
    logger.info(f"Loading data from {parquet_path}")
    df = pl.read_parquet(parquet_path)

    # Filter to single category if specified (for testing)
    if single_category:
        logger.info(f"Filtering to single category: {single_category}")
        df = df.filter(pl.col("ortps_category") == single_category)

        if len(df) == 0:
            logger.error(f"No data found for category: {single_category}")
            return

    # Initialize config and labeler
    config = TopicModelingConfig()
    category_labeler = CategoryLabeler()

    # Build Hamilton driver
    logger.info("Building Hamilton pipeline...")
    dr = build_driver(topic_nodes, config=config.to_hamilton_inputs())

    # Execute pipeline
    logger.info("Executing topic modeling pipeline...")
    results = dr.execute(
        ["topic_assignments", "topic_models", "topic_summary"],
        inputs={
            "df_labeled": df,
            "category_labeler": category_labeler,
        },
    )

    # Export Parquet
    logger.info("Exporting topic assignments to Parquet...")
    parquet_output = directories.INTERIM / "ortps_topics_results.parquet"
    results["topic_assignments"].write_parquet(parquet_output)
    logger.info(f"Saved to {parquet_output}")

    # Export sample complaints
    logger.info("Exporting sample complaints...")
    export_sample_complaints(
        df,
        results["topic_assignments"],
        results["topic_models"],
        config.output_dir,
    )

    # Export LaTeX tables
    logger.info("Generating LaTeX tables...")
    export_latex_tables(
        results["topic_models"],
        results["topic_summary"],
        config.output_dir,
    )

    # Save models
    logger.info("Saving BERTopic models...")
    for category, analyzer in results["topic_models"].items():
        safe_name = category.replace(" & ", "_").replace(" ", "_").replace("&", "and")
        model_path = config.model_dir / f"ortps_topics_{safe_name}.safetensors"
        analyzer.save_model(model_path)

    logger.info("✓ Topic modeling analysis complete!")
    logger.info(f"  - Results: {parquet_output}")
    logger.info(f"  - LaTeX tables: {config.output_dir}")
    logger.info(f"  - Models: {config.model_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ORTPS Topic Modeling Analysis")
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        help="Analyze single category (for testing)",
    )
    args = parser.parse_args()

    main(single_category=args.category)
