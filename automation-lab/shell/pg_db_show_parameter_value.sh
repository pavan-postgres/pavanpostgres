#!/bin/bash

# usage:
# pg_db_show_parameter_value.sh <parameter_name>

function display_current_configuration() {
    # Set the region
    region="ap-south-1"

    # Get the list of RDS hosts
    rds_hosts=$(aws rds describe-db-instances --query "DBInstances[?Engine=='postgres'].Endpoint.Address" --output table --region $region | grep -E 'uat-nonpci' | awk '{print $2}' | tail -n +4)

    # Initialize variables to store data
    data=()

    # Loop through the RDS hosts and list the databases
    for rds_host in $rds_hosts; do
        db_names=$(psql -h $rds_host -U master -p5433 -d postgres -Aqt -X -c "SELECT datname FROM pg_database WHERE datname NOT IN ('information_schema', 'template0', 'template1','postgres','admin','rdsadmin');")
        for db_name in $db_names; do
            log_duration_value=$(psql -v ON_ERROR_STOP=1 -U master -p 5433 -Aqt -X -h $rds_host -d $db_name -c "show $1")
            data+=("$rds_host | $db_name | $1 | $log_duration_value")
        done
    done

    # Display the data in a table format using column
    echo "$(date +%Y-%m-%d_%H:%M:%S):[info]:Current DB Configuration:"
    echo "InstanceName                                                                  | LogicalDBName                                 | ParameterName | ParameterValue"
    printf '%s\n' "${data[@]}" | column -t -s '|'
}

# Display the log_duration current setting across all DBs
display_current_configuration $1
