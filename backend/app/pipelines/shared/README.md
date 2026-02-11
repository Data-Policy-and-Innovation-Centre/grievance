# Shared Pipeline Utilities

Reusable NLP engines and utilities for Hamilton-based data pipelines.

## Overview

This package provides **domain-agnostic NLP components** that can be used across multiple pipelines. Each component is designed to be configurable via profile parameters, allowing pipelines to inject their domain-specific policies (stopwords, language markers, adaptive parameters) without modifying the core engine code.

## Architecture Philosophy

```
┌──────────────────────────────────────────────────────────┐
│              Pipeline-Specific Modules                    │
│         (Policy, Profiles, Hamilton Nodes)               │
│                                                           │
│  Example: app/pipelines/ortps/                           │
│  - language_profiles.py (Odia markers, thresholds)       │
│  - topic_profiles.py (ORTPS stopwords, params)           │
│  - lang_detection_nodes.py (Hamilton wiring)             │
└──────────────────────────────────────────────────────────┘
                            ↓
         (Calls shared engines with profile parameters)
                            ↓
┌──────────────────────────────────────────────────────────┐
│            Shared NLP Engines (Reusable)                 │
│         (Generic algorithms, no domain logic)            │
│                                                           │
│  app/pipelines/shared/                                   │
│  - language_detection.py (Two-stage detector)            │
│  - embedding_cache.py (Cache management)                 │
│  - topic_modeling/bertopic_engine.py (BERTopic wrapper)  │
└──────────────────────────────────────────────────────────┘
```

**Key Principle**: **Engines are generic, profiles provide policy**.

---

## Components

### 1. Language Detection (`language_detection.py`)

Generic two-stage language detector with configurable profiles.

#### `TwoStageLanguageDetector`

**Stage 1**: Script-based filtering (non-Latin script detection)
**Stage 2**: Lingua confidence-based classification
**Stage 3** (optional): Romanized marker detection

**Constructor**:
```python
class TwoStageLanguageDetector:
    def __init__(
        self,
        confidence_threshold: float,
        script_pattern: str,
        lingua_languages: tuple[Language, ...],
        target_language: Language,
        en_label: str = "en",
        non_en_label: str = "non_en",
        non_target_markers: tuple[str, ...] | None = None,
        marker_min_hits: int = 2,
    ):
        ...
```

**Parameters**:
- `confidence_threshold` - Minimum Lingua confidence for target language (e.g., 0.85)
- `script_pattern` - Regex pattern for non-Latin scripts (e.g., `r"[\u0B00-\u0B7F]"` for Odia)
- `lingua_languages` - Tuple of Lingua `Language` enums to consider
- `target_language` - Language to classify as "en" (e.g., `Language.ENGLISH`)
- `en_label`, `non_en_label` - Output labels
- `non_target_markers` - List of romanized words indicating non-target language
- `marker_min_hits` - Minimum marker matches to classify as non-target

---

**Method**: `detect_batch(texts: list[str | None]) -> tuple[list[str | None], dict[str, int]]`

Classify a batch of texts.

**Returns**:
- `labels`: List of labels ("en", "non_en", or None)
- `stats`: Dict with detection method counts

**Example Usage (ORTPS)**:
```python
from app.pipelines.shared.language_detection import TwoStageLanguageDetector
from lingua import Language

detector = TwoStageLanguageDetector(
    confidence_threshold=0.85,
    script_pattern=r"[\u0B00-\u0B7F\u0900-\u097F]",  # Odia + Devanagari
    lingua_languages=(Language.ENGLISH, Language.HINDI),
    target_language=Language.ENGLISH,
    en_label="en",
    non_en_label="non_en",
    non_target_markers=("mu", "mora", "karuchhi", "ghara"),  # Romanized Odia
    marker_min_hits=2
)

texts = [
    "I need a caste certificate",       # → "en"
    "मुझे राशन कार्ड चाहिए",           # → "non_en" (Devanagari script)
    "mu ration card karuchhi",          # → "non_en" (2 Odia markers)
    None                                 # → None
]

labels, stats = detector.detect_batch(texts)
# labels: ["en", "non_en", "non_en", None]
# stats: {"script_filtered": 1, "lingua_high_conf": 1, "romanized_markers": 1, "null": 1}
```

