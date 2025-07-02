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

Create a `.env` file in the `backend/` directory. Example:

```env
# Environment and Debug
ENV=dev
DEBUG=True

# Janasunani API Configuration
JANASUNANI_API_BASE_URL=https://janasunani.odisha.gov.in/api/DataServices
JANASUNANI_API_USERNAME=your_username
JANASUNANI_API_PASSWORD=your_password

# Database Configuration
DB_URL=sqlite:///data/raw/grievance.db

# AWS Configuration
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=ap-south-1
AWS_S3_BUCKET_NAME=janasunani-data
AWS_S3_DOCUMENTS=janasunani-documents
```

### Build and Run with Docker Compose

```bash
cd backend
docker-compose up --build
```

- The API will be available at [http://localhost:8000](http://localhost:8000)
- Prefect UI (if enabled) will be at [http://localhost:4200](http://localhost:4200)

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

1. Fork the repository and create your branch:
   ```bash
   git checkout -b feature/your-feature
   ```
2. Make your changes and add tests.
3. Run tests and ensure all pass.
4. Commit and push your branch.
5. Open a Pull Request with a clear description.

---

## ☁️ Cloud Deployment

- **ECS/Fargate**: Build and push Docker images to ECR, then deploy using ECS task definitions and services.
- **Prefect Cloud**: Register and schedule flows for robust workflow orchestration.

---

## 📄 License

[MIT License](LICENSE)

---

## 🙋‍♂️ Support

For questions, open an [issue](https://github.com/Data-Policy-and-Innovation-Centre/grievance/issues) or contact the maintainers.