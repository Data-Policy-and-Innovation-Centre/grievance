# Ingestion Module

Orchestrates data ingestion from the Janasunani public grievance portal API into the local SQLite database.

## Overview

This module handles the complete ingestion pipeline: fetching district metadata, complaints, action history, and downloading associated documents. It includes retry logic, progress tracking, and API request deduplication.

## Architecture

```
app/ingestion/
├── __init__.py           # Constants (OFFICE, STATUS codes)
├── client.py             # JanasunaniAPIClient (HTTP client)
├── orchestrator.py       # IngestionOrchestrator (coordination)
├── document_ingestion.py # DocumentService (document downloads)
└── schemas.py            # Pydantic validation schemas
```

## Data Flow

```
┌────────────────────────────────────────────────────────────┐
│                   Janasunani API                            │
│  (https://janasunani.odisha.gov.in/api/DataServices)       │
└────────────────────────────────────────────────────────────┘
                            ↓
        ┌───────────────────┼───────────────────┐
        ↓                   ↓                   ↓
┌──────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  Districts   │  │   Complaints     │  │  Action History  │
│    API       │  │      API         │  │       API        │
└──────────────┘  └──────────────────┘  └──────────────────┘
        ↓                   ↓                   ↓
┌──────────────────────────────────────────────────────────┐
│           JanasunaniAPIClient (client.py)                 │
│  - HTTP requests with retry logic                        │
│  - Rate limiting via semaphore                           │
│  - Error handling and logging                            │
└──────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────┐
│       IngestionOrchestrator (orchestrator.py)             │
│  - Coordinate multi-entity ingestion                     │
│  - Progress tracking with tqdm                           │
│  - API request deduplication                             │
│  - Document download orchestration                       │
└──────────────────────────────────────────────────────────┘
                            ↓
        ┌───────────────────┼───────────────────┐
        ↓                   ↓                   ↓
┌──────────────┐  ┌──────────────────┐  ┌──────────────────┐
│   Pydantic   │  │   CRUD Layer     │  │  DocumentService │
│  Validation  │  │   (db/crud.py)   │  │ (S3 + Local)     │
└──────────────┘  └──────────────────┘  └──────────────────┘
        ↓                   ↓                   ↓
┌──────────────────────────────────────────────────────────┐
│              SQLite Database + S3 Storage                 │
│  - complaints table (main data)                          │
│  - action_history table (tracking)                       │
│  - api_request_tracking (deduplication)                  │
│  - S3 bucket (documents)                                 │
└──────────────────────────────────────────────────────────┘
```

## Components

### 1. API Client (`client.py`)

`JanasunaniAPIClient` - HTTP client for Janasunani API endpoints.

#### Configuration

```python
from app.config import settings

client = JanasunaniAPIClient()
# Uses settings.JANASUNANI_API_BASE_URL
# Uses settings.JANASUNANI_API_USERNAME
# Uses settings.JANASUNANI_API_PASSWORD
```

#### Key Methods

**`get_districts() -> list[dict]`**

Fetch all districts from Janasunani API.

```python
districts = client.get_districts()
# Returns: [{"distId": 1, "distName": "Khordha"}, ...]
```

---

**`async get_complaints(year, distId, status, office, semaphore) -> list[dict] | None`**

Fetch complaints for specific parameters.

**Parameters**:
- `year` (int) - Complaint year (e.g., 2024)
- `distId` (int) - District ID (1-30)
- `status` (int) - Status code (0=Resolved, 1=Pending, etc.)
- `office` (int) - Office code (1=Collectorate, 2=Block, etc.)
- `semaphore` (asyncio.Semaphore) - Rate limiting

**Returns**: List of complaint dicts or `None` if API error

**Example**:
```python
semaphore = asyncio.Semaphore(5)
complaints = await client.get_complaints(2024, 1, 0, 1, semaphore)
```

---

**`async get_action_history(ticket_no, semaphore) -> list[dict] | None`**

Fetch action history for a complaint.