---

**Why This Design?**

Different pipelines can use the same detector with different profiles:

```python
# ORTPS pipeline (Odisha-specific)
ortps_detector = TwoStageLanguageDetector(
    confidence_threshold=0.85,
    script_pattern=r"[\u0B00-\u0B7F\u0900-\u097F]",  # Odia + Hindi
    lingua_languages=(Language.ENGLISH, Language.HINDI),
    target_language=Language.ENGLISH,
    non_target_markers=("mu", "mora", "karuchhi", ...)
)

# Tamil Nadu pipeline (hypothetical)
tamil_detector = TwoStageLanguageDetector(
    confidence_threshold=0.85,
    script_pattern=r"[\u0B80-\u0BFF]",  # Tamil script
    lingua_languages=(Language.ENGLISH, Language.TAMIL),
    target_language=Language.ENGLISH,
    non_target_markers=("naan", "enna", "ungal", ...)  # Romanized Tamil
)
```

Same engine, different profiles → no code duplication.

---

### 2. Embedding Cache (`embedding_cache.py`)

Utilities for caching sentence embeddings to avoid recomputation.

#### Core Functions

**`compute_text_hash(texts: list[str]) -> str`**

Compute deterministic hash of text list for cache key.

**Algorithm**: MD5 hash of concatenated texts (first 8 characters).

**Example**:
```python
from app.pipelines.shared.embedding_cache import compute_text_hash

texts = ["text1", "text2", "text3"]
hash_val = compute_text_hash(texts)  # "a3f4b9e2"
```

---

**`build_embeddings_cache_path(model_name: str, text_hash: str) -> Path`**

Construct cache file path for embeddings.

**Location**: `{directories.MODELS}/embeddings_{model_slug}_{text_hash}.pkl`

**Example**:
```python
path = build_embeddings_cache_path("sentence-transformers/all-MiniLM-L6-v2", "a3f4b9e2")
# → models/embeddings_sentence_transformers_all_MiniLM_L6_v2_a3f4b9e2.pkl
```

---

**`save_embeddings_cache(cache_path: Path, embeddings: np.ndarray, metadata: dict)`**

Save embeddings with metadata to pickle file.

**Metadata** (recommended):
```python
{
    "model_name": "sentence-transformers/all-MiniLM-L6-v2",
    "text_hash": "a3f4b9e2",
    "num_texts": 1000,
    "embedding_dim": 384
}
```

**Example**:
```python
from app.pipelines.shared.embedding_cache import save_embeddings_cache

save_embeddings_cache(
    cache_path=cache_path,
    embeddings=text_embeddings,  # (N, 384) numpy array
    metadata={
        "model_name": model_name,
        "text_hash": text_hash,
        "num_texts": len(texts),
        "embedding_dim": 384
    }
)
```

---

**`load_embeddings_cache(cache_path: Path, expected_model_name: str, expected_text_hash: str) -> np.ndarray | None`**

Load cached embeddings with validation.

**Returns**: Embeddings array or `None` if cache invalid/missing

**Validation**:
- File exists
- Model name matches
- Text hash matches

**Example**:
```python
from app.pipelines.shared.embedding_cache import load_embeddings_cache

embeddings = load_embeddings_cache(
    cache_path=cache_path,
    expected_model_name="sentence-transformers/all-MiniLM-L6-v2",
    expected_text_hash="a3f4b9e2"
)

if embeddings is None:
    # Cache miss, compute embeddings
    embeddings = model.encode(texts, ...)
    save_embeddings_cache(...)
else:
    # Cache hit
    logger.info("Loaded from cache")
```

---

**Full Caching Pattern**:

