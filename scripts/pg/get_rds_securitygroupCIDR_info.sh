#!/bin/bash

# Get RDS instances and their associated security groups
rds_instances=$(aws rds describe-db-instances --query 'DBInstances[*].[DBInstanceIdentifier, VpcSecurityGroups[0].VpcSecurityGroupId]' --output json)

# Print the header for the table
echo "DBInstanceIdentifier | SecurityGroupId | FromPort | ToPort | IpRange"

# Loop through each RDS instance
for row in $(echo "${rds_instances}" | jq -r '.[] | @base64'); do
    _jq() {
        echo ${row} | base64 --decode | jq -r ${1}
    }

    db_instance_id=$(_jq '.[0]')
    security_group_id=$(_jq '.[1]')

    # Get inbound rules for the security group
    inbound_rules=$(aws ec2 describe-security-groups --group-ids ${security_group_id} --query 'SecurityGroups[].IpPermissions[]' --output json)

    # Print the RDS instance details along with inbound rules
    echo "$inbound_rules" | jq -r --arg db_instance_id "$db_instance_id" --arg security_group_id "$security_group_id" '.[] | "\($db_instance_id) | \($security_group_id) | \(.FromPort) | \(.ToPort) | \(.IpRanges[].CidrIp)"'
done

