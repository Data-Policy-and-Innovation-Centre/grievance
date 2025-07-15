variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "ap-south-1"
}

variable "environment" {
  description = "Environment name (e.g., main)"
  type        = string
  default     = "main"
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

variable "db_allocated_storage" {
  description = "RDS allocated storage in GB"
  type        = number
  default     = 20
}

variable "db_max_allocated_storage" {
  description = "RDS maximum allocated storage in GB"
  type        = number
  default     = 100
}

variable "db_name" {
  description = "Database name"
  type        = string
  default     = "grievance_db"
}

variable "db_username" {
  description = "Database username"
  type        = string
  default     = "grievance_user"
}

variable "db_password" {
  description = "Database password"
  type        = string
  sensitive   = true
}

variable "db_backup_retention_period" {
  description = "RDS backup retention period in days"
  type        = number
  default     = 7
}

variable "janasunani_api_username" {
  description = "Janasunani API username"
  type        = string
  sensitive   = true
}

variable "janasunani_api_password" {
  description = "Janasunani API password"
  type        = string
  sensitive   = true
}

variable "janasunani_api_base_url" {
  description = "Janasunani API base URL"
  type        = string
  default     = "https://janasunani.odisha.gov.in/api/DataServices"
} 

variable "image_tag" {
  description = "Docker image tag to use for ECS deployment"
  type        = string
  default     = "v1.0.0"
}