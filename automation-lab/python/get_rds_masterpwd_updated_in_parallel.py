import boto3

# AWS region where your RDS instances are located
region = 'ap-south-1'

# New master user password
new_password = ''

# Initialize AWS RDS client
rds_client = boto3.client('rds', region_name=region)

# List all RDS instances in the specified region
rds_instances = rds_client.describe_db_instances()

# Iterate through the instances and update the master password
for instance in rds_instances['DBInstances']:
    if instance['Engine'] == 'postgres':
        instance_identifier = instance['DBInstanceIdentifier']

        # Update the master user password for the PostgreSQL RDS instance
        rds_client.modify_db_instance(
            DBInstanceIdentifier=instance_identifier,
            MasterUserPassword=new_password,
            ApplyImmediately=True
        )

        print(f"Updated password for RDS instance {instance_identifier}")

print("Password update complete for all PostgreSQL RDS instances.")

