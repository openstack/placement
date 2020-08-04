#!/bin/bash -x

WORK_DIR=$1

# create database
sudo debconf-set-selections <<MYSQL_PRESEED
mysql-server mysql-server/root_password password secret
mysql-server mysql-server/root_password_again password secret
mysql-server mysql-server/start_on_boot boolean true
MYSQL_PRESEED
sudo apt-get install -y mysql-server mysql-client libmysqlclient-dev jq parallel apache2-utils
sudo mysql -uroot -psecret -e "DROP DATABASE IF EXISTS placement;"
sudo mysql -uroot -psecret -e "CREATE DATABASE placement CHARACTER SET utf8;"
sudo mysql -uroot -psecret -e "GRANT ALL PRIVILEGES ON placement.* TO 'root'@'%' identified by 'secret';"

# Create a venv for placement to run in
python3 -m venv .placement
. .placement/bin/activate
pip3 install . PyMySQL uwsgi

# set config via environment
export OS_PLACEMENT_DATABASE__CONNECTION=mysql+pymysql://root:secret@127.0.0.1/placement?charset=utf8
export OS_PLACEMENT_DATABASE__MAX_POOL_SIZE=25
export OS_PLACEMENT_DATABASE__MAX_OVERFLOW=100
export OS_PLACEMENT_DATABASE__SYNC_ON_STARTUP=True
# Increase our chances of allocating to different providers.
export OS_PLACEMENT_PLACEMENT__RANDOMIZE_ALLOCATION_CANDIDATES=True
export OS_DEFAULT__DEBUG=True
export OS_API__AUTH_STRATEGY=noauth2
uwsgi --http :8000 --wsgi-file .placement/bin/placement-api --daemonize ${WORK_DIR}/logs/placement-api.log --processes 5 --threads 25
