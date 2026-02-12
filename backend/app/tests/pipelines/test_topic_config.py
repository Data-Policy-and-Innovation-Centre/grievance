"""Unit tests for ORTPS topic modeling config."""

from __future__ import annotations

from app.config import directories
from app.pipelines.ortps.topic_config import TopicModelingConfig


def test_topic_modeling_config_defaults():
    config = TopicModelingConfig()
    assert config.min_text_length == 50
    assert config.output_dir == directories.OUTPUT / "ortps_analysis" / "topics"
    assert config.model_dir == directories.MODELS


def test_topic_modeling_config_to_hamilton_inputs():
    config = TopicModelingConfig(min_text_length=75)
    assert config.to_hamilton_inputs() == {"min_text_length": 75}

