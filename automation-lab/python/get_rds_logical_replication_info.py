"""
RDS Replication Info Script

Python script named rep_info_rds_who_am_i.py identifies replication details for a given Amazon RDS.
It determines if the RDS instance is a publisher, subscriber, or CDC Publisher.
The script also finds its counterpart in the replication setup.
Its purpose is to provide concise information on RDS replication.

Usage:
python3 rds_pub_sub_info.py <rds_instance_name> <dbuser> <db>

        Arguments:
            - <rds_instance_name>: The name of your Amazon RDS instance.
            - <dbuser>: The username to connect to the database.
            - <db>: The name of the database.

Output:
    - If the RDS instance is a publisher, the script will indicate this and identify its subscriber.
    - If the RDS instance is a subscriber, the script will indicate this and identify its publisher.

Requirements:
    - Python 3.x
    - boto3 library (ensure it's installed via pip install boto3)
    - AWS credentials configured (either through environment variables or AWS CLI configuration)

Example:
    python3 rep_pub_sub_info.py my-rds-instance myuser mydb

Note:
This script assumes that the RDS instance has replication configured and that the appropriate IAM permissions are in place to access RDS APIs.
"""

import subprocess
import psycopg2
from psycopg2 import OperationalError
import getpass
import argparse
from prettytable import PrettyTable

def connect_to_rds(endpoint, user, password, database):
    try:
        connection = psycopg2.connect(
            host=endpoint,
            user=user,
            password=password,
            database=database
        )
        print("Connected to PostgreSQL RDS")
        return connection
    except OperationalError as e:
        print(f"Error: {e}")
        return None

def is_publisher_alone(connection, rds_endpoints):
    try:
        cursor = connection.cursor()
        cursor.execute("""
            SELECT prs.slot_name,
            psa.datname,
            psa.client_addr,
            CASE
            WHEN substring(psa.query FROM '"publication_names" ''([^'']+)''') IS NOT NULL
            THEN substring(psa.query FROM '"publication_names" ''([^'']+)''')
            WHEN substring(psa.query FROM 'publication_names ''"([^"]+)"''') IS NOT NULL
            THEN substring(psa.query FROM 'publication_names ''"([^"]+)"''')
            END AS publication_name,
            prs.database
            FROM pg_stat_activity psa JOIN pg_replication_slots prs ON psa.pid = prs.active_pid order by prs.slot_name
        """)
        rows = cursor.fetchall()
        if rows:
            print("This is a Publisher RDS and below are the rep_slot(s) details")
            table = PrettyTable(['Slot Name', 'Database Name', 'Client Address', 'Publication Name', 'Database'])
            for row in rows:
                ip_address = row[2]
                matching_rds = next((rds for rds in rds_endpoints if ip_address in subprocess.check_output(['dig', '+short', rds], universal_newlines=True)), None)
                if matching_rds:
                    row = list(row)
                    row[2] = matching_rds.strip()
                    table.add_row(row)
                else:
                    # If no matching RDS found, print the original IP address
                    table.add_row(row)
            print(table)
            return True
        else:
            return False
    except OperationalError as e:
        print(f"Error checking Publisher RDS: {e}")
        return False


def is_subscriber_alone(connection):
    try:
        cursor = connection.cursor()
        cursor.execute("""
            SELECT pd.datname,subname,subconninfo,subpublications 
            FROM pg_subscription ps 
            JOIN pg_database pd ON pd.oid = ps.subdbid
        """)
        rows = cursor.fetchall()
        if rows:
            print("This is a Subscriber RDS and below are the subscription(s) details")
            table = PrettyTable(['Database Name', 'Subscriber Name', 'Connection Info', 'Publications'])
            for row in rows:
                # Find the index of 'password='
                password_index = row[2].find('password=')
                if password_index != -1:
                    # Replace characters after 'password=' with asterisks
                    row = list(row)
                    row[2] = row[2][:password_index + len('password=')] + '*' * 12
                    row = tuple(row)
                table.add_row(row)
            print(table)
            return True
        else:
            return False
    except OperationalError as e:
        print(f"Error checking Subscriber RDS: {e}")
        return False

def is_both_publisher_and_subscriber(connection, rds_endpoints):
    publisher_alone = is_publisher_alone(connection, rds_endpoints)
    if publisher_alone and is_subscriber_alone(connection):
        print("This instance is acting as both Publisher and Subscriber.")
    elif publisher_alone:
        print("This instance is acting as a Publisher alone.")
    elif is_subscriber_alone(connection):
        print("This instance is acting as a Subscriber alone.")
    else:
        print("This instance is not acting as either Publisher or Subscriber.")


def main():
    parser = argparse.ArgumentParser(description='Connect to PostgreSQL RDS')
    parser.add_argument('hostname', type=str, help='RDS hostname')
    parser.add_argument('username', type=str, help='Username')
    parser.add_argument('database', type=str, help='Database name')

    args = parser.parse_args()

    password = getpass.getpass(prompt="Enter password: ")

    # Connection parameters
    connection = connect_to_rds(args.hostname, args.username, password, args.database)
    if connection:
        # Replace 'your_region' with the desired AWS region
        region = 'ap-south-1'
        # Fetch all RDS instances in the given region
        rds_endpoints = subprocess.check_output(['aws', 'rds', 'describe-db-instances', '--region', region, '--query', 'DBInstances[*].Endpoint.Address', '--output', 'text'], universal_newlines=True).split()

        is_both_publisher_and_subscriber(connection,rds_endpoints)
        connection.close()

if __name__ == "__main__":
    main()
