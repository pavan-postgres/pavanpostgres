import boto3
import psycopg2
# import pandas as pd



# Initialize AWS RDS client
rds_client = boto3.client('rds', region_name='ap-south-1')

cloudwatch_client = boto3.client('cloudwatch', region_name='ap-south-1')  # Replace 'us-east-1' with your desired region


# List of excluded database names
excluded_dbs = ['rdsadmin', 'postgres', 'template0', 'template1']


# Create an empty DataFrame
# df = pd.DataFrame(columns=["RDS","allocated_storage","used_storage","db_name", "db_size"])

# Iterate over RDS instances
for instance in rds_client.describe_db_instances()['DBInstances']:
    instance_name = instance['DBInstanceIdentifier']

    
    # Check if the RDS instance is a PostgreSQL instance
    if instance['Engine'] == 'postgres':
        endpoint = instance['Endpoint']['Address']
        allocated_storage = instance['AllocatedStorage']
        port = instance['Endpoint']['Port']
        username = instance['MasterUsername']  # Get the master username dynamically
        password = 'xxxxxx'
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

            cursor.execute("SELECT pg_size_pretty(sum(pg_database_size(d.datname))) AS cluster_size FROM pg_database d;")

            used_storage = cursor.fetchall()[0][0]

            cursor.execute(" SELECT   d.datname AS db_name,   pg_size_pretty(pg_database_size(d.datname)) AS db_size  FROM   pg_database d  WHERE   pg_database_size(d.datname) > 10737418240   ORDER BY   pg_database_size(d.datname) DESC;")

            databases = [(row[0],row[1]) for row in cursor.fetchall()]

            if(len(databases)) == 0:
                print(endpoint,allocated_storage,used_storage)
            
            for db_name , db_size in databases:
                # temp_df = pd.DataFrame({'RDS':[endpoint],'allocated_storage':[str(allocated_storage)+"GB"],'used_storage':[used_storage],'db_name': [db_name], 'db_size': [db_size]}) 
                # print(temp_df)
                # df = df._append(temp_df,ignore_index = True) 
                print(endpoint,allocated_storage,used_storage,db_name,db_size)

        except Exception as e:
            print(e)
            break
        conn.close()
