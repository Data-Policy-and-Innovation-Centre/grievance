# Development environment variables
aws_region = "ap-south-1"
environment = "dev"

# Database configuration
db_instance_class = "db.t3.micro"
db_allocated_storage = 20
db_max_allocated_storage = 100
db_backup_retention_period = 7

# You'll need to provide the database password when running terraform
# terraform apply -var-file="terraform.dev.tfvars" -var="db_password=your_secure_password" 