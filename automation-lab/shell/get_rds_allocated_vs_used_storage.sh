#!/bin/bash

# ==============================================================================
# Read Me !
# ==============================================================================

# description :
# script to get the list of RDS instance vs Logical Dbs which are configured with logical replication

# usage :
# git clone your repo
# cd database-engineering/dbe-tech/bash
# sh get_rds_allocated_vs_used_storage.sh

# documentation :
#

# debugging
# set -x

# ==============================================================================
# error exit
set -e

# Get all Postgres RDS instances
instances=$(aws rds describe-db-instances --query 'DBInstances[?Engine==`postgres`].[DBInstanceIdentifier,Endpoint.Address,Endpoint.Port,MasterUsername,AllocatedStorage]' --output text | grep -v 'uat')

# Header
echo "RDSInstance Identifier | AllocatedStorage(GB) | SizeCluster(ActualUsedinDB) "

# Iterate over each RDS instance
while IFS=$'\t' read -r instance_name endpoint port username allocatedstorage; do
    # Connect to the RDS instance's postgres database and retrieve replication slots information
    size_cluster=$(psql -h "$endpoint" -p "$port" -U "$username" -d postgres -Aqt -X <<-EOF
        SELECT pg_size_pretty(sum(pg_database_size(datname))) AS cluster_size FROM pg_database WHERE datname NOT IN ('information_schema', 'template0', 'template1', 'postgres', 'admin', 'rdsadmin');
EOF
)

    # Output instance name and replication slots information with Replication Role as Publisher
    if [ -n "$size_cluster" ]; then
        echo "$size_cluster" | while IFS=$'\n' read -r size_cluster_info; do
            echo "$instance_name | $allocatedstorage | $size_cluster_info"
        done
    fi
done <<< "$instances"
