# Database Module

SQLAlchemy-based ORM layer with async support for the Grievance Analytics system.

## Overview

This module provides database models, session management, and CRUD operations for persisting complaint data from the Janasunani API. It uses SQLAlchemy with async support (aiosqlite) and follows the Repository pattern.

## Architecture

```
app/db/
├── __init__.py           # Package exports
├── models.py             # SQLAlchemy ORM models
├── session.py            # Database session management
└── crud.py               # CRUD operations (Create, Read, Update, Delete)
```

## Database Schema

### Entity Relationship Diagram

```
┌─────────────────┐
│    District     │
│                 │
│ - id            │
│ - dist_name     │
│ - dist_id (UQ)  │
└─────────────────┘

┌──────────────────────────────────┐
│          Complaint               │
│                                  │
│ - id (PK)                        │
│ - ticket_no (UQ)                 │◄─────┐
│ - petitioner_name                │      │
│ - petitioner_mobile              │      │
│ - petitioner_email               │      │
│ - grievance (text)               │      │
│ - document_url                   │      │
│ - office, district, block        │      │
│ - status, created_on             │      │
│ - category, dept, subcategory    │      │
│ - local_document_path            │      │
│ - document_downloaded            │      │
│ ... (30+ columns)                │      │
└──────────────────────────────────┘      │
                                          │
┌──────────────────────────────────┐      │
│       ActionHistory              │      │
│                                  │      │
│ - id (PK)                        │      │
│ - ticket_no (FK) ────────────────┘
│ - action_taken_date              │
│ - action_taken_by                │
│ - action_status                  │
│ - action_taken_remark            │
│ - complaint_status_with_authority│
└──────────────────────────────────┘

┌──────────────────────────────────┐
│    APIRequestTracking            │
│                                  │
│ - id (PK)                        │
│ - year, dist_id, status, office  │ (composite unique)
│ - last_successful_fetch          │
│ - records_count                  │
│ - failure_count                  │
└──────────────────────────────────┘

┌──────────────────────────────────┐
│ ActionHistoryAPIRequestTracking  │
│                                  │
│ - id (PK)                        │
│ - ticket_no (UQ, FK)             │
│ - last_successful_fetch          │
│ - records_count                  │
│ - failure_count                  │
└──────────────────────────────────┘
```

## Models (`models.py`)

### Core Models

#### `District`

Administrative district reference data.

**Columns**:
- `id` (Integer, PK) - Auto-increment primary key
- `dist_name` (String) - District name (e.g., "Khordha")
- `dist_id` (Integer, UQ) - Unique district identifier from Janasunani API

**Constraints**:
- Unique constraint on `dist_id`

---

#### `Complaint`

Main complaint record with petitioner details and grievance information.

**Key Columns**:
- `id` (Integer, PK) - Auto-increment primary key
- `ticket_no` (String, UQ) - Unique complaint identifier (e.g., "CMS2024000123")
- `grievance` (String) - Complaint text (main analysis target)
- `petitioner_name`, `petitioner_mobile`, `petitioner_email` - Petitioner details
- `district`, `block`, `office` - Administrative location
- `category`, `dept`, `subcategory` - Complaint classification
- `status` - Current status (Pending, Resolved, etc.)
- `created_on`, `assigned_on`, `resolved_on` - Timestamps
- `document_url` - URL to complaint document on Janasunani portal
- `local_document_path` - Local file path after download
- `document_downloaded` - Boolean flag for download status

**30+ columns total** - see `models.py` for complete schema.

**Constraints**:
- Unique constraint on `ticket_no`

**Relationships**:
- One-to-many with `ActionHistory` (backref: `action_history`)
- One-to-one with `ActionHistoryAPIRequestTracking` (backref: `action_history_api_request_tracking`)

---

#### `ActionHistory`

Tracks actions taken on complaints (assignments, status changes, remarks).

**Columns**:
- `id` (Integer, PK)
- `ticket_no` (String, FK) - Foreign key to `Complaint.ticket_no`
- `action_taken_date` (DateTime) - When action occurred
- `action_taken_by` (String) - Officer/authority name
- `action_status` (String) - Action type (Assigned, Pending, Resolved)
- `action_taken_remark` (String) - Officer's comment/note
- `complaint_status_with_authority` (String) - Status at authority level

**Constraints**:
- Composite unique constraint on (ticket_no, action_taken_by, action_status, action_taken_remark, complaint_status_with_authority)
  - Prevents duplicate action entries

**Relationships**:
- Many-to-one with `Complaint`

---

### Tracking Models

#### `APIRequestTracking`

Tracks successfully processed API requests to prevent duplicate fetches.

