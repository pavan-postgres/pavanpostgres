import sys
import boto3
import time
import subprocess
from datetime import datetime
import jwt
import os

# Changing path to access rds/helpers package/modules
sys.path.append('../')

# import package helpers
from package_helpers import module_global as helpers

# load the configuration
config = helpers.load_configuration()

# global variables
connections = {}
replication_slots = []
rds_dict = {}
rep_slots_data = []
pub_db_list = []
cdc_db_list = []
login_roles = []
cdc_replication_slots = []
source_connector_list = []
replication_slots_health_data = []
subscriptions_health_data = []
cdc_replication_slots_health_data = []
subscriptions = []

# generic functions start

# function to define client
def get_boto3_client():
    # load the configuration
    config = helpers.load_configuration()

    # validate the configuration
    try:
        helpers.validate_configuration(config)
    except ValueError as e:
        helpers.generate_log('ERROR', config, str(e))
        return

    if config['use_iam'] == 'true':
        # Initialize the RDS client with attached iam role to an ec2 instance
        # for tf workstation like environments
        client = boto3.client('rds', region_name=config['region_name'])
    else:
        # Initialize the RDS client using secret keys
        if not os.environ["AWS_SESSION_TOKEN"] :
            client = boto3.client('rds', aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
                                  aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
                                  region_name=config['region_name'])
        else:
            print(config['region_name'])
            client = boto3.client('rds', aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
                                  aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
                                  aws_session_token=os.environ["AWS_SESSION_TOKEN"],
                                  region_name=config['region_name'])

    connections['boto3_client'] = client

    return True

# function to validate db instance
def validate_db_instance(db_instance_identifier):
    client = connections['boto3_client']
    # validate if the instance identifier mentioned in the config file exists
    helpers.validate_instance_identifier(db_instance_identifier, client)

    # get the instance parameter group
    db_parameter_group_name = helpers.get_instance_parameter_group(db_instance_identifier, client)

    # backup db parameter group
    helpers.backup_db_parameter_group(db_instance_identifier, db_parameter_group_name, client, config)

    return True

# function to get db instance details
def get_db_instance_details(db_instance_identifier):
    client = connections['boto3_client']
    # get db instance details
    db_instance_details = helpers.get_db_instance_details(db_instance_identifier, client)

    return db_instance_details

# generic function to execute query with no results
def execute_query_with_no_results(db_instance_identifier,connection_info,query):
    connection = helpers.connect_to_postgresql(connection_info['db_instance_identifier'],
                                               connection_info['db_name'] ,
                                               connection_info['master_user_name'] ,
                                               os.environ["database_password"],
                                               connection_info['rds_endpoint'],
                                               connection_info['port'])
    helpers.execute_db_query_with_no_results(db_instance_identifier, connection,
                                                    query)
    connection.close()
    return True

# generic function to execute query
def execute_query(connection_info,query,block_mode=False):
    connection = helpers.connect_to_postgresql(connection_info['db_instance_identifier'],
                                               connection_info['db_name'] ,
                                               connection_info['master_user_name'] ,
                                               os.environ["database_password"],
                                               connection_info['rds_endpoint'],
                                               connection_info['port'])

    if  block_mode:
        # Execute the query
        # Rollback any open transactions
        connection.rollback()

        # Set autocommit mode
        connection.autocommit = True

        with connection.cursor() as cursor:
            cursor.execute(query)

        # Commit the changes
        connection.commit()
        connection.close()
        return True
    else:
        query_result = helpers.execute_db_query(connection_info['db_instance_identifier'],
                                            connection,
                                            query)
        connection.close()

        return  query_result
    return True

# function to get the list of roles who can login
def get_login_roles(db_instance_identifier):
    db_instance_info = get_db_instance_details(db_instance_identifier)
    connection_details = {
        "db_instance_identifier": db_instance_identifier,
        "db_name":"postgres",
        "master_user_name": db_instance_info['MasterUsername'],
        "rds_endpoint": db_instance_info['Endpoint']['Address'],
        "port": db_instance_info['Endpoint']['Port']
    }
    get_role_list_query = f"""select rolname from pg_roles where rolcanlogin = 't' and rolname not like '%rds%' and rolname not in ('metis_replication','master') and rolname not like ('%master%') """

    get_role_list_data = execute_query(connection_details,
                                           get_role_list_query)

    for each_role  in get_role_list_data:
        login_roles.append(each_role[0])

    return True

# generic functions end

# functions to perform replication health check start

# function to get replication details for rep slots as part of health check
def get_replication_details_rep_slots(db_instance_identifier):
    rep_health_get_rep_slots = f"""SELECT prs.slot_name,prs.database,prs.active,
    pg_wal_lsn_diff(pg_current_wal_lsn(),
    confirmed_flush_lsn)
    from pg_replication_slots prs where slot_name not like '%cdc%'"""

    db_instance_info = get_db_instance_details(db_instance_identifier)
    connection_details = {
        "db_instance_identifier": db_instance_identifier,
        "db_name":"postgres",
        "master_user_name": db_instance_info['MasterUsername'],
        "rds_endpoint": db_instance_info['Endpoint']['Address'],
        "port": db_instance_info['Endpoint']['Port']
    }
    replication_slots_details = execute_query(connection_details,
                                           rep_health_get_rep_slots)

    # validate rep_slots if present
    if not replication_slots_details:
        helpers.generate_log('INFO',
            db_instance_identifier,
            f"""pre-upgrade check: get_replication_details_rep_slots: replication slots are not configured in this rds """)
        return False
    else:
        for row in replication_slots_details:
            replication_slots_health_data.append(row)

    return True

