#!/bin/bash

# ==============================================================================
# Read Me !
# ==============================================================================

# description :
# script to get the RDS instance allocated storage, clustersize_fromDB, database and its size, fully qualified tablename(schemaname.tablename) and its sizes

# usage :
# git clone your repo
# cd database-engineering/dbe-tech/bash
# sh get_rds_allocated_storage_db_n_table_sizes.sh

# documentation :
#

# debugging
# set -x

# ==============================================================================
# error exit
set -e

# Retrieve RDS instances information from the specified region
instances=$(aws rds describe-db-instances --region ap-south-1 --query 'DBInstances[?Engine==`postgres`].[DBInstanceIdentifier,Endpoint.Address,Endpoint.Port,MasterUsername,AllocatedStorage]' --output text | grep -v 'uat')

# Header
echo "RDSInstance Identifier | AllocatedStorage(GB) | Size_Cluster | DB Name | DB Size | Table Name | Table Size"

# Iterate over each RDS instance
while IFS=$'\t' read -r instance_name endpoint port username allocatedstorage; do

    # Retrieve the size of the cluster from db
    size_cluster=$(psql -h "$endpoint" -p "$port" -U "$username" -d postgres -Aqt -X <<-EOF
        SELECT pg_size_pretty(sum(pg_database_size(d.datname))) AS cluster_size FROM pg_database d;
EOF
    )

    # Check if size_cluster contains results
    if [ -z "$size_cluster" ]; then
       echo "$instance_name | $allocatedstorage | - |No databases found | - | - | -"
        continue
    fi

    # Retrieve the list of databases and their sizes
    db_sizes=$(psql -h "$endpoint" -p "$port" -U "$username" -d postgres -Aqt -X <<-EOF
        SELECT
            d.datname AS db_name,
            pg_size_pretty(pg_database_size(d.datname)) AS db_size
        FROM pg_database d
        WHERE  datname NOT IN ('information_schema', 'template0', 'template1', 'postgres', 'admin', 'rdsadmin')
        ORDER BY pg_database_size(d.datname) DESC;
EOF
    )

    # Check if db_sizes contains results
    if [ -z "$db_sizes" ]; then
       echo "$instance_name | $allocatedstorage | $size_cluster | No databases found | - | - | -"
        continue
    fi
    # Iterate over each database size
    while IFS=$'|' read -r db_name db_size; do
        # Clean up unwanted characters and whitespace
        db_name=$(echo "$db_name" | xargs)
        db_size=$(echo "$db_size" | xargs)


        # Retrieve the list of tables and their sizes for each database
        table_sizes=$(psql -h "$endpoint" -p "$port" -U "$username" -d "$db_name" -Aqt -X <<-EOF
            SELECT n.nspname as "Schema",
                relname AS table_name,
                pg_size_pretty(pg_total_relation_size(c.oid)) AS table_size
            FROM pg_class c LEFT JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE relkind = 'r' and n.nspname not like 'pg_%' and n.nspname not like 'information_schema'
            ORDER BY pg_total_relation_size(c.oid) DESC;
EOF
        )

        # Check if table_sizes contains results
        if [ -z "$table_sizes" ]; then
            echo "$instance_name | $allocatedstorage | $size_cluster | $db_name | $db_size | No tables found | -"
            continue
        fi

        # Print database size and tables size
        while IFS=$'|' read -r schema_name table_name table_size; do
            # Handle missing values
	    schema_name=$(echo "$schema_name" | xargs)
            table_name=$(echo "$table_name" | xargs)
            table_size=$(echo "$table_size" | xargs)
            echo "$instance_name | $allocatedstorage | $size_cluster | $db_name | $db_size |$schema_name.$table_name | $table_size"
        done <<< "$table_sizes"

    done <<< "$db_sizes"
done <<< "$instances"