**Columns**:
- `id` (Integer, PK)
- `year` (Integer) - Complaint year
- `dist_id` (Integer) - District ID
- `status` (Integer) - Status code (0=Resolved, 1=Pending, etc.)
- `office` (Integer) - Office code
- `last_successful_fetch` (DateTime) - Timestamp of last successful fetch
- `records_count` (Integer) - Number of records fetched
- `failure_count` (Integer) - Number of consecutive failures

**Constraints**:
- Composite unique constraint on (year, dist_id, status, office)

**Purpose**: Enables incremental ingestion - skip already-fetched complaint batches.

---

#### `ActionHistoryAPIRequestTracking`

Tracks action history fetch attempts per complaint.

**Columns**:
- `id` (Integer, PK)
- `ticket_no` (String, FK) - Foreign key to `Complaint.ticket_no`
- `last_successful_fetch` (DateTime)
- `records_count` (Integer)
- `failure_count` (Integer)

**Constraints**:
- Unique constraint on `ticket_no`

**Purpose**: Enables retry logic for failed action history fetches.

---

## Session Management (`session.py`)

### Async Engine & SessionLocal

```python
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings

engine = create_async_engine(
    settings.DB_URL,  # e.g., "sqlite+aiosqlite:///data/raw/grievance.db"
    echo=False,
    future=True
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)
```

### Dependency Injection

```python
async def get_db() -> AsyncSession:
    """FastAPI dependency for database sessions."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

**Usage in API**:
```python
from fastapi import Depends
from app.db.session import get_db

@router.get("/complaints/{ticket_no}")
async def get_complaint(
    ticket_no: str,
    db: AsyncSession = Depends(get_db)
):
    return await crud.get_complaint_by_ticket(db, ticket_no)
```

---

## CRUD Operations (`crud.py`)

### Bulk Loading

#### `bulk_load_complaints(db, complaints: list[Complaint]) -> list[Complaint]`

Bulk insert complaints with upsert logic (insert or ignore duplicates).

**Features**:
- Uses SQLite `INSERT OR IGNORE` for idempotency
- Handles large batches efficiently
- Returns list of successfully stored complaints

**Usage**:
```python
from app.ingestion.schemas import Complaint

complaints_validated = validate(raw_complaints, Complaint)
stored = await bulk_load_complaints(db, complaints_validated)
logger.info(f"Stored {len(stored)} complaints")
```

---

#### `bulk_load_action_histories(db, action_histories: list[ActionHistory]) -> list[ActionHistory]`

Bulk insert action history records.

**Features**:
- Uses `INSERT OR IGNORE` to handle duplicate constraint
- Efficient batch processing

---

#### `bulk_load_districts(db, districts: list[District]) -> list[District]`

Bulk insert district reference data.

---

### Query Operations

#### `get_all_complaints(db) -> list[Complaint]`

Fetch all complaints from database.

**Returns**: List of `Complaint` ORM objects

**Usage**:
```python
complaints = await get_all_complaints(db)
for complaint in complaints:
    print(complaint.ticket_no, complaint.grievance)
```

---

#### `get_complaint_by_ticket(db, ticket_no: str) -> Complaint | None`

Fetch single complaint by ticket number.

**Returns**: `Complaint` object or `None` if not found

---

#### `get_complaints_without_documents(db) -> list[Complaint]`

Fetch complaints where `document_downloaded=False` and `document_url` exists.

**Purpose**: Identify complaints needing document download.

---

#### `get_tickets_needing_action_history(db) -> list[str]`

Fetch ticket numbers of complaints that don't have action history tracking records.

**Purpose**: Identify complaints needing action history fetch.

---

### Filtering & Tracking

#### `filter_complaints_api_request(db, year, dist_id, status, office) -> APIRequestTracking | None`

Check if a specific API request combination has already been successfully processed.

**Returns**: Tracking record if exists, else `None`

**Usage**:
```python
existing = await filter_complaints_api_request(db, 2024, 1, 0, 1)
if existing:
    logger.info("Already fetched, skipping")
else:
    # Fetch from API
    ...
```

---

#### `record_complaint_api_request_success(db, year, dist_id, status, office, records_count)`

Record successful API request for tracking.

**Creates or updates** `APIRequestTracking` record.

---

#### `mark_complaints_api_request_failed(db, year, dist_id, status, office)`

Increment failure count for failed API request.

**Purpose**: Track transient failures for retry logic.

---

### Update Operations

#### `update_complaint_document_status(db, ticket_no, document_path, success=True, error=None)`

Update complaint document download status.

**Parameters**:
- `ticket_no` - Complaint identifier
- `document_path` - Local file path (if successful)
- `success` - Boolean flag
- `error` - Error message (if failed)

**Updates**:
- `local_document_path` (if success)
- `document_downloaded` (True/False)
- `document_download_date` (current timestamp)
- `document_download_error` (error message if failed)

---

## Database Migrations

**Current**: No migration framework (manual schema changes).

**Future**: Alembic integration

```bash
# Generate migration
alembic revision --autogenerate -m "Add new column"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

