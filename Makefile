-include common.mk

update-common:
	wget -O common.mk https://raw.githubusercontent.com/ordinaryexperts/aws-marketplace-utilities/1.9.2/common.mk

deploy: build
	docker compose run -w /code/cdk --rm devenv cdk deploy \
	--require-approval never \
	--parameters AlbCertificateArn=arn:aws:acm:us-east-1:992593896645:certificate/943928d7-bfce-469c-b1bf-11561024580e \
	--parameters AlbIngressCidr=0.0.0.0/0 \
	--parameters AsgAmiIdv130=ami-0a9598e01ba1af838 \
	--parameters AsgReprovisionString=20230824.1 \
	--parameters AsgInstanceType=m5.large \
	--parameters DnsHostname=zulip-${USER}.dev.patterns.ordinaryexperts.com \
	--parameters DnsRoute53HostedZoneName=dev.patterns.ordinaryexperts.com \
	--parameters EmailIngressCidr=0.0.0.0/0 \
	--parameters EnableMobilePushNotifications=true \
	--parameters SesCreateDomainIdentity=true
