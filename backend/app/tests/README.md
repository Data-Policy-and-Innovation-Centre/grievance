# Tests Module

Pytest-based test suite for the Grievance Analytics system.

## Overview

Comprehensive test coverage for API endpoints, database operations, ingestion workflows, and data pipelines. Uses pytest with async support, fixtures, and mocking for isolated unit tests and end-to-end integration tests.

## Test Structure

```
app/tests/
├── conftest.py                          # Shared fixtures (test_db, async_client, etc.)
├── pipelines/                           # Pipeline tests
│   ├── conftest.py                      # Pipeline-specific fixtures
│   ├── shared/                          # Shared utility tests
│   │   ├── test_embedding_cache.py      # Embedding cache tests
│   │   ├── test_language_detection.py   # Language detection tests
│   │   └── test_bertopic_engine.py      # Topic modeling tests
│   ├── test_lang_detection_nodes.py     # Language detection nodes
│   ├── test_category_labeling_nodes.py  # Category labeling nodes
│   ├── test_topic_nodes.py              # Topic modeling nodes
│   └── test_ortps_integration.py        # End-to-end ORTPS pipeline
├── test_crud.py                         # Database CRUD operations
├── test_health.py                       # API health endpoint
├── test_document_ingest.py              # Document download tests
├── test_ingestion_api_client.py         # API client tests
├── test_ingestion_orchestration.py      # Ingestion orchestrator tests
├── test_integration_ingestion.py        # End-to-end ingestion tests
├── test_s3service.py                    # S3 service tests
└── test_schemas.py                      # Pydantic schema validation tests
```

## Running Tests

### All Tests

```bash
pytest app/tests/ -v
```

### With Coverage

```bash
pytest app/tests/ --cov=app --cov-report=html --cov-report=term
```

Open coverage report: `open htmlcov/index.html`

### Specific Module

```bash
# Database tests
pytest app/tests/test_crud.py -v

# Pipeline tests
pytest app/tests/pipelines/ -v

# Shared utilities tests
pytest app/tests/pipelines/shared/ -v
```

### Specific Test

```bash
pytest app/tests/test_crud.py::test_bulk_load_complaints -v
```

### Run with Markers

```bash
# Only integration tests
pytest app/tests/ -m integration -v

# Skip slow tests
pytest app/tests/ -m "not slow" -v
```

## Key Fixtures (`conftest.py`)

### `test_db`

In-memory SQLite database for isolated testing.

```python
@pytest.fixture
async def test_db():
    """Create test database with schema."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSession(engine) as session:
        yield session

    await engine.dispose()
```

**Usage**:
```python
@pytest.mark.asyncio
async def test_create_complaint(test_db):
    complaint = Complaint(ticket_no="TEST001", ...)
    await crud.bulk_load_complaints(test_db, [complaint])
    result = await crud.get_complaint_by_ticket(test_db, "TEST001")
    assert result.ticket_no == "TEST001"
```

---

### `async_client`

AsyncClient for testing FastAPI endpoints.

```python
@pytest.fixture
async def async_client():
    """Create async HTTP client for API tests."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
```

**Usage**:
```python
@pytest.mark.asyncio
async def test_health_endpoint(async_client):
    response = await async_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

---

### `sample_english_df`

Sample English complaints DataFrame for pipeline tests.

```python
@pytest.fixture
def sample_english_df():
    """Sample English complaints for testing."""
    return pl.DataFrame({
        "grievance": [
            "Need caste certificate urgently",
            "Income certificate pending",
            "My ration card is not working"
        ],
        "language": ["en", "en", "en"],
        "ticket_no": ["TKT001", "TKT002", "TKT003"]
    })
```

**Usage**:
```python
def test_category_labeling(sample_english_df):
    labeler = CategoryLabeler()
    result = labeler.label_dataframe(sample_english_df, method="keyword")
    assert "ortps_category" in result.columns
