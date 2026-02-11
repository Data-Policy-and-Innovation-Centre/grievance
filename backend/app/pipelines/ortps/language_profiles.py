"""ORTPS language-detection profile (Janasunani complaint corpus defaults)."""

from __future__ import annotations

from lingua import Language

SCRIPT_FILTER_PATTERN = r"[\u0B00-\u0B7F\u0900-\u097F]"
LINGUA_LANGUAGES: tuple[Language, ...] = (Language.ENGLISH, Language.HINDI)
TARGET_LANGUAGE = Language.ENGLISH
DEFAULT_CONFIDENCE_THRESHOLD = 0.85
ENGLISH_LABEL = "en"
NON_ENGLISH_LABEL = "non_en"

# Romanized Odia markers seen in Janasunani complaints.
# If at least two are present in Latin script text, classify as non-English.
ROMANIZED_NON_ENGLISH_MARKERS: tuple[str, ...] = (
    "mu",
    "mora",
    "karuchhi",
    "deithili",
    "ghara",
    "abedana",
    "jau",
    "achhi",
    "nku",
    "paribar",
)
ROMANIZED_MARKER_MIN_HITS = 2
