# ORTPS Pipeline

Hamilton-based data pipeline for analyzing **Right to Public Services (ORTPS)** complaints in the Janasunani grievance corpus.

## Overview

This pipeline identifies and analyzes complaints related to ORTPS (Odisha Right to Public Services Act, 2012), which mandates time-bound delivery of 159 public services across 8 categories. The pipeline filters English complaints, labels them into 7 ORTPS categories using keyword + embedding hybrid matching, and extracts dominant themes per category using BERTopic.

## Pipeline Architecture

```
┌────────────────────────────────────────────────────────────┐
│                   Input: Raw Complaints                     │
│              (SQLite → Polars DataFrame)                    │
└────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────┐
│         Stage 1: Language Detection (Hamilton)             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Nodes: lang_detection_nodes.py                     │   │
│  │  Engine: shared.language_detection                  │   │
│  │  Profile: language_profiles.py                      │   │
│  └─────────────────────────────────────────────────────┘   │
│  Output: English-only complaints (~770K / 1.25M)           │
└────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────┐
│      Stage 2: Category Labeling (Hamilton)                 │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Nodes: category_labeling_nodes.py                  │   │
│  │  Engine: labelers.CategoryLabeler                   │   │
│  │  Keywords: 164 service-specific keywords            │   │
│  │  Embeddings: sentence-transformers/all-MiniLM-L6-v2 │   │
│  └─────────────────────────────────────────────────────┘   │
│  Output: 7 ORTPS categories (~60K labeled)                 │
│  ├─ Certificates (caste, income, birth, death, etc.)       │
│  ├─ Scholarship                                             │
│  ├─ Ration card                                             │
│  ├─ Land matters (RoR, mutation, conveyance, etc.)         │
│  ├─ Building & Construction                                 │
│  ├─ Utilities & Connections (water, electricity)           │
│  └─ Vehicle Services (DL, RC)                               │
│     Police & Legal (verification, FIR, trade license)       │
└────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────┐
│       Stage 3: Topic Modeling (Hamilton)                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Nodes: topic_nodes.py                              │   │
│  │  Engine: shared.topic_modeling.bertopic_engine      │   │
│  │  Profile: topic_profiles.py                         │   │
│  │  Model: BERTopic + HDBSCAN + UMAP                   │   │
│  └─────────────────────────────────────────────────────┘   │
│  Output: 3-10 topics per category (adaptive)               │
└────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────┐
│                   Output Artifacts                          │
│  - Labeled Parquet files (data/interim/)                   │
│  - BERTopic models (output/ortps_analysis/models/)         │
│  - Wordclouds (output/ortps_analysis/wordclouds/)          │
│  - Topic samples (output/ortps_analysis/topics/samples/)   │
│  - LaTeX tables (output/ortps_analysis/tables/)            │
└────────────────────────────────────────────────────────────┘
```

## ORTPS Categories

The pipeline labels complaints into 7 consolidated categories based on the Odisha RPS Act service definitions:

| Category | Services Included | Example Keywords |
|----------|------------------|------------------|
| **Certificates** | Caste, SC/ST, OBC, Legal Heir, Birth, Death, Marriage, Income, EWS | "caste certificate", "birth certificate", "income certificate" |
| **Scholarship** | Post-matric, Pre-matric, OASIS, Minority scholarships | "scholarship", "post matric", "oasis" |
| **Ration card** | New ration card, Correction, AAY, PHH, BPL cards | "ration card", "food security", "aay card" |
| **Land matters** | RoR copy, Encumbrance cert, Registered document copy, Property registration, Mortgage permission, Conveyance deed, Mutation, Land conversion | "ror copy", "mutation", "encumbrance certificate", "sale deed registration" |
| **Building & Construction** | Building plan approval, Addition/alteration permission, Occupancy certificate | "building plan", "occupancy certificate" |
| **Utilities & Connections** | Water connection (BMC/CMC/BEMC), Non-industrial power connection | "water connection", "electricity connection" |
| **Vehicle Services** | Driving license (new, renewal, address change), Learner's license, RC copy, Vehicle ownership transfer | "driving licence", "learner licence", "vehicle registration" |
| **Police & Legal** | Employee verification, Character verification, FIR copy, Trade license | "police verification", "fir copy", "trade licence" |

