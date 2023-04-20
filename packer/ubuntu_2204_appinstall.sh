#
# Zulip configuration
#

# Dependencies
apt-get update && apt-get install -y gettext

# Download & unpack Zulip files

mkdir -p /root/zulipfiles
cd /root/zulipfiles

# from a release
# wget https://github.com/zulip/zulip/releases/download/6.1/zulip-server-6.1.tar.gz
# tar -xf zulip-server-6.1.tar.gz

# OR

# latest from git
git clone https://github.com/zulip/zulip.git zulip-server-6.1

# front-end install
PUPPET_CLASSES=zulip::profile::app_frontend ./zulip-server-6.1/scripts/setup/install --self-signed-cert --no-init-db --postgresql-missing-dictionaries
