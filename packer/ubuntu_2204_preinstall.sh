#!/bin/bash -eux

# wait for cloud-init to be done
if [ ! "$IN_DOCKER" = true ]; then
    cloud-init status --wait
fi

# apt upgrade
export DEBIAN_FRONTEND=noninteractive
apt-get -y update && apt-get -y upgrade

# install helpful utilities
apt-get -y install curl git jq ntp software-properties-common unzip vim wget zip xfsprogs

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

# install RDS SSL CA for Aurora
mkdir -p /opt/aws/rds
cd /opt/aws/rds
wget https://www.amazontrust.com/repository/AmazonRootCA1.pem
cd -
