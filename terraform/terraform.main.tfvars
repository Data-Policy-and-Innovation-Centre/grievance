# Main environment variables
aws_region = "ap-south-1"
environment = "main"

# Database configuration
db_instance_class = "db.t3.micro"
db_allocated_storage = 20
db_max_allocated_storage = 100
db_backup_retention_period = 30

# You'll need to provide the database password when running terraform
# terraform apply -var-file="terraform.main.tfvars" -var="db_password=your_secure_password" 