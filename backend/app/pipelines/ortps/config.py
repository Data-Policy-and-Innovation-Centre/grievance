"""Pydantic configuration models for the ORTPS Hamilton pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.config import directories


class LanguageDetectionConfig(BaseModel):
    """Configuration for language detection stage."""

    lingua_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Minimum Lingua confidence for English classification",
    )
    text_col: str = Field(
        default="grievance",
        description="Name of the text column in the DataFrame",
    )


class CategoryLabelingConfig(BaseModel):
    """Configuration for category labeling stage."""

    embedding_model_name: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="SentenceTransformer model identifier",
    )
    embedding_threshold: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Minimum cosine similarity for embedding match",
    )
    embedding_device: str | None = Field(
        default=None,
        description="Device for model inference (mps/cuda/cpu/None for auto)",
    )
    labeling_method: Literal["keyword", "embedding", "hybrid"] = Field(
        default="hybrid",
        description="Category labeling method",
    )


class OrtpsPipelineConfig(BaseModel):
    """
    Top-level configuration combining all pipeline stages.

    Constructed from argparse args, then converted to Hamilton inputs dict.
    """

    # Data loading (not part of Hamilton DAG, handled by CLI)
    db_path: Path = Field(default=directories.RAW_DATA / "grievance.db")
    output_dir: Path = Field(default=directories.OUTPUT / "ortps_analysis")
    sample_size: int | None = Field(default=None, ge=1)

    # Pipeline stages
    lang: LanguageDetectionConfig = Field(
        default_factory=LanguageDetectionConfig
    )
    labeling: CategoryLabelingConfig = Field(
        default_factory=CategoryLabelingConfig
    )

    # Post-pipeline (not part of Hamilton DAG)
    fiscal_years: list[int] = Field(default=[2023, 2024])
    skip_wordclouds: bool = False
    skip_embeddings: bool = False
    generate_latex_wrapper: bool = False

    @field_validator("fiscal_years")
    @classmethod
    def validate_fiscal_years(cls, v: list[int]) -> list[int]:
        for y in v:
            if y < 2000 or y > 2100:
                raise ValueError(f"Fiscal year {y} out of plausible range")
        return sorted(v)

    def to_hamilton_inputs(self) -> dict:
        """Flatten config into the dict Hamilton expects for inputs."""
        return {
            "lingua_threshold": self.lang.lingua_threshold,
            "text_col": self.lang.text_col,
            "embedding_model_name": self.labeling.embedding_model_name,
            "embedding_threshold": self.labeling.embedding_threshold,
            "embedding_device": self.labeling.embedding_device,
            "labeling_method": self.labeling.labeling_method,
        }

    @classmethod
    def from_argparse(cls, args) -> OrtpsPipelineConfig:
        """Construct from argparse Namespace."""
        labeling_method = args.labeling_method
        if args.skip_embeddings:
            labeling_method = "keyword"

        return cls(
            db_path=args.db_path,
            output_dir=args.output_dir,
            sample_size=args.sample_size,
            lang=LanguageDetectionConfig(
                lingua_threshold=args.lingua_threshold,
            ),
            labeling=CategoryLabelingConfig(
                embedding_threshold=args.embedding_threshold,
                labeling_method=labeling_method,
            ),
            fiscal_years=args.fiscal_years,
            skip_wordclouds=args.skip_wordclouds,
            skip_embeddings=args.skip_embeddings,
            generate_latex_wrapper=args.generate_latex_wrapper,
        )
