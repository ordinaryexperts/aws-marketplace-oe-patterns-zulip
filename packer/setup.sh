#!/bin/bash -eux

# wait for cloud-init to be done
if [ ! "$IN_DOCKER" = true ]; then
    cloud-init status --wait
fi

# apt upgrade
export DEBIAN_FRONTEND=noninteractive
apt-get -y update && apt-get -y upgrade

# install helpful utilities
apt-get -y install curl git jq ntp software-properties-common unzip vim wget zip

# xfs
apt-get -y install xfsprogs

# install latest CFN utilities
apt-get -y install python3-pip
ln -s /usr/bin/pip3 /usr/bin/pip
pip install https://s3.amazonaws.com/cloudformation-examples/aws-cfn-bootstrap-py3-latest.tar.gz

# install aws cli
cd /tmp
curl https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip -o awscliv2.zip
unzip awscliv2.zip
./aws/install
cd -

# install SSM Agent
# https://docs.aws.amazon.com/systems-manager/latest/userguide/agent-install-deb.html
mkdir /tmp/ssm
cd /tmp/ssm
wget https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/debian_amd64/amazon-ssm-agent.deb
dpkg -i -E ./amazon-ssm-agent.deb
systemctl enable amazon-ssm-agent

# install CloudWatch agent
cd /tmp
curl https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb -o amazon-cloudwatch-agent.deb
dpkg -i -E ./amazon-cloudwatch-agent.deb
cd -
# collectd for metrics
apt-get -y install collectd

# Download & unpack Zulip files
mkdir -p /root/zulipfiles
cd /root/zulipfiles
wget https://github.com/zulip/zulip/releases/download/5.6/zulip-server-5.6.tar.gz
tar -xf zulip-server-5.6.tar.gz
PUPPET_CLASSES=zulip::profile::app_frontend ./zulip-server-5.6/scripts/setup/install --self-signed-cert --no-init-db

# AMI hardening

# Update the AMI tools before using them
# https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/building-shared-amis.html#public-amis-update-ami-tools
# More details
# https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/set-up-ami-tools.html
# http://www.dowdandassociates.com/blog/content/howto-install-aws-cli-amazon-elastic-compute-cloud-ec2-ami-tools/
mkdir -p /tmp/aws
mkdir -p /opt/aws
curl https://s3.amazonaws.com/ec2-downloads/ec2-ami-tools.zip -o /tmp/aws/ec2-ami-tools.zip
unzip -d /tmp/aws /tmp/aws/ec2-ami-tools.zip
mv /tmp/aws/ec2-ami-tools-* /opt/aws/ec2-ami-tools
rm -f /tmp/aws/ec2-ami-tools.zip
cat <<'EOF' > /etc/profile.d/ec2-ami-tools.sh
export EC2_AMITOOL_HOME=/opt/aws/ec2-ami-tools
export PATH=$PATH:$EC2_AMITOOL_HOME/bin
EOF
cat <<'EOF' >> /etc/bash.bashrc

# https://askubuntu.com/a/1139138
if [ -d /etc/profile.d ]; then
  for i in /etc/profile.d/*.sh; do
    if [ -r $i ]; then
      . $i
    fi
  done
  unset i
fi
EOF

# Disable password-based remote logins for root
# https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/building-shared-amis.html#public-amis-disable-password-logins-for-root
# install ssh...
apt-get -y install ssh
# Default in Ubuntu already is PermitRootLogin prohibit-password...

# Disable local root access
# https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/building-shared-amis.html#restrict-root-access
passwd -l root

# Remove SSH host key pairs
# https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/building-shared-amis.html#remove-ssh-host-key-pairs
shred -u /etc/ssh/*_key /etc/ssh/*_key.pub

# Install public key credentials
# https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/building-shared-amis.html#public-amis-install-credentials
# Default in Ubuntu already does this...

# Disabling sshd DNS checks (optional)
# https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/building-shared-amis.html#public-amis-disable-ssh-dns-lookups
# Default in Ubuntu already is UseDNS no

# AWS Marketplace Security Checklist
# https://docs.aws.amazon.com/marketplace/latest/userguide/product-and-ami-policies.html#security
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config

# remove python2.7
apt-get -y remove --purge python2.7
apt-get -y autoremove
ln -s /usr/bin/python3 /usr/bin/python

# apt cleanup
apt-get -y autoremove
apt-get -y update

# https://aws.amazon.com/articles/how-to-share-and-use-public-amis-in-a-secure-manner/
find / -name "authorized_keys" -exec rm -f {} \;
