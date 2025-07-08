#!/bin/bash

# Local Development Runner Script for Grievance Analytics
# Usage: ./scripts/run-local.sh [command]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if .env file exists
check_env_file() {
    if [ ! -f ".env" ]; then
        print_warning ".env file not found. Creating template..."
        cat > .env << EOF
# Environment and Debug
ENV=dev
DEBUG=True

# Janasunani API Configuration (REQUIRED)
JANASUNANI_API_USERNAME=your_username
JANASUNANI_API_PASSWORD=your_password

# Database Configuration (local SQLite)
DB_URL=sqlite:///data/raw/grievance.db

# AWS Configuration (optional for local development)
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=ap-south-1
AWS_S3_BUCKET_NAME=janasunani-data
AWS_S3_DOCUMENTS=janasunani-documents
EOF
        print_warning "Please edit .env file with your actual credentials before running services."
        print_warning "Note: Data is stored in local ./data directory."
    fi
}

# Function to check if uv is installed
check_uv() {
    if ! command -v uv &> /dev/null; then
        print_error "UV is not installed. Please install it first:"
        echo "curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi
}

# Function to setup local environment
setup_local() {
    print_status "Setting up local environment..."
    
    # Create data directories
    mkdir -p data/raw data/processed logs
    
    # Install dependencies
    print_status "Installing dependencies with UV..."
    uv sync
    
    print_success "Local environment setup completed!"
}

# Function to run tests
run_tests() {
    print_status "Running tests locally..."
    
    # Set test environment
    export ENV=test
    export DB_URL=sqlite:///data/raw/test_grievance.db
    
    uv run pytest app/tests -v --tb=short
    
    if [ $? -eq 0 ]; then
        print_success "Tests passed!"
    else
        print_error "Tests failed!"
        exit 1
    fi
}

# Function to run ingestion
run_ingestion() {
    print_status "Running data ingestion locally..."
    
    # Parse ingestion arguments
    local ingest_complaints=""
    local ingest_documents=""
    local ingest_action_history=""
    local force_params=""
    
    # Parse additional arguments
    shift  # Remove the "ingest" command
    while [[ $# -gt 0 ]]; do
        case $1 in
            --complaints)
                ingest_complaints="--ingest-complaints"
                shift
                ;;
            --documents)
                ingest_documents="--ingest-documents"
                shift
                ;;
            --action-history)
                ingest_action_history="--ingest-action-history"
                shift
                ;;
            --force)
                force_params="--force-params"
                shift
                ;;
            --all)
                ingest_complaints="--ingest-complaints"
                ingest_documents="--ingest-documents"
                ingest_action_history="--ingest-action-history"
                shift
                ;;
            *)
                print_warning "Unknown argument: $1"
                shift
                ;;
        esac
    done
    
    # Ensure data directory exists
    mkdir -p data/raw data/processed logs
    
    # Run ingestion with arguments
    uv run python -m app.ingestion.orchestrator $ingest_complaints $ingest_documents $ingest_action_history $force_params
    
    if [ $? -eq 0 ]; then
        print_success "Data ingestion completed!"
    else
        print_error "Data ingestion failed!"
        exit 1
    fi
}

# Function to run complaints ingestion only
run_ingest_complaints() {
    print_status "Running complaints ingestion locally..."
    
    # Ensure data directory exists
    mkdir -p data/raw data/processed logs
    
    # Run complaints ingestion
    uv run python -m app.ingestion.orchestrator --ingest-complaints
    
    if [ $? -eq 0 ]; then
        print_success "Complaints ingestion completed!"
    else
        print_error "Complaints ingestion failed!"
        exit 1
    fi
}

# Function to run documents ingestion only
run_ingest_documents() {
    print_status "Running documents ingestion locally..."
    
    # Ensure data directory exists
    mkdir -p data/raw data/processed logs
    
    # Run documents ingestion
    uv run python -m app.ingestion.orchestrator --ingest-documents
    
    if [ $? -eq 0 ]; then
        print_success "Documents ingestion completed!"
    else
        print_error "Documents ingestion failed!"
        exit 1
    fi
}

# Function to run action history ingestion only
run_ingest_action_history() {
    print_status "Running action history ingestion locally..."
    
    # Ensure data directory exists
    mkdir -p data/raw data/processed logs
    
    # Run action history ingestion
    uv run python -m app.ingestion.orchestrator --ingest-action-history
    
    if [ $? -eq 0 ]; then
        print_success "Action history ingestion completed!"
    else
        print_error "Action history ingestion failed!"
        exit 1
    fi
}

