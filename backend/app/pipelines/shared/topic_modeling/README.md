# Topic Modeling Engine

Reusable BERTopic wrapper for theme extraction from complaint text.

## Overview

This module provides a generic BERTopic implementation that can be configured with domain-specific profiles (stopwords, adaptive parameters). It wraps BERTopic's core functionality with:
- Adaptive parameter selection based on dataset size
- Custom stopword injection
- Outlier reduction
- Polars DataFrame integration
- Safetensors model persistence

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│      TopicAnalyzer (Generic Engine)                     │
│                                                          │
│  - Accepts custom_stopwords                             │
│  - Accepts params_resolver function                     │
│  - Manages BERTopic lifecycle                           │
│  - Returns Polars DataFrames                            │
└─────────────────────────────────────────────────────────┘
                         ↓ calls
┌─────────────────────────────────────────────────────────┐
│        BERTopic Library (maartengr/BERTopic)            │
│                                                          │
│  Components:                                            │
│  - UMAP: Dimensionality reduction                       │
│  - HDBSCAN: Clustering                                  │
│  - CountVectorizer: c-TF-IDF representation             │
└─────────────────────────────────────────────────────────┘
```

## Components

### `TopicModelParams`

Dataclass for BERTopic configuration parameters.

```python
@dataclass
class TopicModelParams:
    """Configuration for BERTopic model."""

    min_cluster_size: int
    """Minimum cluster size for HDBSCAN."""

    min_samples: int
    """Minimum samples per cluster for HDBSCAN."""

    top_n_words: int
    """Number of representative words per topic."""

    n_components: int
    """Number of UMAP dimensions."""

    min_df: int
    """Minimum document frequency for CountVectorizer."""

    max_df: float
    """Maximum document frequency for CountVectorizer (as fraction)."""

    calculate_probabilities: bool
    """Whether to calculate soft clustering probabilities (expensive)."""
```

**Usage**:
```python
params = TopicModelParams(
    min_cluster_size=50,
    min_samples=15,
    top_n_words=10,
    n_components=5,
    min_df=2,
    max_df=1.0,
    calculate_probabilities=True
)
```

---

### `TopicAnalyzer`

Generic BERTopic wrapper with profile injection.

#### Constructor

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
        """
        Initialize topic analyzer.

        Parameters
        ----------
        category : str
            Category name (for logging and identification)
        n_samples : int
            Number of documents to analyze
        random_state : int
            Random seed for reproducibility
        custom_stopwords : list[str] | None
            Domain-specific stopwords to add to sklearn's ENGLISH_STOP_WORDS
        params_resolver : Callable[[int], TopicModelParams] | None
            Function mapping n_samples → TopicModelParams for adaptive configuration
            If None, uses default adaptive resolver
        """
```

**Example**:
```python
from app.pipelines.shared.topic_modeling.bertopic_engine import TopicAnalyzer, TopicModelParams

# Define adaptive parameter function
def get_params(n_samples: int) -> TopicModelParams:
    if n_samples < 1000:
        return TopicModelParams(
            min_cluster_size=30,
            min_samples=10,
            top_n_words=12,
            n_components=3,
            min_df=1,
            max_df=1.0,
            calculate_probabilities=True
        )
    elif n_samples < 5000:
        return TopicModelParams(
            min_cluster_size=50,
            min_samples=15,
            top_n_words=10,
            n_components=5,
            min_df=1,
            max_df=1.0,
            calculate_probabilities=True
        )
    else:
        return TopicModelParams(
            min_cluster_size=100,
            min_samples=30,
            top_n_words=10,
            n_components=5,
            min_df=2,
            max_df=1.0,
            calculate_probabilities=False  # Too expensive for large datasets
        )

# Create analyzer
analyzer = TopicAnalyzer(
    category="Certificates",
    n_samples=15234,
    custom_stopwords=["sir", "madam", "office", "district"],
    params_resolver=get_params
)
```

---

#### Methods

##### `fit(texts: list[str], embeddings: np.ndarray) -> tuple[list[int], np.ndarray | None]`

Fit BERTopic model on pre-computed embeddings.

**Parameters**:
- `texts` (list[str]) - List of document texts
- `embeddings` (np.ndarray) - Pre-computed embeddings with shape (n_texts, embedding_dim)

**Returns**:
- `topics` (list[int]) - Topic assignments (-1 for outliers)
- `probabilities` (np.ndarray | None) - Soft clustering probabilities (if `calculate_probabilities=True`)

