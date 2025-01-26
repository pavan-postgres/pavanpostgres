pipeline {
    agent any
    stages {
        stage('aws-cli-query') {
            steps {
                withAWS(credentials: 'beta-test-creds', region: 'ap-south-1') {
                    sh('''
                        set +x
                        export AWS_ACCESS_KEY_ID=""
                        export AWS_SECRET_ACCESS_KEY=""
                        export AWS_SESSION_TOKEN=""
                        export REGION="ap-south-1"
                        set -x
                        
                        set +x
                        instances=$(aws rds describe-db-instances --query 'DBInstances[*].[DBInstanceIdentifier]' --region $REGION --output text | grep -w <pattern-rds-to-delete>)
                        set -x

                        echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [info    ] : $instances"

                        # Function to delete an RDS instance and monitor its status

                        set +x
                        delete_rds_instance() {
                            instance=$1

                            # Delete the RDS instance
                            deleted_rds=$(aws rds delete-db-instance --region $REGION --db-instance-identifier $instance --delete-automated-backups --skip-final-snapshot --output text)
                            set -x
                            
                            echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [info    ] : Deleting RDS instance $instance"

                            # Monitor the status of the delete operation
                            set +x
                            while true; do
                                status=$(aws rds describe-db-instances --db-instance-identifier $instance --query 'DBInstances[0].DBInstanceStatus' --output text --region $REGION)

                                if [ "$status" = "deleting" ]; then
                                    sleep 10  # Wait for 10 seconds before checking the status again
                                elif [ -z "$status" ]; then
                                    sleep 10  # Wait for 10 seconds before rechecking if the instance exists
                                    status=$(aws rds describe-db-instances --db-instance-identifier $instance --query 'DBInstances[0].DBInstanceStatus' --output text --region $REGION)

                                    if [ -z "$status" ]; then
                                        set -x
                                        echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [info    ] : RDS instance $instance not found. Assuming deletion is complete."
                                        break
                                    fi
                                else
                                    echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [error    ] : Deleting RDS instance $instance failed"
                                    break
                                fi
                            done
                        }

                        # Delete RDS instances in parallel
                        for instance in $instances; do
                            delete_rds_instance $instance &
                        done

                        # Wait for all background processes to complete
                        wait
                    ''')
                }
            }
        }
    }
}
