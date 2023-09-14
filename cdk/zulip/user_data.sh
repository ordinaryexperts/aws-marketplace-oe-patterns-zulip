#!/bin/bash

# aws cloudwatch
sed -i 's/ASG_APP_LOG_GROUP_PLACEHOLDER/${AsgAppLogGroup}/g' /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
sed -i 's/ASG_SYSTEM_LOG_GROUP_PLACEHOLDER/${AsgSystemLogGroup}/g' /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
systemctl enable amazon-cloudwatch-agent
systemctl start amazon-cloudwatch-agent

# reprovision if access key is rotated
# access key serial: ${SesInstanceUserAccessKeySerial}

mkdir -p /opt/oe/patterns

# secretsmanager
SECRET_ARN="${DbSecretArn}"
echo $SECRET_ARN > /opt/oe/patterns/secret-arn.txt
SECRET_NAME=$(aws secretsmanager list-secrets --query "SecretList[?ARN=='$SECRET_ARN'].Name" --output text)
echo $SECRET_NAME > /opt/oe/patterns/secret-name.txt

aws ssm get-parameter \
    --name "/aws/reference/secretsmanager/$SECRET_NAME" \
    --with-decryption \
    --query Parameter.Value \
| jq -r . > /opt/oe/patterns/secret.json

DB_PASSWORD=$(cat /opt/oe/patterns/secret.json | jq -r .password)
DB_USERNAME=$(cat /opt/oe/patterns/secret.json | jq -r .username)

RABBITMQ_SECRET_ARN="${RabbitMQSecretArn}"
echo $RABBITMQ_SECRET_ARN > /opt/oe/patterns/rabbitmq-secret-arn.txt
RABBITMQ_SECRET_NAME=$(aws secretsmanager list-secrets --query "SecretList[?ARN=='$RABBITMQ_SECRET_ARN'].Name" --output text)
echo $RABBITMQ_SECRET_NAME > /opt/oe/patterns/rabbitmq-secret-name.txt

aws ssm get-parameter \
    --name "/aws/reference/secretsmanager/$RABBITMQ_SECRET_NAME" \
    --with-decryption \
    --query Parameter.Value \
| jq -r . > /opt/oe/patterns/rabbitmq_secret.json

RABBITMQ_PASSWORD=$(cat /opt/oe/patterns/rabbitmq_secret.json | jq -r .password)
RABBITMQ_USERNAME=$(cat /opt/oe/patterns/rabbitmq_secret.json | jq -r .username)
RABBITMQ_ID=$(echo "${RabbitMQBroker.Arn}" | awk -F: '{print $NF}')

# drop RDS pem cert onto instance
mkdir -p /home/zulip/.postgresql
wget -O /home/zulip/.postgresql/root.crt https://truststore.pki.rds.amazonaws.com/${AWS::Region}/${AWS::Region}-bundle.pem

/root/check-secrets.py ${AWS::Region} ${InstanceSecretName}

aws ssm get-parameter \
    --name "/aws/reference/secretsmanager/${InstanceSecretName}" \
    --with-decryption \
    --query Parameter.Value \
| jq -r . > /opt/oe/patterns/instance.json

ACCESS_KEY_ID=$(cat /opt/oe/patterns/instance.json | jq -r .access_key_id)
AVATAR_SALT=$(cat /opt/oe/patterns/instance.json | jq -r .avatar_salt)
CAMO_KEY=$(cat /opt/oe/patterns/instance.json | jq -r .camo_key)
SECRET_ACCESS_KEY=$(cat /opt/oe/patterns/instance.json | jq -r .secret_access_key)
SECRET_KEY=$(cat /opt/oe/patterns/instance.json | jq -r .secret_key)
SHARED_SECRET=$(cat /opt/oe/patterns/instance.json | jq -r .shared_secret)
SMTP_PASSWORD=$(cat /opt/oe/patterns/instance.json | jq -r .smtp_password)
ZULIP_ORG_ID=$(cat /opt/oe/patterns/instance.json | jq -r .zulip_org_id)
ZULIP_ORG_KEY=$(cat /opt/oe/patterns/instance.json | jq -r .zulip_org_key)

cat <<EOF > /etc/zulip/zulip.conf
[machine]
puppet_classes = zulip::profile::app_frontend
deploy_type = production

[postgresql]
missing_dictionaries = true
EOF

cp /etc/zulip/settings.py /etc/zulip/settings.py.orig
cat <<EOF > /etc/zulip/settings.py
from typing import Any, Dict, Tuple

from .config import get_secret

ZULIP_ADMINISTRATOR = "zulip@${HostedZoneName}"
EXTERNAL_HOST = "${Hostname}"
ALLOWED_HOSTS = ["*"]

EMAIL_HOST = "email-smtp.${AWS::Region}.amazonaws.com"
EMAIL_HOST_USER = "$ACCESS_KEY_ID"
EMAIL_USE_TLS = True
EMAIL_PORT = 587

EMAIL_GATEWAY_PATTERN = ""
EMAIL_GATEWAY_LOGIN = ""
EMAIL_GATEWAY_IMAP_SERVER = ""
EMAIL_GATEWAY_IMAP_PORT = 993
EMAIL_GATEWAY_IMAP_FOLDER = "INBOX"

AUTHENTICATION_BACKENDS: Tuple[str, ...] = (
    "zproject.backends.EmailAuthBackend",  # Email and password; just requires SMTP setup
)

REMOTE_POSTGRES_HOST = "${DbCluster.Endpoint.Address}"

