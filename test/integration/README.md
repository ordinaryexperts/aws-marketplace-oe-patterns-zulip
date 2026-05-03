# Zulip Integration Tests

Two layers of tests run against a deployed Zulip pattern stack.

## Run

```bash
# Health + infrastructure only (no realm bootstrap, fastest)
AWS_PROFILE=oe-patterns-dev make test-integration

# Realm-bootstrapped workflow tests (requires SSM access to the ASG instance)
AWS_PROFILE=oe-patterns-dev make test-integration INTEGRATION_TEST_FILE=test_workflows.py

# Everything
AWS_PROFILE=oe-patterns-dev make test-integration-all
```

The target installs `requirements.txt` inside the devenv container and runs `pytest`. Tests default to `https://zulip-${USER}.dev.patterns.ordinaryexperts.com` and the matching CFN stack `oe-patterns-zulip-${USER}`. Override via env vars:

```bash
TEST_BASE_URL=https://other-host AWS_PROFILE=oe-patterns-dev make test-integration
TEST_STACK_NAME=other-stack AWS_PROFILE=oe-patterns-dev make test-integration
```

## What is covered

- `test_health.py::TestZulipHealth` — HTTPS reachability, branding, `/api/v1/server_settings` version check, push-notification flag, response time, SSL cert, security headers.
- `test_health.py::TestZulipInfrastructure` — CloudFormation stack status, required outputs, EC2 instance state and AMI.
- `test_workflows.py::TestZulipRealmActive` — realm landing page, `/login/` returns 200, `realm_name` populated in server_settings.
- `test_workflows.py::TestZulipApi` — REST API authentication via `fetch_api_key`, `/users/me`, send + retrieve a direct message.

## Realm bootstrap

The workflow tests need a Zulip realm to exist. The `realm_credentials` fixture in `conftest.py` calls `realm_helpers.bootstrap_realm` which uses SSM (`AWS-RunShellScript`) to run `manage.py create_realm` on the ASG instance. The fixture is idempotent: if a realm already exists at the root host, it is `delete_realm`'d first so each test session uses a fresh, known-password realm.

The ASG instance is discovered via the CloudFormation stack tag `aws:cloudformation:stack-name`. The IAM principal running the tests must have `ssm:SendCommand`/`ssm:GetCommandInvocation` plus `ec2:DescribeInstances`/`cloudformation:DescribeStacks`.

## Notes

- Browser-based UI flows are not yet covered — `requests`-driven API tests cover the same ground for less complexity. If you need real browser coverage later, see `aws-marketplace-oe-patterns-mastodon/test/integration/test_workflows.py` for a Playwright pattern.
- `test_workflows.py` mutates the live realm (deletes + recreates). Do not run against production.
