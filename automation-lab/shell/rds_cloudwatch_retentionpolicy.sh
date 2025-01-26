#!/bin/bash

#==========================================================================================
# Author : Pavanteja ASSR (pavantejaa@zeta.tech)
# Description : script to enforce retention policy for rds log groups
# Usage
#==========================================================================================
# debug mode (disabled)
# set -x

# input parameters
export AWS_ACCESS_KEY_ID=""
export AWS_SECRET_ACCESS_KEY=""

# get the instance list

loggroups=$(aws logs describe-log-groups --query 'logGroups[*].[logGroupName]' --region ap-south-1  --output text | grep rds)


if [[ -z ${loggroups} ]];then
    echo "[error]: Incorrect result set check above aws query"
    exit 1
fi

for loggroup in ${loggroups};do
    echo "###############################################################"
    #Convert retention for all rds cloudwatch log-groups to 2 weeks
    aws logs put-retention-policy --log-group-name ${loggroup} --retention-in-days 14 --region ap-south-1
    echo "###############################################################"

done # end of instance loop

#end of script
