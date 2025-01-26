#!/bin/bash
#Instance Name vs DB Name Vs Total DB count in each RDS instance Vs Total DB count in all RDS instances Script 
# Set the AWS region
region="ap-south-1"

# Initialize a variable to store the total database count
total_db_count=0

# Get the list of PostgreSQL RDS instances
rds_instances=$(aws rds describe-db-instances --query "DBInstances[?Engine=='postgres'].DBInstanceIdentifier" --output text --region ap-south-1 | tr '\t' '\n' | grep 'uat-nonpci' | grep -v 'uat-pci')

# Loop through the RDS instances
for instance_name in $rds_instances; do
  echo "Instance: $instance_name"
  db_count=0

  # Connect to the PostgreSQL RDS instance and count databases
  db_names=$(psql -h $instance_name.<>.ap-south-1.rds.amazonaws.com -U master -p 5433 -d postgres -Aqt -X  -c "SELECT datname FROM pg_database WHERE datname NOT IN ('information_schema', 'template0', 'template1', 'postgres', 'admin', 'rdsadmin');")

  for db_name in $db_names; do
    echo "  Database: $db_name"
    ((db_count++))
    ((total_db_count++))
  done

  echo "  Total Databases for $instance_name: $db_count"
  echo
done

echo "Total Databases across all instances: $total_db_count"