```python
from sentence_transformers import SentenceTransformer
from app.pipelines.shared.embedding_cache import *

model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
texts = ["text1", "text2", ...]

# Compute cache key
text_hash = compute_text_hash(texts)
cache_path = build_embeddings_cache_path(model.model_name, text_hash)

# Try to load
embeddings = load_embeddings_cache(
    cache_path=cache_path,
    expected_model_name=model.model_name,
    expected_text_hash=text_hash
)

if embeddings is None:
    # Cache miss - compute and save
    logger.info("Computing embeddings...")
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        batch_size=256,
        show_progress_bar=True
    )
    save_embeddings_cache(cache_path, embeddings, {
        "model_name": model.model_name,
        "text_hash": text_hash,
        "num_texts": len(texts),
        "embedding_dim": embeddings.shape[1]
    })
else:
    # Cache hit
    logger.info(f"Loaded {len(embeddings)} embeddings from cache")
```

---

**Benefits**:
- **Performance**: Avoid recomputing embeddings (2-10 min → <1 sec)
- **Reproducibility**: Same texts → same hash → same cache
- **Storage efficiency**: Pickle format (~400 MB per 100K texts)

---

### 3. Topic Modeling (`topic_modeling/bertopic_engine.py`)

Generic BERTopic wrapper with configurable parameters.

#### `TopicModelParams`

Dataclass for BERTopic configuration.

```python
@dataclass
class TopicModelParams:
    min_cluster_size: int        # HDBSCAN parameter
    min_samples: int             # HDBSCAN parameter
    top_n_words: int             # Number of representative words per topic
    n_components: int            # UMAP dimensions
    min_df: int                  # CountVectorizer min_df
    max_df: float                # CountVectorizer max_df
    calculate_probabilities: bool  # Soft clustering (expensive)
```

---

#### `TopicAnalyzer`

Generic BERTopic wrapper with adaptive parameter resolution.

**Constructor**:
```python
class TopicAnalyzer:
    def __init__(
        self,
        category: str,
        n_samples: int,
        random_state: int = 42,
        custom_stopwords: list[str] | None = None,
        params_resolver: Callable[[int], TopicModelParams] | None = None,
    ):
        ...
```

**Parameters**:
- `category` - Category name (for logging)
- `n_samples` - Number of documents to analyze
- `random_state` - Random seed for reproducibility
- `custom_stopwords` - Domain-specific stopwords (added to English stopwords)
- `params_resolver` - Function `(n_samples) -> TopicModelParams` for adaptive parameters

---

**Method**: `fit(texts: list[str], embeddings: np.ndarray) -> tuple[list[int], np.ndarray | None]`

Fit BERTopic model on pre-computed embeddings.

**Parameters**:
- `texts` - List of complaint texts
- `embeddings` - Pre-computed sentence embeddings (N, embedding_dim)

**Returns**:
- `topics` - List of topic IDs (-1 for outliers)
- `probabilities` - Soft clustering probabilities (or None)

**Example Usage (ORTPS)**:
```python
from app.pipelines.shared.topic_modeling.bertopic_engine import TopicAnalyzer, TopicModelParams

# Define adaptive parameter resolver
def get_ortps_params(n_samples: int) -> TopicModelParams:
    if n_samples < 1000:
        return TopicModelParams(
            min_cluster_size=30, min_samples=10,
            top_n_words=12, n_components=3,
            min_df=1, max_df=1.0,
            calculate_probabilities=True
        )
    # ... (other size buckets)

# ORTPS stopwords
ortps_stopwords = ["sir", "madam", "kindly", "office", "district", ...]

# Create analyzer
analyzer = TopicAnalyzer(
    category="Certificates",
    n_samples=15234,
    custom_stopwords=ortps_stopwords,
    params_resolver=get_ortps_params
)

# Fit model
texts = df["grievance"].to_list()
embeddings = model.encode(texts, ...)
topics, probs = analyzer.fit(texts, embeddings)

# Get topic info
topic_info = analyzer.get_topic_info()
print(topic_info)
# │ Topic │ Count │ Name                              │
# │ 0     │ 3201  │ caste certificate delay           │
# │ 1     │ 2156  │ income certificate pending        │
# ...
```

---

**Why This Design?**

Different pipelines can use the same analyzer with different profiles:

