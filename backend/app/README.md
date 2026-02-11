# Grievance Analytics Application

This is the main application package for the Odisha Grievance Analytics system, which ingests, processes, and analyzes complaint data from the Janasunani public grievance portal.

## Architecture Overview

The application follows a **layered architecture** with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                      Scripts Layer                           │
│              (CLI tools, analysis scripts)                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                     Application Layer (app/)                 │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │   API       │  │  Pipelines   │  │   Ingestion      │   │
│  │  (FastAPI)  │  │  (Hamilton)  │  │  (Orchestrator)  │   │
│  └─────────────┘  └──────────────┘  └──────────────────┘   │
│         │                 │                    │             │
│         └─────────────────┴────────────────────┘             │
│                           ↓                                  │
│         ┌──────────────────────────────────────┐            │
│         │   Services & Database Layer          │            │
│         │   (CRUD, Models, S3Service)          │            │
│         └──────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              External Systems & Storage                      │
│   ┌─────────────┐  ┌──────────┐  ┌─────────────────┐       │
│   │ Janasunani  │  │ SQLite   │  │   AWS S3        │       │
│   │    API      │  │    DB    │  │ (Documents)     │       │
│   └─────────────┘  └──────────┘  └─────────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
app/
├── api/                    # FastAPI routes and endpoints
├── db/                     # Database models, session management, CRUD operations
├── ingestion/              # Data ingestion from Janasunani API
├── pipelines/              # Hamilton-based data processing pipelines
│   ├── ortps/              # ORTPS-specific pipeline (policy & orchestration)
│   └── shared/             # Reusable NLP engines (language detection, topic modeling)
├── services/               # Business logic services (currently empty)
├── tests/                  # Pytest test suite
├── config.py               # Configuration, settings, and utilities
├── main.py                 # FastAPI application entry point
├── s3service.py            # AWS S3 client wrapper
└── utils.py                # Utility functions
```

## Core Components

### 1. Configuration (`config.py`)

Central configuration module providing:

- **`Directories`**: Singleton managing all data paths (raw, processed, interim, output, models)
- **`Settings`**: Pydantic settings loaded from environment variables and `.env` file
- **`load_duckdb()`**: Utility to load SQLite data using DuckDB (returns Polars/Pandas DataFrames)
- **Logging utilities**: `stop_logging_to_console()`, `resume_logging_to_console()`

**Key Settings**:
- Janasunani API credentials and base URL
- Database connection string
- AWS S3 bucket names and credentials
- Local storage paths

### 2. API Layer (`api/`)

FastAPI-based REST API for health checks and future endpoints.

**Current Endpoints**:
- `GET /health` - Health check endpoint

**Future Expansion**:
- Complaint query endpoints
- Analysis results API
- Dashboard data endpoints

### 3. Database Layer (`db/`)

SQLAlchemy-based ORM with async support (aiosqlite).

**Key Models**:
- `Complaint` - Main complaint records with petitioner details, grievance text, status
- `ActionHistory` - Complaint action tracking (assignments, resolutions)
- `District` - Administrative district reference data
- `APIRequestTracking` - Tracks successful API ingestion requests (prevents duplicates)

**CRUD Operations**: Bulk loading, filtering, updates for all models.

### 4. Ingestion Layer (`ingestion/`)

Orchestrates data ingestion from the Janasunani public grievance portal.

**Components**:
- `JanasunaniAPIClient` - HTTP client for Janasunani API
- `IngestionOrchestrator` - Coordinates complaint, district, and action history ingestion
- `DocumentService` - Downloads and stores complaint documents (PDF, images)
- Pydantic schemas for validation

**Ingestion Flow**:
1. Fetch districts from API
2. For each district/year/status/office combination, fetch complaints
3. Validate and bulk-load into SQLite
4. Download associated documents to S3 and local storage
5. Fetch action history for each complaint

### 5. Pipelines Layer (`pipelines/`)

Hamilton-based data transformation pipelines for NLP analysis.

**Architecture**: Two-layer design
- **`shared/`**: Reusable NLP engines (language detection, embedding cache, BERTopic)
- **`ortps/`**: ORTPS-specific policies, profiles, and Hamilton nodes

**ORTPS Pipeline** (Right to Public Services analysis):
1. **Language Detection**: Filter English complaints using Lingua + script detection
2. **Category Labeling**: Keyword + embedding hybrid matching to 7 ORTPS categories
3. **Topic Modeling**: BERTopic clustering per category to identify themes

### 6. Services Layer (`services/`)

Reserved for business logic services (currently empty).

**Future Services**:
- Analytics computation services
- Report generation services
- ML model inference services

### 7. S3 Service (`s3service.py`)

Boto3 wrapper for AWS S3 operations.

**Capabilities**:
- Upload files with content type metadata
- Download files with progress tracking
- Check file existence
- List bucket contents

## Data Flow

### Ingestion Flow

```
Janasunani API
    ↓
