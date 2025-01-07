#!/bin/bash

# ==============================================================================
# Read Me !
# ==============================================================================

# description :
# script to get the list of RDS instance vs Logical Dbs which are configured with logical replication

# usage :
# git clone your repo
# cd database-engineering/dbe-tech/bash
# sh get_rds_vs_dbs_with_logical_replication.sh

# documentation :
#

# debugging
# set -x

# ==============================================================================
# error exit
set -e

# Get all Postgres RDS instances
instances=$(aws rds describe-db-instances --query 'DBInstances[?Engine==`postgres`].[DBInstanceIdentifier,Endpoint.Address,Endpoint.Port,MasterUsername]' --output text | grep -v 'uat')

# Header
echo "RDSInstance Identifier | Replication Role | SlotName | Database"

# Iterate over each RDS instance
while IFS=$'\t' read -r instance_name endpoint port username; do
    # Connect to the RDS instance's postgres database and retrieve replication slots information
    rep_slots=$(psql -h "$endpoint" -p "$port" -U "$username" -d postgres -Aqt -X <<-EOF
        SELECT prs.slot_name,
            psa.datname
        FROM pg_stat_activity psa JOIN pg_replication_slots prs ON psa.pid = prs.active_pid;
EOF
)

    # Output instance name and replication slots information with Replication Role as Publisher
    if [ -n "$rep_slots" ]; then
        echo "$rep_slots" | while IFS=$'\n' read -r rep_slot_info; do
            echo "$instance_name | Publisher | $rep_slot_info"
        done
    fi
done <<< "$instances"


# Header for subscriptions
echo "RDSInstance Identifier | Replication Role | Subname | Database "

# Iterate over each RDS instance
while IFS=$'\t' read -r instance_name endpoint port username; do
    # Connect to the RDS instance's postgres database and retrieve subscriptions information
    subscriptions=$(psql -h "$endpoint" -p "$port" -U "$username" -d postgres -Aqt -X <<-EOF
    SELECT subname, datname FROM pg_subscription s JOIN pg_database d on s.subdbid = d.oid;
EOF
)

    # Output instance name and subscriptions information with Replication Role as Subscriber
    if [ -n "$subscriptions" ]; then
        echo "$subscriptions" | while IFS=$'\n' read -r subscription_info; do
            echo "$instance_name | Subscriber | $subscription_info"
        done
    fi
done <<< "$instances"
