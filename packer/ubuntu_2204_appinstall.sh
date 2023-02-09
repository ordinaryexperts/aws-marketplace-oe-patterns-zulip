#
# Zulip configuration
#

# Download & unpack Zulip files
mkdir -p /root/zulipfiles
cd /root/zulipfiles
wget https://github.com/zulip/zulip/releases/download/6.1/zulip-server-6.1.tar.gz
tar -xf zulip-server-6.1.tar.gz
PUPPET_CLASSES=zulip::profile::app_frontend ./zulip-server-6.1/scripts/setup/install --self-signed-cert --no-init-db --postgresql-missing-dictionaries
