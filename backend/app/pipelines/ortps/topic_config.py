"""Configuration for ORTPS topic modeling pipeline."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from app.config import directories


class TopicModelingConfig(BaseModel):
    """Configuration for BERTopic topic modeling stage.

    Attributes:
        min_text_length: Minimum character length for complaint text
        output_dir: Directory for topic analysis outputs (LaTeX, CSV)
        model_dir: Directory to save fitted BERTopic models
    """

    min_text_length: int = Field(
        default=50,
        description="Minimum character length for grievance text to include in analysis",
    )

    output_dir: Path = Field(
        default=directories.OUTPUT / "ortps_analysis" / "topics",
        description="Output directory for topic tables and reports",
    )

    model_dir: Path = Field(
        default=directories.MODELS,
        description="Directory to save BERTopic model files",
    )

    def to_hamilton_inputs(self) -> dict:
        """Convert config to Hamilton driver inputs.

        Returns:
            Dict of parameter_name -> value for Hamilton nodes
        """
        return {
            "min_text_length": self.min_text_length,
        }