# function to get cdc replication details for cdc rep slots as part of health check
def get_replication_details_cdc_rep_slots(db_instance_identifier):
    rep_health_get_cdc_rep_slots = f"""SELECT prs.slot_name,prs.database,prs.active,
    pg_wal_lsn_diff(pg_current_wal_lsn(),
    confirmed_flush_lsn)
    from pg_replication_slots prs where slot_name like '%cdc%'"""

    db_instance_info = get_db_instance_details(db_instance_identifier)
    connection_details = {
        "db_instance_identifier": db_instance_identifier,
        "db_name":"postgres",
        "master_user_name": db_instance_info['MasterUsername'],
        "rds_endpoint": db_instance_info['Endpoint']['Address'],
        "port": db_instance_info['Endpoint']['Port']
    }
    cdc_replication_slots_details = execute_query(connection_details,
                                           rep_health_get_cdc_rep_slots)

    # validate cdc rep_slots if present
    if not cdc_replication_slots_details:
        helpers.generate_log('INFO',
            db_instance_identifier,
            f"""pre-upgrade check: get_replication_details_cdc_rep_slots: cdc replication slots are not configured in this rds """)
        return False
    else:
        for row in cdc_replication_slots_details:
            cdc_replication_slots_health_data.append(row)

    return True

# function to get replication details for subscriptions as part of health check
def get_replication_details_subscriptions(db_instance_identifier):
    db_instance_info = get_db_instance_details(db_instance_identifier)
    connection_details = {
        "db_instance_identifier": db_instance_identifier,
        "db_name":"postgres",
        "master_user_name": db_instance_info['MasterUsername'],
        "rds_endpoint": db_instance_info['Endpoint']['Address'],
        "port": db_instance_info['Endpoint']['Port']
    }

    # validate subscriptions if present
    rep_health_get_subscriptions = f"""SELECT subname,subowner,subenabled,subconninfo,subpublications from pg_subscription"""
    subscriptions_details = execute_query(connection_details,
                                           rep_health_get_subscriptions)
    if not subscriptions_details:
        helpers.generate_log('INFO',
            db_instance_identifier,
            f"""pre-upgrade check: get_replication_details_subscriptions: subscriptions are not configured in this rds """)
    else:
        for row in subscriptions_details:
            subscriptions_health_data.append(row)

    return True

# function to perform replication health check for rep slots
def perform_replication_health_check_for_rep_slots(db_instance_identifier):
    if not replication_slots_health_data:
        helpers.generate_log('INFO',
            db_instance_identifier,
            f"""pre-upgrade check: perform_replication_health_check_for_rep_slots: no rep slots are present to perform replication health check""")
        return False
    else:
        # perform replication health check
        for rep_datum in replication_slots_health_data:
            rep_slot = rep_datum[0]
            rep_active = rep_datum[2]
            rep_wal_diff = rep_datum[3]
            # active and lag checks
            if rep_active == True and rep_wal_diff < 1000:
                helpers.generate_log('INFO',
                    db_instance_identifier,
                    f"""pre-upgrade check: perform_replication_health_check_for_rep_slots : slot {rep_slot} is healthy, continuing with next phase of upgrade""")
            elif rep_active != True and rep_wal_diff < 1000:
                helpers.generate_log('ERROR',
                    db_instance_identifier,
                    f"""pre-upgrade check: perform_replication_health_check_for_rep_slots : slot {rep_slot} is inactive, exiting the script""")
                raise Exception("replication health check failed, exiting the script")
            elif rep_active == True and rep_wal_diff > 1000:
                helpers.generate_log('ERROR',
                    db_instance_identifier,
                    f"""pre-upgrade check: perform_replication_health_check_for_rep_slots : slot {rep_slot} lag is more than 1KB, exiting the script""")
                raise Exception("replication health check failed, exiting the script")
            else:
                helpers.generate_log('ERROR',
                    db_instance_identifier,
                    f"""pre-upgrade check: perform_replication_health_check_for_rep_slots : replication is un-healthy, exiting the script""")
                raise Exception("replication health check failed, exiting the script")
    return

# function to perform replication health check for cdc rep slots
def perform_replication_health_check_for_cdc_rep_slots(db_instance_identifier):
    if not cdc_replication_slots_health_data:
        helpers.generate_log('INFO',
            db_instance_identifier,
            f"""pre-upgrade check: perform_replication_health_check_for_cdc_rep_slots: no cdc slots are present to perform replication health check""")
        return False
    else:
        # perform replication health check
        for rep_datum in cdc_replication_slots_health_data:
            rep_slot = rep_datum[0]
            rep_active = rep_datum[2]
            rep_wal_diff = rep_datum[3]
            # active and lag checks
            if rep_active == True and rep_wal_diff < 500000000:
                helpers.generate_log('INFO',
                    db_instance_identifier,
                    f"""pre-upgrade check: perform_replication_health_check_for_cdc_rep_slots : slot {rep_slot} is healthy, continuing with next phase of upgrade""")
            elif rep_active != True and rep_wal_diff < 500000000:
                helpers.generate_log('ERROR',
                    db_instance_identifier,
                    f"""pre-upgrade check: perform_replication_health_check_for_cdc_rep_slots : slot {rep_slot} is inactive, exiting the script""")
                raise Exception("replication health check failed, exiting the script")
            elif rep_active == True and rep_wal_diff > 500000000:
                helpers.generate_log('ERROR',
                    db_instance_identifier,
                    f"""pre-upgrade check: perform_replication_health_check_for_cdc_rep_slots : slot {rep_slot} lag is more than 1KB, exiting the script""")
                raise Exception("replication health check failed, exiting the script")
            else:
                helpers.generate_log('ERROR',
                    db_instance_identifier,
                    f"""pre-upgrade check: perform_replication_health_check_for_cdc_rep_slots : replication is un-healthy, exiting the script""")
                raise Exception("replication health check failed, exiting the script")
    return

