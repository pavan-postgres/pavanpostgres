#!/bin/bash

# usage: sh postgresql-rds-modify-db-parameter-group.sh autovacuum_vacuum_cost_delay 2 immediate

# Set your AWS region
AWS_REGION="ap-south-1"
parameter_name=${1}
parameterval=${2}
apply_meth=${3}

# Function to display the current configuration of PostgreSQL RDS instances
function display_current_configuration() {
  # List all PostgreSQL RDS instances in the specified region
  RDS_INSTANCES=$(aws rds describe-db-instances --region $AWS_REGION   --query "DBInstances[?Engine=='postgres'].DBInstanceIdentifier" --output table | awk '{print $2}' | tail -n +4)

  if [ -z "$RDS_INSTANCES" ]; then
    echo "$(date +%Y-%m-%d_%H:%M:%S):[error]:No PostgreSQL RDS instances found in the region."
  else
    echo "$(date +%Y-%m-%d_%H:%M:%S):[info]:Current Configuration"
    echo "$(date +%Y-%m-%d_%H:%M:%S):[info]:Configuration Details:"
    echo "InstanceName | ParameterGroupName | ParameterName | ParameterValue"
    for INSTANCE in $RDS_INSTANCES; do
      PARAMETER_GROUP_NAME=$(aws rds describe-db-instances --region $AWS_REGION \
        --db-instance-identifier "$INSTANCE" \
        --query "DBInstances[0].DBParameterGroups[0].DBParameterGroupName" --output text)

      if [ -z "$PARAMETER_GROUP_NAME" ]; then
        PARAMETER_GROUP_NAME="Not found"
      fi

      get_param=$(aws rds describe-db-parameters --db-parameter-group-name "$PARAMETER_GROUP_NAME" --region $AWS_REGION \
        --query "Parameters[?ParameterName=='${parameter_name}'].[ParameterName,ParameterValue]" --output text)

      if [ -z "$get_param" ]; then
        get_param="Not found"
      fi

      echo "$INSTANCE | $PARAMETER_GROUP_NAME | $get_param"
    done
  fi
}

# Function to modify the parameter for a specific instance
function modify_db_parameter_group() {
  INSTANCE_NAME="$1"

  # Fetch the associated parameter group name
  PARAMETER_GROUP_NAME=$(aws rds describe-db-instances --region $AWS_REGION \
    --db-instance-identifier "$INSTANCE_NAME" \
    --query "DBInstances[0].DBParameterGroups[0].DBParameterGroupName" --output text )

  if [ -z "$PARAMETER_GROUP_NAME" ]; then
    PARAMETER_GROUP_NAME="Not found"
  else
    # Modify the parameter group to set parameter
    aws rds modify-db-parameter-group --db-parameter-group-name "$PARAMETER_GROUP_NAME" \
      --parameters "ParameterName=${parameter_name},ParameterValue=${parameterval},ApplyMethod=${apply_meth}" --region $AWS_REGION > /dev/null 2>&1

    echo "$(date +%Y-%m-%d_%H:%M:%S):[info]:Triggered modification for ${parameter_name} for RDS/$INSTANCE_NAME : $PARAMETER_GROUP_NAME"
  fi
}

# Display the current configuration
display_current_configuration

# Modify the parameter for each instance and display the result
echo "$(date +%Y-%m-%d_%H:%M:%S):[info]:Modifying ${parameter_name} parameter to ${parameterval}..."
RDS_INSTANCES=$(aws rds describe-db-instances --region $AWS_REGION   --query "DBInstances[?Engine=='postgres'].DBInstanceIdentifier" --output table | awk '{print $2}' | tail -n +4)

for INSTANCE in $RDS_INSTANCES; do
  modify_db_parameter_group "$INSTANCE"  "${parameter_name}" "${parameterval}" "${apply_meth}"
done

# Display the updated configuration
echo "$(date +%Y-%m-%d_%H:%M:%S):[info]:Updated Configuration(post change)"
display_current_configuration
