# API Module

FastAPI-based REST API for the Grievance Analytics system.

## Overview

This module provides HTTP endpoints for health checks and future complaint query/analysis endpoints. The API follows RESTful conventions and uses FastAPI's automatic OpenAPI documentation.

## Architecture

```
app/main.py (FastAPI app instance)
    ↓
app/api/
├── __init__.py           # Package marker
└── health.py             # Health check router
```

## Current Endpoints

### Health Check

**Endpoint**: `GET /health`

**Description**: Simple health check to verify API is running.

**Request**: None

**Response**:
```json
{
  "status": "ok"
}
```

**Status Codes**:
- `200 OK` - Service is healthy

**Example**:
```bash
curl http://localhost:8000/health
```

## API Documentation

FastAPI automatically generates interactive API documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

## Adding New Endpoints

### Step 1: Create Router Module

Create a new file in `app/api/` (e.g., `complaints.py`):

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db import crud

router = APIRouter(prefix="/complaints", tags=["complaints"])

@router.get("/{ticket_no}")
async def get_complaint(
    ticket_no: str,
    db: AsyncSession = Depends(get_db)
):
    """Retrieve a complaint by ticket number."""
    complaint = await crud.get_complaint_by_ticket(db, ticket_no)
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")
    return complaint
```

### Step 2: Include Router in Main App

Update `app/main.py`:

```python
from fastapi import FastAPI

from app.api import health, complaints

app = FastAPI()
app.include_router(health.router)
app.include_router(complaints.router)  # Add new router
```

### Step 3: Add Tests

Create `app/tests/test_complaints.py`:

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_get_complaint(async_client: AsyncClient):
    response = await async_client.get("/complaints/TKT001")
    assert response.status_code == 200
    assert response.json()["ticket_no"] == "TKT001"
```

## Planned Endpoints

### Complaints API

```
GET    /complaints                    # List complaints with filters
GET    /complaints/{ticket_no}        # Get single complaint
GET    /complaints/{ticket_no}/history # Get action history
POST   /complaints/search             # Advanced search with filters
```

### Analysis API

```
GET    /analysis/ortps/categories     # ORTPS category distribution
GET    /analysis/ortps/topics         # Topic summaries by category
GET    /analysis/districts            # Complaint counts by district
GET    /analysis/trends               # Time-series trends
```

### Export API

```
POST   /export/complaints             # Export filtered complaints as CSV/Excel
POST   /export/analysis               # Export analysis results
```

## Request/Response Schemas

### Using Pydantic Models

Define schemas for type-safe request/response validation:

```python
from pydantic import BaseModel, Field
from datetime import datetime

class ComplaintResponse(BaseModel):
    ticket_no: str
    petitioner_name: str | None
    grievance: str
    status: str
    created_on: datetime
    district: str

    model_config = {"from_attributes": True}  # Enable ORM mode

class ComplaintListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    complaints: list[ComplaintResponse]
```

## Authentication & Authorization

**Current**: No authentication (local development only)

**Future**: Implement JWT-based authentication:

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """Verify JWT token and return user info."""
    token = credentials.credentials
    # Decode and verify JWT
    # Return user claims
    ...

@router.get("/protected")
async def protected_route(user: dict = Depends(verify_token)):
    return {"user": user}
```

## Error Handling

### Standard Error Response

All errors return a consistent format:

```json
{
  "detail": "Error message here"
}
```

### Status Codes

- `200 OK` - Request successful
- `201 Created` - Resource created
- `400 Bad Request` - Invalid input
- `401 Unauthorized` - Authentication required
- `403 Forbidden` - Insufficient permissions
- `404 Not Found` - Resource not found
- `422 Unprocessable Entity` - Validation error
- `500 Internal Server Error` - Server error

### Custom Exception Handlers

Add custom handlers in `app/main.py`:

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)}
    )
```

## CORS Configuration

For frontend integration, configure CORS in `app/main.py`:

```python
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Rate Limiting

For production, add rate limiting:

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@router.get("/complaints")
@limiter.limit("5/minute")
async def list_complaints(request: Request):
    ...
```

## Monitoring & Logging

### Request Logging Middleware

```python
import time
from loguru import logger

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time

    logger.info(
        f"{request.method} {request.url.path} "
        f"status={response.status_code} duration={duration:.3f}s"
    )
    return response
```

### Health Check with Dependencies

Enhanced health check that verifies database connection:

```python
from sqlalchemy import text

@router.get("/health/detailed")
async def detailed_health_check(db: AsyncSession = Depends(get_db)):
    """Health check with dependency verification."""
    try:
        # Check database connection
        await db.execute(text("SELECT 1"))

        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail="Service unavailable"
        )
```

## Testing

### Pytest Fixtures

Use `async_client` fixture from `app/tests/conftest.py`:

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_health_check(async_client: AsyncClient):
    response = await async_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

### Testing with Database

```python
@pytest.mark.asyncio
async def test_create_complaint(
    async_client: AsyncClient,
    test_db: AsyncSession
):
    # Setup test data
    complaint_data = {
        "ticket_no": "TEST001",
        "grievance": "Test complaint",
        ...
    }

    # Make request
    response = await async_client.post("/complaints", json=complaint_data)
    assert response.status_code == 201

    # Verify in database
    complaint = await crud.get_complaint_by_ticket(test_db, "TEST001")
    assert complaint is not None
```

## Deployment

### Running with Uvicorn

**Development**:
```bash
uvicorn app.main:app --reload --port 8000
```

**Production**:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Docker

```dockerfile
FROM python:3.13-slim

WORKDIR /app
COPY . .
RUN pip install -e .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Related Components

- **Database Layer**: `app/db/` - Models and CRUD operations
- **Configuration**: `app/config.py` - Settings and environment variables
- **Testing**: `app/tests/test_health.py` - API endpoint tests

## References

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [Uvicorn Documentation](https://www.uvicorn.org/)
