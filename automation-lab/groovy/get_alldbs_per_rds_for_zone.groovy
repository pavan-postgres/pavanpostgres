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
#HDFC UAT --- Instance Name vs DB Name Vs Total DB count in each RDS instance Vs Total DB count in all RDS instances Script 
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
    echo "  Database: $db_name"
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
