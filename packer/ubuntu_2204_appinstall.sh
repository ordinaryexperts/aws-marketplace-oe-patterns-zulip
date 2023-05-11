#
# Zulip configuration
#

# Dependencies
apt-get update && apt-get install -y gettext memcached

# Download & unpack Zulip files

ZULIP_VERSION=7.0-beta1

mkdir -p /root/zulipfiles
cd /root/zulipfiles

# from a release
wget https://github.com/zulip/zulip/releases/download/$ZULIP_VERSION/zulip-server-$ZULIP_VERSION.tar.gz
tar -xf zulip-server-$ZULIP_VERSION.tar.gz

# OR

# latest from git
# git clone https://github.com/zulip/zulip.git zulip-server-$ZULIP_VERSION

# front-end install
PUPPET_CLASSES=zulip::profile::app_frontend ./zulip-server-$ZULIP_VERSION/scripts/setup/install --self-signed-cert --no-init-db --postgresql-missing-dictionaries