```python
# ORTPS pipeline
ortps_analyzer = TopicAnalyzer(
    category="Certificates",
    n_samples=15234,
    custom_stopwords=ORTPS_STOPWORDS,  # "sir", "office", "district", ...
    params_resolver=get_ortps_topic_model_params
)

# News analysis pipeline (hypothetical)
news_analyzer = TopicAnalyzer(
    category="Politics",
    n_samples=50000,
    custom_stopwords=NEWS_STOPWORDS,  # "said", "reported", "according", ...
    params_resolver=get_news_topic_model_params
)
```

Same engine, different profiles → flexible and reusable.

---

#### Additional Methods

**`get_topic_info() -> pl.DataFrame`**

Get topic statistics (topic ID, count, name, representative words).

---

**`get_topics() -> dict[int, list[tuple[str, float]]]`**

Get all topics with their top words and c-TF-IDF scores.

**Example**:
```python
topics_dict = analyzer.get_topics()
# {
#   0: [("caste", 0.82), ("certificate", 0.75), ("pending", 0.68), ...],
#   1: [("income", 0.79), ("certificate", 0.71), ("annual", 0.65), ...],
#   ...
# }
```

---

**`save_model(path: Path)`**

Save BERTopic model to disk (safetensors format).

---

## Interaction Between Components

### Example: ORTPS Pipeline Uses All Three Components

```python
from app.pipelines.shared.language_detection import TwoStageLanguageDetector
from app.pipelines.shared.embedding_cache import *
from app.pipelines.shared.topic_modeling.bertopic_engine import TopicAnalyzer

# 1. Language detection (with ORTPS profile)
detector = TwoStageLanguageDetector(
    confidence_threshold=0.85,
    script_pattern=ORTPS_SCRIPT_PATTERN,
    lingua_languages=ORTPS_LINGUA_LANGUAGES,
    target_language=Language.ENGLISH,
    non_target_markers=ORTPS_ROMANIZED_MARKERS
)
labels, stats = detector.detect_batch(texts)

# 2. Embedding cache (generic, no profile needed)
text_hash = compute_text_hash(texts)
cache_path = build_embeddings_cache_path(model_name, text_hash)
embeddings = load_embeddings_cache(cache_path, model_name, text_hash)
if embeddings is None:
    embeddings = model.encode(texts, ...)
    save_embeddings_cache(cache_path, embeddings, {...})

# 3. Topic modeling (with ORTPS profile)
analyzer = TopicAnalyzer(
    category="Certificates",
    n_samples=len(texts),
    custom_stopwords=ORTPS_STOPWORDS,
    params_resolver=get_ortps_topic_model_params
)
topics, probs = analyzer.fit(texts, embeddings)
```

---

## Testing

### Unit Tests

**Location**: `app/tests/pipelines/shared/`

- `test_language_detection.py` - TwoStageLanguageDetector tests
- `test_embedding_cache.py` - Cache utilities tests
- `test_bertopic_engine.py` - TopicAnalyzer tests

**Run**:
```bash
pytest app/tests/pipelines/shared/ -v
```

---

### Test Examples

**Language Detection**:
```python
def test_script_filter():
    detector = TwoStageLanguageDetector(
        confidence_threshold=0.85,
        script_pattern=r"[\u0900-\u097F]",  # Devanagari
        lingua_languages=(Language.ENGLISH, Language.HINDI),
        target_language=Language.ENGLISH
    )

    texts = ["Hello", "नमस्ते"]
    labels, stats = detector.detect_batch(texts)

    assert labels[0] == "en"
    assert labels[1] == "non_en"
    assert stats["script_filtered"] == 1
```

---

**Embedding Cache**:
```python
def test_cache_roundtrip(tmp_path):
    embeddings = np.random.rand(100, 384)
    cache_path = tmp_path / "test_cache.pkl"

    # Save
    save_embeddings_cache(cache_path, embeddings, {
        "model_name": "test-model",
        "text_hash": "abc123",
        "num_texts": 100,
        "embedding_dim": 384
    })

    # Load
    loaded = load_embeddings_cache(cache_path, "test-model", "abc123")
    assert loaded is not None
    np.testing.assert_array_equal(embeddings, loaded)
```