# function to perform replication health check for subscriptions
def perform_replication_health_check_for_subscriptions(db_instance_identifier):
    if not subscriptions_health_data:
        helpers.generate_log('INFO',
            db_instance_identifier,
            f"""pre-upgrade check: perform_replication_health_check_for_subscriptions: no subscriptions are present to perform replication health check""")
        return False
    else:
        # perform replication health check
        for sub in subscriptions_health_data:
            subscription_name = sub[0]
            subscription_enabled = sub[2]
            # active and lag checks
            if subscription_enabled == True:
                helpers.generate_log('INFO',
                    db_instance_identifier,
                    f"""pre-upgrade check: perform_replication_health_check_for_subscriptions : subscription {subscription_name} is healthy, continuing with next phase of upgrade""")
            else:
                helpers.generate_log('ERROR',
                    db_instance_identifier,
                    f"""pre-upgrade check: perform_replication_health_check_for_subscriptions : subscription {subscription_name} is un-healthy, exiting the script""")
                raise Exception("replication health check failed, exiting the script")
    return

# functions to perform replication health check end

# functions to handle replication slots logic start

# function to get replication slots info
def get_rep_slots_info(db_instance_identifier):
    get_replication_slots_query = f"""SELECT prs.slot_name,
    psa.datname,
    psa.client_addr,
    CASE
    WHEN substring(psa.query FROM '"publication_names" ''([^'']+)''') IS NOT NULL
    THEN substring(psa.query FROM '"publication_names" ''([^'']+)''')
    WHEN substring(psa.query FROM 'publication_names ''"([^"]+)"''') IS NOT NULL
    THEN substring(psa.query FROM 'publication_names ''"([^"]+)"''')
    END AS publication_name,
    prs.database
    FROM pg_stat_activity psa JOIN pg_replication_slots prs ON psa.pid = prs.active_pid
    where prs.slot_name not like '%cdc%'"""

    db_instance_info = get_db_instance_details(db_instance_identifier)
    connection_details = {
        "db_instance_identifier": db_instance_identifier,
        "db_name":"postgres",
        "master_user_name": db_instance_info['MasterUsername'],
        "rds_endpoint": db_instance_info['Endpoint']['Address'],
        "port": db_instance_info['Endpoint']['Port']
    }
    replication_slots_data = execute_query(connection_details,
                                           get_replication_slots_query)
    # validate rep_slots if present
    if not replication_slots_data:
        helpers.generate_log('INFO',
            db_instance_identifier,
            f"""pre-upgrade check: get_rep_slots_info : no replication slots found""")
        return False
    else:
        for row in replication_slots_data:
            replication_slots.append(row)

    return True

# function to map RDS to IP address
def instance_ip_config_map():
    client = connections['boto3_client']
    response = client.describe_db_instances()
    # Initialize a dictionary to store the results
    instance_ip_configmap = {}
    # Iterate through each RDS instance
    for db_instance in response['DBInstances']:
        # Get the endpoint of the RDS instance
        rds_endpoint = db_instance['Endpoint']['Address']
        # Run the dig command and capture the output
        dig_output = subprocess.check_output(['dig', '+short', rds_endpoint],
                                             universal_newlines=True).strip()
        # Add the result to the dictionary
        instance_ip_configmap[dig_output] = rds_endpoint

    return instance_ip_configmap

# function to get subcriber info for publisher
def get_subsciber_info_for_publisher(db_instance_identifier):
    ip_config_map = instance_ip_config_map()
    get_rep_slots_info(db_instance_identifier)

    if not replication_slots:
        helpers.generate_log('INFO',
            db_instance_identifier,
            f"""pre-upgrade check: get_subscriber_info_for_publisher: no rep_slots found""")
        return False
    else:
        for replication_slot in replication_slots:
            sub_name = replication_slot[0]
            pub_db_name = replication_slot[1]
            sub_host_ip = replication_slot[2]
            if pub_db_name not in pub_db_list:
                pub_db_list.append(pub_db_name)
            # pub rep_slot ip vs sub cname match
            if sub_host_ip in ip_config_map:
                sub_rds_endpoint = ip_config_map[sub_host_ip]
                sub_db_instance_identifier = sub_rds_endpoint.split('.')[0]
                rds_dict[sub_name]=[sub_rds_endpoint,sub_db_instance_identifier]

                helpers.generate_log('INFO',
                db_instance_identifier,
                f"""pre-upgrade check: get_subscriber_info_for_publisher : fetched sub rds {sub_db_instance_identifier} for slot {sub_name} """)
            else:
                # case where sub_host_ip is not found in instance_ip_configmap
                helpers.generate_log('ERROR',
                    db_instance_identifier,
                    f"""pre-upgrade check: get_subscriber_info_for_publisher : no match found """)
                continue

            sub_db_instance_details = get_db_instance_details(sub_db_instance_identifier)
            connection_details = {
                        "db_instance_identifier": sub_db_instance_identifier,
                        "db_name":"postgres",
                        "master_user_name": sub_db_instance_details['MasterUsername'],
                        "rds_endpoint": sub_db_instance_details['Endpoint']['Address'],
                        "port": sub_db_instance_details['Endpoint']['Port']
                    }

            get_sub_details_for_pub = f"""SELECT pd.datname, subname AS "Name" ,
            pg_catalog.pg_get_userbyid(subowner) AS "Owner",
            subconninfo AS conninfo, subenabled AS "Enabled",
            subpublications AS "Publication"
            FROM pg_catalog.pg_subscription join pg_database pd on pd.oid=pg_subscription.subdbid
            where subname = '{sub_name}'"""

            get_sub_details_data = execute_query(connection_details,
                                        get_sub_details_for_pub)

            for row in get_sub_details_data:
                rep_slots_data.append(row)
        return True

