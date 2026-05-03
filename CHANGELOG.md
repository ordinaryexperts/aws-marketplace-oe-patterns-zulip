# 2.0.0

* Upgrade to Zulip version 12.0
* Bump versioned AMI parameter to `AsgAmiIdv200`
* Add `test/integration/` pytest suite (health + SSM-driven realm bootstrap + REST API workflow)
* Bump `common.mk` pin to 1.9.4
* Rebrand AWS Marketplace listing to "Zulip on AWS by FOSSonCloud" with new FOSSonCloud logo
* Flatten Marketplace pricing to $0.02/hr across all instance dimensions

# 1.3.0

* Upgrade base OS to Ubuntu 24.04
* Upgrade to Zulip version 11.6
* Upgrade to OE Common Constructs 4.5.1
* Upgrade to CDK 2.225.0
* Upgrade to OE Utilities 1.9.2
* Upgrade to OE devenv 2.8.3
* Adopt versioned AMI parameter (`AsgAmiIdv130`)

# 1.2.0

* Add LICENSE file
* Upgrade to Zulip version 9.4
* Upgrade to OE Common Constructs 4.1.9
* Upgrade to CDK 2.120.0
* Upgrade to OE Utilities 1.6.0
* Upgrade to OE devenv 2.5.3
* Add TaskCat test
* Add GitHub Actions for TaskCat

# 1.1.0

* Fix issue with ALB when no existing VPC given
* Fix issue with avatar bucket when provided
* Upgrade to Zulip version 7.5

# 1.0.0

* GIPHY integration
* Zulip push notification integration
* Fix full text search
* Fix issue with NLB dependency during deletion
* Initial development
