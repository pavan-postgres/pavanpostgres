#!/bin/bash

# ==============================================================================
# Read Me !
# ==============================================================================

# description :
# script to insert the rows recursively between two dates from one table to another between 2 different rds / pg hosts

# benefits of this script
# 0.1. No performance degradation even for large tables
# 0.2. Retryable script from the point it halted / broken
# 0.3. Log traces available to know the progress reporting


# usage :
# git clone repo
# cd your-folder-location
# sh postgresql-recursive-batch-insert.sh

# documentation :
#

# debugging
# set -x

# ==============================================================================
# error exit
set -e

function recursiveBatchInsert() {

    PGOPTIONS='--client-min-messages=error' psql -v ON_ERROR_STOP=1 -U "${pgUser}" -h "${instance}" -p "${dbPort}" -d "$database" -X -Aqt <<EOF
        set role master_prod;
        SET statement_timeout to 0;
        insert into ledger_posting_v1 select * from ledger_posting_foreign where createdat >='$startDate' AND createdat < '$endDate';
EOF

    if [ $? -eq 0 ]; then
        #increment the start date
        startDate=$(date '+%Y-%m-%d' -d "$startDate + 1 day")
        #increment the end date = start date +1
        endDate=$(date '+%Y-%m-%d' -d "$startDate + 1 day")

        if [ "$(date -d $endDate +%s)" -ge "$(date -d $stopDate +%s)" ]; then
            echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [info      ] : Insert is success till $stopDate"
            exit 0

        elif [ "$(date -d $endDate +%s)" -le "$(date -d $stopDate +%s)" ]; then
            echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [log      ] : $endDate is not greater than $stopDate so continuing with recursive insert"
            recursiveBatchInsert
        fi

    else
        echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [log      ] : Insert failed for dates between start date $startDate and end date $endDate"
    fi
}

# ==============================================================================
# input variables
# ==============================================================================

instance="<rds-endpoint> / <pg-hostname>"
pgUser='dbuser'
dbPort='dbport'
database='dbname'                                   # default database to establish connection to the rds
startDate="2017-09-01"                              # get the start date
endDate=$(date '+%Y-%m-%d' -d "$startDate + 1 day") # get the end date (by incrementing 1 day to the start date)
stopDate="2018-09-01"                               # script execution will stop at stop date

# pgpassword input from STDIN
echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [notice   ] : enter password for database user $pgUser!!!"
read -r -s feedbackPgUserPass

if [ -z "${feedbackPgUserPass}" ]; then
    echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [error    ] : no password entered. quitting !"
    exit 0
else
    export PGPASSWORD="$feedbackPgUserPass"
fi

# call the function
recursiveBatchInsert

# end of script
