# Docker Compose Setup for Grievance Analytics

This document describes how to use the Docker Compose setup to test, ingest data, and serve the grievance analytics application.

## 🚀 Quick Start

### Prerequisites
- Docker and Docker Compose installed
- Environment variables configured (see `.env` file setup below)

### Environment Setup

Create a `.env` file in the `backend/` directory:

```env
# Environment and Debug
ENV=dev
DEBUG=True

# Janasunani API Configuration
JANASUNANI_API_BASE_URL=https://janasunani.odisha.gov.in/api/DataServices
JANASUNANI_API_USERNAME=your_username
JANASUNANI_API_PASSWORD=your_password

# Database Configuration
DB_PASSWORD=your_db_password

# AWS Configuration (optional for local development)
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=ap-south-1
AWS_S3_BUCKET_NAME=janasunani-data
AWS_S3_DOCUMENTS=janasunani-documents
```

## 📋 Available Services

The Docker Compose setup includes the following services:

### 1. **Test Service** (`test`)
- **Purpose**: Run all unit tests
- **Profile**: `test`
- **Database**: Uses separate test database
- **Command**: `pytest app/tests -v --tb=short`

### 2. **Ingestion Service** (`ingestion`)
- **Purpose**: Download and process grievance data
- **Profile**: `ingest`
- **Dependencies**: Requires test service to pass
- **Command**: Runs the ingestion orchestrator

### 3. **API Service** (`api`)
- **Purpose**: Serve the FastAPI application
- **Profile**: `serve`
- **Port**: 8000
- **Dependencies**: Requires ingestion service
- **Health Check**: Monitors `/health` endpoint

### 4. **Development API Service** (`api-dev`)
- **Purpose**: Development server with hot reload
- **Profile**: `dev`
- **Port**: 8000
- **Features**: Code mounting for live reload

## 💾 Data Storage Strategy

### Why Named Volumes?

We use Docker named volumes instead of bind mounts for several reasons:

1. **Security**: Prevents accidental exposure of sensitive data on the host filesystem
2. **Performance**: Better I/O performance for database operations
3. **Isolation**: Keeps application data separate from development files
4. **Portability**: Volumes work consistently across different environments
5. **Cleanliness**: No data files cluttering your project directory

### Volume Structure
- **`grievance_data`**: Contains database, documents, and processed data
- **`grievance_logs`**: Contains application logs
- **Code mounting**: Only the `./app` directory is mounted for development hot reload

## 🎯 Usage Scenarios

### Scenario 1: Full Pipeline (Test → Ingest → Serve)

Run the complete pipeline from testing to serving:

```bash
# Run tests first
docker-compose --profile test up test

# If tests pass, run ingestion
docker-compose --profile ingest up ingestion

# Finally, serve the application
docker-compose --profile serve up api
```

### Scenario 2: Development Mode

For local development with hot reload:

```bash
# Run tests
docker-compose --profile test up test

# Start development server
docker-compose --profile dev up api-dev
```

### Scenario 3: Individual Services

Run specific services as needed:

```bash
# Only run tests
docker-compose --profile test up test

# Only run ingestion (assumes tests passed)
docker-compose --profile ingest up ingestion

# Only serve API (assumes data is ingested)
docker-compose --profile serve up api
```

## 🔧 Service Profiles

### Test Profile
```bash
docker-compose --profile test up test
```
- Runs all unit tests
- Uses test database
- Exits after completion

### Ingest Profile
```bash
docker-compose --profile ingest up ingestion
```
- Downloads grievance data
- Processes complaints and documents
- Stores data in SQLite database

### Serve Profile
```bash
docker-compose --profile serve up api
```
- Starts FastAPI server
- Serves on http://localhost:8000
- Includes health checks

### Dev Profile
```bash
docker-compose --profile dev up api-dev
```
- Development server with hot reload
- Mounts app code for live changes
- Serves on http://localhost:8000

## 📊 Monitoring and Logs

### View Logs
```bash
# View logs for all services
docker-compose logs

# View logs for specific service
docker-compose logs api
docker-compose logs ingestion
docker-compose logs test

# Follow logs in real-time
docker-compose logs -f api
```

### Health Checks
The API service includes health checks:
- **Endpoint**: `http://localhost:8000/health`
- **Interval**: 30 seconds
- **Timeout**: 10 seconds
- **Retries**: 3

### Data Persistence
The application uses Docker named volumes for data persistence:

- **Database**: Stored in `grievance_data` volume (`/app/data/raw/grievance.db`)
- **Logs**: Stored in `grievance_logs` volume (`/app/logs/`)
- **Documents**: Stored in `grievance_data` volume (`/app/data/raw/documents/`)

#### Accessing Data from Host (if needed)
```bash
# Create a temporary container to access data
docker run --rm -v grievance_data:/data -v grievance_logs:/logs alpine sh

# Or copy data out of volumes
docker run --rm -v grievance_data:/data -v $(pwd):/backup alpine tar czf /backup/data_backup.tar.gz -C /data .

# List volume contents
docker run --rm -v grievance_data:/data alpine ls -la /data
```

#### Volume Management
```bash
# List volumes
docker volume ls | grep grievance

# Inspect volume
docker volume inspect grievance_data

# Remove volumes (WARNING: deletes all data)
docker-compose down -v
```

## 🛠️ Troubleshooting

### Common Issues

1. **Tests Fail**
   ```bash
   # Check test logs
   docker-compose --profile test up test
   ```

2. **Ingestion Fails**
   ```bash
   # Check API credentials in .env
   # Verify network connectivity
   docker-compose --profile ingest up ingestion
   ```

3. **API Won't Start**
   ```bash
   # Check if ingestion completed
   # Verify database exists
   docker-compose --profile serve up api
   ```

4. **Port Already in Use**
   ```bash
   # Change port in docker-compose.yml
   ports:
     - "8001:8000"  # Use port 8001 instead
   ```

### Clean Up
```bash
# Stop all services
docker-compose down

# Remove volumes (WARNING: deletes data)
docker-compose down -v

# Rebuild images
docker-compose build --no-cache

# Clean up unused resources
docker system prune
```

## 🔄 Workflow Examples

### Complete Development Workflow
```bash
# 1. Set up environment
cp .env.example .env
# Edit .env with your credentials

# 2. Run tests
docker-compose --profile test up test

# 3. Start development server
docker-compose --profile dev up api-dev

# 4. Access application
# Open http://localhost:8000
```

### Production-like Workflow
```bash
# 1. Run tests
docker-compose --profile test up test

# 2. Ingest data
docker-compose --profile ingest up ingestion

# 3. Serve application
docker-compose --profile serve up api

# 4. Monitor health
curl http://localhost:8000/health
```

## 📝 API Endpoints

Once the API is running, you can access:

- **Health Check**: `GET /health`
- **API Documentation**: `GET /docs` (Swagger UI)
- **ReDoc Documentation**: `GET /redoc`

## 🔐 Security Notes

- Never commit `.env` files to version control
- Use strong passwords for API credentials
- Consider using Docker secrets for production
- Regularly update base images for security patches

## 📈 Performance Tips

- Use `--build` flag only when needed: `docker-compose up --build`
- Use volume mounts for development to avoid rebuilding
- Monitor resource usage: `docker stats`
- Consider using Docker Compose override files for different environments 