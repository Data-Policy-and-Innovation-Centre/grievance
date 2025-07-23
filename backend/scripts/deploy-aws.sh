#!/bin/bash

# AWS Deployment Script for Grievance Analytics
# Usage: ./scripts/deploy-aws.sh [action]
# Example: ./scripts/deploy-aws.sh deploy
# Default values


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

if [ -f .env ]; then
    print_status "Loading environment variables from .env"
    set -a
    source .env
    set +a
else
    print_warning ".env file not found. Skipping environment variable loading."
fi


ENVIRONMENT=${ENV:-"main"}
ACTION=${1:-deploy}
TERRAFORM_DIR="../terraform"
if [ "$ENVIRONMENT" = "main" ]; then
    TERRAFORM_CMD="terraform"
    AWS_CMD="aws"
elif [ "$ENVIRONMENT" = "dev" ]; then
    TERRAFORM_CMD="tflocal"
    AWS_CMD="awslocal"
else
    print_error "Environment '$ENVIRONMENT' is not valid. Exiting."
    exit 1
fi

HOME_DIR=$(pwd)
AWS_REGION="ap-south-1"

# Function to check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    # Check if AWS CLI is installed
    if ! command -v $AWS_CMD &> /dev/null; then
        print_error "AWS CLI is not installed. Please install it first."
        exit 1
    fi
    
    # Check if Docker is installed
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install it first."
        exit 1
    fi

    if ! command -v localstack &> /dev/null; then
        print_error "Localstack is not installed. Please install it first."
        exit 1
    fi
    
    # Check if Terraform is installed
    if ! command -v $TERRAFORM_CMD &> /dev/null; then
        print_error "Terraform is not installed. Please install it first."
        exit 1
    fi
    
    # Check AWS credentials
    if ! $AWS_CMD sts get-caller-identity &> /dev/null; then
        print_error "AWS credentials not configured. Please run 'aws configure' first."
        exit 1
    fi
    
    print_status "Terraform command: $TERRAFORM_CMD"
    print_status "AWS command: $AWS_CMD"
    print_success "All prerequisites are met!"
}

# Function to get AWS account ID
get_aws_account_id() {
    AWS_ACCOUNT_ID=$($AWS_CMD sts get-caller-identity --query Account --output text)
    print_status "Using AWS Account ID: $AWS_ACCOUNT_ID"
}

# Function to build and push Docker images
build_and_push_images() {
    print_status "Building and pushing Docker images to ECR..."
    
    # Get ECR login token
    print_status "Logging into ECR..."
    $AWS_CMD ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
    
    # Build and push ingestion image
    print_status "Building ingestion image..."
    # Change to backend directory for Docker build
    cd $HOME_DIR
    # Build for linux/amd64 platform (required for ECS Fargate)
    docker build --platform linux/amd64 -f Dockerfile.ingestion -t grievance-ingestion-$ENVIRONMENT:latest .
    
    print_status "Tagging ingestion image..."
    docker tag grievance-ingestion-$ENVIRONMENT:latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/grievance-ingestion-$ENVIRONMENT:latest
    
    print_status "Pushing ingestion image to ECR..."
    docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/grievance-ingestion-$ENVIRONMENT:latest
    
    print_success "Docker images built and pushed successfully!"
}

# Function to initialize Terraform
init_terraform() {
    print_status "Initializing Terraform..."
    cd $TERRAFORM_DIR
    
    # Initialize Terraform
    $TERRAFORM_CMD init
    
    print_success "Terraform initialized successfully!"
}

init_localstack() {
    if [ "$ENVIRONMENT" = "dev" ]; then
        print_status "Initializing Localstack..."
        localstack start
        print_success "Localstack initialized successfully!"
    else 
        print_status "Localstack not initialized for $ENVIRONMENT environment."
    fi
}

# Function to plan Terraform deployment
plan_terraform() {
    print_status "Planning Terraform deployment..."
    
    # Check if database password is provided
    if [ -z "$DB_PASSWORD" ]; then
        print_error "Database password not set. Please set DB_PASSWORD environment variable."
        print_error "Example: export DB_PASSWORD='your_secure_password'"
        exit 1
    fi
    
    # Check if Janasunani API credentials are provided
    if [ -z "$JANASUNANI_API_USERNAME" ] || [ -z "$JANASUNANI_API_PASSWORD" ]; then
        print_warning "Janasunani API credentials not set. Using empty values."
        print_warning "Set JANASUNANI_API_USERNAME and JANASUNANI_API_PASSWORD environment variables for full functionality."
        JANASUNANI_API_USERNAME=${JANASUNANI_API_USERNAME:-""}
        JANASUNANI_API_PASSWORD=${JANASUNANI_API_PASSWORD:-""}
    fi
    
    # Run terraform plan
    $TERRAFORM_CMD plan \
        -var-file="terraform.main.tfvars" \
        -var="db_password=$DB_PASSWORD" \
        -var="janasunani_api_username=$JANASUNANI_API_USERNAME" \
        -var="janasunani_api_password=$JANASUNANI_API_PASSWORD" \
        -out=tfplan
    
    print_success "Terraform plan created successfully!"
}

