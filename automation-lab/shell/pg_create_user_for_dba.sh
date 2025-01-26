#!/usr/bin/env bash

# ==============================================================================
# Read Me !
# ==============================================================================

# description :
# script to create dba user in postgresql database instances as per restricted policy
# in a specific zone

# usage :
# git clone your repo
# cd database-engineering
# sh postgresql-user-creation-dba.sh db_username@domain.tech DATA-9733 ap-south-1 filters[nonpcidsds,pcidss]

# documentation :
# https://docs.google.com/document/d/17EUUHkcJVKnELhnUdJhHpXqRDcfQp_Tk-AwzAq_eKNA/edit

# debugging
# set -x

# ==============================================================================

set -o pipefail ## fail if there is any error during "|" piping operation

unset pgUser

# script usage function
function usage(){
  echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [error    ] : missing $1"
  echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [usage    ] : /path/to/pg-dba-user-creation.sh emailId jiraId region filter[optional]"
  echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [sample   ] : /path/to/pg-dba-user-creation.sh mohamedtanveer@domain.tech DATA-9733 ap-south-1 picdss"
  echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [info     ] : quitting !"
  exit 0
}

# recursive password generation script
function randomPasswordGen(){

  # random complex database password as per the bank policy
  randomPassword=$(openssl rand -base64 18) # create complex random database login password
  # validate the password
  ## atleast 1 upper case
  ## atleast 1 lower case
  ## atleast 1 numeric
  ## atleast 1 special character
  ## length of the string should be 18 characters
  randomPasswordValidate=$(echo $randomPassword | egrep -e '[A-Z]' | egrep -e '[a-z]' | egrep -e '[0-9]' | grep -e '[!#$%^&*+\\/\]' )

  if [ -z $randomPasswordValidate ]; then
    randomPasswordGen
  else
    echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [log      ] : complex random password is generated and validated as per the password policy defined by the bank"
  fi
}

# ==============================================================================
# input variables
# ==============================================================================

emailId=${1}
jiraId=${2}
region=${3}
filter=${4}
keyPath='tmp'
database='postgres'   # default database to establish connection to the rds
updatedAt=$(date -u '+%Y-%m-%d %H:%M:%S')   # sample format 2022-09-17 13:32:46
userName=$(echo ${emailId} | cut -d '@' -f1 | tr -d '.')  # extract the email prefix, since the email id is unique accross tbe organisation
fixedFilters="grep -iv -e replica -e data-[0-9] -e temp -e testing -e -drop"  # keywrords to ignore the instances

# ==============================================================================
# sendgrid inputs
# ==============================================================================

sendgridApiKey="" #sample : SG.uS94n5maRcmh1HOmF0lmQA.YsJx0BXYGz4qsbZjk7XVa5UxWFHc1B9eC9ZR15CQ3iZU
emailTo="${emailId}"
emailFrom="noreply@domain.tech"
emailFromName="Quark Database Operations"
subject="RDS - PostgreSQL - Database Login Credentials"

# check if all the inputs values are passed
if [ -z $emailId ] || [ -z $jiraId ] || [ -z $region ] ; then
  usage 'input values'
fi

if [ -z $filter ]; then
  # using a constant filter for the grep to work if filter is not set
  filterString="grep -e "aws""
  filter='all'
else
  filterString="grep -i -e "-${filter}""
fi


# mac does not support --date switch
if [ $(uname) == 'Darwin' ];then
  validity=$(date -v +60d '+%Y-%m-%d %H:%M:%S') # sample format 2022-09-17 13:32:46
else
  validity=$(date --date='+60 days' '+%Y-%m-%d %H:%M:%S') # sample format 2022-09-17 13:32:46
fi

# check if aws secrets are configured to eexcute the aws cli commands
# echo the caller identity to get the account and user details of the scprit executor
if [ -z $AWS_ACCESS_KEY_ID ] || [ -z $AWS_SECRET_ACCESS_KEY ] || [ -z $AWS_SESSION_TOKEN ]; then
  echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [error    ] : aws session token is not set. quitting !"
  exit 0
else
  getCallerIdentity=$(aws sts get-caller-identity --output text --region us-east-1 --query 'Arn')
  echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [log      ] : caller identity : ${getCallerIdentity}"
fi

# generate the complex random password as per the policy
randomPasswordGen

# write the database login password to a local temp file
echo $randomPassword > /${keyPath}/$userName

# create complex random key to encrypt the password
encryptionKey=$(openssl rand -base64 15)

# write the ecnryption key to a local temp file
echo $encryptionKey > /${keyPath}/$userName.key

