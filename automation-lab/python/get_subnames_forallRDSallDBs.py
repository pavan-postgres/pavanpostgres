import boto3
import psycopg2

# Initialize AWS RDS client
rds_client = boto3.client('rds', region_name='ap-south-1')

# List of excluded database names
excluded_dbs = ['rdsadmin', 'postgres', 'template0', 'template1']

# Iterate over RDS instances
for instance in rds_client.describe_db_instances()['DBInstances']:
    instance_name = instance['DBInstanceIdentifier']

    # Check if the RDS instance is a PostgreSQL instance
    if instance['Engine'] == 'postgres':
        endpoint = instance['Endpoint']['Address']
        port = instance['Endpoint']['Port']
        username = instance['MasterUsername']  # Get the master username dynamically
        password = ''

        # Connect to the PostgreSQL RDS instance
        conn = psycopg2.connect(
            host=endpoint,
            port=port,
            user=username,
            password=password,
            database='postgres'  # Connect to the 'postgres' database
        )

        cursor = conn.cursor()

        # Get the list of databases
        cursor.execute("SELECT datname FROM pg_database;")
        databases = [row[0] for row in cursor.fetchall() if row[0] not in excluded_dbs]

        # Iterate over the databases
        for db_name in databases:
            cursor.execute(f"SELECT subname FROM pg_stat_subscription;")
            subscriptions = [row[0] for row in cursor.fetchall()]
            for subscription_name in subscriptions:
                print(f"{instance_name} | {db_name} | {subscription_name}")

        conn.close()