```

---

## Test Categories

### 1. Unit Tests

Test individual functions/classes in isolation using mocks.

**Example**: `test_embedding_cache.py`
```python
def test_compute_text_hash():
    """Test deterministic text hashing."""
    texts1 = ["hello", "world"]
    texts2 = ["hello", "world"]
    texts3 = ["world", "hello"]  # Different order

    hash1 = compute_text_hash(texts1)
    hash2 = compute_text_hash(texts2)
    hash3 = compute_text_hash(texts3)

    assert hash1 == hash2  # Same texts → same hash
    assert hash1 != hash3  # Different order → different hash
```

---

### 2. Integration Tests

Test multiple components working together with real database.

**Example**: `test_ortps_integration.py`
```python
@pytest.mark.asyncio
async def test_full_ortps_pipeline(test_db):
    """Test complete ORTPS pipeline end-to-end."""
    # Load sample data
    raw_df = pl.read_parquet("tests/fixtures/sample_complaints.parquet")

    # Run pipeline
    config = OrtpsPipelineConfig(sample_size=100)
    result = run_pipeline(raw_df, config)

    # Verify outputs
    assert "df_labeled" in result
    assert "ortps_category" in result["df_labeled"].columns
    assert result["df_labeled"]["ortps_category"].null_count() < len(result["df_labeled"])