JanasunaniAPIClient (fetch complaints)
    ↓
IngestionOrchestrator (coordinate)
    ↓
Pydantic Validation (schemas.py)
    ↓
CRUD bulk_load (db/crud.py)
    ↓
SQLite Database (data/raw/grievance.db)
```

### Analysis Flow

```
SQLite Database
    ↓
load_duckdb() → Polars DataFrame
    ↓
Hamilton Pipeline (pipelines/ortps)
    ├─ Language Detection (filter English)
    ├─ Category Labeling (7 ORTPS categories)
    └─ Topic Modeling (BERTopic per category)
    ↓
Output: Labeled DataFrames, Topic Models, Visualizations
    ↓
data/interim/ (Parquet files)
output/ortps_analysis/ (reports, tables, wordclouds)
```

## Technology Stack

### Core Frameworks
- **FastAPI** - Async web framework for API
- **SQLAlchemy** - ORM with async support (aiosqlite)
- **Hamilton** - DAG-based data pipeline framework
- **Polars** - High-performance DataFrame library (primary)
- **DuckDB** - In-process SQL engine for data loading

### NLP & ML
- **sentence-transformers** - Embedding models (all-MiniLM-L6-v2)
- **BERTopic** - Topic modeling with HDBSCAN clustering
- **Lingua** - Fast language detection
- **scikit-learn** - Vectorization and preprocessing

### Data Validation & Config
- **Pydantic v2** - Data validation and settings management
- **pydantic-settings** - Environment variable loading

### Cloud & Storage
- **boto3** - AWS SDK for S3 operations
- **aiohttp** - Async HTTP client for API calls

### Utilities
- **loguru** - Simple, powerful logging
- **tqdm** - Progress bars
- **more-itertools** - Enhanced iteration utilities

## Configuration

### Environment Variables

Create a `.env` file in the backend root:

```bash
# Janasunani API (required for ingestion)
JANASUNANI_API_USERNAME=your_username
JANASUNANI_API_PASSWORD=your_password
JANASUNANI_API_BASE_URL=https://janasunani.odisha.gov.in/api/DataServices

# Database (optional, defaults to local SQLite)
DB_URL=sqlite+aiosqlite:///data/raw/grievance.db

# AWS S3 (required for document storage)
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=ap-south-1
AWS_S3_BUCKET_NAME=janasunani-data-main
AWS_S3_DOCUMENTS=janasunani-documents-main

# Environment
ENV=local
DEBUG=True
```

### Directory Structure

The application automatically creates the following directories on first run:

```
backend/
├── data/
│   ├── raw/              # Raw SQLite database, documents
│   ├── processed/        # Processed datasets
│   └── interim/          # Intermediate pipeline outputs
├── output/               # Analysis outputs (reports, tables)
├── models/               # Cached ML models and embeddings
└── logs/                 # Application logs
```

## Running the Application

### API Server

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Access at: http://localhost:8000
Health check: http://localhost:8000/health

### Ingestion

See `scripts/ingest_complaints.py` for ingestion orchestration.

### Analysis Pipelines

See `scripts/ortps_category_analysis.py` for ORTPS pipeline execution.

## Testing

```bash
# Run all tests
pytest app/tests/

# Run with coverage
pytest app/tests/ --cov=app --cov-report=html

# Run specific test module
pytest app/tests/test_crud.py -v
```

## Development Guidelines

### Adding New Pipelines

1. Create pipeline package: `app/pipelines/your_pipeline/`
2. Define Hamilton nodes in separate modules (e.g., `nodes.py`)
3. Create config classes using Pydantic
4. Add reusable engines to `app/pipelines/shared/` if applicable
5. Write integration tests in `app/tests/pipelines/`

### Adding New API Endpoints

1. Create router in `app/api/your_module.py`
2. Define Pydantic schemas for request/response
3. Include router in `app/main.py`
4. Write tests in `app/tests/test_your_module.py`

### Database Schema Changes

1. Update models in `app/db/models.py`
2. Create Alembic migration (future - not currently using migrations)
3. Update corresponding Pydantic schemas in `app/ingestion/schemas.py`
4. Update CRUD operations in `app/db/crud.py`

## Key Design Patterns

1. **Dependency Injection**: Database sessions injected via FastAPI dependencies
2. **Repository Pattern**: CRUD operations separated from business logic
3. **DAG-based Pipelines**: Hamilton for reproducible, testable data transformations
4. **Pydantic Validation**: Type-safe configuration and data validation throughout
5. **Async by Default**: Async/await for I/O operations (API, database)
6. **Polars-first**: Prefer Polars over Pandas for performance

## Contact & Support

For questions about this codebase, refer to:
- `MEMORY.md` in `.claude/projects/-Users-ymohanty-Documents-GitHub-grievance/memory/`
- Individual component READMEs in each subdirectory