**Parameters**:
- `ticket_no` (str) - Complaint ticket number
- `semaphore` (asyncio.Semaphore) - Rate limiting

**Returns**: List of action history dicts

---

**`async download_document(url, semaphore) -> bytes | None`**

Download document from Janasunani portal.

**Parameters**:
- `url` (str) - Document URL
- `semaphore` (asyncio.Semaphore) - Rate limiting

**Returns**: Document bytes or `None` if error

---

### 2. Orchestrator (`orchestrator.py`)

`IngestionOrchestrator` - Coordinates the full ingestion pipeline.

#### Initialization

```python
from app.ingestion.orchestrator import IngestionOrchestrator
from app.db.session import AsyncSessionLocal

async with AsyncSessionLocal() as db:
    orchestrator = IngestionOrchestrator(
        db=db,
        semaphore_value=5  # Concurrent API requests
    )
```

#### Key Methods

**`async ingest_districts() -> list[District]`**

Ingest district reference data.

**Flow**:
1. Fetch from API
2. Validate with Pydantic
3. Bulk load to `districts` table
4. Return validated districts

**Usage**:
```python
districts = await orchestrator.ingest_districts()
logger.info(f"Ingested {len(districts)} districts")
```

---

**`async ingest_complaints(year, distId, status, office) -> list[Complaint]`**

Ingest complaints for specific parameters.

**Flow**:
1. Check `api_request_tracking` for duplicates
2. If new, fetch from API
3. Validate with Pydantic
4. Bulk load to `complaints` table
5. Record success in `api_request_tracking`
6. Return validated complaints

**Error Handling**:
- On failure, increments `failure_count` in tracking table
- Returns empty list on error

**Usage**:
```python
complaints = await orchestrator.ingest_complaints(
    year=2024,
    distId=1,
    status=0,  # Resolved
    office=1   # Collectorate
)
```

---

**`async ingest_action_history(ticket_no) -> list[ActionHistory]`**

Ingest action history for a complaint.

**Flow**:
1. Check `action_history_api_request_tracking` for duplicates
2. If new, fetch from API
3. Validate with Pydantic
4. Bulk load to `action_history` table
5. Record success in tracking table

---

**`async orchestrate_full_ingestion(years, districts, statuses, offices)`**

Orchestrate full ingestion across all parameter combinations.

**Parameters**:
- `years` (list[int]) - Years to ingest (e.g., [2023, 2024])
- `districts` (list[District]) - District objects
- `statuses` (list[int]) - Status codes to fetch
- `offices` (list[int]) - Office codes to fetch

**Flow**:
1. Generate all (year, district, status, office) combinations
2. Filter out already-processed combinations via `api_request_tracking`
3. Fetch complaints for each combination with progress bar
4. Handle failures with retry logic
5. Orchestrate document downloads
6. Orchestrate action history ingestion

**Example**:
```python
await orchestrator.orchestrate_full_ingestion(
    years=[2023, 2024],
    districts=districts,
    statuses=[0, 1],  # Resolved, Pending
    offices=[1, 2, 3]  # Collectorate, Block, Panchayat
)
```

---

**`async orchestrate_document_downloads()`**

Download documents for all complaints missing them.

**Flow**:
1. Query `complaints` where `document_downloaded=False`
2. Download each document via `DocumentService`
3. Update complaint record with download status

---

**`async orchestrate_action_history_ingestion()`**

Fetch action history for all complaints.

**Flow**:
1. Query complaints without action history tracking
2. Fetch action history for each ticket
3. Record results in tracking table

---

### 3. Document Service (`document_ingestion.py`)

`DocumentService` - Handles document downloads to S3 and local storage.

#### Initialization

```python
from app.ingestion.document_ingestion import DocumentService

doc_service = DocumentService(db=db)
# Uses settings.LOCAL_STORAGE_PATH for local files
# Uses settings.AWS_S3_DOCUMENTS for S3 bucket
```

#### Key Methods

**`async download_and_store(ticket_no, document_url) -> bool`**

Download document and store in S3 + local filesystem.

