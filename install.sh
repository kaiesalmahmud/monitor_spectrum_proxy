#!/bin/sh
#
# Install the RF monitor and its dependencies.
#
wget -O - http://repos.emulab.net/emulab.key | sudo apt-key add -
if [ $? -ne 0 ]; then
    echo 'apt-key add failed'
    exit 1
fi

RELEASE="$(. /etc/os-release ; echo $UBUNTU_CODENAME)"

REPO="powder-testing"

# WTF! The tabs before priority actually matter.
echo "http://boss/mirror/repos.emulab.net/$REPO/ubuntu	priority:1" | sudo tee -a /etc/apt/emulab-$REPO-mirrorlist.txt &&
    echo "http://repos.emulab.net/$REPO/ubuntu	priority:2" | sudo tee -a /etc/apt/emulab-$REPO-mirrorlist.txt &&
    echo "deb mirror+file:/etc/apt/emulab-$REPO-mirrorlist.txt $RELEASE main" | sudo tee -a /etc/apt/sources.list.d/$REPO.list
if [ $? -ne 0 ]; then
    echo "creating $REPO failed"
    exit 1
fi

REPO="powder"

# WTF! The tabs before priority actually matter.
echo "http://boss/mirror/repos.emulab.net/$REPO/ubuntu	priority:1" | sudo tee -a /etc/apt/emulab-$REPO-mirrorlist.txt &&
    echo "http://repos.emulab.net/$REPO/ubuntu	priority:2" | sudo tee -a /etc/apt/emulab-$REPO-mirrorlist.txt &&
    echo "deb mirror+file:/etc/apt/emulab-$REPO-mirrorlist.txt $RELEASE main" | sudo tee -a /etc/apt/sources.list.d/$REPO.list
if [ $? -ne 0 ]; then
    echo "creating $REPO failed"
    exit 1
fi

REPO="powder-endpoints"

# WTF! The tabs before priority actually matter.
echo "http://boss/mirror/repos.emulab.net/$REPO/ubuntu	priority:1" | sudo tee -a /etc/apt/emulab-$REPO-mirrorlist.txt &&
    echo "http://repos.emulab.net/$REPO/ubuntu	priority:2" | sudo tee -a /etc/apt/emulab-$REPO-mirrorlist.txt &&
    echo "deb mirror+file:/etc/apt/emulab-$REPO-mirrorlist.txt $RELEASE main" | sudo tee -a /etc/apt/sources.list.d/$REPO.list
if [ $? -ne 0 ]; then
    echo "creating $REPO failed"
    exit 1
fi

sudo apt-get update
if [ $? -ne 0 ]; then
    echo 'apt-get update failed'
    exit 1
fi

sudo apt-get -y install uhd-host libuhd-dev python3-uhd
if [ $? -ne 0 ]; then
    echo 'apt-get install UHD failed'
    exit 1
fi

sudo apt-get -y install --no-install-recommends python3-rfmonitor rfmonitor-calibration python3-tk python3-matplotlib socat tigervnc-standalone-server autocutsel fvwm
if [ $? -ne 0 ]; then
    echo 'apt-get install support failed'
    exit 1
fi

sudo uhd_images_downloader -t b2xx
if [ $? -ne 0 ]; then
    echo 'uhd_images_downloader failed'
    exit 1
fi
sudo uhd_images_downloader -t x3xx
if [ $? -ne 0 ]; then
    echo 'uhd_images_downloader failed'
    exit 1
fi

# Temporary fixes.
#sudo cp -f /local/repository/files/device.py /usr/lib/python3/dist-packages/monitor/radio
#sudo cp -f /local/repository/files/iso_receiver.py /usr/lib/python3/dist-packages/monitor/radio

#
# Marker that says we completed the install. In case we have to power
# cycle to bring the B210 back to life.
#
sudo touch /etc/rfmonitor/.ready
exit 0