**Note**: This is a subset of the 159 total ORTPS services. Only services with significant complaint volume are included.

## Directory Structure

```
app/pipelines/ortps/
├── __init__.py                   # Public API: run_pipeline, build_ortps_driver
├── config.py                     # Pydantic configuration models
├── lang_detection_nodes.py       # Hamilton nodes for language detection
├── category_labeling_nodes.py    # Hamilton nodes for category labeling
├── topic_nodes.py                # Hamilton nodes for topic modeling
├── language_profiles.py          # Language detection profile (script patterns, markers)
├── topic_profiles.py             # Topic modeling profile (stopwords, params)
├── validation.py                 # DataFrame contracts for pipeline stages
├── labelers.py                   # CategoryLabeler implementation
├── detectors.py                  # Compatibility shim for ImprovedLanguageDetector
├── analyzers.py                  # Compatibility shim for TopicAnalyzer
└── topic_config.py               # Legacy topic config (may be deprecated)
```

## Configuration (`config.py`)

### `LanguageDetectionConfig`

```python
class LanguageDetectionConfig(BaseModel):
    lingua_threshold: float = 0.85  # Min confidence for English
    text_col: str = "grievance"     # Column containing complaint text
```

### `CategoryLabelingConfig`

```python
class CategoryLabelingConfig(BaseModel):
    # Embedding model
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_threshold: float = 0.45  # Min cosine similarity
    embedding_device: str | None = None  # "mps"/"cuda"/"cpu"/None (auto)

    # Labeling method
    labeling_method: Literal["keyword", "embedding", "hybrid"] = "hybrid"

    # Embedding strategy (new: keyword enhancement)
    embedding_strategy: Literal["label_only", "keyword_only", "combined"] = "label_only"
    keyword_weight: float = 1.0   # Weight for keyword similarity (combined mode)
    label_weight: float = 0.5     # Weight for label similarity (combined mode)
```

**Embedding Strategies**:
- `label_only` (default): Match against 7 category labels (e.g., "Certificates")
- `keyword_only`: Match against 164 keywords (e.g., "caste certificate"), max-pool per category
- `combined`: Weighted fusion of label + keyword similarities

### `OrtpsPipelineConfig`

Top-level config combining all stages.

```python
class OrtpsPipelineConfig(BaseModel):
    # Data loading
    db_path: Path = directories.RAW_DATA / "grievance.db"
    output_dir: Path = directories.OUTPUT / "ortps_analysis"
    sample_size: int | None = None  # For testing

    # Pipeline stages
    lang: LanguageDetectionConfig
    labeling: CategoryLabelingConfig

    # Post-pipeline
    fiscal_years: list[int] = [2023, 2024]
    skip_wordclouds: bool = False
    skip_embeddings: bool = False
    generate_latex_wrapper: bool = False

    def to_hamilton_inputs(self) -> dict:
        """Flatten config for Hamilton."""
        return {
            "lingua_threshold": self.lang.lingua_threshold,
            "text_col": self.lang.text_col,
            "embedding_model_name": self.labeling.embedding_model_name,
            ...
        }
```

---

## Hamilton Nodes

### Language Detection Nodes (`lang_detection_nodes.py`)

#### `language_detector(lingua_threshold: float) -> TwoStageLanguageDetector`

Construct language detector with ORTPS profile.

**Profile** (from `language_profiles.py`):
- Script filter: Odia/Devanagari Unicode ranges
- Lingua languages: English, Hindi
- Romanized Odia markers: "mu", "mora", "karuchhi", etc.
- Confidence threshold: 0.85

---

#### `raw_texts(raw_df: pl.DataFrame, text_col: str) -> list[str | None]`

Extract complaint text column as list.

---

#### `language_labels_and_stats(language_detector, raw_texts) -> dict`

Run batch language detection.

**Returns**:
```python
{
    "labels": ["en", "en", "non_en", None, ...],  # Per-text labels
    "stats": {
        "script_filtered": 450000,      # Non-Latin script
        "lingua_high_conf": 770000,     # English (high confidence)
        "lingua_low_conf": 15000,       # Non-English (low confidence)
        "null": 5000                    # Empty/None texts
    }
}
```

---

#### `df_with_lang(raw_df, language_labels_and_stats) -> pl.DataFrame`