RABBITMQ_HOST = "$RABBITMQ_ID.mq.${AWS::Region}.amazonaws.com"
RABBITMQ_PORT = 5671
RABBITMQ_USE_TLS = True
## To use another RabbitMQ user than the default "zulip", set RABBITMQ_USERNAME here.
RABBITMQ_USERNAME = "$RABBITMQ_USERNAME"

REDIS_HOST = "${RedisCluster.RedisEndpoint.Address}"

MEMCACHED_LOCATION = "127.0.0.1:11211"
## To authenticate to memcached, set memcached_password in zulip-secrets.conf,
## and optionally change the default username "zulip@localhost" here.
# MEMCACHED_USERNAME = "zulip@localhost"

## Controls whether session cookies expire when the browser closes
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

## Session cookie expiry in seconds after the last page load
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7 * 2  # 2 weeks

## Controls whether or not Zulip will parse links starting with
## "file:///" as a hyperlink (useful if you have e.g. an NFS share).
ENABLE_FILE_LINKS = False

## By default, files uploaded by users and profile pictures are stored
## directly on the Zulip server.  You can configure files being instead
## stored in Amazon S3 or another scalable data store here.  See docs at:
##
##   https://zulip.readthedocs.io/en/latest/production/upload-backends.html
##
## If you change LOCAL_UPLOADS_DIR to a different path, you will also
## need to manually edit Zulip's nginx configuration to use the new
## path.  For that reason, we recommend replacing /home/zulip/uploads
## with a symlink instead of changing LOCAL_UPLOADS_DIR.
# LOCAL_UPLOADS_DIR = "/home/zulip/uploads"
S3_AUTH_UPLOADS_BUCKET = "${AssetsBucketName}"
S3_AVATAR_BUCKET = "${AvatarsBucketName}"
S3_REGION = "${AWS::Region}"
# S3_ENDPOINT_URL = None
# S3_SKIP_PROXY = True

MAX_FILE_UPLOAD_SIZE = 25
NAME_CHANGES_DISABLED = False
AVATAR_CHANGES_DISABLED = False
ENABLE_GRAVATAR = True

# GIPHY_API_KEY = "<Your API key from GIPHY>"
# PUSH_NOTIFICATION_BOUNCER_URL = ""

## The default CAMO_URI of "/external_content/" is served by the camo
## setup in the default Zulip nginx configuration.  Setting CAMO_URI
## to "" will disable the Camo integration.
CAMO_URI = ""
EOF
if [ -n "${AdminEmail}" ]; then
    sed -i 's|ZULIP_ADMINISTRATOR = .*|ZULIP_ADMINISTRATOR = "${AdminEmail}"|' /etc/zulip/settings.py
fi
if [ -n "${GiphyApiKey}" ]; then
    sed -i 's|# GIPHY_API_KEY = .*|GIPHY_API_KEY = "${GiphyApiKey}"|' /etc/zulip/settings.py
fi
if [ "${EnableIncomingEmail}" == "true" ]; then
    sed -i 's|EMAIL_GATEWAY_PATTERN = .*|EMAIL_GATEWAY_PATTERN = "%s@${Hostname}"|' /etc/zulip/settings.py
fi
if [ "${EnableMobilePushNotifications}" == "true" ]; then
    sed -i 's|# PUSH_NOTIFICATION_BOUNCER_URL = .*|PUSH_NOTIFICATION_BOUNCER_URL = "https://push.zulipchat.com"|' /etc/zulip/settings.py
fi

cat <<EOF > /etc/zulip/zulip-secrets.conf
[secrets]
avatar_salt = $AVATAR_SALT
rabbitmq_password = $RABBITMQ_PASSWORD
email_password = $SMTP_PASSWORD
shared_secret = $SHARED_SECRET
secret_key = $SECRET_KEY
camo_key = $CAMO_KEY
# memcached_password = ""
# redis_password = ""
s3_key = $ACCESS_KEY_ID
s3_secret_key = $SECRET_ACCESS_KEY
zulip_org_key = $ZULIP_ORG_KEY
zulip_org_id = $ZULIP_ORG_ID
postgres_password = $DB_PASSWORD
EOF

echo "${DbCluster.Endpoint.Address}:5432:zulip:zulip:$DB_PASSWORD" > /root/.pgpass
chmod 600 /root/.pgpass
psql -U zulip -h ${DbCluster.Endpoint.Address} -d zulip -c "ALTER ROLE zulip SET search_path TO zulip,public"
psql -U zulip -h ${DbCluster.Endpoint.Address} -d zulip -c "CREATE SCHEMA IF NOT EXISTS zulip AUTHORIZATION zulip"
rm /root/.pgpass

# postfix config
/usr/sbin/make-ssl-cert generate-default-snakeoil
echo -n '${Hostname}' > /etc/mailname
sed -i 's/\(mydestination = localhost,\) .*/\1 ${Hostname}/' /etc/postfix/main.cf
sed -i 's/myhostname = .*/myhostname = ${Hostname}/' /etc/postfix/main.cf
ESCAPED_HOSTNAME=$(echo "${Hostname}" | sed 's/\([.-]\)/\\\\\1/g')
sed -i "s|if .*|if /@$ESCAPED_HOSTNAME|" /etc/postfix/virtual
service postfix restart

su zulip -c '/home/zulip/deployments/current/scripts/setup/initialize-database'

sed -i "/ssl_certificate_key/a\    location /elb-check { access_log off; return 200 'ok'; add_header Content-Type text/plain; }" /etc/nginx/sites-available/zulip-enterprise
service nginx restart

su zulip -c '/home/zulip/deployments/current/scripts/restart-server'

success=$?
cfn-signal --exit-code $success --stack ${AWS::StackName} --resource Asg --region ${AWS::Region}