# Function to apply Terraform deployment
apply_terraform() {
    print_status "Applying Terraform deployment..."
    
    # Apply the plan
    $TERRAFORM_CMD apply tfplan
    
    print_success "Terraform deployment completed successfully!"
}

# Function to get deployment outputs
get_outputs() {
    print_status "Getting deployment outputs..."
    
    # Get ECR repository URL
    ECR_REPO_URL=$($TERRAFORM_CMD output -raw ingestion_ecr_repository_url)
    print_status "ECR Repository URL: $ECR_REPO_URL"
    
    # Get RDS endpoint
    RDS_ENDPOINT=$($TERRAFORM_CMD output -raw rds_endpoint)
    print_status "RDS Endpoint: $RDS_ENDPOINT"
    
    # Get ECS cluster name
    ECS_CLUSTER=$($TERRAFORM_CMD output -raw ecs_cluster_name)
    print_status "ECS Cluster: $ECS_CLUSTER"
    
    # Get EventBridge rule name
    EVENTBRIDGE_RULE=$($TERRAFORM_CMD output -raw eventbridge_rule_name)
    print_status "EventBridge Rule: $EVENTBRIDGE_RULE"
    
    # Get S3 bucket name
    S3_BUCKET_NAME=$($TERRAFORM_CMD output -raw documents_s3_bucket_name)
    print_status "S3 Documents Bucket: $S3_BUCKET_NAME"
    
    print_success "Deployment outputs retrieved!"
}

# Function to test the deployment
test_deployment() {
    print_status "Testing deployment..."
    
    # Get ECS cluster name
    ECS_CLUSTER=$(cd $TERRAFORM_DIR && $TERRAFORM_CMD output -raw ecs_cluster_name)
    
    # List ECS tasks
    print_status "Checking ECS tasks..."
    $AWS_CMD ecs list-tasks --cluster $ECS_CLUSTER --region $AWS_REGION
    
    # Check CloudWatch logs
    print_status "Checking CloudWatch logs..."
    $AWS_CMD logs describe-log-groups --log-group-name-prefix "/ecs/grievance-ingestion" --region $AWS_REGION
    
    print_success "Deployment test completed!"
}

# Function to destroy infrastructure
destroy_infrastructure() {
    print_warning "This will destroy all AWS infrastructure for environment: $ENVIRONMENT"
    print_warning "For complete destruction including ECR images, use: ./scripts/destroy-aws.sh $ENVIRONMENT"
    read -p "Are you sure you want to continue? (y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_status "Destroying infrastructure..."
        cd $TERRAFORM_DIR
        
        $TERRAFORM_CMD destroy \
            -var-file="terraform.main.tfvars" \
            -var="db_password=$DB_PASSWORD" \
            -var="janasunani_api_username=$JANASUNANI_API_USERNAME" \
            -var="janasunani_api_password=$JANASUNANI_API_PASSWORD" \
            -auto-approve
        
        print_success "Infrastructure destroyed successfully!"
        print_warning "Note: ECR images may still exist. Use ./scripts/destroy-aws.sh for complete cleanup."
    else
        print_status "Destroy cancelled."
    fi
}

# Function to show deployment status
show_status() {
    print_status "Checking deployment status..."
    
    cd $TERRAFORM_DIR
    
    # Get outputs
    ECS_CLUSTER=$($TERRAFORM_CMD output -raw ecs_cluster_name 2>/dev/null || echo "Not deployed")
    RDS_ENDPOINT=$($TERRAFORM_CMD output -raw rds_endpoint 2>/dev/null || echo "Not deployed")
    ECR_REPO_URL=$($TERRAFORM_CMD output -raw ingestion_ecr_repository_url 2>/dev/null || echo "Not deployed")
    
    echo "=== Deployment Status ==="
    echo "Environment: $ENVIRONMENT"
    echo "ECS Cluster: $ECS_CLUSTER"
    echo "RDS Endpoint: $RDS_ENDPOINT"
    echo "ECR Repository: $ECR_REPO_URL"
    
    if [ "$ECS_CLUSTER" != "Not deployed" ]; then
        echo ""
        echo "=== ECS Tasks ==="
        $AWS_CMD ecs list-tasks --cluster $ECS_CLUSTER --region $AWS_REGION --query 'taskArns' --output table 2>/dev/null || echo "No tasks found"
        
        echo ""
        echo "=== CloudWatch Log Groups ==="
        $AWS_CMD logs describe-log-groups --log-group-name-prefix "/ecs/grievance-ingestion" --region $AWS_REGION --query 'logGroups[].logGroupName' --output table 2>/dev/null || echo "No log groups found"
    fi
}

