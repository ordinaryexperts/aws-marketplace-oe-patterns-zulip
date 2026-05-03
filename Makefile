-include common.mk

update-common:
	wget -O common.mk https://raw.githubusercontent.com/ordinaryexperts/aws-marketplace-utilities/1.9.4/common.mk

deploy: build
	docker compose run -w /code/cdk --rm devenv cdk deploy \
	--require-approval never \
	--parameters AlbCertificateArn=arn:aws:acm:us-east-1:992593896645:certificate/943928d7-bfce-469c-b1bf-11561024580e \
	--parameters AlbIngressCidr=0.0.0.0/0 \
	--parameters AsgAmiIdv200=ami-01aaaebac2a5d501e \
	--parameters AsgReprovisionString=20230824.1 \
	--parameters AsgInstanceType=m5.large \
	--parameters DnsHostname=zulip-${USER}.dev.patterns.ordinaryexperts.com \
	--parameters DnsRoute53HostedZoneName=dev.patterns.ordinaryexperts.com \
	--parameters EmailIngressCidr=0.0.0.0/0 \
	--parameters EnableMobilePushNotifications=true \
	--parameters SesCreateDomainIdentity=true

test-integration: build
	docker compose run -w /code/test/integration --rm devenv bash -c "pip3 install -q -r requirements.txt --break-system-packages && pytest -v $(INTEGRATION_TEST_FILE)"

test-integration-all: build
	docker compose run -w /code/test/integration --rm devenv bash -c "pip3 install -q -r requirements.txt --break-system-packages && pytest -v"

REBRAND_SCRIPT_VERSION = 1.10.0
REBRAND_SCRIPT_URL = https://raw.githubusercontent.com/ordinaryexperts/aws-marketplace-utilities/$(REBRAND_SCRIPT_VERSION)/scripts

fetch-rebrand-script:
	mkdir -p scripts
	wget -q -O scripts/marketplace_rebrand.py     $(REBRAND_SCRIPT_URL)/marketplace_rebrand.py
	wget -q -O scripts/marketplace_rebrand_lib.py $(REBRAND_SCRIPT_URL)/marketplace_rebrand_lib.py

marketplace-rebrand-dry-run: build fetch-rebrand-script
	docker compose run -w /code --rm devenv \
	  bash -c "PYTHONPATH=/code/scripts python3 /code/scripts/marketplace_rebrand.py --dry-run"

marketplace-rebrand: build fetch-rebrand-script
	docker compose run -w /code --rm devenv \
	  bash -c "PYTHONPATH=/code/scripts python3 /code/scripts/marketplace_rebrand.py"

fetch-reprice-script:
	mkdir -p scripts
	wget -q -O scripts/marketplace_reprice.py     $(REBRAND_SCRIPT_URL)/marketplace_reprice.py
	wget -q -O scripts/marketplace_reprice_lib.py $(REBRAND_SCRIPT_URL)/marketplace_reprice_lib.py

marketplace-reprice-dry-run: build fetch-reprice-script
	docker compose run -w /code --rm devenv \
	  bash -c "PYTHONPATH=/code/scripts python3 /code/scripts/marketplace_reprice.py --dry-run"

marketplace-reprice: build fetch-reprice-script
	docker compose run -w /code --rm devenv \
	  bash -c "PYTHONPATH=/code/scripts python3 /code/scripts/marketplace_reprice.py"
