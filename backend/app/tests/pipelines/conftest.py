"""Shared fixtures for pipeline tests."""

import datetime

import polars as pl
import pytest


@pytest.fixture
def sample_raw_df() -> pl.DataFrame:
    """
    Small sample DataFrame mimicking the complaints table.

    Includes texts in English, Hindi script, Odia script, and null.
    """
    return pl.DataFrame({
        "grievance": [
            "My caste certificate application is pending for 3 months",
            "Please provide income certificate urgently",
            "ration card mein naam nahi hai",
            "\u0B2E\u0B4B \u0B28\u0B3E\u0B2E \u0B30\u0B3E\u0B36\u0B28 \u0B15\u0B3E\u0B30\u0B4D\u0B21",
            "\u092E\u0947\u0930\u093E \u0930\u093E\u0936\u0928 \u0915\u093E\u0930\u094D\u0921",
            None,
            "scholarship amount not received for post matric scheme",
            "road condition is very bad in our village",
            "BPL card not updated after new survey",
            "please check my SC certificate status",
        ],
        "created_on": [
            datetime.datetime(2023, 8, 15),
            datetime.datetime(2023, 9, 1),
            datetime.datetime(2023, 10, 1),
            datetime.datetime(2023, 11, 1),
            datetime.datetime(2024, 1, 1),
            datetime.datetime(2024, 2, 1),
            datetime.datetime(2024, 3, 1),
            datetime.datetime(2024, 4, 1),
            datetime.datetime(2024, 5, 1),
            datetime.datetime(2024, 7, 15),
        ],
        "ticket_no": [f"T{i:04d}" for i in range(10)],
    })


@pytest.fixture
def sample_english_df() -> pl.DataFrame:
    """Pre-filtered English DataFrame for category labeling tests."""
    return pl.DataFrame({
        "grievance": [
            "My caste certificate application is pending for 3 months",
            "Please provide income certificate urgently",
            "scholarship amount not received for post matric scheme",
            "road condition is very bad in our village",
            "BPL card not updated after new survey",
            "please check my SC certificate status",
            "ration card delivery is delayed",
            "family income proof needed for loan",
        ],
        "grievance_lang": ["en"] * 8,
        "created_on": [
            datetime.datetime(2023, 8, i + 1) for i in range(8)
        ],
        "ticket_no": [f"T{i:04d}" for i in range(8)],
    })


@pytest.fixture
def default_hamilton_inputs() -> dict:
    """Default Hamilton inputs for testing."""
    return {
        "lingua_threshold": 0.85,
        "text_col": "grievance",
        "embedding_model_name": "sentence-transformers/all-MiniLM-L6-v2",
        "embedding_threshold": 0.45,
        "embedding_device": "cpu",
        "labeling_method": "keyword",
    }
