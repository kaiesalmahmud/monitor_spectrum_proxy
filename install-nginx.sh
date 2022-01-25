#!/bin/sh

#
# This script pilfered and then reduced to a shell of its former self. 
# https://gitlab.flux.utah.edu/johnsond/k8s-profile/-/blob/master/setup-nginx.sh 
#

set -x

OURDIR=/local
WWWPUB=/local/www
SUDO=sudo
SWAPPER=`geni-get user_urn | cut -f4 -d+`

if [ -f $OURDIR/nginx-done ]; then
    exit 0
fi

sudo apt-get -y install --no-install-recommends nginx
if [ $? -ne 0 ]; then
    echo 'apt-get install nginx failed'
    exit 1
fi

$SUDO mkdir -p $WWWPUB
$SUDO chown $SWAPPER $WWWPUB
$SUDO mkdir /var/www/profile-public
$SUDO chown www-data /var/www/profile-public
$SUDO mount -o bind,ro $WWWPUB /var/www/profile-public/
echo $WWWPUB /var/www/profile-public none defaults,bind 0 0 | $SUDO tee -a /etc/fstab
cat <<EOF | $SUDO tee /etc/nginx/sites-available/profile-public
server {
        include /etc/nginx/mime.types;
        types { text/plain log; }
        listen 7998 default_server;
        listen [::]:7998 default_server;
        root /var/www/profile-public;
        index index.html;
        server_name _;
        location / {
                 autoindex on;
        }
}
EOF
$SUDO ln -s /etc/nginx/sites-available/profile-public \
    /etc/nginx/sites-enabled/profile-public
sudo systemctl enable nginx
sudo systemctl restart nginx

touch $OURDIR/nginx-done