```

---

### 3. API Tests

Test FastAPI endpoints with async client.

**Example**: `test_health.py`
```python
@pytest.mark.asyncio
async def test_health_check(async_client):
    """Test /health endpoint."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

---

### 4. Database Tests

Test CRUD operations with test database.

**Example**: `test_crud.py`
```python
@pytest.mark.asyncio
async def test_bulk_load_complaints(test_db):
    """Test bulk complaint insertion."""
    complaints = [
        Complaint(ticket_no="TEST001", grievance="Test 1", ...),
        Complaint(ticket_no="TEST002", grievance="Test 2", ...)
    ]

    stored = await crud.bulk_load_complaints(test_db, complaints)
    assert len(stored) == 2

    # Verify retrieval
    all_complaints = await crud.get_all_complaints(test_db)
    assert len(all_complaints) == 2
```

---

## Mocking External Dependencies

### Mock API Client

```python
from unittest.mock import AsyncMock

@pytest.fixture
def mock_api_client(monkeypatch):
    """Mock JanasunaniAPIClient."""
    client = AsyncMock()
    client.get_districts.return_value = [
        {"distId": 1, "distName": "Khordha"}
    ]
    client.get_complaints.return_value = [
        {"ticketNo": "TEST001", "grievanceDetails": "Test complaint", ...}
    ]

    monkeypatch.setattr(
        "app.ingestion.orchestrator.JanasunaniAPIClient",
        lambda: client
    )
    return client
```

---

### Mock S3 Client

```python
@pytest.fixture
def mock_s3(monkeypatch):
    """Mock boto3 S3 client."""
    mock_client = MagicMock()
    mock_client.upload_file.return_value = None
    mock_client.download_file.return_value = None

    monkeypatch.setattr("boto3.client", lambda x: mock_client)
    return mock_client
```

---

### Mock Sentence Transformer

```python
@pytest.fixture
def mock_sentence_transformer(monkeypatch):
    """Mock SentenceTransformer for faster tests."""
    mock_model = MagicMock()
    mock_model.encode.return_value = np.random.rand(10, 384)

    monkeypatch.setattr(
        "app.pipelines.ortps.labelers.SentenceTransformer",
        lambda model_name, device: mock_model
    )
    return mock_model
```

---

## Test Markers

Define custom markers in `pytest.ini`:

```ini
[pytest]
markers =
    slow: marks tests as slow (skip with -m "not slow")
    integration: marks tests as integration tests
    unit: marks tests as unit tests
    requires_api: marks tests that require external API
```

**Usage**:
```python
@pytest.mark.slow
@pytest.mark.integration
async def test_full_ingestion_workflow():
    """Slow integration test."""
    ...

@pytest.mark.unit
def test_compute_text_hash():
    """Fast unit test."""
    ...
```

**Run only unit tests**:
```bash
pytest -m unit -v
```

---

## Testing Best Practices

### 1. Isolate Tests

Each test should be independent:
- Use fixtures for setup/teardown
- Use in-memory database (`:memory:`)
- Mock external dependencies (API, S3)

### 2. Test Naming Convention

Use descriptive test names:
```python
# Good
def test_bulk_load_complaints_handles_duplicates()
def test_language_detector_filters_non_latin_script()
def test_category_labeler_keyword_matching_case_insensitive()

# Bad
def test_1()
def test_complaints()
```

### 3. Arrange-Act-Assert (AAA)

Structure tests clearly:
```python
def test_example():
    # Arrange: Setup test data
    labeler = CategoryLabeler()
    df = pl.DataFrame({"grievance": ["test complaint"]})

    # Act: Execute function
    result = labeler.label_dataframe(df, method="keyword")

    # Assert: Verify outcome
    assert "ortps_category" in result.columns
    assert result["ortps_category"][0] is not None
```

### 4. Use Parametrize for Multiple Cases

```python
@pytest.mark.parametrize("text,expected_category", [
    ("Need caste certificate", "Certificates"),
    ("Scholarship not received", "Scholarship"),
    ("Ration card issue", "Ration card"),
])
def test_keyword_matching(text, expected_category):
    labeler = CategoryLabeler()
    df = pl.DataFrame({"grievance": [text]})
    result = labeler.label_dataframe(df, method="keyword")
    assert result["ortps_category"][0] == expected_category
```

### 5. Test Edge Cases

```python
def test_empty_dataframe():
    """Test with empty input."""
    labeler = CategoryLabeler()
    df = pl.DataFrame({"grievance": []})
    result = labeler.label_dataframe(df)
    assert len(result) == 0

def test_null_grievance_text():
    """Test with None/null grievance."""
    labeler = CategoryLabeler()
    df = pl.DataFrame({"grievance": [None, "valid text"]})
    result = labeler.label_dataframe(df)
    assert result["ortps_category"][0] is None
```

---

## Coverage Goals

**Target**: >80% code coverage

**Current Coverage** (approximate):
- `app/db/`: 85%
- `app/pipelines/shared/`: 90%
- `app/pipelines/ortps/`: 75%
- `app/ingestion/`: 70%
- `app/api/`: 60%

**Uncovered Areas**:
- Error handling edge cases
- Retry logic branches
- S3 upload failures

---

## Continuous Integration

### GitHub Actions (Planned)

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.13'
      - name: Install dependencies
        run: |
          pip install -e .
          pip install pytest pytest-asyncio pytest-cov
      - name: Run tests
        run: pytest app/tests/ --cov=app --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

---

## Debugging Failed Tests

### Run with Verbose Output

```bash
pytest app/tests/test_crud.py -vv
```

### Run with Print Statements

```bash
pytest app/tests/test_crud.py -s
```

### Run with PDB Debugger

```bash
pytest app/tests/test_crud.py --pdb
```

### Show Local Variables on Failure

```bash
pytest app/tests/test_crud.py -l
```

---

## Related Components

- **Source Code**: `app/` - All application code being tested
- **Fixtures**: `app/tests/conftest.py`, `app/tests/pipelines/conftest.py` - Shared test setup
- **CI/CD**: `.github/workflows/` (planned) - Automated test execution

## References

- [Pytest Documentation](https://docs.pytest.org/)
- [Pytest-Asyncio](https://pytest-asyncio.readthedocs.io/)
- [HTTPX AsyncClient](https://www.python-httpx.org/async/)
- [Testing FastAPI](https://fastapi.tiangolo.com/tutorial/testing/)