**Flow**:
1. Download document bytes via `JanasunaniAPIClient`
2. Determine file type (PDF, JPG, PNG)
3. Save to local path: `{LOCAL_STORAGE_PATH}/{ticket_no}.{ext}`
4. Upload to S3: `s3://{bucket}/{ticket_no}.{ext}`
5. Update complaint record via CRUD

**Returns**: `True` if successful, `False` otherwise

**Usage**:
```python
success = await doc_service.download_and_store(
    ticket_no="CMS2024000123",
    document_url="https://janasunani.odisha.gov.in/documents/..."
)
```

---

### 4. Validation Schemas (`schemas.py`)

Pydantic models for type-safe validation of API responses.

#### `District`

```python
class District(BaseModel):
    distId: int
    distName: str
```

---

#### `Complaint`

```python
class Complaint(BaseModel):
    ticketNo: str
    grievanceDetails: str  # Maps to 'grievance' in DB
    petitionerName: str | None
    petitionerMobile: str | None
    petitionerEmail: str | None
    documentUrl: str | None
    office: str
    receivedBy: str
    district: str
    block: str | None
    address: str | None
    mode: str
    disability: str | None
    status: str
    govtTicket: bool
    createdOn: datetime
    category: str
    dept: str | None
    subcategory: str | None
    state: str
    petitionerGender: str
    # ... 30+ fields total
```

**Field Mappings**: Pydantic field names (camelCase from API) automatically map to snake_case for DB via aliases.

---

#### `ActionHistory`

```python
class ActionHistory(BaseModel):
    ticketNo: str
    actionTakenDate: datetime | None
    actionTakenBy: str
    actionStatus: str
    actionTakenRemark: str | None
    complaintStatusWithAuthority: str
```

---

#### Validation Utilities

**`validate(data, model, dict_mode=False)`**

Validate API response data against Pydantic model.

**Parameters**:
- `data` (list[dict]) - Raw API response
- `model` (BaseModel) - Pydantic model class
- `dict_mode` (bool) - If True, return dicts; else return model instances

**Returns**: List of validated objects

**Error Handling**: Logs validation errors, returns only valid records

**Example**:
```python
from app.ingestion.schemas import Complaint, validate

raw_complaints = await client.get_complaints(...)
validated = validate(raw_complaints, Complaint, dict_mode=False)
# Returns list[Complaint] with only valid records
```

---

## Constants (`__init__.py`)

### Status Codes

```python
STATUS = {
    0: "Resolved",
    1: "Pending",
    2: "Rejected",
    3: "Forwarded"
}
```

### Office Codes

```python
OFFICE = {
    1: "Collectorate",
    2: "Block",
    3: "Gram Panchayat",
    4: "Municipality",
    5: "NAC (Notified Area Council)"
}
```

---

## Error Handling

### Retry Logic

API client automatically retries on transient failures:
- Network timeouts
- 5xx server errors
- Rate limit errors (429)

**Configuration**: 3 retries with exponential backoff (2, 4, 8 seconds)

### Tracking Failures

Orchestrator tracks failed API requests in `api_request_tracking.failure_count`:
- Incremented on each failure
- Can be used to skip repeatedly failing requests
- Reset on successful fetch

### Document Download Errors

Document download errors stored in `complaints.document_download_error`:
- Network errors
- Invalid document format
- S3 upload failures

---

## Performance Optimization

### Rate Limiting

Use semaphore to limit concurrent API requests:
```python
semaphore = asyncio.Semaphore(5)  # Max 5 concurrent requests
```

**Why?** Prevents overwhelming Janasunani API and triggering rate limits.

### Batch Processing

Complaints fetched in batches by (year, district, status, office):
- Each batch typically 10-500 complaints
- Processed concurrently with semaphore control

### Deduplication

`api_request_tracking` prevents re-fetching already processed batches:
- Saves API calls
- Enables incremental ingestion
- Supports resume-after-failure

---

## Usage Examples

### Full Ingestion Script

