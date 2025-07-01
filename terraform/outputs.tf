output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "public_subnet_id" {
  description = "Public subnet ID"
  value       = aws_subnet.public.id
}

output "private_subnet_id" {
  description = "Private subnet ID"
  value       = aws_subnet.private.id
}

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint"
  value       = aws_db_instance.postgres.endpoint
}

output "rds_port" {
  description = "RDS PostgreSQL port"
  value       = aws_db_instance.postgres.port
}

output "rds_database_name" {
  description = "RDS database name"
  value       = aws_db_instance.postgres.db_name
}

output "ecs_cluster_name" {
  description = "Name of the ECS cluster"
  value       = aws_ecs_cluster.main.name
}

output "ecs_cluster_arn" {
  description = "ARN of the ECS cluster"
  value       = aws_ecs_cluster.main.arn
}

output "ingestion_ecr_repository_url" {
  description = "ECR repository URL for ingestion"
  value       = aws_ecr_repository.ingestion.repository_url
}

output "ingestion_task_definition_arn" {
  description = "ARN of the ingestion task definition"
  value       = aws_ecs_task_definition.ingestion.arn
}

output "eventbridge_rule_name" {
  description = "Name of the EventBridge rule"
  value       = aws_cloudwatch_event_rule.weekly_ingestion.name
}

output "cloudwatch_log_group_name" {
  description = "Name of the CloudWatch log group"
  value       = aws_cloudwatch_log_group.ingestion.name
} 