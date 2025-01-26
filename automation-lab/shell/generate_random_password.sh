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
  randomPasswordValidate=$(echo $randomPassword | egrep -e '[A-Z]' | egrep -e '[a-z]' | egrep -e '[0-9]' | grep -e '[!#$%^&*+\\/\]' | grep -v -e '[+]' )

  if [ -z $randomPasswordValidate ]; then
    randomPasswordGen
  else
    echo $randomPassword
    echo "$(date '+%Y-%m-%d %H:%M:%S') : [info     ] : complex random password is generated and validated as per the password policy defined by the client"
  fi
}
