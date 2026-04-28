# FOSSonCloud Rebrand — Design

**Date:** 2026-04-22
**Scope:** Rebrand the Zulip pattern from "Ordinary Experts Zulip Pattern" to "Zulip on AWS by FOSSonCloud" on the AWS Marketplace, including a new product logo. Establish a repeatable tool for rolling the same rebrand out to the other ~30 pattern repos.

## Motivation

OE has adopted the "FOSSonCloud" brand for the open-source-on-AWS product line. Mastodon's Marketplace listing is already titled "Mastodon on AWS by FOSSonCloud"; the other patterns (Zulip, WordPress, Drupal, Discourse, etc.) still carry the legacy "Ordinary Experts X Pattern" title. We need to update every listing's title, descriptions, highlights, and logo.

The existing version-submission flow (`make marketplace-submit`) ships new AMIs and CFN templates but does **not** touch product metadata (title/desc/logo). UPGRADE.md confirms product metadata is intentionally out of scope for version submissions — it lives in the Marketplace Management Portal or must be updated via a separate `ChangeType=UpdateInformation` / `ChangeType=UpdateLogo` Catalog API call.

We are not using the PLF process anymore, so the API path is required.

## Deliverables

### 1. Logo asset

Direction picked in brainstorming: **cloud icon only, no pattern name.** The product title "[Pattern] on AWS by FOSSonCloud" renders right next to the logo on the Marketplace page and carries the product name; the logo only needs to convey brand.

- **Source:** `/home/dylan/Documents/patterns/logos/fossoncloud_logoonly_transparent_nobuffer.png` (1280×865, RGBA, transparent background)
- **Exported asset:** `logo.png` at **640×640**, square, padded with transparency to 1:1, PNG
- **Location per repo:** `<repo-root>/logo.png`
- **Sharing:** identical file in every pattern repo. Distinction between products comes from the title, not the icon.
- **Marketplace spec compliance:** 640 px fits the 120–640 px allowed range, 1:1 ratio, transparent background, PNG, well under 5 MB. [Source](https://www.awssome.io/blog/aws-marketplace-listing-requirements-checklist-2025)

### 2. Rebrand script

Python script that drives the AWS Marketplace Catalog API to update product metadata + logo for a single pattern. Same script reused for each pattern repo.

**File:** `/scripts/marketplace_rebrand.py` — added to `aws-marketplace-utilities`, baked into the devenv Docker image so every pattern's `make marketplace-rebrand` target can invoke it out of the box.

**Inputs:**
- `--product-id` (defaults to `marketplace_config.yaml` `product_id`)
- `--logo-path` (defaults to `logo.png`)
- `--config-path` (defaults to `marketplace_config.yaml`)
- `--dry-run` (prints intended change set, does not submit)

**`marketplace_config.yaml` extension:**

```yaml
# Existing fields (product_id, ami_access_role_arn, …) remain unchanged.

product_info:
  title: "Zulip on AWS by FOSSonCloud"
  short_description: "Zulip on AWS by FOSSonCloud is a custom AMI + open-source AWS CloudFormation template that provisions a production-ready, AWS infrastructure solution for deploying Zulip 11.6."
  long_description: |
    Zulip on AWS by FOSSonCloud is an open-source AWS CloudFormation template
    that offers an easy-to-install AWS infrastructure solution for quickly
    deploying Zulip, using both AWS and Zulip best practices.
    …
  highlights:
    - "Production-ready Zulip v11.6 site, with search, email, and caching"
    - "Integrated with AWS Certificate Manager for HTTPS support"
    - "Logs in CloudWatch Logs, Remote access via Session Manager"
  categories:
    - "Application Stacks"
    - "Media & Entertainment"
    - "Content Management"
  search_keywords:
    - "zulip"
    - "social"
    - "chat"
  sku: "OE_PATTERNS_ZULIP"
  support_description: |
    Email support offered with subscription.
    https://fossoncloud.com/products/zulip
  resources:
    - name: "FOSSonCloud Product Page"
      url:  "https://fossoncloud.com/products/zulip"  # verified 200 OK
    - name: "Github Source Code and Documentation"
      url:  "https://github.com/ordinaryexperts/aws-marketplace-oe-patterns-zulip"
    - name: "Zulip Homepage"
      url:  "https://zulip.com/"
```

**Runtime flow:**

1. Load `marketplace_config.yaml`; validate required fields.
2. Read `logo.png`; base64-encode.
3. Build a Marketplace change set with two changes:
   - `ChangeType=UpdateInformation` on the `AmiProduct` entity — title, descriptions, highlights, categories, search keywords, resources, support description, SKU.
   - `ChangeType=UpdateLogo` on the same entity — upload the new logo.
4. If `--dry-run`: print the change set JSON and exit.
5. Otherwise submit via `marketplace-catalog start-change-set`.
6. Print the change set ID and `make marketplace-status` hint.

**Failure handling:** the script exits non-zero on any API failure; the caller re-runs after fixing. No stateful retry logic.

### 3. Makefile targets

In the pattern repo's `Makefile` (not `common.mk`, per the user's global instruction), invoking the shared script from the devenv image:

```make
marketplace-rebrand: build
	docker compose run -w /code --rm devenv python3 /scripts/marketplace_rebrand.py

marketplace-rebrand-dry-run: build
	docker compose run -w /code --rm devenv python3 /scripts/marketplace_rebrand.py --dry-run
```

## Scope for this session

- Apply the rebrand + new logo to the **Zulip pattern only**.
- Leave rolling the rebrand out to the other ~30 pattern repos as a follow-up — once the Zulip rebrand validates, the same script + new `marketplace_config.yaml` block can be dropped into each repo.

## Resolved decisions

1. **Tool location:** The rebrand script lives in the shared `aws-marketplace-utilities` repo — added to `/scripts/marketplace_rebrand.py`, baked into the devenv Docker image. Each pattern repo gets a local `Makefile` target (not in `common.mk`) that invokes it.

2. **Product page URL:** `https://fossoncloud.com/products/zulip` verified — HTTP 200. Use it in the `Resources` list.

3. **SKU:** Keep `OE_PATTERNS_ZULIP` unchanged.

## Non-goals

- No AMI / CFN template changes. The 1.3.0 version is already live; this is a pure metadata update.
- No regeneration of the PLF spreadsheet (user confirmed PLF is no longer in use).
- No changes to the plf_config.yaml file (can be deleted in a later cleanup once all listings are rebranded).
