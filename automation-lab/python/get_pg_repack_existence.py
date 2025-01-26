import boto3
import psycopg2

# Initialize AWS RDS client
rds_client = boto3.client('rds', region_name='ap-south-1')

# Function to check if pg_repack extension is present in the specified database
def is_pg_repack_installed(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'pg_repack';")
    return cursor.fetchone() is not None

# Length of the adjusted instance name string
instance_name_length = len("aws-aps1-non-white-stageeeeee-commons-01-pg")

# Print header
print(f"{'RDS instance name':<{instance_name_length}} | {'DB name':<50} | pg_repack installed")

# Iterate over RDS instances
for instance in rds_client.describe_db_instances()['DBInstances']:
    instance_name = instance['DBInstanceIdentifier']

    # Check if the instance is a PostgreSQL instance and matches the desired pattern for non-pcidss-preprod-commons instances
    if instance['Engine'] == 'postgres' and 'uat-nonpci' in instance_name:
        endpoint = instance['Endpoint']['Address']
        port = instance['Endpoint']['Port']
        username = instance['MasterUsername']  # Get the master username dynamically
        password = ''  # Update with the actual master password

        try:
            # Connect to the PostgreSQL RDS instance
            conn = psycopg2.connect(
                host=endpoint,
                port=port,
                user=username,
                password=password,
                database='postgres'  # Connect to the 'postgres' database
            )

            cursor = conn.cursor()

            # Get the list of databases in the RDS instance
            cursor.execute("SELECT datname FROM pg_database WHERE datistemplate = false and datname not in ('rdsadmin','template0','template1');")
            databases = [row[0] for row in cursor.fetchall()]

            # Check if pg_repack extension is present for each database
            for db in databases:
                try:
                    # Connect to the individual database
                    conn_db = psycopg2.connect(
                        host=endpoint,
                        port=port,
                        user=username,
                        password=password,
                        database=db
                    )
                    
                    # Check if pg_repack extension is installed in the current database
                    pg_repack_installed = is_pg_repack_installed(conn_db)
                    print(f"{instance_name:<{instance_name_length}} | {db:<50} | {'yes' if pg_repack_installed else 'no'}")
                    
                except psycopg2.Error as e:
                    print(f"Error connecting to the '{db}' database: {e}")

        except psycopg2.Error as e:
            print(f"Error connecting to the '{instance_name}' instance: {e}")

