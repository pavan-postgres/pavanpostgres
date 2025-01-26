"""
Module with helper functions for RDS, PostgreSQL
"""

# import the required packages for the script
import time
import yaml
import argparse
import os
import datetime
import psycopg2
import concurrent.futures
import json5 as json
from colorama import init, Fore, Style
import logging
import socket

# Initialize colorama
init()

# Define color for log messages
COLOR_SUCCESS = Fore.GREEN
COLOR_WARNING = Fore.YELLOW
COLOR_RESOURCE = Fore.MAGENTA
COLOR_ERROR = Fore.RED
COLOR_RESET = Style.RESET_ALL

# Function to generate log entry
def generate_log(log_level, log_resource, log_message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    if log_level == 'INFO':
        print(f"{timestamp}:{COLOR_SUCCESS}{log_level}{COLOR_RESET}:{COLOR_RESOURCE}{log_resource}{COLOR_RESET}:{log_message}")
    elif log_level == 'NOTICE' or log_level == 'WARNING' :
        print(f"{timestamp}:{COLOR_WARNING}{log_level}{COLOR_RESET}:{log_resource}:{log_message}")
    else:
        print(f"{timestamp}:{COLOR_ERROR}{log_level}{COLOR_RESET}:{log_resource}:{log_message}")

# Function to load configuration
def load_configuration():
    # Parse the command-line arguments
    parser = argparse.ArgumentParser(description="Upgrade RDS instances using a config file.")
    parser.add_argument("--config_file","-c", help="Path to the configuration yaml file")
    args = parser.parse_args()

    # Check if the input configuration file has .yaml or .yml extension
    if not args.config_file.lower().endswith(('.yaml', '.yml')):
        generate_log('ERROR', args.config_file, 'The input file must have a .yaml or .yml extension')
        exit(1)

    # Ensure that the input file exists
    if not os.path.exists(args.config_file):
        generate_log('ERROR', args.config_file, f"The input file '{args.config_file}' does not exist")
        logging.error(f"The input file '{args.config_file}' does not exist")
        exit(1)

    # Load configuration from the specified config.yaml file
    config_file_path = args.config_file
    with open(config_file_path, "r") as config_file:
        config = yaml.safe_load(config_file)
    return config

# Function to validate the rds identifier
def validate_configuration(config):
    required_keys = ["region_name", "db_instance_identifiers", "new_engine_version",
        "new_template_db_parameter_group_name", "parameter_group_backup_path"]
    for key in required_keys:
        if key not in config:
            generate_log('ERROR', config, f"Missing required key in configuration yaml file: '{key}' ")
            exit(1)
        if not config[key]:
            generate_log('ERROR',config, f"Value for key '{key}' is empty in configuration yaml file")
            exit(1)

# Function to validate the instance identifier mentioned in the inputs
def validate_instance_identifier(db_instance_identifier, client):
    try:
        response = client.describe_db_instances(DBInstanceIdentifier=db_instance_identifier)
        # return response['DBInstances'][0]['DBInstanceIdentifier']
        generate_log('INFO', db_instance_identifier, 'instance exists')
    except Exception as e:
        generate_log('ERROR', db_instance_identifier, str(e))
        exit(1)

# Function to get the current RDS instance status
def get_db_instance_status(db_instance_identifier, client):
    try:
        response = client.describe_db_instances(DBInstanceIdentifier=db_instance_identifier)
        return response['DBInstances'][0]['DBInstanceStatus']
    except Exception as e:
        generate_log('ERROR', db_instance_identifier, str(e))
        exit(1)

def track_db_instance_status(db_instance_identifier, client, timeout=300):

    wait_sec = 20
    counter = 1

    # run the while loop until the instance in available status
    while get_db_instance_status(db_instance_identifier, client) != 'available':
        if counter*wait_sec > timeout:
            raise TimeoutError(f'instance in {get_db_instance_status(db_instance_identifier, client)} status for more than {timeout} seconds')
            break
        else:
            generate_log('INFO', db_instance_identifier, f'instance in {get_db_instance_status(db_instance_identifier, client)} status (poll:{counter})')
            counter += 1
        time.sleep(wait_sec)  # Wait for 5 seconds before checking again

    if get_db_instance_status(db_instance_identifier, client) == 'available':
        generate_log('INFO', db_instance_identifier, 'instance in available status')
        return

# Function to track the modified instances status
def track_db_instances_status(db_instance_identifiers, client):

    # prepare a set
    modified_instances = set(db_instance_identifiers)

    # Check status continuously until all instances are "available"
    while modified_instances:
        for db_instance_identifier in list(modified_instances):
            status = get_db_instance_status(db_instance_identifier, client)
            if status == "available":
                generate_log('INFO', db_instance_identifier, f'tracking status={status}')
                modified_instances.discard(db_instance_identifier)
            else:
                generate_log('INFO', db_instance_identifier, f'tracking status={status}')

        if not modified_instances:
            break

        time.sleep(20)  # Wait for 5 seconds before checking again

# Function to get db instance details like endpoint,port,masteruser etc
def get_db_instance_details(db_instance_identifier, client):
    try:
        response = client.describe_db_instances(DBInstanceIdentifier=db_instance_identifier)
        if response:
            return response['DBInstances'][0]
    except Exception as e:
        generate_log('ERROR', db_instance_identifier, str(e))
        exit(1)

# Function to get the engine version of the RDS instance
def get_engine_version(db_instance_identifier, client):
    try:
        response = client.describe_db_instances(DBInstanceIdentifier=db_instance_identifier)
        if response:
            engine_version = response['DBInstances'][0]['EngineVersion']
            return engine_version
    except Exception as e:
        generate_log('ERROR', db_instance_identifier, str(e))
        exit(1)


# Function to get the current RDS instance Parameter Group
def get_instance_parameter_group(db_instance_identifier, client):
    try:
        response = client.describe_db_instances(DBInstanceIdentifier=db_instance_identifier)
        db_parameter_group_name = response['DBInstances'][0]['DBParameterGroups'][0]['DBParameterGroupName']
        return db_parameter_group_name
    except Exception as e:
        generate_log('ERROR', db_instance_identifier, str(e))
        exit(1)

# Function to get the modifed parameter and their values
def get_modified_parameters(db_parameter_group_name, client):
    response = client.describe_db_parameters(
        DBParameterGroupName=db_parameter_group_name,
        Source='user'
    )

    modified_parameters = []
    for parameter in response['Parameters']:
        modified_parameters.append(parameter)
    return modified_parameters

# Function to backup modified parameters
def backup_db_parameter_group(db_instance_identifier, db_parameter_group_name, client, config):

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M")

    try:

        # get the list of modified parameters
        modified_parameters = get_modified_parameters(db_parameter_group_name, client)

        parameter_group_backup_path = config['parameter_group_backup_path']

        # write the modified parameters with value to a file
        parameter_group_list = {"Parameters":[]}
        file_name = f'{parameter_group_backup_path}/{db_instance_identifier}.backup.{timestamp}.json'

        for parameter in modified_parameters:

            parameter_group_dict = {
                str("ParameterName"): parameter['ParameterName'],
                "ParameterValue": parameter['ParameterValue']
            }

            parameter_group_list["Parameters"].append(parameter_group_dict)

        with open(file_name,"w") as json_file:
            json.dump(parameter_group_list, json_file, indent=4)

        generate_log('INFO', f'{db_instance_identifier}[{db_parameter_group_name}]', f'{file_name} modified prameters backup file created')
    except Exception as e:
        generate_log('ERROR', f'{db_instance_identifier}[{db_parameter_group_name}]', str(e))
        exit(1)

# Function to create a new parameter group
def create_db_parameter_group(parameter_group_name, parameter_group_family, parameter_group_description, client):
    try:
        response = client.create_db_parameter_group(
            DBParameterGroupName=parameter_group_name,
            DBParameterGroupFamily=parameter_group_family,
            Description=parameter_group_description
        )
        generate_log('INFO', parameter_group_name, 'parameter group created')

    except Exception as e:
        generate_log('ERROR', parameter_group_name, str(e))

# Function to modify parameters in the parameter group
def modify_db_parameter_group(parameter_group_name, parameter_name, parameter_value, apply_method, client):
    try:
        response = client.modify_db_parameter_group(
            DBParameterGroupName=parameter_group_name,
            Parameters=[
                {
                    'ParameterName': parameter_name,
                    'ParameterValue': parameter_value,
                    'ApplyMethod': apply_method
                }
            ]
        )
        generate_log('INFO', parameter_group_name, f"parameter group modified ({parameter_name}={parameter_value})")
    except Exception as e:
        generate_log('ERROR', parameter_group_name, str(e))

# Function to copy parameter group
def copy_db_parameter_group(source_db_parameter_group_identifier, target_db_parameter_group_identifier, target_db_parameter_group_description, client):
    try:
        response = client.copy_db_parameter_group(
            SourceDBParameterGroupIdentifier=source_db_parameter_group_identifier,
            TargetDBParameterGroupIdentifier=target_db_parameter_group_identifier,
            TargetDBParameterGroupDescription=target_db_parameter_group_description
        )
        generate_log('INFO', target_db_parameter_group_identifier, 'parameter group created')
    except Exception as e:
        generate_log('ERROR', target_db_parameter_group_identifier, str(e))

# Function to delete parameter group
def delete_db_parameter_group(db_parameter_group_name, client):
    try:
        response = client.delete_db_parameter_group(
            DBParameterGroupName=db_parameter_group_name
        )
        generate_log('INFO', db_parameter_group_name, 'parameter group deleted')
    except Exception as e:
        generate_log('ERROR', db_parameter_group_name, str(e))

# Function for minor version upgrade of RDS instance
def minor_version_upgrade_rds_instance(config, db_instance_identifier, client, timeout=1800):

    try:
        # track the instance status
        track_db_instance_status(db_instance_identifier, client, timeout)

        # Check the current status of the RDS instance
        current_status = get_db_instance_status(db_instance_identifier, client)

        # Perform the upgrade if the instance is available
        if current_status == 'available':
            # trigger the modification
            response = client.modify_db_instance(
                DBInstanceIdentifier=db_instance_identifier,
                EngineVersion=config['new_engine_version'],
                AllowMajorVersionUpgrade=False,
                ApplyImmediately=True
            )
        generate_log('INFO', db_instance_identifier, 'minor version upgrade api triggered')
    except Exception as e:
        generate_log('ERROR', db_instance_identifier, str(e))
        exit(0)

    time.sleep(20) # there is a delay in changing the status after triggering the api

# Function for major version upgrade of RDS instance
def major_version_upgrade_rds_instance(config, db_instance_identifier, client, timeout=300):
    try:
        # Check the current status of the RDS instance
        current_status = get_db_instance_status(db_instance_identifier, client)

        # Perform the upgrade if the instance is available
        if current_status == 'available':
            # get the parameter group associated with this rds
            db_instance_info = client.describe_db_instances(DBInstanceIdentifier=db_instance_identifier)
            db_parameter_group_name = db_instance_info['DBInstances'][0]['DBParameterGroups'][0]['DBParameterGroupName']
            parameters_info = client.describe_db_parameters(DBParameterGroupName=db_parameter_group_name,Source="user")
            db_instance_parameters = parameters_info['Parameters']
            db_instance_custom_params = []

            for each_param in db_instance_parameters:
                db_instance_custom_params.append(
                    {
                        "ParameterName" : each_param["ParameterName"],
                        "ParameterValue" : each_param["ParameterValue"],
                        "ApplyMethod" : each_param["ApplyMethod"],
                    }
                )
            # Extract first two digits of the new engine version
            version_prefix = config['new_engine_version'].split('.')[0]

            # Create a new parameter group based on the template group
            new_parameter_group_name = f"{db_instance_identifier}-pg-{version_prefix}"
            try:
                existing_parameter_groups = client.describe_db_parameter_groups(
                DBParameterGroupName=new_parameter_group_name
                )
                generate_log('INFO', db_instance_identifier,
                             f"""parameter group '{new_parameter_group_name}' already exists, skipping creation.""")
            except Exception as e:
                # If the parameter group doesn't exist, create it
                client.create_db_parameter_group(
                        DBParameterGroupName=new_parameter_group_name,
                        DBParameterGroupFamily=f'postgres{version_prefix}',
                        Description='Parameter group for new engine version'
                    )
                client.modify_db_parameter_group(
                        DBParameterGroupName=new_parameter_group_name,
                        Parameters=db_instance_custom_params
                    )
                generate_log('INFO', db_instance_identifier,
                             f"""parameter group '{new_parameter_group_name}' created """)

            # Trigger the modification to use the new parameter group
            response = client.modify_db_instance(
                DBInstanceIdentifier=db_instance_identifier,
                EngineVersion=config['new_engine_version'],
                DBParameterGroupName=new_parameter_group_name,
                AllowMajorVersionUpgrade=True,
                ApplyImmediately=True
            )
            generate_log('INFO', db_instance_identifier, 'major version upgrade API triggered')
    except Exception as e:
        generate_log('ERROR', db_instance_identifier, str(e))
        exit(0)

    # There is a delay in changing the status after triggering the API
    while get_db_instance_status(db_instance_identifier, client) == 'available':
        time.sleep(5)



# Function to reboot the RDS instance
def reboot_db_intance(db_instance_identifier, client, timeout=1800):

    try:
        # Check the current status of the RDS instance
        current_status = get_db_instance_status(db_instance_identifier, client)

        # Perform the upgrade if the instance is available
        if current_status == 'available':
            # trigger the reboot
            response = client.reboot_db_instance(
                DBInstanceIdentifier=db_instance_identifier,
            )
    except Exception as e:
        generate_log('ERROR', db_instance_identifier, str(e))

    generate_log('INFO', db_instance_identifier, 'reboot_db_instance api triggered')

    # there is a delay in changing the status after triggering the api
    while get_db_instance_status(db_instance_identifier, client) == 'available':
        time.sleep(5)

# Function to reboot the RDS instance
def stop_db_intance(db_instance_identifier, client, timeout=1800):

    try:
        # Check the current status of the RDS instance
        current_status = get_db_instance_status(db_instance_identifier, client)

        # Perform the upgrade if the instance is available
        if current_status == 'available':
            # trigger the reboot
            response = client.stop_db_instance(
                DBInstanceIdentifier=db_instance_identifier,
            )

        generate_log('INFO', db_instance_identifier, 'stop_db_instance api triggered')
    except Exception as e:
        generate_log('ERROR', db_instance_identifier, str(e))

    # there is a delay in changing the status after triggering the api
    while get_db_instance_status(db_instance_identifier, client) == 'available':
        time.sleep(5)

# Function to create db snapshot
def create_db_snapshot(db_instance_identifier, client, timeout=300):

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M")

    try:
        track_db_instance_status(db_instance_identifier, client, timeout)

        response = client.create_db_snapshot(
            DBSnapshotIdentifier=f'{db_instance_identifier}-{timestamp}',
            DBInstanceIdentifier=db_instance_identifier
        )
    except Exception as e:
        generate_log('ERROR', db_instance_identifier, str(e))
        exit(1)

    generate_log('INFO', db_instance_identifier, 'manual snapshot api triggered')

    time.sleep(10) # there is a delay in changing the status after triggering the api

# Function to open connection to the database
def db_connection_string(db_instance_identifier,client):

    # get db instance details
    db_instance_details = get_db_instance_details(db_instance_identifier,client)
    user = db_instance_details['MasterUsername']
    password = config['database_password']
    host = db_instance_details['Endpoint']['Address']
    port = db_instance_details['Endpoint']['Port']
    sslmode = 'require'
    dbname = 'postgres'

    connection_string = f'dbname={dbname}, user={user}, password={password}, host={host}, port={port}, sslmode={sslmode}'

    # connection_string = f"postgresql://{db_instance_details['MasterUsername']}:config['database_password']@{db_instance_details['Endpoint']['Address']}:{db_instance_details['Endpoint']['Port']}/postgres"
    return psycopg2.connect(connection_string)

# Function to connect to the postgresql database
def connect_to_postgresql(db_instance_identifier, dbname, user, password, host, port=5432):
    try:
        connection = psycopg2.connect(
            dbname=dbname,
            user=user,
            password=password,
            host=host,
            port=port,
            sslmode = 'require',
            options="-c statement_timeout=0"
        )
        return connection
    except psycopg2.Error as e:
        generate_log('ERROR', db_instance_identifier, f'Error connecting to PostgreSQL: {e}')
    return None

# Function to terminate connections in the postgresql
def execute_db_query(db_instance_identifier, connection, query):
    if connection is None:
        return

    cursor = connection.cursor()

    try:
        cursor.execute(query)
        results=cursor.fetchall()
        #generate_log('INFO', db_instance_identifier,  f'query=[{query}] executed')
        return results
    except psycopg2.Error as e:
        generate_log('ERROR', db_instance_identifier, str(e))
        exit(0)
    finally:
        cursor.close()
        connection.commit()

# Function to execute queries in the connected database
def execute_db_queries(db_instance_identifier, connection, queries):
    if connection is None:
        return

    cursor = connection.cursor()

    try:
        for query in queries:
            cursor.execute(query)
            #generate_log('INFO', db_instance_identifier, f"query:[{query}]")
            cursor.close()
            connection.commit()
    except psycopg2.Error as e:
        generate_log('ERROR', db_instance_identifier, str(e))
    finally:
        # commit and close the connection.
        connection.close()

# Function to execute the query with no result
def execute_db_query_with_no_results(db_instance_identifier, connection, query):
    if connection is None:
        return

    cursor = connection.cursor()

    try:
        cursor.execute(query)
        #generate_log('INFO', db_instance_identifier, f'query=[{query}] executed')
        return None
    except psycopg2.Error as e:
        generate_log('ERROR', db_instance_identifier, str(e))
        exit(0)
    finally:
        cursor.close()
        connection.commit()

def rds_host_available(host, port):
    try:
        # Create a socket object
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Set a timeout for the connection attempt (in seconds)
        sock.settimeout(5)

        # Try to connect to the specified host and port
        sock.connect((host, port))

        # If the connection is successful, the port is open
        return True
    except Exception as e:
        # If there's an error or the connection times out, the port is not open
        return False
    finally:
        # Close the socket
        sock.close()
