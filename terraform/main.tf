terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# VPC for RDS and ECS
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name        = "grievance-vpc-${var.environment}"
    Environment = var.environment
  }
}

# Internet Gateway
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name        = "grievance-igw-${var.environment}"
    Environment = var.environment
  }
}

# Public Subnet for ECS
resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = "${var.aws_region}a"
  map_public_ip_on_launch = true

  tags = {
    Name        = "grievance-public-subnet-${var.environment}"
    Environment = var.environment
  }
}

# Private Subnet for RDS
resource "aws_subnet" "private" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.2.0/24"
  availability_zone = "${var.aws_region}b"

  tags = {
    Name        = "grievance-private-subnet-${var.environment}"
    Environment = var.environment
  }
}

# Route Table for Public Subnet
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name        = "grievance-public-rt-${var.environment}"
    Environment = var.environment
  }
}

# Route Table Association
resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# Security Group for RDS
resource "aws_security_group" "rds" {
  name_prefix = "grievance-rds-${var.environment}"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [aws_vpc.main.cidr_block]
  }

  tags = {
    Name        = "grievance-rds-sg-${var.environment}"
    Environment = var.environment
  }
}

# Security Group for ECS
resource "aws_security_group" "ecs" {
  name_prefix = "grievance-ecs-${var.environment}"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [aws_vpc.main.cidr_block]
  }

  tags = {
    Name        = "grievance-ecs-sg-${var.environment}"
    Environment = var.environment
  }
}

# Subnet Group for RDS
resource "aws_db_subnet_group" "main" {
  name       = "grievance-db-subnet-group-${var.environment}"
  subnet_ids = [aws_subnet.private.id, aws_subnet.public.id]

  tags = {
    Name        = "grievance-db-subnet-group-${var.environment}"
    Environment = var.environment
  }
}

# RDS PostgreSQL Instance
resource "aws_db_instance" "postgres" {
  identifier = "grievance-postgres-${var.environment}"

  engine         = "postgres"
  engine_version = "15.13"
  instance_class = var.db_instance_class

  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_max_allocated_storage
  storage_type          = "gp2"
  storage_encrypted     = true

  db_name  = var.db_name
  username = var.db_username
  password = var.db_password

  vpc_security_group_ids = [aws_security_group.rds.id]
  db_subnet_group_name   = aws_db_subnet_group.main.name

  backup_retention_period = var.db_backup_retention_period
  backup_window          = "03:00-04:00"
  maintenance_window     = "sun:04:00-sun:05:00"

  skip_final_snapshot = true
  deletion_protection = false

  tags = {
    Name        = "grievance-postgres-${var.environment}"
    Environment = var.environment
  }
}

# ECS Cluster
resource "aws_ecs_cluster" "main" {
  name = "grievance-cluster-${var.environment}"

  tags = {
    Name        = "grievance-cluster-${var.environment}"
    Environment = var.environment
  }
}

# ECR Repository for ingestion
resource "aws_ecr_repository" "ingestion" {
  name = "grievance-ingestion-${var.environment}"
  
  image_tag_mutability = "IMMUTABLE"
  
  image_scanning_configuration {
    scan_on_push = true
    }

  force_delete = true
  tags = {
    Name        = "grievance-ingestion-${var.environment}"
    Environment = var.environment
  }
}

# S3 Bucket for Janasunani documents
resource "aws_s3_bucket" "documents" {
  bucket = "janasunani-documents-${var.environment}"

  tags = {
    Name        = "janasunani-documents-${var.environment}"
    Environment = var.environment
    Purpose     = "Document storage for grievance analytics"
  }
}

# S3 Bucket versioning
resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id
  versioning_configuration {
    status = "Enabled"
  }
}

# S3 Bucket server-side encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# S3 Bucket public access block
resource "aws_s3_bucket_public_access_block" "documents" {
  bucket = aws_s3_bucket.documents.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# S3 Bucket lifecycle configuration
resource "aws_s3_bucket_lifecycle_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id

  rule {
    id     = "document_retention"
    status = "Enabled"

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = 90
      storage_class = "GLACIER"
    }

    expiration {
      days = 2555  # 7 years retention
    }
  }
}

