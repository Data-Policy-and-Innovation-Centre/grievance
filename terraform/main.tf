terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  
  backend "s3" {
    # Configure your backend here
    # bucket = "your-terraform-state-bucket"
    # key    = "grievance/terraform.tfstate"
    # region = "your-region"
  }
}

provider "aws" {
  region = var.aws_region
}

# S3 bucket for raw data
resource "aws_s3_bucket" "raw_data" {
  bucket = "grievance-raw-data-${var.environment}"

  tags = {
    Name        = "Grievance Raw Data"
    Environment = var.environment
  }
}

# S3 bucket versioning
resource "aws_s3_bucket_versioning" "raw_data_versioning" {
  bucket = aws_s3_bucket.raw_data.id
  versioning_configuration {
    status = "Enabled"
  }
}

# DynamoDB table
resource "aws_dynamodb_table" "grievance_data" {
  name           = "grievance-data-${var.environment}"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "id"

  attribute {
    name = "id"
    type = "S"
  }

  tags = {
    Name        = "Grievance Data"
    Environment = var.environment
  }
}

# Lambda function
resource "aws_lambda_function" "ingestion" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "grievance-ingestion-${var.environment}"
  role            = aws_iam_role.lambda_exec.arn
  handler         = "ingestion.orchestrator.lambda_handler"
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  runtime         = "python3.11"
  timeout         = 300
  memory_size     = 256

  environment {
    variables = {
      ENVIRONMENT = var.environment
    }
  }

  tags = {
    Name        = "Grievance Ingestion"
    Environment = var.environment
  }
}

# Lambda IAM role
resource "aws_iam_role" "lambda_exec" {
  name = "grievance-lambda-exec-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

# Lambda IAM policy
resource "aws_iam_role_policy" "lambda_policy" {
  name = "grievance-lambda-policy-${var.environment}"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject"
        ]
        Resource = "${aws_s3_bucket.raw_data.arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem"
        ]
        Resource = aws_dynamodb_table.grievance_data.arn
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

# EventBridge (CloudWatch Events) rule
resource "aws_cloudwatch_event_rule" "hourly" {
  name                = "grievance-ingestion-hourly-${var.environment}"
  description         = "Trigger grievance ingestion every hour"
  schedule_expression = "rate(1 hour)"
}

# EventBridge target
resource "aws_cloudwatch_event_target" "lambda" {
  rule      = aws_cloudwatch_event_rule.hourly.name
  target_id = "SendToLambda"
  arn       = aws_lambda_function.ingestion.arn
}

# Lambda permission for EventBridge
resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingestion.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.hourly.arn
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${aws_lambda_function.ingestion.function_name}"
  retention_in_days = 30
}

# Archive Lambda code
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../backend"
  output_path = "${path.module}/lambda.zip"
} 