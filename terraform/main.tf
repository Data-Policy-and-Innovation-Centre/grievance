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
    cidr_blocks = ["0.0.0.0/0"]
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
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
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
  engine_version = "15.4"
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

  skip_final_snapshot = var.environment != "prod"
  deletion_protection = var.environment == "prod"

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

  tags = {
    Name        = "grievance-ingestion-${var.environment}"
    Environment = var.environment
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