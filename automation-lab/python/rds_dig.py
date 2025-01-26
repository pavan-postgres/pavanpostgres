import boto3
import subprocess

# Replace 'your_region' with the desired AWS region
region = 'ap-south-1'

# Create an RDS client
rds_client = boto3.client('rds', region_name=region)

# Fetch all RDS instances in the given region
response = rds_client.describe_db_instances()

# Print the table header
print("RDS Endpoint\t|\tdig output")

# Iterate through each RDS instance
for db_instance in response['DBInstances']:
    # Get the endpoint of the RDS instance
    rds_endpoint = db_instance['Endpoint']['Address']

    # Run the dig command and capture the output
    dig_output = subprocess.check_output(['dig', '+short', rds_endpoint], universal_newlines=True).strip()

    # Print the result in the table format
    print(f"{rds_endpoint}\t|\t{dig_output}")

