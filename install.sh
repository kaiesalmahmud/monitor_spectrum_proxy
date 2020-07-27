#
# Install the RF monitor and its dependencies.
#
wget -O - http://repos.emulab.net/emulab.key | sudo apt-key add -
if [ $? -ne 0 ]; then
    echo 'apt-key add failed'
    exit 1
fi

echo "deb http://repos.emulab.net/powder/ubuntu $(. /etc/os-release ; echo $UBUNTU_CODENAME) main" | sudo tee -a /etc/apt/sources.list.d/powder.list
if [ $? -ne 0 ]; then
    echo 'creating powder.list failed'
    exit 1
fi

echo "deb http://repos.emulab.net/powder-endpoints/ubuntu $(. /etc/os-release ; echo $UBUNTU_CODENAME) main" | sudo tee -a /etc/apt/sources.list.d/powder-endpoints.list
if [ $? -ne 0 ]; then
    echo 'creating powder-endpoint.list failed'
    exit 1
fi

sudo apt-get update
if [ $? -ne 0 ]; then
    echo 'apt-get update failed'
    exit 1
fi

sudo apt-get -y install --no-install-recommends python3-rfmonitor python3-uhd uhd-host python3-tk
if [ $? -ne 0 ]; then
    echo 'apt-get install failed'
    exit 1
fi

sudo uhd_images_downloader -t b2xx
if [ $? -ne 0 ]; then
    echo 'uhd_images_downloader failed'
    exit 1
fi

sudo mkdir /etc/rfmonitor && 
   nodeid=`cat /var/emulab/boot/nodeid` &&
   echo "{ \"$nodeid\" : [\"rf0\"] }" | sudo tee -a /etc/rfmonitor/device_config.json
if [ $? -ne 0 ]; then
    echo 'Creating device_config.json failed'
    exit 1
fi

sudo cp /local/repository/etc/cal_data_ref.pkl /etc/rfmonitor
if [ $? -ne 0 ]; then
    echo 'Copying cal_data_ref.pkl failed'
    exit 1
fi
sudo cp /local/repository/etc/cal_config.json /etc/rfmonitor
if [ $? -ne 0 ]; then
    echo 'Copying cal_config.json failed'
    exit 1
fi

#
# Marker that says we completed the install. In case we have to power
# cycle to bring the B210 back to life.
#
sudo touch /etc/rfmonitor/.ready
exit 0