# encrypt the plain text password file
openssl aes-256-cbc -a -salt -k $encryptionKey -in /${keyPath}/$userName -out /${keyPath}/${userName}.encrypted

# remove plain text password local file
rm -rf /${keyPath}/$userName

# rds postgresql master instance list
instances=$(aws rds describe-db-instances --region $region \
  --query 'DBInstances[?Engine==`postgres`].[Endpoint.Address]' \
  --output text | $fixedFilters | ${filterString} | sed 's/ /\n/g')

if [ $(echo $instances | sed 's/ /\n/g' | wc -l) -lt 1 ]; then
    echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [error    ] : no rds instances in the mentioned region"
fi


if [ -z $PGUSER ]; then

  read -p "$(date -u '+%Y-%m-%d %H:%M:%S') : [notice   ] : proceed creating the DBA user with RDS Master user credentials ? (yes/no) :" feedback00

  if [ -z $feedback00 ];then
    echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [error    ] : no input. quitting !"
    exit 0
  else

    if [ ${feedback00} == 'yes' ] || [ ${feedback00} == 'Yes' ] || [ ${feedback00} == 'YES' ] || [ ${feedback00} == 'Y' ] || [ ${feedback00} == 'y' ] ;then

        pgMasterUser='rdsMaster'

        echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [notice   ] : enter password for RDS.MasterUser $pgMasterUser !!!"

        read -s feedbackPgUserPass

        if [ -z ${feedbackPgUserPass} ];then
          echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [error    ] : no password entered. quitting !"
          exit 0
        else
          export PGPASSWORD=$feedbackPgUserPass
        fi

    elif [ ${feedback00} == 'no' ] || [ ${feedback00} == 'No' ] || [ ${feedback00} == 'NO' ] || [ ${feedback00} == 'N' ] || [ ${feedback00} == 'n' ] ;then

      pgMasterUser='dbaUser'

      read -p "$(date -u '+%Y-%m-%d %H:%M:%S') : [notice   ] : enter your database userName : " feedbackPgUserName

      if [ -z ${feedbackPgUserName} ];then
        echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [error    ] : no userName entered. quitting !"
        exit 0
      else
        pgUser=$feedbackPgUserName

        echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [notice   ] : enter password for user $pgUser !!!"

        read -s feedbackPgUserPass

        if [ -z ${feedbackPgUserPass} ];then
          echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [error    ] : no password entered. quitting !"
          exit 0
        else
          export PGPASSWORD=${feedbackPgUserPass}
        fi

      fi

    else
      echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [error    ] : unknown input. quitting !"
      exit 0
    fi
  fi

else
  echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [error    ] : looks like script was interrupted in the previous execution. Please execute 'unset PGUSER' and re run the script"
  exit 0
fi

# ==============================================================================
# create database user or reset password if user already exists
# ==============================================================================

# loop through each instances
for instance in $instances; do

  # extract the identifier from the endpoint
  dbInstanceIdentifier=$(echo $instance | cut -d '.' -f1 )

  if [ $pgMasterUser == 'rdsMaster' ]; then
    # RDS pg master user
    pgUser=$(aws rds describe-db-instances --output text --region $region --db-instance-identifier $dbInstanceIdentifier --query 'DBInstances[*].[MasterUsername]' )

    # both the users are same in this context
    # this is to use in the grant role
    pgMasterRole=$pgUser

    setRoleString='-- this user has the required permissions'
  else
    pgMasterRole=$(aws rds describe-db-instances --output text --region $region --db-instance-identifier $dbInstanceIdentifier --query 'DBInstances[*].[MasterUsername]' )
    setRoleString="SET ROLE ${pgMasterRole};"
  fi


  # RDS PG port
  dbPort=$(aws rds describe-db-instances --output text --region $region --db-instance-identifier $dbInstanceIdentifier --query 'DBInstances[*].[Endpoint.Port]' )

  if [ -z $dbPort ]; then
    echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [error    ] : unbale to fetch the RDS Endpoint.Port . quitting !"
    exit 0
  fi

  # check if user exists in the db instance
  checkUser=$(psql -v ON_ERROR_STOP=1 -U $pgUser -h ${instance} -p ${dbPort} -d $database -X -Aqt -c "select rolname from pg_roles where rolname='$userName';")

  if [ $? -ne 0 ]; then
    echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [error    ] : Invalid Password. Enter valid password and retry. Quitting !"
    exit 0
  fi

  # check if user does not exist
  if [ -z $checkUser ]; then

      # create user
      PGOPTIONS='--client-min-messages=error' psql -v ON_ERROR_STOP=1 -U ${pgUser} -h ${instance} -p ${dbPort} -d $database -X -Aqt <<EOF
        ${setRoleString}
        SET log_statement ='none';
        CREATE USER ${userName} WITH ENCRYPTED PASSWORD '${randomPassword}' VALID UNTIL '$validity';
        RESET log_statement;
        COMMENT ON ROLE ${userName} IS 'email : ${emailId}, jira : ${jiraId}, createdat : ${updatedAt}';
        GRANT ${pgMasterRole} TO ${userName};
        GRANT rds_superuser TO ${userName};
        ALTER USER ${userName} SET statement_timeout = '15min' ;
        ALTER USER ${userName} SET idle_in_transaction_session_timeout = '15min' ;
