pipeline {
    agent {
        kubernetes {
            label "test-pr-build"
            yaml '''
                apiVersion: v1
                kind: Pod
                metadata:
                  labels:
                    app.kubernetes.io/name: vault
                  annotations:
                    vault.security.banzaicloud.io/vault-addr: "https://vault.default:8200"
                    vault.security.banzaicloud.io/vault-role: "cluster-service"
                    vault.security.banzaicloud.io/vault-skip-verify: "true"
                spec:
                  securityContext:
                    runAsNonRoot: false
                    privileged: true
                    runAsUser: 0
                  containers:
                    - name: "jnlp"
                      image: "<>.dkr.ecr.ap-south-1.amazonaws.com/dockerhub:<image_name>"
                    - name: python
                      image: "<>.dkr.ecr.ap-south-1.amazonaws.com/dockerhub:<image_name>"
                      imagePullPolicy: IfNotPresent
                      command: ["sleep", "3600"]
                      tty: true
                      resources:
                        requests:
                          memory: "500Mi"
                          cpu: "250m"
                        limits:
                          memory: "1024Mi"
                          cpu: "500m"
            '''
        }
    }
    environment {
        USER_CREDENTIALS = credentials('osre-494-db-user')
    }

    stages {
        stage('rds_vs_logicalDB_count') {
            steps {
                container("python") {
                    script {
                        // Load AWS credentials from Jenkins credentials
                        withCredentials([
                            [$class: 'AmazonWebServicesCredentialsBinding',
                             credentialsId: 'osre-494',
                             accessKeyVariable: 'AWS_ACCESS_KEY_ID',
                             secretKeyVariable: 'AWS_SECRET_ACCESS_KEY']
                        ]) {
                            def scriptContent = '''
#!/bin/bash
set +x
#Instance Name vs DB Name Vs Total DB count in each RDS instance Vs Total DB count in all RDS instances Script 
# Set the AWS region
region="ap-south-1"

export PGPASSWORD="$USER_CREDENTIALS_PSW"

# Initialize a variable to store the total database count
total_db_count=0

# Get the list of PostgreSQL RDS instances
rds_instances=$(aws rds describe-db-instances --query "DBInstances[?Engine=='postgres' && DBInstanceStatus=='available'].DBInstanceIdentifier" --output text --region ap-south-1| tr '\t' '\n' | grep 'uat-nonpci' | grep -v 'uat-pci')
instance_count=0
# Loop through the RDS instances
for instance_name in $rds_instances; do
  echo "Instance: $instance_name"
  db_count=0
  instance_count=$((instance_count + 1))

  # Connect to the PostgreSQL RDS instance and count databases
  db_names=$(psql -h $instance_name.<>.ap-south-1.rds.amazonaws.com -U master -p <> -d postgres -Aqt -X  -c "SELECT datname FROM pg_database WHERE datname NOT IN ('information_schema', 'template0', 'template1', 'postgres', 'admin', 'rdsadmin');")

  for db_name in $db_names; do
    echo "  Database: $db_name"import boto3
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago
from datetime import timedelta

# Function to scale the RDS instance
def scale_rds_instance(db_instance_identifier: str, db_instance_class: str, aws_region: str = 'ap-south-1'):
    """
    Function to scale an RDS instance to a new DB instance class.

    :param db_instance_identifier: RDS DB instance identifier (e.g., 'my-db-instance')
    :param db_instance_class: The new DB instance class (e.g., 'db.m5.large')
    :param aws_region: AWS region where the RDS instance is located
    """
    rds_client = boto3.client('rds', region_name=aws_region)

    try:
        # Describe the DB instance to check its current status
        response = rds_client.describe_db_instances(DBInstanceIdentifier=db_instance_identifier)
        instance_status = response['DBInstances'][0]['DBInstanceStatus']

        print(f"DB Instance {db_instance_identifier} is in {instance_status} state.")

        # Wait for the DB instance to be available if it's not already
        if instance_status != 'available':
            print(f"Waiting for DB instance {db_instance_identifier} to become available...")
            rds_client.wait_for_db_instance_available(DBInstanceIdentifier=db_instance_identifier)
            print(f"DB instance {db_instance_identifier} is now available.")

        # Modify the DB instance class
        print(f"Modifying RDS instance {db_instance_identifier} to {db_instance_class}")
        rds_client.modify_db_instance(
            DBInstanceIdentifier=db_instance_identifier,
            DBInstanceClass=db_instance_class,
            ApplyImmediately=True  # Apply the change immediately
        )
        print(f"Successfully modified RDS instance {db_instance_identifier} to {db_instance_class}")

    except rds_client.exceptions.DBInstanceNotFound:
        print(f"RDS instance {db_instance_identifier} not found.")
        raise Exception(f"Instance {db_instance_identifier} not found.")
    except rds_client.exceptions.InvalidDBInstanceState as e:
        print(f"Error modifying {db_instance_identifier}: {e}")
        raise Exception(f"Failed to modify {db_instance_identifier}.")
    except Exception as e:
        print(f"Unexpected error for {db_instance_identifier}: {e}")
        raise Exception(f"Unexpected error for {db_instance_identifier}: {str(e)}")

# Define the DAG
default_args = {
    'owner': 'airflow',
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
    'start_date': days_ago(1),
}

dag = DAG(
    'rds_instance_scaling_on_demand_parallel',
    default_args=default_args,
    description='Scale RDS instances on demand in parallel',
    schedule=None,  # Trigger manually
    catchup=False,
)

# List of RDS instances and their respective instance classes
rds_instance_details = {
    'pp-data-orcus': 'db.t4g.medium'
#    'preprod-ofac-db': 'db.t4g.small'
    # Add more instances and classes here
}

# Create a task for each RDS instance in the list
for db_instance_identifier, db_instance_class in rds_instance_details.items():
    scale_rds_task = PythonOperator(
        task_id=f'scale_{db_instance_identifier}',
        python_callable=scale_rds_instance,
        op_args=[db_instance_identifier, db_instance_class, 'ap-south-1'],  # Pass aws_region as part of op_args
        dag=dag,
    )
    db_count=$((db_count + 1))
    total_db_count=$((total_db_count + 1))
  done

  echo "  Total Databases for $instance_name: $db_count"
  echo
done
echo "Total NonPCI RDS Instance count: $instance_count "
echo "Total Databases across all instances: $total_db_count"
set -x
'''
                            sh script: scriptContent, label: ''
                        }
                    }
                }
            }
        }
    }
}