# function to set pub db ready for upgrade
def set_pub_db_ready_for_upgrade(db_instance_identifier):
    nologin_mode_query_list = []
    db_instance_details = get_db_instance_details(db_instance_identifier)
    connection_details = {
                        "db_instance_identifier": db_instance_identifier,
                        "db_name":"postgres",
                        "master_user_name": db_instance_details['MasterUsername'],
                        "rds_endpoint": db_instance_details['Endpoint']['Address'],
                        "port": db_instance_details['Endpoint']['Port']
                    }
    get_login_roles(db_instance_identifier)

    for each_role  in login_roles:
        nologin_mode_query_list.append(f"ALTER ROLE {each_role} WITH NOLOGIN;\n")

    nologin_mode_query = ''.join(nologin_mode_query_list)

    execute_query_with_no_results(db_instance_identifier,connection_details,nologin_mode_query)
    helpers.generate_log('INFO',
               db_instance_identifier,
               f"""pre-upgrade check: set_pub_db_ready_for_upgrade : altered role(s) with nologin mode """)

    for each_db in pub_db_list:
        terminate_connections_query = f"""SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = '{each_db}' AND usename not in ('postgres','master','rdsadmin','metis_replication')
            and usename not like '%rep%' AND usename not like '%master%' AND pid <> pg_backend_pid();"""

        execute_query_with_no_results(db_instance_identifier,connection_details,terminate_connections_query)

        helpers.generate_log('INFO',
               db_instance_identifier,
               f"""pre-upgrade check: set_pub_db_ready_for_upgrade : terminated connections for {each_db} """)

    return True

# function to drop subscriptions for a replication slot
def drop_subscriptions_for_rep_slots(db_instance_identifier):
    if not rep_slots_data:
        helpers.generate_log('INFO',
            db_instance_identifier,
            f"""pre-upgrade check: drop_subscriptions_for_rep_slots: no rep_slots found""")
        return False
    else:
        for row in rep_slots_data:
            sub_detail = row
            sub_name = sub_detail[1]
            sub_db_name = sub_detail[0]
            sub_owner = sub_detail[2]

            sub_rds_endpoint = rds_dict[sub_name][0]
            sub_db_instance_identifier = rds_dict[sub_name][1]

            sub_db_instance_details = get_db_instance_details(sub_db_instance_identifier)
            connection_details = {
                            "db_instance_identifier": sub_db_instance_identifier,
                            "db_name": sub_db_name,
                            "master_user_name": sub_db_instance_details['MasterUsername'],
                            "rds_endpoint": sub_rds_endpoint,
                            "port": sub_db_instance_details['Endpoint']['Port']
                        }

            # disable subscription
            disable_sub_query = f'set role {sub_owner};  ALTER SUBSCRIPTION {sub_name} disable;'
            execute_query_with_no_results(sub_db_instance_identifier,connection_details,disable_sub_query)

            helpers.generate_log('INFO',
                sub_db_instance_identifier,
                f"""pre-upgrade check: drop_subscriptions_for_rep_slots : disabled subscription {sub_name}""")

            # set slot to none
            set_slot_null_for_sub = f"""set role {sub_owner}; ALTER SUBSCRIPTION {sub_name}
            set (slot_name=none);"""
            execute_query_with_no_results(sub_db_instance_identifier,connection_details,set_slot_null_for_sub)

            helpers.generate_log('INFO',
                sub_db_instance_identifier,
                f"""pre-upgrade check: drop_subscriptions_for_rep_slots : set slot name to none for subscription {sub_name}""")

            # drop subscription
            drop_sub_query = f'set role {sub_owner}; DROP SUBSCRIPTION {sub_name};'
            execute_query_with_no_results(sub_db_instance_identifier,connection_details,drop_sub_query)

            helpers.generate_log('INFO',
                sub_db_instance_identifier,
                f"""pre-upgrade check: drop_subscriptions_for_rep_slots : dropped subscription {sub_name}""")


        return True

# function to drop replication slot on pub db
def drop_rep_slots_on_pub_db(db_instance_identifier):
    for row in rep_slots_data:
        sub_detail = row
        sub_name = sub_detail[1]

        # connect to pub rds
        db_instance_details = get_db_instance_details(db_instance_identifier)

        connection_details = {
                        "db_instance_identifier": db_instance_identifier,
                        "db_name": "postgres",
                        "master_user_name": db_instance_details['MasterUsername'],
                        "rds_endpoint": db_instance_details['Endpoint']['Address'],
                        "port": db_instance_details['Endpoint']['Port']
                    }
        pub_master = db_instance_details['MasterUsername']

        # drop rep slot
        drop_rep_slot_on_pub = f"set role {pub_master}; select pg_drop_replication_slot('{sub_name}');"
        execute_query_with_no_results(db_instance_identifier,connection_details,drop_rep_slot_on_pub)

        helpers.generate_log('INFO',
               db_instance_identifier,
               f"""pre-upgrade check: drop_rep_slots_on_pub_db : dropped replication slot {sub_name}""")


    return True

