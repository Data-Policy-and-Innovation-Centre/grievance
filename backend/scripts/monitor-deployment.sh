#!/bin/bash

# Monitoring Script for Grievance Analytics AWS Deployment
# Usage: ./scripts/monitor-deployment.sh [environment]
# Example: ./scripts/monitor-deployment.sh dev

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# Default values
ENVIRONMENT=${1:-dev}
AWS_REGION="ap-south-1"

# Function to check ECS cluster status
check_ecs_status() {
    print_status "Checking ECS Cluster Status..."
    
    CLUSTER_NAME="grievance-cluster-$ENVIRONMENT"
    
    # Check if cluster exists
    CLUSTER_STATUS=$(aws ecs describe-clusters --clusters $CLUSTER_NAME --region $AWS_REGION --query 'clusters[0].status' --output text 2>/dev/null || echo "NOT_FOUND")
    
    if [ "$CLUSTER_STATUS" = "ACTIVE" ]; then
        print_success "ECS Cluster $CLUSTER_NAME is ACTIVE"
        
        # List tasks
        TASKS=$(aws ecs list-tasks --cluster $CLUSTER_NAME --region $AWS_REGION --query 'taskArns' --output text 2>/dev/null)
        
        if [ ! -z "$TASKS" ] && [ "$TASKS" != "None" ]; then
            print_status "Found tasks: $TASKS"
            
            # Get task details
            aws ecs describe-tasks --cluster $CLUSTER_NAME --tasks $TASKS --region $AWS_REGION --query 'tasks[].{TaskArn:taskArn,LastStatus:lastStatus,DesiredStatus:desiredStatus,HealthStatus:healthStatus}' --output table
        else
            print_warning "No tasks found in cluster"
        fi
        
        # List services
        SERVICES=$(aws ecs list-services --cluster $CLUSTER_NAME --region $AWS_REGION --query 'serviceArns' --output text 2>/dev/null)
        if [ ! -z "$SERVICES" ] && [ "$SERVICES" != "None" ]; then
            print_status "Services in cluster:"
            aws ecs describe-services --cluster $CLUSTER_NAME --services $SERVICES --region $AWS_REGION --query 'services[].{ServiceName:serviceName,Status:status,RunningCount:runningCount,DesiredCount:desiredCount}' --output table
        fi
    else
        print_error "ECS Cluster $CLUSTER_NAME is not active (Status: $CLUSTER_STATUS)"
    fi
}

# Function to check RDS status
check_rds_status() {
    print_status "Checking RDS Database Status..."
    
    DB_IDENTIFIER="grievance-postgres-$ENVIRONMENT"
    
    # Check if RDS instance exists and get status
    DB_STATUS=$(aws rds describe-db-instances --db-instance-identifier $DB_IDENTIFIER --region $AWS_REGION --query 'DBInstances[0].DBInstanceStatus' --output text 2>/dev/null || echo "NOT_FOUND")
    
    if [ "$DB_STATUS" = "available" ]; then
        print_success "RDS Database $DB_IDENTIFIER is AVAILABLE"
        
        # Get database details
        aws rds describe-db-instances --db-instance-identifier $DB_IDENTIFIER --region $AWS_REGION --query 'DBInstances[0].{Engine:Engine,EngineVersion:EngineVersion,DBInstanceClass:DBInstanceClass,AllocatedStorage:AllocatedStorage,Endpoint:Endpoint.Address,Port:Endpoint.Port}' --output table
    else
        print_error "RDS Database $DB_IDENTIFIER is not available (Status: $DB_STATUS)"
    fi
}

# Function to check CloudWatch logs
check_cloudwatch_logs() {
    print_status "Checking CloudWatch Logs..."
    
    LOG_GROUP="/ecs/grievance-ingestion-$ENVIRONMENT"
    
    # Check if log group exists
    LOG_GROUP_EXISTS=$(aws logs describe-log-groups --log-group-name-prefix $LOG_GROUP --region $AWS_REGION --query 'logGroups[0].logGroupName' --output text 2>/dev/null || echo "NOT_FOUND")
    
    if [ "$LOG_GROUP_EXISTS" = "$LOG_GROUP" ]; then
        print_success "CloudWatch Log Group $LOG_GROUP exists"
        
        # Get recent log streams
        LOG_STREAMS=$(aws logs describe-log-streams --log-group-name $LOG_GROUP --region $AWS_REGION --order-by LastEventTime --descending --max-items 5 --query 'logStreams[].logStreamName' --output text 2>/dev/null)
        
        if [ ! -z "$LOG_STREAMS" ] && [ "$LOG_STREAMS" != "None" ]; then
            print_status "Recent log streams:"
            echo "$LOG_STREAMS" | tr '\t' '\n'
            
            # Get recent logs from the latest stream
            LATEST_STREAM=$(echo "$LOG_STREAMS" | head -1)
            if [ ! -z "$LATEST_STREAM" ]; then
                print_status "Recent logs from $LATEST_STREAM:"
                aws logs get-log-events --log-group-name $LOG_GROUP --log-stream-name "$LATEST_STREAM" --region $AWS_REGION --start-time $(date -d '1 hour ago' +%s)000 --query 'events[].{Timestamp:timestamp,Message:message}' --output table 2>/dev/null || print_warning "No recent logs found"
            fi
        else
            print_warning "No log streams found"
        fi
    else
        print_error "CloudWatch Log Group $LOG_GROUP not found"
    fi
}