**Process**:
1. Creates BERTopic model with resolved parameters
2. Fits model on texts + embeddings
3. Logs topic statistics (count, outlier rate)
4. Reduces outliers if rate > 20% (using probability-based strategy)
5. Returns topic assignments and probabilities

**Example**:
```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")
texts = df["grievance"].to_list()
embeddings = model.encode(texts, normalize_embeddings=True)

analyzer = TopicAnalyzer("Certificates", len(texts), custom_stopwords=[...])
topics, probs = analyzer.fit(texts, embeddings)

# topics: [0, 1, 0, -1, 2, 1, ...]
# -1 = outlier (no clear topic)
# 0, 1, 2, ... = topic IDs
```

---

##### `get_topic_info() -> pl.DataFrame`

Extract topic information as Polars DataFrame.

**Returns**: DataFrame with columns:
- `Topic` (int) - Topic ID
- `Count` (int) - Number of documents in topic
- `Name` (str) - Auto-generated topic name from top words
- `Representation` (list[str]) - Representative words
- Other BERTopic metadata columns

**Example**:
```python
topic_info = analyzer.get_topic_info()
print(topic_info)

# Output:
# ┌────────┬───────┬──────────────────────────┬─────────────────────────────┐
# │ Topic  │ Count │ Name                     │ Representation              │
# ├────────┼───────┼──────────────────────────┼─────────────────────────────┤
# │ 0      │ 3201  │ caste certificate delay  │ [caste, certificate, st...] │
# │ 1      │ 2156  │ income certificate...    │ [income, annual, family...] │
# │ 2      │ 1845  │ birth certificate...     │ [birth, certificate, ch...] │
# │ -1     │ 8032  │ outliers                 │ []                          │
# └────────┴───────┴──────────────────────────┴─────────────────────────────┘
```

---

##### `get_topics() -> dict[int, list[tuple[str, float]]]`

Get all topics with their top words and c-TF-IDF scores.

**Returns**: Dict mapping topic_id → list of (word, score) tuples

**Example**:
```python
topics_dict = analyzer.get_topics()

print(topics_dict[0])
# Output:
# [
#   ("caste", 0.823),
#   ("certificate", 0.751),
#   ("sc", 0.689),
#   ("pending", 0.645),
#   ("applied", 0.612),
#   ...
# ]
```

---

##### `save_model(path: Path) -> None`

Save BERTopic model to disk using safetensors format.

**Parameters**:
- `path` (Path) - Output file path (e.g., `output/models/bertopic_certificates.safetensors`)

**Example**:
```python
from pathlib import Path

analyzer.save_model(Path("output/models/bertopic_certificates.safetensors"))
# Saved model to output/models/bertopic_certificates.safetensors
```

**Loading**:
```python
from bertopic import BERTopic

model = BERTopic.load("output/models/bertopic_certificates.safetensors")
topics = model.get_topics()
```

---

## BERTopic Components

### UMAP (Dimensionality Reduction)

Reduces embedding dimensions (e.g., 384 → 5) for efficient clustering.

**Parameters** (set by `TopicAnalyzer`):
- `n_neighbors=15` - Size of local neighborhood (fixed)
- `n_components` - Target dimensions (adaptive: 3 for small, 5 for large)
- `min_dist=0.0` - Minimum distance between points (fixed)
- `metric="cosine"` - Distance metric (fixed)

---

### HDBSCAN (Clustering)

Hierarchical density-based clustering to find topics.

**Parameters** (set by `TopicAnalyzer`):
- `min_cluster_size` - Minimum documents per topic (adaptive: 30-100)
- `min_samples` - Minimum samples for core points (adaptive: 10-30)
- `metric="euclidean"` - Distance metric (fixed)
- `cluster_selection_method="eom"` - Excess of Mass (fixed)

**Why Adaptive?**
- Small datasets (<1000): Smaller clusters (30) to avoid merging distinct topics
- Large datasets (>5000): Larger clusters (100) to avoid over-fragmentation

---

### CountVectorizer (c-TF-IDF)

Extracts representative words per topic using class-based TF-IDF.

**Parameters** (set by `TopicAnalyzer`):
- `ngram_range=(1, 3)` - Capture 1-3 word phrases
- `token_pattern=r"\b[a-z]{3,}\b"` - Only lowercase words ≥3 chars (no numbers)
- `stop_words` - English stopwords + custom stopwords
- `min_df` - Minimum document frequency (adaptive: 1-2)
- `max_df` - Maximum document frequency (adaptive: 1.0 = no upper limit)

**Why `max_df=1.0`?**
Prevents "min_df/max_df conflict" errors when few unique documents exist per cluster.

---

## Outlier Reduction

