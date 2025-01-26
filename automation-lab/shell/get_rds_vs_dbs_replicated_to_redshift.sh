#!/bin/bash

# ==============================================================================
# Read Me !
# ==============================================================================

# description :
# script to get the list of RDS instance vs Logical Dbs which are replicated to redshift

# usage :
# git clone your repo
# cd database-engineering/dbe-tech/bash
# sh get_rds_vs_dbs_replicated_to_redshift.sh

# documentation :
#

# debugging
# set -x

# ==============================================================================
# error exit
set -e

# Fetch RDS instances information
instances=$(aws rds describe-db-instances --query 'DBInstances[?Engine==`postgres`].[DBInstanceIdentifier,Endpoint.Address,Endpoint.Port,MasterUsername]' --output text | grep -v delta)

# Print header for output
echo 'RDSInstance Identifier | SlotName | Database | ClientIP | Publication(s) | Publicated Schema | Publicated Tables'

# Loop through each RDS instance
while IFS=$'\t' read -r instance_name endpoint port username; do
    # Fetch replication slots for the current RDS instance
    rep_slots=$(psql -h "$endpoint" -p "$port" -U "$username" -d postgres -Aqt -X <<-QUERY
        SELECT psa.datname || '|' || prs.slot_name
            FROM pg_stat_activity psa JOIN pg_replication_slots prs ON psa.pid = prs.active_pid and prs.slot_name like '%cdc%';
QUERY
)

    # Check if any replication slots were found
    if [ -n "$rep_slots" ]; then
        # Iterate over each row of replication slots
        while IFS=$'\n' read -r datname_slotname; do
            # Split datname and slotname
            datname=$(echo "$datname_slotname" | cut -d '|' -f 1)
            slotname=$(echo "$datname_slotname" | cut -d '|' -f 2)

            # Connect to the database indicated by datname
            # Execute the second query
            rep_slot_info=$(psql -h "$endpoint" -p "$port" -U "$username" -d "$datname" -Aqt -X <<-QUERY
                SELECT
                    '$instance_name',
                    '$slotname',
                    psa.datname,
                    psa.client_addr,
                    p.pubname AS publication_name,
                    n.nspname AS schema_name,
                    c.relname AS table_name
                FROM
                    pg_stat_activity psa
                JOIN
                    pg_replication_slots prs ON psa.pid = prs.active_pid
                JOIN
                    pg_publication p ON p.pubname = CASE
                                                        WHEN substring(psa.query FROM '"publication_names" ''([^'']+)''') IS NOT NULL
                                                            THEN substring(psa.query FROM '"publication_names" ''([^'']+)''')
                                                        WHEN substring(psa.query FROM 'publication_names ''"([^"]+)"''') IS NOT NULL
                                                            THEN substring(psa.query FROM 'publication_names ''"([^"]+)"''')
                                                    END
                JOIN
                    pg_publication_rel pr ON pr.prpubid = p.oid
                JOIN
                    pg_class c ON pr.prrelid = c.oid
                JOIN
                    pg_namespace n ON c.relnamespace = n.oid
                WHERE
                    prs.slot_name = '$slotname'
                ORDER BY
                    schema_name, table_name;
QUERY
)
            # Output instance name and subscriptions if there are any
            if [ -n "$rep_slot_info" ]; then
                echo "$rep_slot_info"
            fi
        done <<< "$rep_slots"
    fi
done <<< "$instances"