Add language labels to DataFrame.

**New columns**: `language` (str: "en"/"non_en"/None)

---

#### `df_english(df_with_lang) -> pl.DataFrame`

Filter to English-only complaints.

**Output**: ~770K complaints (62% of corpus)

---

### Category Labeling Nodes (`category_labeling_nodes.py`)

#### `category_labeler(...) -> CategoryLabeler`

Construct labeler with configured embedding model and strategy.

---

#### `df_labeled(df_english, category_labeler, labeling_method, text_col, embedding_strategy) -> pl.DataFrame`

Apply category labeling.

**New columns**:
- `ortps_category` (str): Category name or None
- `ortps_method` (str): "keyword" / "embedding" / None
- `ortps_confidence` (float): Similarity score (for embeddings)

**Methods**:
- `keyword`: Regex matching on 164 keywords (fast, high precision)
- `embedding`: Sentence embedding similarity (slower, handles paraphrases)
- `hybrid`: Keyword first, then embedding for unmatched (recommended)

---

#### `category_distribution(df_labeled) -> pl.DataFrame`

Compute category value counts.

**Logs**:
```
Category distribution:
  Certificates: 15,234
  Scholarship: 8,921
  Land matters: 12,456
  ...
```

---

### Topic Modeling Nodes (`topic_nodes.py`)

#### `filtered_data(df_labeled, fiscal_years) -> dict[str, pl.DataFrame]`

Split labeled data by category and filter by fiscal year.

**Returns**: `{"Certificates": df_certs, "Scholarship": df_scholar, ...}`

---

#### `cached_embeddings(category_splits, category_labeler) -> dict[str, np.ndarray]`

Compute or load cached sentence embeddings per category.

**Cache location**: `models/ortps_embeddings_{model}_{hash}.pkl`

---

#### `topic_models(category_splits, cached_embeddings) -> dict[str, TopicAnalyzer]`

Fit BERTopic models per category.

**Adaptive parameters** (from `topic_profiles.py`):
- Small (<1000 complaints): `min_cluster_size=30`, `n_components=3`
- Medium (1000-5000): `min_cluster_size=50`, `n_components=5`
- Large (>5000): `min_cluster_size=100`, `n_components=5`

**Returns**: `{"Certificates": analyzer1, ...}`

---

## Profiles

### Language Profile (`language_profiles.py`)

ORTPS-specific language detection configuration.

```python
SCRIPT_FILTER_PATTERN = r"[\u0B00-\u0B7F\u0900-\u097F]"  # Odia + Devanagari
LINGUA_LANGUAGES = (Language.ENGLISH, Language.HINDI)
TARGET_LANGUAGE = Language.ENGLISH
DEFAULT_CONFIDENCE_THRESHOLD = 0.85

# Romanized Odia markers
ROMANIZED_NON_ENGLISH_MARKERS = (
    "mu", "mora", "karuchhi", "deithili", "ghara",
    "abedana", "jau", "achhi", "nku", "paribar"
)
ROMANIZED_MARKER_MIN_HITS = 2
```

**Why these markers?** Common Odia words written in Latin script in Janasunani complaints.

---

### Topic Profile (`topic_profiles.py`)

ORTPS-specific topic modeling configuration.

**Stopwords** (156 terms):
- Petition boilerplate: "sir", "madam", "kindly", "please", "request"
- Generic admin terms: "office", "department", "district", "grievance"
- Poverty language: "poor", "bpl", "needy", "helpless"
- Odisha place names: "bhubaneswar", "cuttack", "puri", etc.

**Adaptive Parameters**:
```python
def get_ortps_topic_model_params(n_samples: int) -> TopicModelParams:
    if n_samples < 1000:
        return TopicModelParams(
            min_cluster_size=30, min_samples=10,
            top_n_words=12, n_components=3
        )
    # ... (see file for full logic)
```

---

## Labeler (`labelers.py`)

### `CategoryLabeler`

Hybrid keyword + embedding labeler for ORTPS categories.

#### Keyword Matching

164 keywords across 7 categories:
```python
CATEGORY_KEYWORDS = {
    "Certificates": [
        "caste certificate", "sc certificate", "birth certificate",
        "income certificate", "legal heir certificate", ...
    ],
    "Scholarship": ["scholarship", "post matric", "oasis", ...],
    ...
}
```

