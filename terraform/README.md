# Terraform Setup for Grievance Analytics

This Terraform configuration creates AWS infrastructure to run the grievance ingestion container once a week for 6 hours.

## What This Creates

### Infrastructure Components
- **VPC** with public and private subnets
- **RDS PostgreSQL** database (t3.micro, 20GB storage)
- **ECS Cluster** (Fargate - serverless)
- **ECR Repository** for storing Docker images
- **S3 Bucket** for storing Janasunani documents
- **EventBridge Rule** to run ingestion every 7 days
- **CloudWatch Log Group** for container logs
- **IAM Roles** for ECS and EventBridge permissions

### Network Security
- **Security Groups** allowing ECS to connect to RDS
- **Public subnets** for ECS tasks with internet access
- **Private subnets** for RDS database

## How It Works

1. **Every 7 days**, EventBridge triggers an ECS task
2. **ECS starts your ingestion container** with database connection
3. **Container runs for up to 6 hours** (or until completion)
4. **Logs are sent to CloudWatch** for monitoring
5. **Task stops automatically** when done

## Usage

### Prerequisites
- AWS CLI configured
- Terraform installed
- Docker image built and pushed to ECR

### Deploy Infrastructure

```bash
# Initialize Terraform
terraform init

# Plan the deployment
terraform plan -var-file="terraform.main.tfvars" -var="db_password=your_secure_password"

# Apply the configuration
terraform apply -var-file="terraform.main.tfvars" -var="db_password=your_secure_password"
```

### Build and Push Docker Image

```bash
# Get ECR login token
aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.ap-south-1.amazonaws.com

# Build image for linux/amd64 platform (required for ECS Fargate)
docker build --platform linux/amd64 -f backend/Dockerfile.ingestion -t grievance-ingestion-main:latest backend

# Tag image
docker tag grievance-ingestion-main:latest $AWS_ACCOUNT_ID.dkr.ecr.ap-south-1.amazonaws.com/grievance-ingestion-main:latest

# Push image
docker push $AWS_ACCOUNT_ID.dkr.ecr.ap-south-1.amazonaws.com/grievance-ingestion-main:latest
```

### Check Status

```bash
# View outputs
terraform output

# Check ECS cluster
aws ecs list-tasks --cluster grievance-cluster-main

# Check CloudWatch logs
aws logs describe-log-groups --log-group-name-prefix "/ecs/grievance-ingestion"
```

## Environment Variables

The ingestion container receives these environment variables:
- `ENV`: Environment name (main)
- `DB_URL`: PostgreSQL connection string (auto-generated)
- `AWS_S3_DOCUMENTS`: S3 bucket name for document storage (auto-generated)

## S3 Bucket Configuration

The S3 bucket for documents includes:
- **Versioning**: Enabled for document history
- **Encryption**: AES256 server-side encryption
- **Public Access**: Blocked for security
- **Lifecycle**: Documents transition to IA after 30 days, Glacier after 90 days, and expire after 7 years
- **Permissions**: ECS tasks can read, write, and delete documents

## Cost Estimation

- **RDS t3.micro**: ~$15/month
- **ECS Fargate**: ~$5/month (for weekly runs)
- **ECR**: ~$1/month
- **S3**: ~$2/month (for document storage)
- **EventBridge**: ~$1/month
- **CloudWatch**: ~$1/month

**Total**: ~$25/month

## Next Steps

1. Add API service for serving data
2. Add monitoring and alerting 