# function to set pub db ready post upgrade
def set_pub_db_ready_post_upgrade(db_instance_identifier):
    login_mode_query_list = []
    db_instance_details = get_db_instance_details(db_instance_identifier)
    connection_details = {
                        "db_instance_identifier": db_instance_identifier,
                        "db_name":"postgres",
                        "master_user_name": db_instance_details['MasterUsername'],
                        "rds_endpoint": db_instance_details['Endpoint']['Address'],
                        "port": db_instance_details['Endpoint']['Port']
                    }

    get_login_roles(db_instance_identifier)

    for each_role  in login_roles:
        login_mode_query_list.append(f"ALTER ROLE {each_role} WITH LOGIN;\n")

    login_mode_query = ''.join(login_mode_query_list)

    execute_query_with_no_results(db_instance_identifier,connection_details,login_mode_query)
    helpers.generate_log('INFO',
               db_instance_identifier,
               f"""post-upgrade check: set_pub_db_ready_post_upgrade : altered role(s) with login mode """)

    return True

# function to create subscriptions for pub db
def create_subscriptions_for_pub_db(db_instance_identifier):
    for row in rep_slots_data:
        sub_detail = row
        sub_name = sub_detail[1]
        sub_db_name = sub_detail[0]
        sub_owner = sub_detail[2]
        sub_conninfo = sub_detail[3]
        sub_pub_name = sub_detail[5][0]

        sub_rds_endpoint = rds_dict[sub_name][0]
        sub_db_instance_identifier = rds_dict[sub_name][1]

        sub_db_instance_details = get_db_instance_details(sub_db_instance_identifier)

        # Connect to the subscription RDS instance
        connection_details = {
                        "db_instance_identifier": sub_db_instance_identifier,
                        "db_name": sub_db_name,
                        "master_user_name": sub_owner,
                        "rds_endpoint": sub_rds_endpoint,
                        "port": sub_db_instance_details['Endpoint']['Port']
                    }

        # Perform post-upgrade actions for each replication slot
        recreate_sub_query = f"""CREATE SUBSCRIPTION {sub_name} CONNECTION '{sub_conninfo}'
                                PUBLICATION {sub_pub_name} WITH (copy_data = false, create_slot = true);"""

        execute_query(connection_details,recreate_sub_query,True)

        helpers.generate_log('INFO',
               db_instance_identifier,
               f"""post-upgrade check: create_subscriptions_for_pub_db : created subscription and replication slot {sub_name} on publisher""")

    return True

# functions to handle replication slots logic end

# function to trigger major version upgrade start
def perform_major_version_upgrade(db_instance_identifier):

    client = connections['boto3_client']

    # check if there are not replication slots present
    get_rep_slots_query = f"""SELECT prs.slot_name,prs.database,prs.active,
    pg_wal_lsn_diff(pg_current_wal_lsn(),
    confirmed_flush_lsn)
    from pg_replication_slots prs"""

    get_subs_query = f"""SELECT subname from pg_subscription"""

    db_instance_info = get_db_instance_details(db_instance_identifier)

    connection_details = {
        "db_instance_identifier": db_instance_identifier,
        "db_name":"postgres",
        "master_user_name": db_instance_info['MasterUsername'],
        "rds_endpoint": db_instance_info['Endpoint']['Address'],
        "port": db_instance_info['Endpoint']['Port']
    }
    get_rep_slots = execute_query(connection_details,
                                           get_rep_slots_query)

    get_subs = execute_query(connection_details,
                                           get_subs_query)
    # validate rep_slots if present
    if not get_rep_slots and not get_subs:
        helpers.generate_log('INFO',
            db_instance_identifier,
            f"""perform_major_version_upgrade :rep_slots and subs sanity check: no slots and subscriptions are present at this stage. Proceeding with the major version upgrade""")
        # Trigger major version upgrade
        helpers.major_version_upgrade_rds_instance(config, db_instance_identifier, client)
        # Wait for 60 seconds for upgrade to initiate
        time.sleep(60)
        while True:
            # Check engine version
            current_engine_version = helpers.get_engine_version(db_instance_identifier, client)

            # Check if engine version matches the new engine version
            if current_engine_version == config['new_engine_version']:
                # Log upgrade success
                helpers.generate_log('INFO',
                    db_instance_identifier,
                    f"""perform_major_version_upgrade: engine version check from rds: instance available post upgrade and upgraded to {current_engine_version}""")

                # version checking post connecting to db
                db_version_query = f"""select split_part(version(),' ',2);"""
                db_version = execute_query(connection_details,
                                           db_version_query)

                if db_version[0][0] == config['new_engine_version']:
                    helpers.generate_log('INFO',
                    db_instance_identifier,
                    f"""perform_major_version_upgrade: engine version check from database: db is accepting connections post upgrade and upgraded to {current_engine_version} """)

                    return True

            else:
                # Log upgrade in progress
                helpers.generate_log('INFO',
                    db_instance_identifier,
                    f"""perform_major_version_upgrade: engine version check: db instance upgrade is in progress""")
                time.sleep(30)

    else:
        helpers.generate_log('ERROR',
            db_instance_identifier,
            f"""perform_major_version_upgrade: rep_slots and subs sanity check : there are some slots / subscriptions present at this stage. Can't proceed further with the major version upgrade. Exiting""")
        raise Exception("replication health check failed, exiting the script")

# function to trigger major version upgrade end

# functions to handle cdc replication slots logic start