EOF

      # error handling
      if [ $? -ne 0 ]
      then
        echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [error    ] : User creation failed in the RDS instance ${dbInstanceIdentifier}"
        echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [hint     ] : check if master role is created and rerun the script"
        exit 1
      else
        echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [log      ] : user ${userName} has been created in the instance ${dbInstanceIdentifier}"
      fi

  else

      # reset the password if already exists
      PGOPTIONS='--client-min-messages=error' psql -v ON_ERROR_STOP=1 -U ${pgUser} -h ${instance} -p ${dbPort} -d $database -X -Aqt <<EOF
        ${setRoleString}
        SET log_statement ='none';
        ALTER USER ${userName} WITH ENCRYPTED PASSWORD '${randomPassword}' VALID UNTIL '$validity';
        RESET log_statement;
        COMMENT ON ROLE ${userName} IS 'email : ${emailId}, jira : ${jiraId}, updatedAt : ${updatedAt}';
        GRANT rds_replication TO ${userName};
        GRANT ${pgMasterRole} TO ${userName};
        ALTER USER ${userName} SET statement_timeout = '15min' ;
        ALTER USER ${userName} SET idle_in_transaction_session_timeout = '15min' ;
EOF

        # error handling
        if [ $? -ne 0 ];then
          echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [error    ] : User creation failed in the instance ${dbInstanceIdentifier}"
          echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [error    ] : fix the error and rerun the script. quitting !"
          exit 1
        else
          echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [log      ] : user ${userName} already exists, password has been reset in the instance ${dbInstanceIdentifier}"
        fi

  fi

done # end of instances loop

# share the decryption key in the external channel
echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [info     ] : Encrypted Password File : '/${keyPath}/$userName.encrypted'"

# share the decryption key in the external channel
echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [info     ] : User creation / password reset for the target instances : ${filter}"

# echo the command to decrypt in console output for reference
echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [info     ] : Decryption Command : 'openssl aes-256-cbc -a -d -salt -in $userName.encrypted'"

# ==============================================================================
# send the password decryption key through email
# ==============================================================================

# construct email body
bodyHtml="BuildDate : ${updatedAt} \n\nUserName : ${userName} \n\nDecryptionKey : ${encryptionKey} \n\nDecryptionCommand : 'openssl aes-256-cbc -a -d -salt -in ${userName}.encrypted' \n\nEncryptedPassword : Will be shared in a private communication \n\nTargetInstances : ${filter} \n\n"

mailData='{"personalizations": [{"to": [{"email": "'${emailTo}'"}]}],"from": {"email": "'${emailFrom}'",
 "name": "'${emailFromName}'"},"subject": "'${subject}'","content": [{"type": "text/plain", "value": "'${bodyHtml}'"}] }'

# invoke the sendgrid api
curl -s --request POST \
  --url https://api.sendgrid.com/v3/mail/send \
  --header 'Authorization: Bearer '${sendgridApiKey} \
  --header 'Content-Type: application/json' \
  --data "${mailData}" \
  --globoff

# error handling
if [ $? -ne 0 ];then
  echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [error    ] : Unable to send the decryption key to ${emailId}"
  echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [info     ] : Share the below decryption key manually"
  echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [info     ] : Decryption Key : /${keyPath}/${userName}.key"
  echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [warning  ] : Investigate the failure and fix it"
  echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [warning  ] : Decryption key has to be deleted manually"
else
  echo "$(date -u '+%Y-%m-%d %H:%M:%S') : [info     ] : Successfully sent the decryption key to ${emailId}"
  rm -rf /${keyPath}/${userName}.key
fi

exit 0

# ==============================================================================
# todo
# ==============================================================================

# https://drive.google.com/drive/folders/1kcYoHcBrpVmiGLRDShRAs6N2oIjxg_cK
# 1. [open] new password prompt during database login after password reset
# 2. [open] input validation like email, jira etc
# 3. [clos] decouple the decryption key and encrypted passwords.

# end of script
