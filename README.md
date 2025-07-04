# Grievance Analytics

An analytics platform for Odisha Janasunani grievance redressal data, featuring robust data ingestion, processing, and API services.

---

## 🚀 Features

- **Automated Data Ingestion**: Fetches and stores raw grievance data from external sources.
- **Data Processing & Analytics**: Cleans, transforms, and analyzes data for downstream applications.
- **REST API**: Serves processed data and analytics via a FastAPI-based API.
- **Cloud-Ready**: Deployable on Docker, AWS ECS/Fargate, and supports Prefect for workflow orchestration.

---

## 🏁 Getting Started

### Prerequisites

- [Docker](https://www.docker.com/get-started)
- [Docker Compose](https://docs.docker.com/compose/)
- (Optional) [AWS CLI](https://aws.amazon.com/cli/) for cloud deployment

### Clone the Repository

```bash
git clone https://github.com/your-org/grievance.git
cd grievance
```

### Environment Variables

Create a `.env` file in the `backend/` directory:

```env
# Environment and Debug
ENV=dev
DEBUG=True

# Janasunani API Configuration
JANASUNANI_API_BASE_URL=https://janasunani.odisha.gov.in/api/DataServices
JANASUNANI_API_USERNAME=your_username
JANASUNANI_API_PASSWORD=your_password

# Database Configuration (uses Docker volumes, not local files)
DB_URL=sqlite:///data/raw/grievance.db

# AWS Configuration (optional for local development)
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=ap-south-1
AWS_S3_BUCKET_NAME=janasunani-data
AWS_S3_DOCUMENTS=janasunani-documents
```

**Note**: The application uses Docker named volumes for data persistence. Data is stored within Docker volumes and not directly in your local filesystem. See [README-DOCKER.md](backend/README-DOCKER.md) for details on accessing data.

### Build and Run with Docker Compose

#### Quick Start with Convenience Script
```bash
cd backend

# Make the script executable (first time only)
chmod +x scripts/docker-run.sh

# Run the full pipeline (test → ingest → serve)
./scripts/docker-run.sh full

# Or run individual components:
./scripts/docker-run.sh test     # Run tests only
./scripts/docker-run.sh ingest   # Run data ingestion
./scripts/docker-run.sh serve    # Start API server
./scripts/docker-run.sh dev      # Start development server with hot reload
```

#### Manual Docker Compose Commands
```bash
cd backend

# Run tests first
docker-compose --profile test up test

# If tests pass, run ingestion
docker-compose --profile ingest up ingestion

# Finally, serve the application
docker-compose --profile serve up api

# For development with hot reload
docker-compose --profile dev up api-dev
```

- The API will be available at [http://localhost:8000](http://localhost:8000)
- API Documentation at [http://localhost:8000/docs](http://localhost:8000/docs)
- Health check at [http://localhost:8000/health](http://localhost:8000/health)

#### Available Profiles
- **`test`**: Run unit tests
- **`ingest`**: Download and process grievance data
- **`serve`**: Start production API server
- **`dev`**: Start development server with hot reload

For detailed Docker Compose documentation, see [README-DOCKER.md](backend/README-DOCKER.md).

---

## 🧑‍💻 Developer Guide

### Project Structure

```
backend/
  app/
    api/           # FastAPI routes
    db/            # Database models and CRUD
    ingestion/     # Ingestion and ETL logic
    services/      # Business logic/services
    config.py      # Configuration and settings
    main.py        # FastAPI entrypoint
  pyproject.toml   # Project dependencies and metadata
  uv.lock         # Locked dependency versions
  Dockerfile.api
  Dockerfile.ingestion
  Dockerfile.test
  docker-compose.yml
```

### Install for Local Development

1. **Install dependencies** (using [uv](https://docs.astral.sh/uv/)):
   ```bash
   # Install uv if you haven't already
   curl -LsSf https://astral.sh/uv/install.sh | sh
   
   # Install dependencies
   uv sync
   
   # Activate the environment
   source .venv/bin/activate  # On Unix/macOS
   # or
   .venv\Scripts\activate     # On Windows
   ```

2. **Run tests**:
   ```bash
   uv run pytest
   ```

### Contributing

1. Clone repository and create your branch:
   ```bash
   git checkout -b feature
   ```
2. Make your changes and add tests.
3. Run tests and ensure all pass.
4. Commit and push your branch.
5. Open a Pull Request to branch `dev` with a clear description.

---

## ☁️ Cloud Deployment

For detailed deployment instructions and infrastructure setup, please refer to the comprehensive guide in [terraform/README.md](terraform/README.md).

---

<!-- ## 📄 License

[MIT License](LICENSE)

--- -->

## 🙋‍♂️ Support

For questions, open an [issue](https://github.com/Data-Policy-and-Innovation-Centre/grievance/issues) or contact the maintainers.