# function to get cdc rep slots info
def get_cdc_rep_slots_info(db_instance_identifier):
    get_replication_slots_query = f"""SELECT prs.slot_name,
    psa.datname,
    psa.client_addr,
    CASE
    WHEN substring(psa.query FROM '"publication_names" ''([^'']+)''') IS NOT NULL
    THEN substring(psa.query FROM '"publication_names" ''([^'']+)''')
    WHEN substring(psa.query FROM 'publication_names ''"([^"]+)"''') IS NOT NULL
    THEN substring(psa.query FROM 'publication_names ''"([^"]+)"''')
    END AS publication_name,
    prs.database
    FROM pg_stat_activity psa JOIN pg_replication_slots prs ON psa.pid = prs.active_pid
    where prs.slot_name like '%cdc%'"""

    db_instance_info = get_db_instance_details(db_instance_identifier)
    connection_details = {
        "db_instance_identifier": db_instance_identifier,
        "db_name":"postgres",
        "master_user_name": db_instance_info['MasterUsername'],
        "rds_endpoint": db_instance_info['Endpoint']['Address'],
        "port": db_instance_info['Endpoint']['Port']
    }
    cdc_replication_slots_data = execute_query(connection_details,
                                           get_replication_slots_query)
    # validate rep_slots if present
    if not cdc_replication_slots_data:
        helpers.generate_log('INFO',
            db_instance_identifier,
            f"""pre-upgrade check: get_cdc_rep_slots_info : no cdc replication slots found""")
        return False
    else:
        for row in cdc_replication_slots_data:
            cdc_replication_slots.append(row)
            cdc_db_list.append(row[1])

    return True

# function to get jwt metis cdc token
def getJwtToken(tenantid, secret):
    json_data = {
        "sub": tenantid,
        "exp": round(time.time()) + 3600,
        "iat": round(time.time()),
    }

    return jwt.encode(payload=json_data,
                        key=secret,
                        algorithm="HS512", headers={'typ': None})

# function to set cdc db ready for upgrade
def set_cdc_db_ready_for_upgrade(db_instance_identifier):
    nologin_mode_query_list = []
    db_instance_info = get_db_instance_details(db_instance_identifier)
    connection_details = {
        "db_instance_identifier": db_instance_identifier,
        "db_name":"postgres",
        "master_user_name": db_instance_info['MasterUsername'],
        "rds_endpoint": db_instance_info['Endpoint']['Address'],
        "port": db_instance_info['Endpoint']['Port']
    }
    get_login_roles(db_instance_identifier)

    for each_role  in login_roles:
        nologin_mode_query_list.append(f"ALTER ROLE {each_role} WITH NOLOGIN;\n")

    nologin_mode_query = ''.join(nologin_mode_query_list)

    execute_query_with_no_results(db_instance_identifier,connection_details,nologin_mode_query)
    helpers.generate_log('INFO',
               db_instance_identifier,
               f"""pre-upgrade check: set_cdc_db_ready_for_upgrade : altered role(s) with nologin mode """)

    for each_db in cdc_db_list:
        terminate_connections_query = f"""SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = '{each_db}' AND usename not in ('postgres','master','rdsadmin','metis_replication')
            and usename not like '%rep%' AND usename not like '%master%' AND pid <> pg_backend_pid();"""

        execute_query_with_no_results(db_instance_identifier,connection_details,terminate_connections_query)

        helpers.generate_log('INFO',
               db_instance_identifier,
               f"""pre-upgrade check: set_cdc_db_ready_for_upgrade : terminated application user connections for {each_db} """)

    return True

