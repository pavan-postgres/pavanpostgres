import sys
import time
import multiprocessing

# Changing path to access rds/helpers package/modules
sys.path.append('../')

# import package helpers
from package_helpers import module_global as helpers
from package_helpers import module_replication as replication_helpers

def upgrade_activity(each_db_instance_identifier):
    try:
        # validate db instance
        replication_helpers.validate_db_instance(each_db_instance_identifier)

        # perform replication health check
        replication_helpers.get_replication_details_rep_slots(each_db_instance_identifier)
        replication_helpers.get_replication_details_subscriptions(each_db_instance_identifier)
        replication_helpers.perform_replication_health_check_for_rep_slots(each_db_instance_identifier)
        replication_helpers.perform_replication_health_check_for_subscriptions(each_db_instance_identifier)

        #
        #cdc logic - pre-upgrade
        #

        # get cdc slot details
        replication_helpers.get_cdc_rep_slots_info(each_db_instance_identifier)
        
        # set the cdc database ready for upgrade
        replication_helpers.set_cdc_db_ready_for_upgrade(each_db_instance_identifier)

        # sleep for 60 secs
        time.sleep(60)

        # perform health check on cdc slots before dropping slots
        replication_helpers.get_replication_details_cdc_rep_slots(each_db_instance_identifier)
        replication_helpers.perform_replication_health_check_for_cdc_rep_slots(each_db_instance_identifier)

        # drop the cdc replication slots in pre-upgrade phase
        replication_helpers.drop_cdc_rep_slots_on_pub_db(each_db_instance_identifier)

        #
        #sub logic - pre-upgrade
        #

        # get subscription details for db instance
        replication_helpers.get_subscriptions_info(each_db_instance_identifier)

        # handle subscriptions pre upgrade for subscriber
        replication_helpers.drop_subscriptions_for_sub(each_db_instance_identifier)

        #
        # rep slots logic - pre-upgrade
        #

        # get subscriber details for publisher
        replication_helpers.get_subsciber_info_for_publisher(each_db_instance_identifier)

        # set the publication database ready for upgrade
        replication_helpers.set_pub_db_ready_for_upgrade(each_db_instance_identifier)

        # drop the subscriptions for the replication slots
        replication_helpers.drop_subscriptions_for_rep_slots(each_db_instance_identifier)

        # drop the replication slots
        replication_helpers.drop_rep_slots_on_pub_db(each_db_instance_identifier)

        # perform the major version upgrade and validate it
        replication_helpers.perform_major_version_upgrade(each_db_instance_identifier)

        #
        #cdc logic - post-upgrade
        #

        # execute post upgrade curl on pub db which indirectly creates cdc rep_slots back
        replication_helpers.create_cdc_rep_slots_on_pub_db(each_db_instance_identifier)

        #
        # rep slots logic - post-upgrade
        #

        # create subscriptions on sub db which indirectly creates rep_slots back
        replication_helpers.create_subscriptions_for_pub_db(each_db_instance_identifier)

        #
        #sub logic - post-upgrade
        #

        # create subscription on sub rds instance
        replication_helpers.create_subscriptions_for_sub_db(each_db_instance_identifier)

        #
        # enable login mode for users - post-upgrade
        #

        # set the cdc database ready post upgrade
        replication_helpers.set_cdc_db_ready_post_upgrade(each_db_instance_identifier)

        # set the publication database ready post upgrade
        replication_helpers.set_pub_db_ready_post_upgrade(each_db_instance_identifier)

        #
        # final phase
        #


        helpers.generate_log('INFO',
                                each_db_instance_identifier,
                                f"""final phase : upgraded rds instance """)
    except Exception as e:
        helpers.generate_log('ERROR',
                                each_db_instance_identifier,
                                f""" {str(e)} """)
        helpers.generate_log('INFO',
                                each_db_instance_identifier,
                                f""" Unable to trigger upgrade. Please fix the issues and rerun""")



def main():
    # get no of cpus available
    num_processes = multiprocessing.cpu_count()
    # List of RDS instances to upgrade from the config.yaml file
    db_instance_identifiers = replication_helpers.config.get('db_instance_identifiers', [])

    replication_helpers.get_boto3_client()

    # Create a multiprocessing pool
    pool = multiprocessing.Pool(processes=num_processes)

    # Run the upgrade_instance function in parallel for each DB instance identifier
    pool.map(upgrade_activity, db_instance_identifiers)

    # close the pool
    pool.terminate()


if __name__ == "__main__":
    main()
