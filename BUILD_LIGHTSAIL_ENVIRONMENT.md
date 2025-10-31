# Building the Lightsail Environment for Deployment

## Choose Instance

Choose the App+OS Nginx Instance

## Create SSL
Run the following command and follow the prompt

/opt/bitnami/bncert-tool

## Install PSQL client to interact with the Database
Run the following commands

sudo apt update
sudo apt install postgresql-client -y
psql --version

## Create Conf file
Create .conf file in this directory /opt/bitnami/nginx/conf/server_blocks
Files available in this project, ai.factorialsystems.io.conf and app.chatcraft.cc.conf

## Reload nginx
run the following commands
sudo /opt/bitnami/ctlscript.sh restart nginx - to restart nginx
sudo /opt/bitnami/ctlscript.sh status nginx - to check nginx status

## Install Docker
Run the following commands 

sudo apt-get update
sudo apt-get install -y \
apt-transport-https \
ca-certificates \
curl \
gnupg2 \
software-properties-common

curl -fsSL https://download.docker.com/linux/debian/gpg | sudo apt-key add -

sudo add-apt-repository \
"deb [arch=amd64] https://download.docker.com/linux/debian \
$(lsb_release -cs) \
stable"

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io
sudo usermod -aG docker bitnami

sudo docker run hello-world - to test