---

**Topic Analyzer**:
```python
def test_fit_topic_analyzer():
    texts = ["topic 1 text"] * 100 + ["topic 2 text"] * 100
    embeddings = np.random.rand(200, 384)

    analyzer = TopicAnalyzer(
        category="Test",
        n_samples=200,
        custom_stopwords=["stopword1", "stopword2"]
    )

    topics, probs = analyzer.fit(texts, embeddings)
    assert len(topics) == 200
    assert len(set(topics)) >= 2  # At least 2 topics found
```

---

## Design Principles

### 1. **Separation of Concerns**

- **Engines** (shared/) = Generic algorithms
- **Profiles** (pipeline-specific) = Domain policies
- **Nodes** (pipeline-specific) = Hamilton wiring

### 2. **Dependency Injection**

Engines accept configuration as constructor parameters, not hardcoded constants.

**Bad** (hardcoded):
```python
class LanguageDetector:
    def __init__(self):
        self.threshold = 0.85  # Hardcoded!
        self.script_pattern = r"[\u0B00-\u0B7F]"  # Hardcoded!
```

**Good** (injectable):
```python
class LanguageDetector:
    def __init__(self, confidence_threshold: float, script_pattern: str):
        self.threshold = confidence_threshold
        self.script_pattern = script_pattern
```

### 3. **Caching for Performance**

All expensive operations (embeddings, models) should be cacheable:
- Deterministic cache keys (hashes)
- Validation on load (model name, hash)
- Graceful fallback (recompute on cache miss)

### 4. **Polars-First**

When returning DataFrames, prefer Polars over Pandas for performance.

```python
# Good
def get_topic_info() -> pl.DataFrame:
    return pl.from_pandas(self.model.get_topic_info())

# Avoid
def get_topic_info() -> pd.DataFrame:
    return self.model.get_topic_info()
```

---

## Adding New Shared Components

### 1. Identify Reusable Pattern

Ask: "Would another pipeline benefit from this?"

**Examples**:
- ✅ Generic text preprocessing (tokenization, normalization)
- ✅ Named entity recognition (with configurable entity types)
- ✅ Sentiment analysis (with configurable model)
- ❌ ORTPS-specific keyword lists (domain-specific, not reusable)

### 2. Design with Profiles in Mind

Extract configurable parameters:
- Stopwords → custom_stopwords parameter
- Thresholds → threshold parameter
- Models → model_name parameter
- Language-specific logic → marker parameters

### 3. Write Unit Tests

Test with multiple profiles to ensure generalizability:
```python
def test_with_ortps_profile():
    ...

def test_with_tamil_profile():
    ...
```

### 4. Document Profile Interface

Clearly document what profiles are expected:
```python
def __init__(
    self,
    custom_stopwords: list[str] | None = None,
    params_resolver: Callable[[int], ModelParams] | None = None,
):
    """
    Initialize analyzer.

    Parameters
    ----------
    custom_stopwords : list[str] | None
        Domain-specific stopwords to add to English stopwords.
        Example: ["sir", "madam", "office", ...] for ORTPS
    params_resolver : Callable[[int], ModelParams] | None
        Function taking n_samples and returning ModelParams.
        Example: lambda n: ModelParams(min_cluster_size=max(30, n//100))
    """
```

---

## Related Components

- **ORTPS Pipeline**: `app/pipelines/ortps/` - Primary consumer of shared utilities
- **ORTPS Profiles**: `app/pipelines/ortps/language_profiles.py`, `topic_profiles.py`
- **Hamilton Driver**: `app/pipelines/_driver.py` - Driver factory for pipelines
- **Configuration**: `app/config.py` - Directories for model cache

## References

- [Hamilton Documentation](https://hamilton.dagworks.io/)
- [Lingua GitHub](https://github.com/pemistahl/lingua-py)
- [Sentence Transformers](https://www.sbert.net/)
- [BERTopic Documentation](https://maartengr.github.io/BERTopic/)