# function to drop cdc rep slots from cdc pub db
def drop_cdc_rep_slots_on_pub_db(db_instance_identifier):
    db_instance_details = get_db_instance_details(db_instance_identifier)
    if not cdc_replication_slots:
        helpers.generate_log('INFO',
            db_instance_identifier,
            f"""pre-upgrade check: drop_cdc_rep_slots_on_pub_db : no cdc replication slots found""")
        return False
    else:
        cdc_zone_secret = os.environ["cdc_zone_secret"]
        for cdc_replication_slot in cdc_replication_slots:
            cdc_slot_name = cdc_replication_slot[0]
            # split cdc slot name by underscore
            cdc_slot_parts = cdc_slot_name.split("_")
            helpers.generate_log('INFO',
                db_instance_identifier,
                f"""pre-upgrade check: cdc-slots phase : cdc slots are present, validating the slots as per naming convention""")
            # extract the tenant id programatically
            if len(cdc_slot_parts) >=3:
                tenant_id = cdc_slot_parts[2]
                helpers.generate_log('INFO',
                    db_instance_identifier,
                    f"""pre-upgrade check: cdc-slots phase : valid cdc format""")
            else:
                helpers.generate_log('ERROR',
                    db_instance_identifier,
                    f"""pre-upgrade check: cdc-slots phase : invalid cdc format""")

            # get source connector list
            source_connector_list.append({'tenant_id':tenant_id,
                                          'connector': '"' + cdc_slot_name.split('_', 1)[1] + '"',
                                          'metis_cdc_token': getJwtToken(tenant_id,cdc_zone_secret)})


        # pre cdc slots upgrade - generate curl command
        for source_connector in source_connector_list:
            pre_upgrade_metis_cdc_trigger = f"""curl \
            -k --location --request DELETE '{config['metis_cdc_base_url']}/admin/tenants/{source_connector['tenant_id']}/pre-upgrade' \
            --header 'Content-Type: application/json' \
            --header 'Authorization: Bearer {source_connector['metis_cdc_token']}' \
            --data '[
                {source_connector['connector']}
            ]'"""
            # execute curl command
            try:
                subprocess.run(pre_upgrade_metis_cdc_trigger, shell=True,check=True)
                #print(pre_upgrade_metis_cdc_trigger)
                print ('\n')
                helpers.generate_log('INFO',
                    db_instance_identifier,
                    f"""pre-upgrade check: drop_cdc_rep_slots_on_pub_db : {source_connector['connector']} : pre-upgrade api triggered successfully""")
            except subprocess.CalledProcessError as e:
                print ('\n')
                helpers.generate_log('ERROR',
                    db_instance_identifier,
                    f"""pre-upgrade check:drop_cdc_rep_slots_on_pub_db : {source_connector['connector']} : pre-upgrade api unsuccessful {e}""")


        # Check existence of slots in the database
        for cdc_replication_slot in cdc_replication_slots:
            cdc_slot_name = cdc_replication_slot[0]
            cdc_db_name   = cdc_replication_slot[1]
            # Connect to the database and check existence of the slot
            db_instance_info = get_db_instance_details(db_instance_identifier)
            connection_details = {
                "db_instance_identifier": db_instance_identifier,
                "db_name":"postgres",
                "master_user_name": db_instance_info['MasterUsername'],
                "rds_endpoint": db_instance_info['Endpoint']['Address'],
                "port": db_instance_info['Endpoint']['Port']
            }
            cdc_slot_exists_query = f"SELECT slot_name FROM pg_replication_slots WHERE slot_name = '{cdc_slot_name}'"
            check_cdc_slot_exists = execute_query(connection_details, cdc_slot_exists_query)
            if not check_cdc_slot_exists:
                helpers.generate_log('INFO',
                    db_instance_identifier,
                    f"""pre-upgrade check:drop_cdc_rep_slots_on_pub_db :There are no cdc rep slots named '{cdc_slot_name}' for database {cdc_db_name}.""")
            else:
                # Issue command to drop the slot
                dropped = False
                attempts = 0
                max_attempts = 10  
                # Set maximum attempts to avoid infinite loop
                while not dropped and attempts < max_attempts:
                    drop_slot_command = f"SELECT pg_drop_replication_slot('{cdc_slot_name}')"
                    execute_query_with_no_results(db_instance_identifier,connection_details,drop_slot_command)
                    # Wait for 30 seconds
                    time.sleep(30)  
                    # Recheck for existence of the slot
                    check_cdc_slot_exists = execute_query(connection_details, cdc_slot_exists_query)
                    if not check_cdc_slot_exists:
                        helpers.generate_log('INFO',
                            db_instance_identifier,
                            f"""pre-upgrade check:drop_cdc_rep_slots_on_pub_db :The CDC replication slot '{cdc_slot_name}' has been successfully dropped for database {cdc_db_name}""")
                        dropped = True
                    else:
                        attempts += 1
                        if attempts == max_attempts:
                            helpers.generate_log('ERROR',
                            db_instance_identifier,
                            f"""pre-upgrade check:drop_cdc_rep_slots_on_pub_db :Max attempts reached. The CDC replication slot '{cdc_slot_name}' may not have been dropped for database {cdc_db_name}""")
                            break
                        else:
                            helpers.generate_log('INFO',
                            db_instance_identifier,
                            f"""pre-upgrade check:drop_cdc_rep_slots_on_pub_db :The CDC replication slot '{cdc_slot_name}' still exists for database {cdc_db_name}, trying to delete [attempt = {attempts}] ...""")

    return True

# function to set cdc db ready post upgrade
def set_cdc_db_ready_post_upgrade(db_instance_identifier):
    login_mode_query_list = []
    db_instance_info = get_db_instance_details(db_instance_identifier)
    connection_details = {
        "db_instance_identifier": db_instance_identifier,
        "db_name":"postgres",
        "master_user_name": db_instance_info['MasterUsername'],
        "rds_endpoint": db_instance_info['Endpoint']['Address'],
        "port": db_instance_info['Endpoint']['Port']
    }

    for each_role in login_roles:
        login_mode_query_list.append(f"ALTER ROLE {each_role} WITH LOGIN;\n")

    login_mode_query = ''.join(login_mode_query_list)

    execute_query_with_no_results(db_instance_identifier,connection_details,login_mode_query)
    helpers.generate_log('INFO',
               db_instance_identifier,
               f"""post-upgrade check: set_cdc_db_ready_post_upgrade : altered role(s) with login mode """)

    return True

# function to create cdc rep slots on cdc pub db
def create_cdc_rep_slots_on_pub_db(db_instance_identifier):
    db_instance_details = get_db_instance_details(db_instance_identifier)
    if not cdc_replication_slots:
        helpers.generate_log('INFO',
            db_instance_identifier,
            f"""pre-upgrade check: create_cdc_rep_slots_on_pub_db : no cdc replication slots found""")
        return False
    else:
        for cdc_replication_slot in cdc_replication_slots:
            cdc_slot_name = cdc_replication_slot[0]
            # split cdc slot name by underscore
            cdc_slot_parts = cdc_slot_name.split("_")
            helpers.generate_log('INFO',
                db_instance_identifier,
                f"""post-upgrade check: create_cdc_rep_slots_on_pub_db : cdc slots are present, validating the slots as per naming convention""")
            # extract the tenant id programatically
            if len(cdc_slot_parts) >=3:
                tenant_id = cdc_slot_parts[2]
                helpers.generate_log('INFO',
                    db_instance_identifier,
                    f"""post-upgrade check: create_cdc_rep_slots_on_pub_db : valid cdc format""")
            else:
                helpers.generate_log('ERROR',
                    db_instance_identifier,
                    f"""post-upgrade check: create_cdc_rep_slots_on_pub_db : invalid cdc format""")

        for source_connector in source_connector_list:
            post_upgrade_metis_cdc_trigger = f"""curl \
            -k --location '{config['metis_cdc_base_url']}/admin/tenants/{source_connector['tenant_id']}/post-upgrade' \
            --header 'Content-Type: application/json' \
            --header 'Authorization: Bearer {source_connector['metis_cdc_token']}' \
            --data '[
                {source_connector['connector']}
            ]'"""

            # execute curl command
            try:
                subprocess.run(post_upgrade_metis_cdc_trigger, shell=True,check=True)
                print ('\n')
                helpers.generate_log('INFO',
                    db_instance_identifier,
                    f"""post upgrade check: create_cdc_rep_slots_on_pub_db : {source_connector['connector']} : post-upgrade api triggered successfully """)
            except subprocess.CalledProcessError as e:
                print ('\n')
                helpers.generate_log('ERROR',
                    db_instance_identifier,
                    f"""post upgrade check: create_cdc_rep_slots_on_pub_db : {source_connector['connector']} : post-upgrade api unsuccessful {e} """)

    return True