---

## Connection to Other Components

### From Ingestion Layer

```python
from app.db.crud import bulk_load_complaints
from app.db.session import get_db

async def ingest_complaints():
    async with AsyncSessionLocal() as db:
        complaints = fetch_from_api()
        await bulk_load_complaints(db, complaints)
```

### From Pipelines

```python
from app.config import load_duckdb
import polars as pl

# Load into Polars for analysis (bypass ORM for performance)
df = load_duckdb(output_format="polars")
print(df.shape)  # (n_complaints, n_columns)
```

**Why DuckDB?** SQLite → DuckDB → Polars is faster than SQLAlchemy ORM for large analytical queries.

### From API Endpoints

```python
from app.db import crud
from app.db.session import get_db

@router.get("/complaints/{ticket_no}")
async def get_complaint(
    ticket_no: str,
    db: AsyncSession = Depends(get_db)
):
    complaint = await crud.get_complaint_by_ticket(db, ticket_no)
    if not complaint:
        raise HTTPException(status_code=404)
    return complaint
```

---

## Testing

### Test Database Setup

Create isolated test database in `app/tests/conftest.py`:

```python
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from app.db.models import Base

@pytest.fixture
async def test_db():
    """Create test database and session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session
    async with AsyncSession(engine) as session:
        yield session

    # Cleanup
    await engine.dispose()
```

### Testing CRUD Operations

```python
import pytest
from app.db import crud
from app.db.models import Complaint

@pytest.mark.asyncio
async def test_create_complaint(test_db):
    complaint_data = Complaint(
        ticket_no="TEST001",
        grievance="Test complaint",
        office="Test Office",
        received_by="System",
        district="Khordha",
        mode="Online",
        status="Pending",
        category="General",
        state="Odisha",
        petitioner_gender="Male",
        transfer_status="Not Transferred",
        urgent="No",
        govt_ticket=False,
        created_on=datetime.now(),
        assigned_on=datetime.now()
    )

    stored = await crud.bulk_load_complaints(test_db, [complaint_data])
    assert len(stored) == 1

    retrieved = await crud.get_complaint_by_ticket(test_db, "TEST001")
    assert retrieved.ticket_no == "TEST001"
```

---

## Performance Considerations

### Bulk Operations

- Use bulk insert for batches (100-1000 records at a time)
- Avoid row-by-row inserts in loops

### Indexing

Key indexes created via unique constraints:
- `complaints.ticket_no` (unique)
- `districts.dist_id` (unique)
- `api_request_tracking.(year, dist_id, status, office)` (composite unique)

**Future**: Add indexes on frequently queried columns:
```sql
CREATE INDEX idx_complaints_district ON complaints(district);
CREATE INDEX idx_complaints_status ON complaints(status);
CREATE INDEX idx_complaints_created_on ON complaints(created_on);
```

### Query Optimization

For analytical queries, prefer DuckDB over SQLAlchemy:
```python
# Slow (ORM)
complaints = await crud.get_all_complaints(db)
df = pl.DataFrame([c.__dict__ for c in complaints])

# Fast (DuckDB)
df = load_duckdb(output_format="polars")
```

---

## Common Patterns

### Safe Upsert

```python
from sqlalchemy.dialects.sqlite import insert

stmt = insert(Complaint).values(complaints_dict).on_conflict_do_nothing()
await db.execute(stmt)
```

### Batch Processing

```python
from more_itertools import chunked

complaints_batches = chunked(complaints, 500)
for batch in complaints_batches:
    await bulk_load_complaints(db, batch)
```

### Transaction Management

```python
async with db.begin():
    # Multiple operations in single transaction
    await crud.bulk_load_complaints(db, complaints)
    await crud.record_complaint_api_request_success(db, ...)
    # Auto-commit if no exception
```

---

## Related Components

- **Configuration**: `app/config.py` - Database URL settings
- **Ingestion**: `app/ingestion/` - Uses CRUD for data loading
- **Pipelines**: `app/pipelines/` - Uses DuckDB for analysis
- **API**: `app/api/` - Uses CRUD for query endpoints
- **Testing**: `app/tests/test_crud.py` - CRUD operation tests

## References

- [SQLAlchemy Async Documentation](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [Aiosqlite](https://github.com/omnilib/aiosqlite)
- [FastAPI Database Guide](https://fastapi.tiangolo.com/tutorial/sql-databases/)