# Function to show help
show_help() {
    echo "AWS Deployment Script for Grievance Analytics"
    echo ""
    echo "Usage: $0 [action]"
    echo ""
    echo "Actions:"
    echo "  deploy      - Full deployment (build, push, deploy)"
    echo "  build       - Build and push Docker images only"
    echo "  plan        - Plan Terraform deployment"
    echo "  apply       - Apply Terraform deployment"
    echo "  test        - Test the deployment"
    echo "  status      - Show deployment status"
    echo "  destroy     - Destroy infrastructure"
    echo "  help        - Show this help message"
    echo ""
    echo "Environment Variables:"
    echo "  DB_PASSWORD - Database password (required for deployment)"
    echo "  JANASUNANI_API_USERNAME - Janasunani API username (optional)"
    echo "  JANASUNANI_API_PASSWORD - Janasunani API password (optional)"
    echo ""
    echo "Examples:"
    echo "  $0 deploy     # Deploy to main environment"
    echo "  $0 plan      # Plan main deployment"
    echo "  $0 status     # Check main status"
    echo "  $0 destroy    # Destroy main infrastructure"
    echo ""
    echo "Prerequisites:"
    echo "  - AWS CLI configured with appropriate permissions"
    echo "  - Docker installed and running"
    echo "  - Terraform installed"
    echo "  - DB_PASSWORD environment variable set"
}

# Function to validate environment
validate_environment() {
    if [ "$ENVIRONMENT" != "main" ] && [ "$ENVIRONMENT" != "dev" ]; then
        print_error "Invalid environment: $ENVIRONMENT. Use 'main' or 'dev'."
        exit 1
    fi

    if [ "$ENVIRONMENT" = "dev" ]; then
        print_status "Setting up AWS CLI environment  for local development..."
        export AWS_ENDPOINT_URL=http://localhost:4566
        export AWS_ACCESS_KEY_ID=test
        export AWS_SECRET_ACCESS_KEY=test
        export AWS_DEFAULT_REGION=us-east-1
    fi
}


# Function to validate action
validate_action() {
    case $ACTION in
        deploy|build|plan|apply|test|status|destroy|help)
            ;;
        *)
            print_error "Invalid action: $ACTION"
            show_help
            exit 1
            ;;
    esac
}

# Main deployment function
deploy() {
    print_status "Starting deployment for environment: $ENVIRONMENT"
    
    # Check prerequisites
    check_prerequisites
    
    # Get AWS account ID
    get_aws_account_id

    # Initialize Localstack
    init_localstack

    # Initialize Terraform
    init_terraform
    
    # Plan deployment
    plan_terraform
    
    # Apply deployment
    apply_terraform
    
    # Build and push Docker images
    build_and_push_images
    
    # Get outputs
    get_outputs
    
    # Test deployment
    test_deployment
    
    print_success "Deployment completed successfully!"
    print_status "Your grievance analytics application is now running on AWS!"
}

# Main script logic
main() {
    # Check if we're in the right directory
    if [ ! -f "docker-compose.yml" ]; then
        print_error "docker-compose.yml not found. Please run this script from the backend directory."
        exit 1
    fi
    
    # Handle help command first
    if [ "$1" = "help" ]; then
        show_help
        exit 0
    fi
    
    # Validate inputs
    validate_environment
    validate_action
    
    # Execute action
    case $ACTION in
        "deploy")
            deploy
            ;;
        "build")
            check_prerequisites
            get_aws_account_id
            build_and_push_images
            ;;
        "plan")
            check_prerequisites
            init_terraform
            plan_terraform
            ;;
        "apply")
            check_prerequisites
            init_localstack
            init_terraform
            apply_terraform
            get_outputs
            ;;
        "test")
            check_prerequisites
            test_deployment
            ;;
        "status")
            show_status
            ;;
        "destroy")
            check_prerequisites
            destroy_infrastructure
            ;;
        "help")
            show_help
            ;;
    esac
}

# Run main function with all arguments
main "$@" 