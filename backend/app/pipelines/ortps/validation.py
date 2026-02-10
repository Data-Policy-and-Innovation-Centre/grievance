"""
Lightweight DataFrame validation for ORTPS pipeline stages.

Provides a DataFrameContract dataclass that checks column presence,
dtype, nullability, and allowed values on Polars DataFrames.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl
from loguru import logger


@dataclass
class ColumnSpec:
    """Specification for a single expected column."""

    name: str
    dtype: pl.DataType | None = None  # None means "any dtype"
    nullable: bool = True
    allowed_values: set[str] | None = None


@dataclass
class DataFrameContract:
    """
    Lightweight DataFrame shape contract.

    Validates column presence, dtypes, nullability, and optionally
    allowed values.

    Usage::

        contract = DataFrameContract(
            columns=[
                ColumnSpec("grievance_lang", pl.Utf8, nullable=True,
                          allowed_values={"en", "non_en"}),
            ],
            min_rows=1,
        )
        violations = contract.validate(df)  # returns list of violation strings
    """

    columns: list[ColumnSpec] = field(default_factory=list)
    min_rows: int = 0

    def validate(self, df: pl.DataFrame) -> list[str]:
        """
        Validate DataFrame against contract.

        Returns list of violation messages. Empty list means valid.
        """
        violations = []

        if len(df) < self.min_rows:
            violations.append(
                f"Expected >= {self.min_rows} rows, got {len(df)}"
            )

        for spec in self.columns:
            if spec.name not in df.columns:
                violations.append(f"Missing column: {spec.name}")
                continue

            col = df[spec.name]

            if spec.dtype is not None and col.dtype != spec.dtype:
                violations.append(
                    f"Column '{spec.name}': expected dtype {spec.dtype}, "
                    f"got {col.dtype}"
                )

            if not spec.nullable and col.null_count() > 0:
                violations.append(
                    f"Column '{spec.name}': {col.null_count()} nulls "
                    f"but nullable=False"
                )

            if spec.allowed_values is not None:
                actual = set(col.drop_nulls().unique().to_list())
                unexpected = actual - spec.allowed_values
                if unexpected:
                    violations.append(
                        f"Column '{spec.name}': unexpected values {unexpected}"
                    )

        return violations

    def check_or_warn(self, df: pl.DataFrame, stage: str) -> pl.DataFrame:
        """
        Validate and log warnings. Returns df unchanged.

        Suitable for use in Hamilton validation nodes.
        """
        violations = self.validate(df)
        if violations:
            for v in violations:
                logger.warning(f"[{stage}] Validation: {v}")
        else:
            logger.info(f"[{stage}] Validation passed ({len(df):,} rows)")
        return df


# ── Pre-built contracts for each pipeline stage ──────────────────────

LANG_DETECTION_CONTRACT = DataFrameContract(
    columns=[
        ColumnSpec("grievance", pl.String, nullable=True),
        ColumnSpec(
            "grievance_lang",
            pl.String,
            nullable=True,
            allowed_values={"en", "non_en"},
        ),
    ],
    min_rows=1,
)

ENGLISH_FILTER_CONTRACT = DataFrameContract(
    columns=[
        ColumnSpec("grievance", pl.String, nullable=False),
        ColumnSpec(
            "grievance_lang",
            pl.String,
            nullable=False,
            allowed_values={"en"},
        ),
    ],
    min_rows=1,
)

CATEGORY_LABELING_CONTRACT = DataFrameContract(
    columns=[
        ColumnSpec("grievance", pl.String, nullable=False),
        ColumnSpec(
            "grievance_lang",
            pl.String,
            nullable=False,
            allowed_values={"en"},
        ),
        ColumnSpec(
            "ortps_category",
            pl.String,
            nullable=True,
            allowed_values={
                "Caste certificate",
                "Income certificate",
                "Scholarship",
                "Ration Card",
            },
        ),
        ColumnSpec(
            "ortps_method",
            pl.String,
            nullable=True,
            allowed_values={"keyword", "embedding"},
        ),
        ColumnSpec("ortps_confidence", pl.Float64, nullable=True),
    ],
    min_rows=1,
)
