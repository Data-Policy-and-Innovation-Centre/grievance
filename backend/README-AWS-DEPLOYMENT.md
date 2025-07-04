# AWS Deployment Guide for Grievance Analytics

This guide explains how to deploy the grievance analytics application to AWS using the automated deployment script.

## 🚀 Quick Start

### Prerequisites

1. **AWS CLI** installed and configured
2. **Docker** installed and running
3. **Terraform** installed
4. **AWS Permissions** for ECS, ECR, RDS, EventBridge, CloudWatch, and IAM

### Environment Setup

1. **Configure AWS CLI**:
   ```bash
   aws configure
   ```

2. **Set Database Password**:
   ```bash
   export DB_PASSWORD='your_secure_password'
   ```

3. **Deploy to Main Environment**:
   ```bash
   ./scripts/deploy-aws.sh deploy
   ```

## 📋 Deployment Script Usage

### Basic Commands

```bash
# Full deployment (build, push, deploy)
./scripts/deploy-aws.sh deploy

# Build and push Docker images only
./scripts/deploy-aws.sh build

# Plan Terraform deployment
./scripts/deploy-aws.sh plan

# Apply Terraform deployment
./scripts/deploy-aws.sh apply

# Check deployment status
./scripts/deploy-aws.sh status

# Test deployment
./scripts/deploy-aws.sh test

# Destroy infrastructure
./scripts/deploy-aws.sh destroy

# Show help
./scripts/deploy-aws.sh help
```

## 🏗️ What Gets Deployed

### Infrastructure Components

1. **VPC** with public and private subnets
2. **RDS PostgreSQL** database
3. **ECS Cluster** (Fargate - serverless)
4. **ECR Repository** for Docker images
5. **EventBridge Rule** for scheduled ingestion
6. **CloudWatch Log Group** for monitoring
7. **IAM Roles** and policies

### Application Components

1. **Docker Image** - Built from `Dockerfile.ingestion`
2. **ECS Task Definition** - Runs the ingestion service
3. **Scheduled Execution** - Weekly data ingestion

## 🔧 Environment Configuration

### Main Environment (`terraform.main.tfvars`)
- **Database**: t3.micro (1 vCPU, 1 GB RAM)
- **Storage**: 20 GB (max 200 GB)
- **Backup**: 30 days retention
- **Cost**: See infracost estimates in pull requests

## 📊 Monitoring and Logs

### CloudWatch Logs
```bash
# View logs
aws logs tail /ecs/grievance-ingestion-main --follow

# List log groups
aws logs describe-log-groups --log-group-name-prefix "/ecs/grievance-ingestion"
```

### ECS Monitoring
```bash
# List tasks
aws ecs list-tasks --cluster grievance-cluster-main

# Describe task
aws ecs describe-tasks --cluster grievance-cluster-main --tasks <task-arn>
```

### RDS Monitoring
```bash
# Check database status
aws rds describe-db-instances --db-instance-identifier grievance-postgres-main
```

## 🔐 Security Considerations

### Database Security
- **Encryption**: RDS storage is encrypted at rest
- **Network**: Database in private subnet
- **Access**: Only ECS tasks can connect via security groups

### IAM Permissions
The deployment creates minimal IAM roles:
- **ECS Execution Role**: Pulls images from ECR
- **EventBridge Role**: Triggers ECS tasks

### Secrets Management
- **Database Password**: Passed as environment variable
- **API Credentials**: Should be stored in AWS Secrets Manager for production

## 💰 Cost Optimization

### Main Environment
- **RDS t3.small**: ~$30/month
- **ECS Fargate**: ~$10/month (weekly runs)
- **ECR**: ~$2/month
- **EventBridge**: ~$1/month
- **CloudWatch**: ~$2/month
- **Total**: ~$45/month

### Cost Reduction Tips
1. **Stop unused resources**: Use `destroy` command when not needed
2. **Optimize scheduling**: Adjust EventBridge frequency
3. **Monitor usage**: Use AWS Cost Explorer
4. **Use reserved instances**: For RDS

## 🛠️ Troubleshooting

### Common Issues

#### 1. AWS Credentials Not Configured
```bash
# Configure AWS CLI
aws configure
```

#### 2. Database Password Not Set
```bash
# Set environment variable
export DB_PASSWORD='your_secure_password'
```

#### 3. Docker Build Fails
```bash
# Check Docker is running
docker ps

# Build manually to see errors
docker build -f Dockerfile.ingestion -t test .
```

#### 4. ECR Login Fails
```bash
# Manual ECR login
aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.ap-south-1.amazonaws.com
```

#### 5. Terraform State Issues
```bash
# Reinitialize Terraform
cd terraform
terraform init
terraform plan
```

### Debugging Commands

```bash
# Check deployment status
./scripts/deploy-aws.sh status

# View recent logs
aws logs tail /ecs/grievance-ingestion-main --since 1h

# Check ECS task status
aws ecs describe-tasks --cluster grievance-cluster-main --tasks $(aws ecs list-tasks --cluster grievance-cluster-main --query 'taskArns[0]' --output text)
```

## 🔄 CI/CD Integration

### GitHub Actions Example
```yaml
name: Deploy to AWS
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ap-south-1
      - name: Deploy to AWS
        run: |
          cd backend
          export DB_PASSWORD=${{ secrets.DB_PASSWORD }}
          ./scripts/deploy-aws.sh deploy
```

## 📈 Scaling Considerations

### Horizontal Scaling
- **ECS Service**: Can be configured to run multiple tasks
- **RDS**: Can be upgraded to larger instance types
- **Load Balancing**: Can add Application Load Balancer

### Vertical Scaling
- **Database**: Upgrade instance class (t3.micro → t3.small → t3.medium)
- **Storage**: Increase allocated storage
- **Memory**: Adjust ECS task memory allocation

## 🗑️ Cleanup

### Destroy Infrastructure
```bash
# Destroy main environment
./scripts/deploy-aws.sh destroy
```

### Manual Cleanup
```bash
# Remove Docker images
docker rmi grievance-ingestion-main:latest

# Remove ECR images
aws ecr batch-delete-image --repository-name grievance-ingestion-main --image-ids imageTag=latest
```

## 📞 Support

For issues with AWS deployment:
1. Check the troubleshooting section above
2. Review CloudWatch logs for application errors
3. Verify AWS permissions and credentials
4. Check Terraform state and outputs

## 🔗 Related Documentation

- [Terraform Configuration](../terraform/README.md)
- [Docker Setup](README-DOCKER.md)
- [Application Configuration](README.md) 