# functions to handle cdc replication slots logic end

# functions to handle subcriptions logic start

# function to get subscriptions info
def get_subscriptions_info(db_instance_identifier):
    get_subscriptions_query = f"""SELECT subname AS name,  pg_catalog.pg_get_userbyid(subowner) AS owner,
        subenabled AS enabled, subpublications AS publication,
        subsynccommit AS synchronous_commit,
        subconninfo AS conninfo, datname
        FROM pg_subscription s JOIN pg_database d on s.subdbid = d.oid"""

    db_instance_info = get_db_instance_details(db_instance_identifier)
    connection_details = {
        "db_instance_identifier": db_instance_identifier,
        "db_name":"postgres",
        "master_user_name": db_instance_info['MasterUsername'],
        "rds_endpoint": db_instance_info['Endpoint']['Address'],
        "port": db_instance_info['Endpoint']['Port']
    }
    subscriptions_data = execute_query(connection_details,
                                           get_subscriptions_query)
    # validate rep_slots if present
    if not subscriptions_data:
        helpers.generate_log('INFO',
            db_instance_identifier,
            f"""pre-upgrade check: get_subscriptions_info : no subscriptions found""")
        return False
    else:
        for row in subscriptions_data:
            subscriptions.append(row)
    return True

# function to drop subscriptions for sub db
def drop_subscriptions_for_sub(db_instance_identifier):
    db_instance_details = get_db_instance_details(db_instance_identifier)
    if not subscriptions:
        helpers.generate_log('INFO',
            db_instance_identifier,
            f"""pre-upgrade check: drop_subscriptions_for_sub : no subscriptions found""")
        return False
    else:
        for subscription in subscriptions:
            sub_db_name = subscription[6]
            sub_name = subscription[0]
            sub_owner = subscription[1]

            db_instance_info = get_db_instance_details(db_instance_identifier)
            connection_details = {
                            "db_instance_identifier": db_instance_identifier,
                            "db_name": sub_db_name,
                            "master_user_name": db_instance_info['MasterUsername'],
                            "rds_endpoint": db_instance_info['Endpoint']['Address'],
                            "port": db_instance_info['Endpoint']['Port']
                        }

            # disable subscription
            disable_sub_query = f'set role {sub_owner};  ALTER SUBSCRIPTION {sub_name} disable;'
            execute_query_with_no_results(db_instance_identifier,connection_details,disable_sub_query)
            helpers.generate_log('INFO',
                db_instance_identifier,
                f"""pre-upgrade check: drop_subscriptions_for_sub : disabled subscription {sub_name}""")

            # set slot to none
            set_slot_null_for_sub = f"""set role {sub_owner}; ALTER SUBSCRIPTION {sub_name}
            set (slot_name=none);"""
            execute_query_with_no_results(db_instance_identifier,connection_details,set_slot_null_for_sub)

            helpers.generate_log('INFO',
                db_instance_identifier,
                f"""pre-upgrade check: drop_subscriptions_for_sub : set slot name to none for subscription {sub_name}""")

            # drop subscription
            drop_sub_query = f'set role {sub_owner}; DROP SUBSCRIPTION {sub_name};'
            execute_query_with_no_results(db_instance_identifier,connection_details,drop_sub_query)

            helpers.generate_log('INFO',
                db_instance_identifier,
                f"""pre-upgrade check: drop_subscriptions_for_sub : dropped subscription {sub_name}""")

        return True

# function to create subscriptions for sub db
def create_subscriptions_for_sub_db(db_instance_identifier):
    for subscription in subscriptions:
        sub_db_name = subscription[6]
        sub_name = subscription[0]
        sub_owner = subscription[1]
        sub_conninfo = subscription[5]
        sub_pub_name = subscription[3][0]

        db_instance_details = get_db_instance_details(db_instance_identifier)

        # Connect to the subscription RDS instance
        # Connect to the subscription RDS instance
        connection_details = {
                        "db_instance_identifier": db_instance_identifier,
                        "db_name": sub_db_name,
                        "master_user_name": sub_owner,
                        "rds_endpoint": db_instance_details['Endpoint']['Address'],
                        "port": db_instance_details['Endpoint']['Port']
                    }


        # Perform post-upgrade actions for each replication slot
        recreate_sub_query = f"""CREATE SUBSCRIPTION {sub_name} CONNECTION '{sub_conninfo}'
                                PUBLICATION {sub_pub_name} WITH (copy_data = false, create_slot = false);"""

        execute_query(connection_details,recreate_sub_query,True)
        helpers.generate_log('INFO',
               db_instance_identifier,
               f"""post-upgrade check: create_subscriptions_for_sub_db : created subscription {sub_name} on subscriber""")

    return True

# functions to handle subcriptions logic end