# ECS Task Definition
resource "aws_ecs_task_definition" "ingestion" {
  family                   = "grievance-ingestion-${var.environment}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.ecs_execution.arn

  container_definitions = jsonencode([
    {
      name  = "ingestion"
      image = "${aws_ecr_repository.ingestion.repository_url}:latest"

      environment = [
        {
          name  = "ENV"
          value = var.environment
        },
        {
          name  = "DB_URL"
          value = "postgresql://${var.db_username}:${var.db_password}@${aws_db_instance.postgres.endpoint}:5432/${var.db_name}"
        },
        {
          name  = "JANASUNANI_API_USERNAME"
          value = var.janasunani_api_username
        },
        {
          name  = "JANASUNANI_API_PASSWORD"
          value = var.janasunani_api_password
        },
        {
          name  = "JANASUNANI_API_BASE_URL"
          value = var.janasunani_api_base_url
        },
        {
          name  = "AWS_S3_DOCUMENTS"
          value = aws_s3_bucket.documents.bucket
        },
        {
          name  = "INGEST_COMPLAINTS"
          value = "true"
        },
        {
          name  = "INGEST_DOCUMENTS"
          value = "true"
        },
        {
          name  = "INGEST_ACTION_HISTORY"
          value = "true"
        },
        {
          name  = "FORCE_PARAMS"
          value = "false"
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.ingestion.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "ingestion"
        }
      }
    }
  ])

  tags = {
    Name        = "grievance-ingestion-task-${var.environment}"
    Environment = var.environment
  }
}

# IAM Role for ECS Execution
resource "aws_iam_role" "ecs_execution" {
  name = "grievance-ecs-execution-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

# IAM Policy for ECS Execution
resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Custom IAM Policy for S3 access
resource "aws_iam_role_policy" "ecs_s3_access" {
  name = "grievance-ecs-s3-access-${var.environment}"
  role = aws_iam_role.ecs_execution.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Sid    = "AllowListBucket"
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = aws_s3_bucket.documents.arn
      },
      {
        Sid    = "AllowObjectOperations"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject"
        ]
        Resource = "${aws_s3_bucket.documents.arn}/*"
      }
    ]
  })
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "ingestion" {
  name              = "/ecs/grievance-ingestion-${var.environment}"
  retention_in_days = 7

  tags = {
    Name        = "grievance-ingestion-logs-${var.environment}"
    Environment = var.environment
  }
}

# EventBridge Rule to run once a week
resource "aws_cloudwatch_event_rule" "weekly_ingestion" {
  name                = "grievance-weekly-ingestion-${var.environment}"
  description         = "Run ingestion task once a week"
  schedule_expression = "rate(7 days)"

  tags = {
    Name        = "grievance-weekly-ingestion-${var.environment}"
    Environment = var.environment
  }
}

# EventBridge Target
resource "aws_cloudwatch_event_target" "ingestion" {
  rule      = aws_cloudwatch_event_rule.weekly_ingestion.name
  target_id = "grievance-ingestion-target"
  arn       = aws_ecs_cluster.main.arn
  role_arn  = aws_iam_role.eventbridge.arn

  ecs_target {
    task_count          = 1
    task_definition_arn = aws_ecs_task_definition.ingestion.arn
    launch_type         = "FARGATE"
    platform_version    = "LATEST"

    network_configuration {
      subnets          = [aws_subnet.public.id]
      security_groups  = [aws_security_group.ecs.id]
      assign_public_ip = true
    }
  }
}

# IAM Role for EventBridge
resource "aws_iam_role" "eventbridge" {
  name = "grievance-eventbridge-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "events.amazonaws.com"
        }
      }
    ]
  })
}


# IAM Policy for EventBridge
resource "aws_iam_role_policy" "eventbridge" {
  name = "grievance-eventbridge-policy-${var.environment}"
  role = aws_iam_role.eventbridge.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecs:RunTask"
        ]
        Resource = [
          aws_ecs_task_definition.ingestion.arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "iam:PassRole"
        ]
        Resource = [
          aws_iam_role.ecs_execution.arn
        ]
      }
    ]
  })
} 