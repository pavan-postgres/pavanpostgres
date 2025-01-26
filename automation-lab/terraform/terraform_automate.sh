#!/usr/bin/env bash

# ==============================================================================
# Read Me !
# ==============================================================================

# description :
# script to automate the terraform plan and apply for multiple RDS instances

# usage :
# sh terraform_automate.sh

# documentation :
# https://registry.terraform.io/modules/terraform-aws-modules/rds/aws/latest

# debugging
# set -x

# ==============================================================================
# error exit
set -e

# ==============================================================================
# input variables
# ==============================================================================

# provide the zone where the rds instances to be deployed in parallel which are terraform ready
zoneName="zone-1"

# >> replace zonePath with absolute cloned repo Path
zonePath="/data-iac/zones/${zoneName}/rds" 

# clone the data-iac repo (which generally has modules and zones defined in below format)
# git clone git@bitbucket.org:reponame.git

# folder structure can be similar to like below:

#/data-iac
#├── README.md
#├── modules
#└── zones

#\tree -L 1 modules/rds/

#modules
#├── data.tf
#├── iam.tf
#├── kms.tf
#├── locals.tf
#├── network.tf
#├── parameter_group.tf
#├── rds.tf
#├── route53.tf
#├── security-group.tf
#├── terraform.tf
#└── variables.tf

#\tree -L 1 zones

#zones
#├── README.md
#├── zone-1
#├── zone-2
#├── ......
#├── zone-n
#└── zone-template

#\tree -L 1 zones/zone-template/rds/postgresql_template

#zones/zone-template/rds/postgresql_template
#├── README.md
#├── rds.tf
#├── terraform-plans
#├── terraform.tfvars
#└── variables.tf

# navigate to required zones rds from home directory
#cd "$zonePath" # >> example cd data-iac/zones/zone-2/rds


# list the instances which are required to be planned and applied you can apply filter for deploying specific instances only to the below command
instances=$(ls)

for instance in $instances; do

    # terraform init phase
    export initDate=$(date -u '+y%Y-m%m-d%d-h%H-m%M') && terraform -chdir="$zonePath"/"$instance" init >"$zonePath"/"$instance"/terraform.init."${initDate}".log

    if [ $? -ne 0 ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') : [error    ] : $instance : terraform initializaton failed"
        exit 1
    else
        echo "$(date '+%Y-%m-%d %H:%M:%S') : [info     ] : $instance : terraform initialization successful"
    fi

    # terraform validation phase
    terraform -chdir="$zonePath"/"$instance" validate >/dev/null 2>&1 && (echo "$(date '+%Y-%m-%d %H:%M:%S') : [info     ] : $instance : terraform validation successful") || (echo "$(date '+%Y-%m-%d %H:%M:%S') : [error    ] : $instance : terraform validation failed" && exit 1)

    # terraform format phase
    (terraform -chdir="$zonePath"/"$instance" fmt && echo "$(date '+%Y-%m-%d %H:%M:%S') : [info     ] : $instance : terraform code format successful") || (echo "$(date '+%Y-%m-%d %H:%M:%S') : [error     ] : $instance : terraform code format failed" && exit 1)

    # terraform plan phase
    # for destroying add -destroy option in the plan
    export planDate=$(date -u '+y%Y-m%m-d%d-h%H-m%M') && terraform -chdir="$zonePath"/"$instance" plan -no-color -destroy -var database_password="$(pass database_password_stage)" -out="$zonePath"/"$instance"/terraform.plan."${planDate}" >"$zonePath"/"$instance"/terraform.plan."${planDate}".log

    if [ $? -ne 0 ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') : [error    ] : $instance : terraform plan failed"
        exit 1
    else
        echo "$(date '+%Y-%m-%d %H:%M:%S') : [info     ] : $instance : terraform plan successful"

    fi

    # terraform apply phase
    export applyDate=$(date -u '+y%Y-m%m-d%d-h%H-m%M') && terraform -chdir="$zonePath"/"$instance" apply -no-color -auto-approve "$zonePath"/"$instance"/terraform.plan."${planDate}" >"$zonePath"/"$instance"/terraform.apply."${applyDate}".log &

    if [ $? -ne 0 ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') : [error    ] : $instance : terraform apply failed"
        exit 1
    else
        echo "$(date '+%Y-%m-%d %H:%M:%S') : [info     ] : $instance : terraform apply successful"
    fi

done

# end of script

# todo :
# 0.1. Maintain the success states
# 0.2. Retry from the last failed instance
# 1. explore terragrunt to optimise the above logic