If outlier rate > 20%, `TopicAnalyzer` automatically attempts reduction:

**Strategy**: Probabilistic assignment
- For each outlier, assign to the topic with highest probability
- Only if probability > threshold (default: 0.05)

**Example**:
```
Initial: 8032 outliers (20.5%)
After reduction: 3421 outliers (8.7%)
```

**Logging**:
```
WARNING | Certificates: High outlier rate (20.5%), attempting reduction...
INFO    | Certificates: Outlier rate after reduction: 8.7%
```

---

## Adaptive Parameter Resolution

### Default Resolver

If no `params_resolver` provided, uses built-in defaults:

```python
def _default_params_resolver(n_samples: int) -> TopicModelParams:
    if n_samples < 1000:
        return TopicModelParams(
            min_cluster_size=30, min_samples=10,
            top_n_words=10, n_components=3,
            min_df=1, max_df=1.0,
            calculate_probabilities=True
        )
    elif n_samples < 5000:
        return TopicModelParams(
            min_cluster_size=50, min_samples=15,
            top_n_words=10, n_components=5,
            min_df=1, max_df=1.0,
            calculate_probabilities=True
        )
    else:
        return TopicModelParams(
            min_cluster_size=100, min_samples=30,
            top_n_words=10, n_components=5,
            min_df=2, max_df=1.0,
            calculate_probabilities=False
        )
```

### Custom Resolver (ORTPS Example)

```python
def get_ortps_params(n_samples: int) -> TopicModelParams:
    """ORTPS-specific adaptive parameters."""
    if n_samples < 1000:
        return TopicModelParams(
            min_cluster_size=30,
            min_samples=10,
            top_n_words=12,  # More words for better interpretability
            n_components=3,
            min_df=1,
            max_df=1.0,
            calculate_probabilities=True
        )
    # ... (similar for other ranges)
```

---

## Stopword Management

### English Stopwords (sklearn)

Automatically included:
- Common words: "the", "a", "an", "and", "or", "is", "was", ...
- Pronouns: "I", "you", "he", "she", "it", "they", ...
- Prepositions: "in", "on", "at", "from", "to", ...

### Custom Stopwords (Domain-Specific)

Injected via `custom_stopwords` parameter.

**ORTPS Example**:
```python
ORTPS_STOPWORDS = [
    # Petition boilerplate
    "sir", "madam", "kindly", "please", "request",
    # Generic admin terms
    "office", "department", "district", "grievance",
    # Poverty language
    "poor", "bpl", "needy", "helpless",
    # Odisha place names
    "bhubaneswar", "cuttack", "puri",
]

analyzer = TopicAnalyzer(
    category="Certificates",
    n_samples=15234,
    custom_stopwords=ORTPS_STOPWORDS
)
```

**Why Custom Stopwords?**
Generic stopwords don't capture domain-specific filler words. Without custom stopwords, topics contain unhelpful words like "sir", "office", "district" instead of meaningful keywords.

---

## Usage Examples

### Basic Usage

```python
from app.pipelines.shared.topic_modeling.bertopic_engine import TopicAnalyzer
from sentence_transformers import SentenceTransformer

# Load texts
texts = df["grievance"].to_list()

# Compute embeddings
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
embeddings = model.encode(texts, normalize_embeddings=True)

# Create analyzer
analyzer = TopicAnalyzer(
    category="Certificates",
    n_samples=len(texts)
)

# Fit model
topics, probs = analyzer.fit(texts, embeddings)

# Get topic info
topic_info = analyzer.get_topic_info()
print(topic_info)
```

---

### With Custom Stopwords

```python
analyzer = TopicAnalyzer(
    category="Certificates",
    n_samples=len(texts),
    custom_stopwords=["sir", "madam", "office", "district", "grievance"]
)

topics, probs = analyzer.fit(texts, embeddings)
```

---

### With Custom Parameters

```python
def my_params(n_samples: int) -> TopicModelParams:
    # Always use same parameters (not adaptive)
    return TopicModelParams(
        min_cluster_size=50,
        min_samples=20,
        top_n_words=15,
        n_components=5,
        min_df=3,
        max_df=0.95,
        calculate_probabilities=True
    )

analyzer = TopicAnalyzer(
    category="Certificates",
    n_samples=len(texts),
    params_resolver=my_params
)

topics, probs = analyzer.fit(texts, embeddings)
```

---

### Extract Topic Keywords

```python
topics_dict = analyzer.get_topics()

for topic_id, words_scores in topics_dict.items():
    if topic_id == -1:
        continue  # Skip outliers

    print(f"Topic {topic_id}:")
    for word, score in words_scores[:5]:
        print(f"  {word}: {score:.3f}")
```

