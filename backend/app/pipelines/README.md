# Pipelines Architecture

Hamilton-based data transformation pipelines for NLP analysis of complaint data.

## Overview

Pipeline modules are split into **two layers**:

1. **`app.pipelines.shared/`** - Reusable NLP engines (no domain logic)
   - Language detection (two-stage: script filter + Lingua)
   - Embedding cache (deterministic caching with validation)
   - Topic modeling (BERTopic wrapper with adaptive parameters)

2. **`app.pipelines.ortps/`** - ORTPS-specific policy and orchestration
   - Language profiles (Odia script patterns, romanized markers)
   - Topic profiles (ORTPS stopwords, adaptive parameter functions)
   - Category labeler (164 keywords + embeddings for 7 ORTPS categories)
   - Hamilton nodes (DAG wiring for language detection → labeling → topic modeling)

This separation keeps domain logic isolated while allowing other pipelines to reuse core NLP components.

## Structure

```
app/pipelines/
├── __init__.py                   # Package marker
├── _driver.py                    # Hamilton driver factory
├── shared/                       # Reusable NLP engines
│   ├── language_detection.py    # TwoStageLanguageDetector
│   ├── embedding_cache.py       # Cache utilities
│   └── topic_modeling/
│       └── bertopic_engine.py   # TopicAnalyzer
└── ortps/                        # ORTPS pipeline (Right to Public Services)
    ├── __init__.py               # Public API (run_pipeline, build_ortps_driver)
    ├── config.py                 # Pydantic configuration
    ├── language_profiles.py      # Odia-specific language detection config
    ├── topic_profiles.py         # ORTPS-specific stopwords & parameters
    ├── labelers.py               # CategoryLabeler (keyword + embedding)
    ├── lang_detection_nodes.py   # Hamilton nodes for language detection
    ├── category_labeling_nodes.py # Hamilton nodes for category labeling
    ├── topic_nodes.py            # Hamilton nodes for topic modeling
    ├── validation.py             # DataFrame contracts
    ├── detectors.py              # Compatibility shim (historical imports)
    └── analyzers.py              # Compatibility shim (historical imports)
```

## Hamilton Framework

Pipelines use [Hamilton](https://hamilton.dagworks.io/) for declarative DAG-based data transformations.

**Key Concepts**:
- **Nodes**: Python functions that define transformation steps
- **DAG**: Directed Acyclic Graph automatically inferred from function dependencies
- **Inputs**: Initial data passed to the driver
- **Config**: Static configuration for conditional execution

**Example Hamilton Node**:
```python
def df_english(df_with_lang: pl.DataFrame) -> pl.DataFrame:
    """Filter to English-only complaints."""
    return df_with_lang.filter(pl.col("language") == "en")
```

**Dependencies**: `df_english` depends on `df_with_lang` (auto-detected by parameter name)

## Design Philosophy

### Engines are Generic, Profiles Provide Policy

**Bad** (hardcoded domain logic):
```python
class LanguageDetector:
    def __init__(self):
        self.script_pattern = r"[\u0B00-\u0B7F]"  # Odia script (hardcoded!)
        self.markers = ["mu", "mora"]  # Romanized Odia (hardcoded!)
```

**Good** (injectable configuration):
```python
class TwoStageLanguageDetector:
    def __init__(self, script_pattern: str, non_target_markers: tuple[str, ...]):
        self.script_pattern = script_pattern
        self.non_target_markers = non_target_markers

# ORTPS pipeline uses Odia profile
ortps_detector = TwoStageLanguageDetector(
    script_pattern=ORTPS_SCRIPT_PATTERN,  # From language_profiles.py
    non_target_markers=ORTPS_ROMANIZED_MARKERS
)

# Tamil Nadu pipeline (hypothetical) uses Tamil profile
tamil_detector = TwoStageLanguageDetector(
    script_pattern=TAMIL_SCRIPT_PATTERN,
    non_target_markers=TAMIL_ROMANIZED_MARKERS
)
```

**Result**: Same engine, different policies → no code duplication across pipelines.

## Running Pipelines

### From Python

```python
from app.pipelines.ortps import run_pipeline
from app.pipelines.ortps.config import OrtpsPipelineConfig
from app.config import load_duckdb

# Load raw data
raw_df = load_duckdb(output_format="polars")

# Configure pipeline
config = OrtpsPipelineConfig(
    sample_size=1000,  # For testing
    lang=LanguageDetectionConfig(lingua_threshold=0.85),
    labeling=CategoryLabelingConfig(
        embedding_strategy="keyword_only",
        embedding_threshold=0.6
    )
)

# Run pipeline
result = run_pipeline(raw_df, config)
labeled_df = result["df_labeled"]
```

### From Scripts

```bash
cd backend
python scripts/ortps_category_analysis.py \
    --sample-size 5000 \
    --embedding-strategy keyword_only \
    --embedding-threshold 0.6 \
    --fiscal-years 2023 2024
```

## Adding New Pipelines

1. **Create pipeline package**: `app/pipelines/your_pipeline/`
2. **Define profiles**: Language profiles, topic profiles, etc.
3. **Create Hamilton nodes**: Separate modules for each stage
4. **Add reusable engines to shared/** if applicable
5. **Write configuration**: Pydantic models for type-safe config
6. **Write tests**: Unit tests for nodes, integration tests for full pipeline

## Related Components

- **ORTPS Pipeline**: `app/pipelines/ortps/` - Detailed documentation in subdirectory
- **Shared Utilities**: `app/pipelines/shared/` - Detailed documentation in subdirectory
- **Scripts**: `scripts/ortps_category_analysis.py` - CLI entry points
- **Tests**: `app/tests/pipelines/` - Pipeline test suite

## References

- [Hamilton Documentation](https://hamilton.dagworks.io/)
- [Polars Documentation](https://docs.pola.rs/)
- [Pydantic Documentation](https://docs.pydantic.dev/)

