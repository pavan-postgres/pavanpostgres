import boto3

# Connect to RDS
rds = boto3.client('rds')

# Get list of RDS instances
instances = rds.describe_db_instances()['DBInstances']

# Loop through each RDS instance
for instance in instances:
    if instance:
        instance_name = instance.get('DBInstanceIdentifier')
        iops = instance.get('Iops')

        if iops == 12000:
            tag = {'Key': 'alert:aws_rds_total_iops_threshold:static', 'Value': '10000'}
            rds.remove_tags_from_resource(ResourceName=instance['DBInstanceArn'], TagKeys=['alert:aws_rds_total_iops_threshold:pct'])
            rds.remove_tags_from_resource(ResourceName=instance['DBInstanceArn'], TagKeys=['alert:aws_rds_total_iops_threshold:static'])
            rds.add_tags_to_resource(ResourceName=instance['DBInstanceArn'], Tags=[tag])

            tag = {'Key': 'alert:aws_rds_read_iops_threshold:static', 'Value': '10000'}
            rds.remove_tags_from_resource(ResourceName=instance['DBInstanceArn'], TagKeys=['alert:aws_rds_read_iops_threshold:pct'])
            rds.remove_tags_from_resource(ResourceName=instance['DBInstanceArn'], TagKeys=['alert:aws_rds_read_iops_threshold:static'])
            rds.add_tags_to_resource(ResourceName=instance['DBInstanceArn'], Tags=[tag])

            tag = {'Key': 'alert:aws_rds_write_iops_threshold:static', 'Value': '10000'}
            rds.remove_tags_from_resource(ResourceName=instance['DBInstanceArn'], TagKeys=['alert:aws_rds_write_iops_threshold:pct'])
            rds.remove_tags_from_resource(ResourceName=instance['DBInstanceArn'], TagKeys=['alert:aws_rds_write_iops_threshold:static'])
            rds.add_tags_to_resource(ResourceName=instance['DBInstanceArn'], Tags=[tag])

            print(f"Operations performed on instance: {instance_name}")

        elif iops == 3000:
            tag = {'Key': 'alert:aws_rds_total_iops_threshold:static', 'Value': '2800'}
            rds.remove_tags_from_resource(ResourceName=instance['DBInstanceArn'], TagKeys=['alert:aws_rds_total_iops_threshold:pct'])
            rds.remove_tags_from_resource(ResourceName=instance['DBInstanceArn'], TagKeys=['alert:aws_rds_total_iops_threshold:static'])
            rds.add_tags_to_resource(ResourceName=instance['DBInstanceArn'], Tags=[tag])

            tag = {'Key': 'alert:aws_rds_read_iops_threshold:static', 'Value': '2800'}
            rds.remove_tags_from_resource(ResourceName=instance['DBInstanceArn'], TagKeys=['alert:aws_rds_read_iops_threshold:pct'])
            rds.remove_tags_from_resource(ResourceName=instance['DBInstanceArn'], TagKeys=['alert:aws_rds_read_iops_threshold:static'])
            rds.add_tags_to_resource(ResourceName=instance['DBInstanceArn'], Tags=[tag])

            tag = {'Key': 'alert:aws_rds_write_iops_threshold:static', 'Value': '2800'}
            rds.remove_tags_from_resource(ResourceName=instance['DBInstanceArn'], TagKeys=['alert:aws_rds_write_iops_threshold:pct'])
            rds.remove_tags_from_resource(ResourceName=instance['DBInstanceArn'], TagKeys=['alert:aws_rds_write_iops_threshold:static'])
            rds.add_tags_to_resource(ResourceName=instance['DBInstanceArn'], Tags=[tag])

            print(f"Operations performed on instance: {instance_name}")