**Algorithm**: Case-insensitive regex search, returns first match.

---

#### Embedding Matching

**Three strategies**:

1. **Label-only** (default): Encode 7 category labels, compute similarity
2. **Keyword-only**: Encode 164 keywords, max-pool per category
3. **Combined**: Weighted fusion of label + keyword similarities

**Model**: `sentence-transformers/all-MiniLM-L6-v2` (384-dim embeddings)

**Caching**: Text embeddings and keyword embeddings cached to `models/` directory.

**Example (keyword-only)**:
```
Text: "My caste certificate application is pending"

Keyword embeddings:
  - "caste certificate": similarity = 0.82
  - "birth certificate": similarity = 0.45
  - "scholarship": similarity = 0.32

Max per category:
  - Certificates: 0.82 (from "caste certificate")
  - Scholarship: 0.32

Assigned: Certificates (similarity=0.82, threshold=0.45)
```

---

## Validation (`validation.py`)

DataFrame contracts using `DataFrameContract` class.

### `LANG_DETECTION_CONTRACT`

Validates output of language detection:
```python
DataFrameContract(
    required_columns=["grievance", "language"],
    column_types={"language": pl.String},
    nullable_columns={"language": True}
)
```

---

### `ENGLISH_FILTER_CONTRACT`

Validates English-filtered DataFrame:
```python
DataFrameContract(
    required_columns=["grievance", "language"],
    custom_checks=[lambda df: (df["language"] == "en").all()]
)
```

---

### `CATEGORY_LABELING_CONTRACT`

Validates category-labeled DataFrame:
```python
DataFrameContract(
    required_columns=["ortps_category", "ortps_method", "ortps_confidence"],
    column_types={
        "ortps_category": pl.String,
        "ortps_method": pl.String,
        "ortps_confidence": pl.Float64
    }
)
```

---

## Running the Pipeline

### From Python

```python
from app.pipelines.ortps import run_pipeline
from app.pipelines.ortps.config import OrtpsPipelineConfig
from app.config import load_duckdb

# Load data
raw_df = load_duckdb(output_format="polars")

# Configure
config = OrtpsPipelineConfig(
    sample_size=1000,  # For testing
    labeling=CategoryLabelingConfig(
        embedding_strategy="keyword_only"  # Use keyword-enhanced matching
    )
)

# Run
result = run_pipeline(raw_df, config)
labeled_df = result["df_labeled"]
```

---

### From CLI (via scripts)

```bash
cd backend

# Run full pipeline
python scripts/ortps_category_analysis.py \
    --embedding-threshold 0.6 \
    --embedding-strategy keyword_only \
    --fiscal-years 2023 2024 2025

# Run with sampling (for testing)
python scripts/ortps_category_analysis.py \
    --sample-size 5000 \
    --embedding-strategy keyword_only \
    --skip-wordclouds
```

---

## Output Artifacts

### Labeled DataFrames

**Location**: `data/interim/grievance_complaints_ortps_labelled_fyYYYY.parquet`

**Schema**:
```
ticket_no, grievance, language, ortps_category, ortps_method, ortps_confidence, ...
```

---

### BERTopic Models

**Location**: `output/ortps_analysis/models/bertopic_{category}.safetensors`

**Usage**:
```python
from bertopic import BERTopic

model = BERTopic.load("output/ortps_analysis/models/bertopic_Certificates")
topics = model.get_topics()
```

---

### Wordclouds

**Location**: `output/ortps_analysis/wordclouds/{category}_fy{year}.png`

**Generated**: Per category per fiscal year

---

### Topic Samples

**Location**: `output/ortps_analysis/topics/samples/{category}_samples.txt`

**Format**:
```
ORTPS CATEGORY: Certificates
Total complaints: 15,234
Topics found: 5

══════════════════════════════════════════════════════════════
Topic 0 (3,201 complaints): caste certificate delay
──────────────────────────────────────────────────────────────
Top keywords: caste, certificate, st, sc, obc, pending, applied

Sample complaints:
1. [TKT001] My caste certificate application is pending for 6 months...
2. [TKT002] Applied for SC certificate but not received yet...
...
```

---

### LaTeX Tables

