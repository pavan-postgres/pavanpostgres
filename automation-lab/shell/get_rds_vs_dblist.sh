#!/bin/bash

# ==============================================================================
# Read Me !
# ==============================================================================

# description :
# script to get the list of RDS instance vs Logical Dbs present in it for a zone

# usage :
# git clone your repo
# cd database-engineering/dbe-tech/bash
# sh get_rds_vs_dblist.sh

# documentation :
#

# debugging
# set -x

# ==============================================================================
# error exit
set -e


# Get RDS hosts with DBInstanceClass
rds_hosts=$(aws rds describe-db-instances --query "DBInstances[?Engine=='postgres'].Endpoint.Address" --output text --region ap-south-1 | tr '\t' '\n' | grep -v 'uat' | grep 'non-uat')

# Header
echo "RDS Endpoint | Logical DBName"

# Loop through the RDS hosts and list the databases
for rds_host in $rds_hosts; do
  user=$(aws rds describe-db-instances --query "DBInstances[?Endpoint.Address=='$rds_host'].MasterUsername" --output text --region ap-south-1)
  db_names=$(psql -h $rds_host -U $user -p 5432 -d postgres -Aqt -X -c "SELECT datname FROM pg_database WHERE datname NOT IN ('information_schema', 'template0', 'template1', 'postgres', 'admin', 'rdsadmin');" -tA)

  # Print RDS host, DBInstanceClass, and corresponding DB names
  for db_name in $db_names; do
    echo "$rds_host  | $db_name"
  done
done