# Function to check EventBridge rules
check_eventbridge_rules() {
    print_status "Checking EventBridge Rules..."
    
    RULE_NAME="grievance-weekly-ingestion-$ENVIRONMENT"
    
    # Check if rule exists
    RULE_EXISTS=$(aws events describe-rule --name $RULE_NAME --region $AWS_REGION --query 'Name' --output text 2>/dev/null || echo "NOT_FOUND")
    
    if [ "$RULE_EXISTS" = "$RULE_NAME" ]; then
        print_success "EventBridge Rule $RULE_NAME exists"
        
        # Get rule details
        aws events describe-rule --name $RULE_NAME --region $AWS_REGION --query '{Name:Name,ScheduleExpression:ScheduleExpression,State:State}' --output table
    else
        print_error "EventBridge Rule $RULE_NAME not found"
    fi
}

# Function to check ECR repository
check_ecr_repository() {
    print_status "Checking ECR Repository..."
    
    REPO_NAME="grievance-ingestion-$ENVIRONMENT"
    
    # Check if repository exists
    REPO_EXISTS=$(aws ecr describe-repositories --repository-names $REPO_NAME --region $AWS_REGION --query 'repositories[0].repositoryName' --output text 2>/dev/null || echo "NOT_FOUND")
    
    if [ "$REPO_EXISTS" = "$REPO_NAME" ]; then
        print_success "ECR Repository $REPO_NAME exists"
        
        # Get repository details
        aws ecr describe-repositories --repository-names $REPO_NAME --region $AWS_REGION --query 'repositories[0].{RepositoryName:repositoryName,RepositoryUri:repositoryUri,CreatedAt:createdAt}' --output table
        
        # List images
        print_status "Images in repository:"
        aws ecr list-images --repository-name $REPO_NAME --region $AWS_REGION --query 'imageIds[].{ImageTag:imageTag,ImageDigest:imageDigest}' --output table 2>/dev/null || print_warning "No images found"
    else
        print_error "ECR Repository $REPO_NAME not found"
    fi
}

# Function to check overall deployment health
check_deployment_health() {
    print_status "=== Deployment Health Check ==="
    
    # Check all components
    check_ecs_status
    echo ""
    check_rds_status
    echo ""
    check_ecr_repository
    echo ""
    check_eventbridge_rules
    echo ""
    check_cloudwatch_logs
    echo ""
    
    print_status "=== Health Check Summary ==="
    print_success "All components checked. Review the output above for any issues."
}

# Function to show real-time logs
show_realtime_logs() {
    print_status "Showing real-time logs (Ctrl+C to stop)..."
    
    LOG_GROUP="/ecs/grievance-ingestion-$ENVIRONMENT"
    
    # Follow logs in real-time
    aws logs tail $LOG_GROUP --follow --region $AWS_REGION || print_warning "No logs available or log group not found"
}

# Function to show help
show_help() {
    echo "Monitoring Script for Grievance Analytics AWS Deployment"
    echo ""
    echo "Usage: $0 [environment] [action]"
    echo ""
    echo "Environments:"
    echo "  dev     - Development environment (default)"
    echo "  prod    - Production environment"
    echo ""
    echo "Actions:"
    echo "  status      - Check deployment status (default)"
    echo "  logs        - Show real-time logs"
    echo "  ecs         - Check ECS status only"
    echo "  rds         - Check RDS status only"
    echo "  cloudwatch  - Check CloudWatch logs only"
    echo "  eventbridge - Check EventBridge rules only"
    echo "  ecr         - Check ECR repository only"
    echo "  help        - Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 dev status      # Check dev deployment status"
    echo "  $0 prod logs       # Show real-time logs for prod"
    echo "  $0 dev ecs         # Check only ECS status"
}

# Main script logic
main() {
    ACTION=${2:-status}
    
    case $ACTION in
        "status")
            check_deployment_health
            ;;
        "logs")
            show_realtime_logs
            ;;
        "ecs")
            check_ecs_status
            ;;
        "rds")
            check_rds_status
            ;;
        "cloudwatch")
            check_cloudwatch_logs
            ;;
        "eventbridge")
            check_eventbridge_rules
            ;;
        "ecr")
            check_ecr_repository
            ;;
        "help")
            show_help
            ;;
        *)
            print_error "Invalid action: $ACTION"
            show_help
            exit 1
            ;;
    esac
}

# Run main function
main "$@" 