**Location**: `output/ortps_analysis/tables/ortps_category_distribution.tex`

**Usage**: Include in LaTeX reports for publication-ready tables.

---

## Interaction with Shared Components

### Language Detection

ORTPS uses `app/pipelines/shared/language_detection.TwoStageLanguageDetector`:

```python
from app.pipelines.shared.language_detection import TwoStageLanguageDetector
from app.pipelines.ortps.language_profiles import *

detector = TwoStageLanguageDetector(
    confidence_threshold=DEFAULT_CONFIDENCE_THRESHOLD,
    script_pattern=SCRIPT_FILTER_PATTERN,
    lingua_languages=LINGUA_LANGUAGES,
    target_language=TARGET_LANGUAGE,
    en_label=ENGLISH_LABEL,
    non_en_label=NON_ENGLISH_LABEL,
    non_target_markers=ROMANIZED_NON_ENGLISH_MARKERS,
    marker_min_hits=ROMANIZED_MARKER_MIN_HITS
)
```

**Benefits**: Other pipelines can reuse the detector with different profiles.

---

### Embedding Cache

ORTPS uses `app/pipelines/shared/embedding_cache`:

```python
from app.pipelines.shared.embedding_cache import (
    compute_text_hash,
    build_embeddings_cache_path,
    save_embeddings_cache,
    load_embeddings_cache
)

text_hash = compute_text_hash(texts)
cache_path = build_embeddings_cache_path("all-MiniLM-L6-v2", text_hash)
embeddings = load_embeddings_cache(cache_path, ...)
```

**Benefits**: Avoids recomputing embeddings across pipeline runs.

---

### Topic Modeling

ORTPS uses `app/pipelines/shared/topic_modeling.bertopic_engine.TopicAnalyzer`:

```python
from app.pipelines.shared.topic_modeling.bertopic_engine import TopicAnalyzer
from app.pipelines.ortps.topic_profiles import ORTPS_STOPWORDS, get_ortps_topic_model_params

analyzer = TopicAnalyzer(
    category="Certificates",
    n_samples=15234,
    custom_stopwords=ORTPS_STOPWORDS,
    params_resolver=get_ortps_topic_model_params
)
analyzer.fit(texts, embeddings)
```

**Benefits**: Reusable topic modeling engine with pluggable profiles.

---

## Testing

### Unit Tests

**Location**: `app/tests/pipelines/test_category_labeling_nodes.py`, `test_lang_detection_nodes.py`, `test_topic_nodes.py`

**Run**:
```bash
pytest app/tests/pipelines/ -v
```

---

### Integration Test

**Location**: `app/tests/pipelines/test_ortps_integration.py`

Tests full pipeline end-to-end with sample data.

---

## Performance Notes

### Throughput

- **Language detection**: ~10,000 texts/sec
- **Keyword matching**: ~50,000 texts/sec
- **Embedding encoding**: ~2,000 texts/sec (CPU), ~10,000 texts/sec (GPU)
- **Topic modeling**: 5-30 minutes per category (depends on size)

### Memory Usage

- **Raw DataFrame**: ~500 MB (1.25M complaints)
- **Embeddings**: ~400 MB per 100K texts (384-dim float32)
- **BERTopic model**: ~100-500 MB per category

### Optimization Tips

1. **Use sampling** for development: `--sample-size 5000`
2. **Skip embeddings** if only testing keywords: `--skip-embeddings`
3. **Cache embeddings** for repeated runs (automatic)
4. **Use GPU** if available: set `embedding_device="cuda"` in config

---

## Related Components

- **Shared Language Detection**: `app/pipelines/shared/language_detection.py`
- **Shared Embedding Cache**: `app/pipelines/shared/embedding_cache.py`
- **Shared Topic Modeling**: `app/pipelines/shared/topic_modeling/bertopic_engine.py`
- **Analysis Script**: `scripts/ortps_category_analysis.py`
- **Database**: `app/db/` - Data source

## References

- [ORTPS Act 2012](https://odisha.gov.in/content/right-public-services-act-2012)
- [Hamilton Documentation](https://hamilton.dagworks.io/)
- [BERTopic Documentation](https://maartengr.github.io/BERTopic/)
- [Sentence Transformers](https://www.sbert.net/)
