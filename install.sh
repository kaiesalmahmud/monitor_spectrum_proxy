#!/bin/sh
#
# Install the RF monitor and its dependencies.
#
wget -O - http://repos.emulab.net/emulab.key | sudo apt-key add -
if [ $? -ne 0 ]; then
    echo 'apt-key add failed'
    exit 1
fi

REPO="powder"
RELEASE="$(. /etc/os-release ; echo $UBUNTU_CODENAME)"

# WTF! The tabs before priority actually matter.
echo "http://boss/mirror/repos.emulab.net/$REPO/ubuntu	priority:1" | sudo tee -a /etc/apt/emulab-$REPO-mirrorlist.txt &&
    echo "http://repos.emulab.net/$REPO/ubuntu	priority:2" | sudo tee -a /etc/apt/emulab-$REPO-mirrorlist.txt &&
    echo "deb mirror+file:/etc/apt/emulab-$REPO-mirrorlist.txt $RELEASE main" | sudo tee -a /etc/apt/sources.list.d/$REPO.list
if [ $? -ne 0 ]; then
    echo 'creating powder.list failed'
    exit 1
fi

REPO="powder-endpoints"

# WTF! The tabs before priority actually matter.
echo "http://boss/mirror/repos.emulab.net/$REPO/ubuntu	priority:1" | sudo tee -a /etc/apt/emulab-$REPO-mirrorlist.txt &&
    echo "http://repos.emulab.net/$REPO/ubuntu	priority:2" | sudo tee -a /etc/apt/emulab-$REPO-mirrorlist.txt &&
    echo "deb mirror+file:/etc/apt/emulab-$REPO-mirrorlist.txt $RELEASE main" | sudo tee -a /etc/apt/sources.list.d/$REPO.list
if [ $? -ne 0 ]; then
    echo 'creating powder.list failed'
    exit 1
fi
if [ $? -ne 0 ]; then
    echo 'creating powder-endpoints.list failed'
    exit 1
fi

sudo apt-get update
if [ $? -ne 0 ]; then
    echo 'apt-get update failed'
    exit 1
fi

sudo apt-get -y install --no-install-recommends python3-rfmonitor rfmonitor-calibration python3-tk python3-matplotlib socat tigervnc-standalone-server autocutsel fvwm
if [ $? -ne 0 ]; then
    echo 'apt-get install failed'
    exit 1
fi

sudo uhd_images_downloader -t b2xx
if [ $? -ne 0 ]; then
    echo 'uhd_images_downloader failed'
    exit 1
fi

nodeid=`cat /var/emulab/boot/nodeid` &&
    echo "{ \"devices\" : [\"${nodeid}:rf0\"], \"channels\" : {\"0\" : \"RX2\"} }" | sudo tee -a /etc/rfmonitor/device_config.json
if [ $? -ne 0 ]; then
    echo 'Creating device_config.json failed'
    exit 1
fi


# Marker that says we completed the install. In case we have to power
# cycle to bring the B210 back to life.
#
sudo touch /etc/rfmonitor/.ready
exit 0
