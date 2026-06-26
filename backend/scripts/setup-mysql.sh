#!/bin/bash

# MySQL Setup Script for Grievance DB
# This script sets up the MySQL server with the dump file and creates the required user

set -e  # Exit on any error

# Paths
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
ROOT_DIR=$(dirname $SCRIPT_DIR)

# Configuration
MYSQL_ROOT_PASSWORD="dpic@123"
MYSQL_HOST="127.0.0.1"
MYSQL_PORT="3306"
DATABASE_NAME="myapp_db"
DUMP_FILE="$ROOT_DIR/data/raw/Dump20250730.sql"
MYSQL_USER="myapp"
MYSQL_PASSWORD="dpic"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Starting MySQL setup for Grievance Analytics...${NC}"

# Check if MySQL is running: Use mysqld --bind-address=127.0.0.1
if ! mysqladmin ping -h"$MYSQL_HOST" -P"$MYSQL_PORT" --silent; then
    echo -e "${RED}❌ MySQL server is not running on $MYSQL_HOST:$MYSQL_PORT${NC}"
    echo "Please start MySQL server first and try again."
    exit 1
fi

# Check if dump file exists
if [ ! -f "$DUMP_FILE" ]; then
    echo -e "${RED}❌ Dump file not found: $DUMP_FILE${NC}"
    exit 1
fi

echo -e "${GREEN}✅ MySQL server is running${NC}"
echo -e "${GREEN}✅ Dump file found: $DUMP_FILE${NC}"

# Function to execute MySQL commands
execute_mysql() {
    local sql_commands="$1"
    if [ -z "$MYSQL_ROOT_PASSWORD" ]; then
        mysql -uroot -p -h"$MYSQL_HOST" -P"$MYSQL_PORT" -e "$sql_commands"
    else
        mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -h"$MYSQL_HOST" -P"$MYSQL_PORT" -e "$sql_commands"
    fi
}

# Function to execute MySQL commands with file input
execute_mysql_file() {
    local sql_file="$1"
    if [ -z "$MYSQL_ROOT_PASSWORD" ]; then
        mysql -uroot -p -h"$MYSQL_HOST" -P"$MYSQL_PORT" "$DATABASE_NAME" < "$sql_file"
    else
        mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -h"$MYSQL_HOST" -P"$MYSQL_PORT" "$DATABASE_NAME" < "$sql_file"
    fi
}

echo -e "${YELLOW}📋 Setting up database and user...${NC}"

# Create database and user
SQL_COMMANDS="
DROP DATABASE IF EXISTS \`$DATABASE_NAME\`;
CREATE DATABASE \`$DATABASE_NAME\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '$MYSQL_USER'@'localhost' IDENTIFIED BY '$MYSQL_PASSWORD';
CREATE USER IF NOT EXISTS '$MYSQL_USER'@'%' IDENTIFIED BY '$MYSQL_PASSWORD';
GRANT ALL PRIVILEGES ON \`$DATABASE_NAME\`.* TO '$MYSQL_USER'@'localhost';
GRANT ALL PRIVILEGES ON \`$DATABASE_NAME\`.* TO '$MYSQL_USER'@'%';
FLUSH PRIVILEGES;
"

execute_mysql "$SQL_COMMANDS"

echo -e "${GREEN}✅ Database '$DATABASE_NAME' created successfully${NC}"
echo -e "${GREEN}✅ User '$MYSQL_USER' created with password '$MYSQL_PASSWORD'${NC}"

echo -e "${YELLOW}📥 Importing dump file (this may take a while)...${NC}"

# Import the dump file
start_time=$(date +%s)
execute_mysql_file "$DUMP_FILE"
end_time=$(date +%s)

duration=$((end_time - start_time))
echo -e "${GREEN}✅ Dump file imported successfully in ${duration} seconds${NC}"

# Verify the import
echo -e "${YELLOW}🔍 Verifying import...${NC}"
TABLE_COUNT=$(execute_mysql "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = '$DATABASE_NAME';" | tail -n 1)
echo -e "${GREEN}✅ Found $TABLE_COUNT tables in database${NC}"

# Show tables
echo -e "${YELLOW}�� Tables in database:${NC}"
execute_mysql "USE \`$DATABASE_NAME\`; SHOW TABLES;"

echo -e "${GREEN}🎉 MySQL setup completed successfully!${NC}"
echo -e "${GREEN}📝 You can now run the migration script with:${NC}"
echo -e "${YELLOW}   python backend/app/db/migration_from_mysql.py${NC}"
echo ""
echo -e "${GREEN}�� Connection details:${NC}"
echo -e "   Host: $MYSQL_HOST"
echo -e "   Port: $MYSQL_PORT"
echo -e "   Database: $DATABASE_NAME"
echo -e "   User: $MYSQL_USER"
echo -e "   Password: $MYSQL_PASSWORD"
