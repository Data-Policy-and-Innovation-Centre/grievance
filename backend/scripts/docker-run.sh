#!/bin/bash

# Docker Compose Runner Script for Grievance Analytics
# Usage: ./scripts/docker-run.sh [command]

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

# Database Configuration (uses Docker volumes)
DB_URL=sqlite:///data/raw/grievance.db

# AWS Configuration (optional for local development)
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=ap-south-1
AWS_S3_BUCKET_NAME=janasunani-data
AWS_S3_DOCUMENTS=janasunani-documents
EOF
        print_warning "Please edit .env file with your actual credentials before running services."
        print_warning "Note: Data is stored in Docker volumes, not local filesystem."
    fi
}

# Function to run tests
run_tests() {
    print_status "Running tests..."
    docker-compose --profile test up test
    if [ $? -eq 0 ]; then
        print_success "Tests passed!"
    else
        print_error "Tests failed!"
        exit 1
    fi
}

# Function to run ingestion
run_ingestion() {
    print_status "Running data ingestion..."
    docker-compose --profile ingest up ingestion
    if [ $? -eq 0 ]; then
        print_success "Data ingestion completed!"
    else
        print_error "Data ingestion failed!"
        exit 1
    fi
}

# Function to run API server
run_api() {
    print_status "Starting API server..."
    docker-compose --profile serve up api
}

# Function to run development server
run_dev() {
    print_status "Starting development server with hot reload..."
    docker-compose --profile dev up api-dev
}

# Function to run full pipeline
run_full() {
    print_status "Running full pipeline: Test → Ingest → Serve"
    
    # Run tests
    run_tests
    
    # Run ingestion
    run_ingestion
    
    # Run API server
    run_api
}

# Function to show help
show_help() {
    echo "Docker Compose Runner for Grievance Analytics"
    echo ""
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  test       - Run unit tests"
    echo "  ingest     - Run data ingestion"
    echo "  serve      - Start API server"
    echo "  dev        - Start development server with hot reload"
    echo "  full       - Run full pipeline (test → ingest → serve)"
    echo "  clean      - Stop all services and clean up"
    echo "  logs       - Show logs for all services"
    echo "  build      - Build all Docker images"
    echo "  help       - Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 test     # Run tests only"
    echo "  $0 dev      # Start development server"
    echo "  $0 full     # Run complete pipeline"
}

# Function to clean up
clean_up() {
    print_status "Stopping all services and cleaning up..."
    docker-compose down
    print_success "Cleanup completed!"
}

# Function to show logs
show_logs() {
    print_status "Showing logs for all services..."
    docker-compose logs
}

# Function to build images
build_images() {
    print_status "Building all Docker images..."
    docker-compose build --no-cache
    print_success "Build completed!"
}

# Main script logic
main() {
    # Check if we're in the right directory
    if [ ! -f "docker-compose.yml" ]; then
        print_error "docker-compose.yml not found. Please run this script from the backend directory."
        exit 1
    fi
    
    # Check for .env file
    check_env_file
    
    # Parse command
    case "${1:-help}" in
        "test")
            run_tests
            ;;
        "ingest")
            run_ingestion
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
        "clean")
            clean_up
            ;;
        "logs")
            show_logs
            ;;
        "build")
            build_images
            ;;
        "help"|*)
            show_help
            ;;
    esac
}

# Run main function with all arguments
main "$@" 