**Output**:
```
Topic 0:
  caste: 0.823
  certificate: 0.751
  sc: 0.689
  pending: 0.645
  applied: 0.612

Topic 1:
  income: 0.791
  certificate: 0.715
  annual: 0.653
  family: 0.628
  verification: 0.601
```

---

## Performance Considerations

### Computational Cost

| Dataset Size | Embedding Time | UMAP Time | HDBSCAN Time | Total Time |
|--------------|----------------|-----------|--------------|------------|
| 1,000        | 30s (CPU)      | 2s        | 3s           | ~35s       |
| 5,000        | 2.5min (CPU)   | 10s       | 15s          | ~3min      |
| 15,000       | 7.5min (CPU)   | 30s       | 2min         | ~10min     |
| 50,000       | 25min (CPU)    | 3min      | 10min        | ~38min     |

**Bottleneck**: Embedding computation (use GPU for 5-10x speedup)

---

### Memory Usage

- **Embeddings**: ~1.5 KB per text (384-dim float32)
  - 10K texts: ~15 MB
  - 100K texts: ~150 MB
- **UMAP/HDBSCAN**: 2-5x embedding size during computation
- **BERTopic Model**: ~100-500 MB (depends on vocabulary size)

---

### Optimization Tips

1. **Use cached embeddings** (via `embedding_cache.py`)
2. **Disable probabilities** for large datasets (`calculate_probabilities=False`)
3. **Increase min_cluster_size** to reduce number of topics
4. **Filter outliers** before topic analysis (e.g., remove <10 word texts)

---

## Troubleshooting

### Issue: "min_df/max_df conflict"

**Error**:
```
ValueError: max_df corresponds to < documents than min_df
```

**Cause**: Too few unique documents per cluster, combined with strict `min_df` and `max_df`.

**Solution**: Set `max_df=1.0` (no upper limit) in `TopicModelParams`.

---

### Issue: Too many outliers (>30%)

**Symptoms**:
- Most topics are very small
- Topic -1 (outliers) dominates

**Solutions**:
1. **Lower `min_cluster_size`** - Allow smaller topics
2. **Increase `n_components`** - Give UMAP more dimensions
3. **Use better embeddings** - Try larger embedding model
4. **Filter noise** - Remove very short/generic texts before topic modeling

---

### Issue: Topics are too broad

**Symptoms**:
- Only 1-2 topics found
- Topic keywords are very generic

**Solutions**:
1. **Increase `min_cluster_size`** - Force more granular clustering
2. **Add more stopwords** - Filter generic words
3. **Use higher `n_components`** - Preserve more nuance in UMAP

---

## Testing

### Unit Tests

**Location**: `app/tests/pipelines/shared/test_bertopic_engine.py`

**Run**:
```bash
pytest app/tests/pipelines/shared/test_bertopic_engine.py -v
```

---

### Test Example

```python
import numpy as np
from app.pipelines.shared.topic_modeling.bertopic_engine import TopicAnalyzer

def test_fit_topic_analyzer():
    # Create synthetic data
    texts = (
        ["topic 1 keyword1 keyword2"] * 100 +
        ["topic 2 keyword3 keyword4"] * 100
    )
    embeddings = np.random.rand(200, 384)

    # Fit analyzer
    analyzer = TopicAnalyzer("Test", 200)
    topics, probs = analyzer.fit(texts, embeddings)

    # Verify
    assert len(topics) == 200
    assert len(set(topics)) >= 2  # At least 2 topics
    assert -1 in topics or len(set(topics)) >= 2  # Outliers or multiple topics

    # Get topic info
    topic_info = analyzer.get_topic_info()
    assert "Topic" in topic_info.columns
    assert "Count" in topic_info.columns
```

---

## Related Components

- **Embedding Cache**: `app/pipelines/shared/embedding_cache.py` - Cache embeddings before topic modeling
- **ORTPS Topic Profile**: `app/pipelines/ortps/topic_profiles.py` - ORTPS-specific stopwords and params
- **ORTPS Topic Nodes**: `app/pipelines/ortps/topic_nodes.py` - Hamilton nodes using TopicAnalyzer

## References

- [BERTopic Documentation](https://maartengr.github.io/BERTopic/)
- [UMAP Documentation](https://umap-learn.readthedocs.io/)
- [HDBSCAN Documentation](https://hdbscan.readthedocs.io/)
- [c-TF-IDF Paper](https://github.com/MaartenGr/BERTopic#class-based-tf-idf)