```python
import asyncio
from app.ingestion.orchestrator import IngestionOrchestrator
from app.db.session import AsyncSessionLocal
from app.ingestion import STATUS, OFFICE

async def main():
    async with AsyncSessionLocal() as db:
        orchestrator = IngestionOrchestrator(db, semaphore_value=5)

        # Step 1: Ingest districts
        districts = await orchestrator.ingest_districts()

        # Step 2: Ingest complaints
        await orchestrator.orchestrate_full_ingestion(
            years=[2023, 2024],
            districts=districts,
            statuses=list(STATUS.keys()),
            offices=list(OFFICE.keys())
        )

        # Step 3: Download documents
        await orchestrator.orchestrate_document_downloads()

        # Step 4: Fetch action history
        await orchestrator.orchestrate_action_history_ingestion()

if __name__ == "__main__":
    asyncio.run(main())
```

### Incremental Update

```python
# Fetch only new complaints for current year
await orchestrator.orchestrate_full_ingestion(
    years=[2024],
    districts=districts,
    statuses=[1],  # Only pending
    offices=[1]    # Only collectorate
)
```

### Retry Failed Downloads

```python
# Retry document downloads that failed previously
complaints = await crud.get_complaints_with_download_errors(db)
for complaint in complaints:
    await doc_service.download_and_store(
        complaint.ticket_no,
        complaint.document_url
    )
```

---

## Testing

### Mocking API Client

```python
import pytest
from unittest.mock import AsyncMock

@pytest.fixture
def mock_client(monkeypatch):
    client = AsyncMock()
    client.get_districts.return_value = [
        {"distId": 1, "distName": "Khordha"}
    ]
    monkeypatch.setattr(
        "app.ingestion.orchestrator.JanasunaniAPIClient",
        lambda: client
    )
    return client

@pytest.mark.asyncio
async def test_ingest_districts(mock_client, test_db):
    orchestrator = IngestionOrchestrator(test_db)
    districts = await orchestrator.ingest_districts()
    assert len(districts) == 1
    assert districts[0].distName == "Khordha"
```

### Testing Document Downloads

```python
@pytest.mark.asyncio
async def test_download_and_store(test_db, tmp_path, monkeypatch):
    # Mock S3 client
    mock_s3 = AsyncMock()
    monkeypatch.setattr("app.ingestion.document_ingestion.boto3.client", lambda x: mock_s3)

    # Mock document content
    mock_content = b"%PDF-1.4 fake pdf content"
    monkeypatch.setattr(
        "app.ingestion.document_ingestion.JanasunaniAPIClient.download_document",
        AsyncMock(return_value=mock_content)
    )

    # Set local storage to temp directory
    monkeypatch.setattr("app.config.settings.LOCAL_STORAGE_PATH", str(tmp_path))

    # Test
    doc_service = DocumentService(test_db)
    success = await doc_service.download_and_store(
        "TEST001",
        "http://example.com/doc.pdf"
    )

    assert success
    assert (tmp_path / "TEST001.pdf").exists()
```

---

## Monitoring & Logging

### Progress Tracking

Orchestrator uses `tqdm` for progress bars:
```
Ingesting complaints: 85%|████████▌  | 340/400 [02:15<00:25,  2.34it/s]
```

### Logging Events

Key events logged via `loguru`:
- API request start/end
- Validation errors
- Database operations
- Document downloads
- Failures and retries

**Example logs**:
```
INFO  | Successfully stored 142 complaints in database
WARN  | No complaints received for year=2023, dist=5, status=0, office=3
ERROR | Complaint ingestion failed for dist=10, year=2024: Connection timeout
```

---

## Related Components

- **Database Layer**: `app/db/` - CRUD operations for persistence
- **Configuration**: `app/config.py` - API credentials and paths
- **S3 Service**: `app/s3service.py` - S3 upload/download utilities
- **Scripts**: `scripts/ingest_complaints.py` - CLI entry point

## References

- [Janasunani Portal](https://janasunani.odisha.gov.in/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [Asyncio Documentation](https://docs.python.org/3/library/asyncio.html)
- [Aiohttp Documentation](https://docs.aiohttp.org/)
