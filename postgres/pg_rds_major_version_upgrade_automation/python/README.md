# script to perform bulk RDS PostgreSQL Major version upgrades following the best practises

## steps to execute the script

## git clone the repo


## switch to the working directory


## create a python3 isolated virtual environment
python3 -m venv aws-rds-upgrade

## connect to the virtual environment
source aws-rds-upgrade/bin/activate

## install the packages
pip3 install -r requirements.txt

## verify gitignore file content to ignore pushing the sensitive configs to remote branch
cat .gitignore

## create config file
`zone_name='zone-1' cat << EOF > $zone_name.sensitive.yaml db_instance_identifiers: - rds-1 new_engine_version: "15.4"

new_template_db_parameter_group_name: "template-postgres15"

region_name: "ap-south-1"

parameter_group_backup_path: "/tmp"

database_password: ''

aws_access_key_id: "" aws_secret_access_key: "" aws_session_token: ""

EOF `

#### <~~~update the values in the config file accordingly~~~>

## execute the script

python3 major_version_upgrade.py -c zone-config.sensitive.yaml > aws-rds-upgrade.log
