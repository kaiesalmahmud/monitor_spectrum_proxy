#!/bin/sh
#
# Install ZMC stuff.
#

wget -O - http://repos.emulab.net/emulab.key | sudo apt-key add -
if [ $? -ne 0 ]; then
    echo 'apt-key add failed'
    exit 1
fi

RELEASE="$(. /etc/os-release ; echo $UBUNTU_CODENAME)"
REPO="openzms-testing"

sudo apt-get update
sudo apt-get -y install --no-install-recommends software-properties-common

# WTF! The tabs before priority actually matter.
echo "deb http://repos.emulab.net/$REPO/ubuntu $RELEASE main" | sudo tee -a /etc/apt/sources.list.d/$REPO.list
if [ $? -ne 0 ]; then
    echo "creating $REPO failed"
    exit 1
fi
sudo apt-get update
sudo apt-get -y install --no-install-recommends python3-zmsclient python3-typer python3-lxml jq python3-attr

touch /local/zmsclient-done