# Function to run API server
run_api() {
    print_status "Starting API server locally..."
    
    # Ensure data directory exists
    mkdir -p data/raw data/processed logs
    
    # Run API server
    uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
}

# Function to run development server
run_dev() {
    print_status "Starting development server with hot reload..."
    
    # Ensure data directory exists
    mkdir -p data/raw data/processed logs
    
    # Run development server
    uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
}

# Function to run full pipeline
run_full() {
    print_status "Running full pipeline locally: Test → Ingest → Serve"
    
    # Run tests
    run_tests
    
    # Run ingestion
    run_ingestion
    
    # Run API server
    run_api
}

# Function to run coverage
run_coverage() {
    print_status "Running tests with coverage..."
    
    # Set test environment
    export ENV=test
    export DB_URL=sqlite:///data/raw/test_grievance.db
    
    uv run coverage run -m pytest app/tests
    uv run coverage report --show-missing
    uv run coverage html
    
    print_success "Coverage report generated in coverage_html/index.html"
}

# Function to clean up
clean_up() {
    print_status "Cleaning up local data..."
    
    # Remove test database
    rm -f data/raw/test_grievance.db
    
    # Remove coverage files
    rm -f .coverage coverage.xml coverage.lcov
    rm -rf coverage_html
    
    print_success "Cleanup completed!"
}

# Function to show help
show_help() {
    echo "Local Development Runner for Grievance Analytics"
    echo ""
    echo "Usage: $0 [command] [options]"
    echo ""
    echo "Commands:"
    echo "  setup     - Setup local environment (install deps, create dirs)"
    echo "  test      - Run unit tests locally"
    echo "  ingest    - Run data ingestion locally (with options)"
    echo "  ingest-complaints    - Run complaints ingestion only"
    echo "  ingest-documents     - Run documents ingestion only"
    echo "  ingest-action-history - Run action history ingestion only"
    echo "  serve     - Start API server locally"
    echo "  dev       - Start development server with hot reload"
    echo "  full      - Run full pipeline (test → ingest → serve)"
    echo "  coverage  - Run tests with coverage report"
    echo "  clean     - Clean up local test data and coverage files"
    echo "  help      - Show this help message"
    echo ""
    echo "Ingestion Options (for 'ingest' command):"
    echo "  --complaints     - Ingest complaint data only"
    echo "  --documents      - Ingest document data only"
    echo "  --action-history - Ingest action history data only"
    echo "  --force          - Force ingestion with default parameters"
    echo "  --all            - Ingest all data types (default behavior)"
    echo ""
    echo "Examples:"
    echo "  $0 setup   # Setup environment first time"
    echo "  $0 test    # Run tests only"
    echo "  $0 dev     # Start development server"
    echo "  $0 full    # Run complete pipeline"
    echo "  $0 ingest --complaints --documents  # Ingest complaints and documents"
    echo "  $0 ingest --all --force             # Force ingest all data types"
    echo "  $0 ingest-complaints                # Ingest complaints only"
    echo ""
    echo "Data is stored in:"
    echo "  - Database: ./data/raw/grievance.db"
    echo "  - Logs: ./logs/"
    echo "  - Coverage: ./coverage_html/"
}

# Main script logic
main() {
    # Check if we're in the right directory
    if [ ! -f "pyproject.toml" ]; then
        print_error "pyproject.toml not found. Please run this script from the backend directory."
        exit 1
    fi
    
    # Check for UV
    check_uv
    
    # Check for .env file
    check_env_file
    
    # Parse command
    case "${1:-help}" in
        "setup")
            setup_local
            ;;
        "test")
            run_tests
            ;;
        "ingest")
            run_ingestion "$@"
            ;;
        "ingest-complaints")
            run_ingest_complaints
            ;;
        "ingest-documents")
            run_ingest_documents
            ;;
        "ingest-action-history")
            run_ingest_action_history
            ;;
        "serve")
            run_api
            ;;
        "dev")
            run_dev
            ;;
        "full")
            run_full
            ;;
        "coverage")
            run_coverage
            ;;
        "clean")
            clean_up
            ;;
        "help"|*)
            show_help
            ;;
    esac
}

# Run main function with all arguments
main "$@" 