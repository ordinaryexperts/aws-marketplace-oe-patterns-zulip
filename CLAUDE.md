# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

An AWS Marketplace "Pattern" that ships a custom AMI + a CDK-synthesized CloudFormation template for deploying Zulip 11.6 on AWS. The artifacts produced by this repo are (1) a Marketplace AMI built by Packer, (2) a CloudFormation template that consumers launch from the Marketplace listing, and (3) a Marketplace PLF (Product Listing Form) generated from `plf_config.yaml`.

## Development model: everything runs in Docker

All commands execute inside the `devenv` container (`ordinaryexperts/aws-marketplace-patterns-devenv:2.8.3`, defined in `Dockerfile` + `docker-compose.yml`). Do **not** run `cdk`, `taskcat`, `python`, or `pip` directly on the host — go through `make` targets, which wrap `docker compose run`.

`common.mk` is fetched from the external [`aws-marketplace-utilities`](https://github.com/ordinaryexperts/aws-marketplace-utilities) repo at pin `1.9.2` via `make update-common`. It is git-ignored and provides most `make` targets (`build`, `synth`, `deploy`, `lint`, `test-main`, `ami-ec2-build`, `plf`, `clean-*`, etc.). **Do not add targets to `common.mk`** — it is managed in the utilities repo. The repo-local `Makefile` only holds overrides for `update-common` and a dev-account-specific `deploy`.

## Common commands

Run `make update-common` first in a fresh clone. Then:

- `make build` — build the devenv Docker image (needed before most targets)
- `make synth` / `make synth-to-file` — synthesize the CloudFormation template (latter writes to `dist/template.yaml`)
- `make diff` — `cdk diff` against the deployed stack
- `make deploy` — deploys the dev stack (`oe-patterns-zulip-$USER`) with hardcoded dev parameters; edit `Makefile` locally to change them
- `make destroy` — tear down the dev stack
- `make lint` — runs the shared linter from `common.mk`
- `make ami-ec2-build` — builds the Zulip AMI in EC2 via Packer (runs `packer/ubuntu_2404_appinstall.sh`, which itself pulls pre/post-install scripts from `aws-marketplace-utilities@1.9.2`). Updates the AMI ID list in `cdk/zulip/zulip_stack.py` between the `# make ami-ec2-build` / `# End generated code block.` markers.
- `make test-main` — runs TaskCat using `test/main-test/.taskcat.yml` (synthesizes the template into `test/main-test/template.yaml` first). This is what CI runs.
- `make plf` / `make plf-skip-pricing` / `make plf-skip-region` — regenerate the Marketplace PLF spreadsheet from `plf_config.yaml`

There is no unit-test suite; correctness is validated by `cdk synth` succeeding and by TaskCat end-to-end deploys.

## Architecture

### CDK app

`cdk/app.py` → `cdk/zulip/zulip_stack.py` — single `ZulipStack` (CDK 2.225.0, Python). The stack is almost entirely composed of constructs from `oe-patterns-cdk-common` (pinned to `4.5.1` in `cdk/setup.py`): `Vpc`, `Dns`, `AssetsBucket`, `Ses`, `DbSecret`, `AuroraPostgresql`, `ElasticacheRedis`, `RabbitMQ`, `Secret`, `Asg`, `Alb`, `Util`. When something looks "missing" (parameter groups, IAM boilerplate, SG wiring), it is almost certainly coming from those shared constructs — read them in the common repo rather than re-implementing here.

Zulip-specific pieces in `zulip_stack.py`:

- **Two S3 buckets**: `AssetsBucket` (private user uploads) and `AvatarsBucket` (public-read, with `ObjectWriter` ownership and a `BucketPolicy` granting `s3:GetObject` to any principal — avatars must be publicly fetchable).
- **NLB in front of the ALB** (conditional on `EnableIncomingEmail=true`): the NLB terminates port 25 (SMTP) on the ASG and also forwards 80/443 to the ALB. When email is disabled, clients hit the ALB directly. The Route53 A-record target switches between NLB and ALB via `CfnCondition`.
- **Wildcard DNS**: a second A record for `*.{hostname}` is created so Zulip realms can use subdomains.
- **MX record** to the hostname itself (conditional on incoming email), since the NLB receives SMTP.
- **Instance-side secret**: the ASG writes to `{StackName}/instance/credentials-*` in Secrets Manager (granted by `asg_update_secret_policy`) to persist per-instance Zulip secrets (`secret_key`, `zulip_org_key`, `avatar_salt`, generated SMTP password, etc.) so subsequent instances/reboots share them.
- **User data**: `cdk/zulip/user_data.sh` is read at synth time and passed to the `Asg` construct. It uses **CloudFormation `${Var}` substitution syntax**, not shell variables — anything like `${AsgAppLogGroup}`, `${AWS::Region}`, or keys from `user_data_variables` is substituted by CFN during stack create. Shell variables inside the script are escaped (`\$VAR`) or use `$(...)` where needed. Edit carefully.

### AMI build

`packer/ami.json` + `packer/ubuntu_2404_appinstall.sh` build an Ubuntu 24.04 AMI with Zulip `11.6` pre-installed. `ami.json` uses a `source_ami_filter` pinned to Canonical's `hvm-ssd-gp3` 24.04 images so Packer always picks the latest patched base at build time. The provisioning script delegates pre/post-install common work to scripts pulled from `aws-marketplace-utilities@1.9.2`. To bump Zulip, edit `ZULIP_VERSION` in `ubuntu_2404_appinstall.sh` and rebuild with `make ami-ec2-build`.

### Template versioning

`template_version` in `zulip_stack.py` comes from the `TEMPLATE_VERSION` env var, falls back to `git describe --always`, and ultimately to `"CICD"`. It is embedded in template metadata as `OE::Patterns::TemplateVersion`.

### CI

`.github/workflows/main.yml` runs on pushes/PRs to `develop` (and weekly on Mondays): `make update-common` → `make build` → `make test-main`, then always cleans up snapshots and logs via `make clean-snapshots-tcat` / `clean-logs-tcat`. AWS creds come from repo secrets against the OE Patterns dev account (`992593896645`).

## Upgrade Workflow

For upgrading the upstream Zulip version, follow the process in [aws-marketplace-utilities/UPGRADE.md](https://github.com/ordinaryexperts/aws-marketplace-utilities/blob/main/UPGRADE.md).

## Conventions

- Default branch for PRs is `develop`; `main` is release-tracking.
- `CHANGELOG.md` is updated per release under an `# Unreleased` heading; bump Zulip/CDK/common versions here too.
- `supported_regions.txt` is the authoritative region list used by PLF generation — keep it in sync with the `generated_ami_ids` map in `zulip_stack.py`.
- Secrets, marketplace access keys, and `.env` files never get committed (`.gitignore` already covers them, but be deliberate).
