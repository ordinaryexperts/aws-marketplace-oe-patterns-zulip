-include common.mk

update-common:
	wget -O common.mk https://raw.githubusercontent.com/ordinaryexperts/aws-marketplace-utilities/1.4.0/common.mk

deploy: build
	docker-compose run -w /code/cdk --rm devenv cdk deploy \
	--require-approval never \
	--parameters AlbCertificateArn=arn:aws:acm:us-east-1:992593896645:certificate/40c05ec8-16d6-4fe2-8cbc-aecd7ae281b1 \
	--parameters AlbIngressCidr=0.0.0.0/0 \
	--parameters AsgReprovisionString=20230824.1 \
	--parameters AsgInstanceType=m5.large \
	--parameters DnsHostname=zulip-${USER}.dev.patterns.ordinaryexperts.com \
	--parameters DnsRoute53HostedZoneName=dev.patterns.ordinaryexperts.com \
	--parameters EmailIngressCidr=0.0.0.0/0 \
	--parameters EnableMobilePushNotifications=true \
	--parameters VpcId=vpc-00425deda4c835455 \
	--parameters VpcPrivateSubnet1Id=subnet-030c94b9795c6cb96 \
	--parameters VpcPrivateSubnet2Id=subnet-079290412ce63c4d5 \
	--parameters VpcPublicSubnet1Id=subnet-0c2f5d4daa1792c8d \
	--parameters VpcPublicSubnet2Id=subnet-060c39a6ded9e89d7
