#!/bin/bash

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

# drop RDS pem cert onto instance
mkdir -p /home/zulip/.postgresql
wget -O /home/zulip/.postgresql/root.crt https://truststore.pki.rds.amazonaws.com/${AWS::Region}/${AWS::Region}-bundle.pem

echo 'test'
success=$?
cfn-signal --exit-code $success --stack ${AWS::StackName} --resource Asg --region ${AWS::Region}
