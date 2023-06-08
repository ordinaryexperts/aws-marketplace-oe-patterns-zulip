#
# Zulip configuration
#

# Dependencies
apt-get update && apt-get install -y gettext memcached

# Download & unpack Zulip files

ZULIP_VERSION=7.0

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

pip install boto3
cat <<EOF > /root/check-secrets.py
#!/usr/bin/env python3

import boto3
import json
import subprocess
import sys
import uuid

region_name = sys.argv[1]
secret_name = sys.argv[2]
generate_realm_link = sys.argv[3]

client = boto3.client("secretsmanager", region_name=region_name)
response = client.list_secrets(
  Filters=[{"Key": "name", "Values": [secret_name]}]
)
arn = response["SecretList"][0]["ARN"]
response = client.get_secret_value(
  SecretId=arn
)
current_secret = json.loads(response["SecretString"])
needs_update = False

NEEDED_SECRETS_WITH_SIMILAR_REQUIREMENTS = [
    "avatar_salt",
    "camo_key",
    "shared_secret",
    "zulip_org_key"
]
for secret in NEEDED_SECRETS_WITH_SIMILAR_REQUIREMENTS:
  if not secret in current_secret:
    needs_update = True
    cmd = "random_value=\$(seed=\$(date +%s%N); tr -dc '[:alnum:]' < /dev/urandom | head -c 32; echo \$seed | sha256sum | awk '{print substr(\$1, 1, 32)}'); echo \$random_value"
    output = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True).stdout.decode('utf-8').strip()
    current_secret[secret] = output
if not 'secret_key' in current_secret:
    needs_update = True
    cmd = "random_value=\$(seed=\$(date +%s%N); tr -dc 'abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)' < /dev/urandom | head -c 25; echo \$seed | sha256sum | awk '{print substr(\$1, 1, 25)}'); echo \$random_value"
    output = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True).stdout.decode('utf-8').strip()
    current_secret['secret_key'] = output
if not 'zulip_org_id' in current_secret:
    needs_update = True
    current_secret['zulip_org_id'] = str(uuid.uuid4())
if generate_realm_link == 'true' and not 'initial_new_organization_link' in current_secret:
    needs_update = True
    cmd = "su zulip -c '/home/zulip/deployments/current/manage.py generate_realm_creation_link'"
    output = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True).stdout.decode('utf-8').strip()
    current_secret['initial_new_organization_link'] = output

if needs_update:
  client.update_secret(
    SecretId=arn,
    SecretString=json.dumps(current_secret)
  )
else:
  print('Secrets already generated - no action needed.')
EOF
chown root:root /root/check-secrets.py
chmod 744 /root/check-secrets.py
