# FOSSonCloud Rebrand Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebrand the Zulip AWS Marketplace listing to "Zulip on AWS by FOSSonCloud" with a new cloud-mark logo, and ship a reusable rebrand script in `aws-marketplace-utilities` so the other ~30 patterns can follow.

**Architecture:** Two-repo change. (1) In `aws-marketplace-utilities`, add `scripts/marketplace_rebrand.py` — a Python CLI that reads a pattern's `marketplace_config.yaml`, builds an AWS Marketplace Catalog API change set with `UpdateInformation` + `UpdateLogo` change types, and submits it. Ship as a new utilities release tag. (2) In `aws-marketplace-oe-patterns-zulip`, add `logo.png` (the FOSSonCloud cloud mark at 640×640), extend `marketplace_config.yaml` with a new `product_info:` block, and add a `marketplace-rebrand` Makefile target that fetches the script from utilities (same pattern as `update-common`) and runs it inside the devenv container.

**Tech Stack:** Python 3.12, boto3, PyYAML, Pillow (for logo resize), pytest (unit tests), AWS Marketplace Catalog API, Docker devenv image.

---

## File Structure

**`aws-marketplace-utilities` (new release):**
- Create: `scripts/marketplace_rebrand.py` — CLI entry point + API caller
- Create: `scripts/marketplace_rebrand_lib.py` — pure-function helpers (config validation, change-set builder)
- Create: `scripts/tests/test_marketplace_rebrand_lib.py` — pytest unit tests for the pure functions
- Modify: `CHANGELOG.md` — 1.9.4 entry
- Split rationale: keeping `_lib.py` pure and side-effect-free makes it fast to unit-test without mocking the AWS SDK.

**`aws-marketplace-oe-patterns-zulip`:**
- Create: `logo.png` — 640×640 transparent PNG (square-padded from the source 1280×865 cloud mark)
- Modify: `marketplace_config.yaml` — add `product_info:` block with title/descs/highlights/categories/search_keywords/resources/support
- Modify: `Makefile` — add `marketplace-rebrand` + `marketplace-rebrand-dry-run` targets; bump `update-common` URL to utilities `1.9.4`
- Modify: `.gitignore` — ignore the downloaded `scripts/marketplace_rebrand*.py` (same pattern as `common.mk`)
- Modify: `CHANGELOG.md` — "Unreleased" entry for rebrand

---

## Phase A — `aws-marketplace-utilities`: build the tool

Working dir: `/home/dylan/src/oe/patterns/aws-marketplace-utilities/`

### Task 1: Scaffold the script package

**Files:**
- Create: `scripts/marketplace_rebrand.py`
- Create: `scripts/marketplace_rebrand_lib.py`
- Create: `scripts/tests/__init__.py` (empty)
- Create: `scripts/tests/test_marketplace_rebrand_lib.py`

- [ ] **Step 1: Create the lib module with a placeholder function**

File: `scripts/marketplace_rebrand_lib.py`
```python
"""Pure helpers for marketplace_rebrand — no AWS SDK calls, no I/O."""
from __future__ import annotations

import base64
from typing import Any


def load_product_info(config: dict[str, Any]) -> dict[str, Any]:
    """Extract and validate the product_info block from a marketplace_config dict.

    Raises ValueError if required fields are missing.
    """
    raise NotImplementedError  # fleshed out in Task 2
```

- [ ] **Step 2: Create a failing test for `load_product_info`**

File: `scripts/tests/test_marketplace_rebrand_lib.py`
```python
import pytest
from scripts.marketplace_rebrand_lib import load_product_info


def test_load_product_info_happy_path():
    cfg = {
        "product_id": "abc",
        "product_info": {
            "title": "Zulip on AWS by FOSSonCloud",
            "short_description": "Short",
            "long_description": "Long",
            "highlights": ["one", "two", "three"],
            "categories": ["Application Stacks"],
            "search_keywords": ["zulip"],
            "resources": [{"name": "Docs", "url": "https://example.com"}],
            "support_description": "Email support",
            "sku": "OE_PATTERNS_ZULIP",
        },
    }
    info = load_product_info(cfg)
    assert info["title"] == "Zulip on AWS by FOSSonCloud"
    assert info["highlights"] == ["one", "two", "three"]


def test_load_product_info_missing_block_raises():
    with pytest.raises(ValueError, match="product_info"):
        load_product_info({"product_id": "abc"})


def test_load_product_info_missing_title_raises():
    cfg = {"product_info": {"short_description": "x"}}
    with pytest.raises(ValueError, match="title"):
        load_product_info(cfg)
```

- [ ] **Step 3: Run the tests — they should all fail with `NotImplementedError`**

Run from `/home/dylan/src/oe/patterns/aws-marketplace-utilities/`:
```bash
python3 -m pytest scripts/tests/test_marketplace_rebrand_lib.py -v
```
Expected: 3 failures (NotImplementedError)

- [ ] **Step 4: Implement `load_product_info`**

Replace the placeholder in `scripts/marketplace_rebrand_lib.py`:
```python
REQUIRED_FIELDS = (
    "title",
    "short_description",
    "long_description",
    "highlights",
    "categories",
    "search_keywords",
    "resources",
    "support_description",
    "sku",
)


def load_product_info(config: dict[str, Any]) -> dict[str, Any]:
    info = config.get("product_info")
    if not isinstance(info, dict):
        raise ValueError("config missing required 'product_info' block")
    missing = [f for f in REQUIRED_FIELDS if f not in info]
    if missing:
        raise ValueError(f"product_info missing required fields: {missing}")
    return info
```

- [ ] **Step 5: Run tests — all pass**

```bash
python3 -m pytest scripts/tests/test_marketplace_rebrand_lib.py -v
```
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add scripts/marketplace_rebrand_lib.py scripts/tests/
git commit -m "feat(marketplace_rebrand): scaffold lib + load_product_info"
```

---

### Task 2: Change-set builder for `UpdateInformation`

**Files:**
- Modify: `scripts/marketplace_rebrand_lib.py` — add `build_update_information_change`
- Modify: `scripts/tests/test_marketplace_rebrand_lib.py`

- [ ] **Step 1: Write the failing test**

Add to `scripts/tests/test_marketplace_rebrand_lib.py`:
```python
from scripts.marketplace_rebrand_lib import build_update_information_change


def test_update_information_change_shape():
    product_info = {
        "title": "Zulip on AWS by FOSSonCloud",
        "short_description": "Short",
        "long_description": "Long",
        "highlights": ["a", "b"],
        "categories": ["Application Stacks"],
        "search_keywords": ["zulip"],
        "resources": [{"name": "Docs", "url": "https://example.com"}],
        "support_description": "Email support",
        "sku": "OE_PATTERNS_ZULIP",
    }
    change = build_update_information_change("prod-id-123", product_info)
    assert change["ChangeType"] == "UpdateInformation"
    assert change["Entity"] == {"Identifier": "prod-id-123", "Type": "AmiProduct@1.0"}
    details = change["DetailsDocument"]
    assert details["ProductTitle"] == "Zulip on AWS by FOSSonCloud"
    assert details["ShortDescription"] == "Short"
    assert details["LongDescription"] == "Long"
    assert details["Highlights"] == ["a", "b"]
    assert details["Categories"] == ["Application Stacks"]
    assert details["SearchKeywords"] == ["zulip"]
    assert details["Resources"] == [{"Type": "Text", "Text": "Docs", "Url": "https://example.com"}]
    assert details["SupportDescription"] == "Email support"
    assert details["Sku"] == "OE_PATTERNS_ZULIP"
```

- [ ] **Step 2: Run test — expect fail (function not defined)**

```bash
python3 -m pytest scripts/tests/test_marketplace_rebrand_lib.py::test_update_information_change_shape -v
```
Expected: ImportError / AttributeError.

- [ ] **Step 3: Implement**

Append to `scripts/marketplace_rebrand_lib.py`:
```python
def build_update_information_change(product_id: str, info: dict[str, Any]) -> dict[str, Any]:
    return {
        "ChangeType": "UpdateInformation",
        "Entity": {"Identifier": product_id, "Type": "AmiProduct@1.0"},
        "DetailsDocument": {
            "ProductTitle": info["title"],
            "ShortDescription": info["short_description"],
            "LongDescription": info["long_description"],
            "Highlights": info["highlights"],
            "Categories": info["categories"],
            "SearchKeywords": info["search_keywords"],
            "Resources": [
                {"Type": "Text", "Text": r["name"], "Url": r["url"]}
                for r in info["resources"]
            ],
            "SupportDescription": info["support_description"],
            "Sku": info["sku"],
        },
    }
```

- [ ] **Step 4: Run all tests — pass**

```bash
python3 -m pytest scripts/tests/ -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/marketplace_rebrand_lib.py scripts/tests/test_marketplace_rebrand_lib.py
git commit -m "feat(marketplace_rebrand): UpdateInformation change-set builder"
```

---

### Task 3: Change-set builder for `UpdateLogo`

**Files:**
- Modify: `scripts/marketplace_rebrand_lib.py`
- Modify: `scripts/tests/test_marketplace_rebrand_lib.py`

- [ ] **Step 1: Write the failing test**

Add to `scripts/tests/test_marketplace_rebrand_lib.py`:
```python
from pathlib import Path
from scripts.marketplace_rebrand_lib import build_update_logo_change


def test_update_logo_change_base64_encodes(tmp_path: Path):
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"\x89PNG\r\n\x1a\nFAKE")
    change = build_update_logo_change("prod-id-123", logo)
    assert change["ChangeType"] == "UpdateLogo"
    assert change["Entity"] == {"Identifier": "prod-id-123", "Type": "AmiProduct@1.0"}
    # DetailsDocument should contain a base64-encoded data URL for the logo
    assert "LogoUrl" in change["DetailsDocument"]
    logo_url = change["DetailsDocument"]["LogoUrl"]
    assert logo_url.startswith("data:image/png;base64,")
```

- [ ] **Step 2: Run test — expect fail (function not defined)**

```bash
python3 -m pytest scripts/tests/test_marketplace_rebrand_lib.py::test_update_logo_change_base64_encodes -v
```

- [ ] **Step 3: Implement**

Append to `scripts/marketplace_rebrand_lib.py`:
```python
from pathlib import Path as _Path  # local import at end of file


def build_update_logo_change(product_id: str, logo_path: _Path) -> dict[str, Any]:
    raw = _Path(logo_path).read_bytes()
    encoded = base64.b64encode(raw).decode("ascii")
    return {
        "ChangeType": "UpdateLogo",
        "Entity": {"Identifier": product_id, "Type": "AmiProduct@1.0"},
        "DetailsDocument": {
            "LogoUrl": f"data:image/png;base64,{encoded}",
        },
    }
```

- [ ] **Step 4: Run all tests — pass**

```bash
python3 -m pytest scripts/tests/ -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/marketplace_rebrand_lib.py scripts/tests/test_marketplace_rebrand_lib.py
git commit -m "feat(marketplace_rebrand): UpdateLogo change-set builder"
```

---

### Task 4: CLI entry point with `--dry-run`

**Files:**
- Modify: `scripts/marketplace_rebrand.py`

- [ ] **Step 1: Write the CLI**

Replace `scripts/marketplace_rebrand.py` with:
```python
#!/usr/bin/env python3
"""Submit a FOSSonCloud rebrand change set to the AWS Marketplace Catalog API.

Reads marketplace_config.yaml, validates product_info, builds UpdateInformation +
UpdateLogo changes, and submits them as a single change set. --dry-run prints the
change set JSON without calling AWS.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from marketplace_rebrand_lib import (
    build_update_information_change,
    build_update_logo_change,
    load_product_info,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--config-path",
        default="marketplace_config.yaml",
        help="Path to marketplace_config.yaml (default: ./marketplace_config.yaml)",
    )
    p.add_argument(
        "--logo-path",
        default="logo.png",
        help="Path to logo.png (default: ./logo.png)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the change-set JSON and exit without calling AWS",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = yaml.safe_load(Path(args.config_path).read_text())
    product_id = config.get("product_id")
    if not product_id:
        print("ERROR: config missing product_id", file=sys.stderr)
        return 2
    try:
        info = load_product_info(config)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    logo_path = Path(args.logo_path)
    if not logo_path.is_file():
        print(f"ERROR: logo file not found: {logo_path}", file=sys.stderr)
        return 2

    change_set = [
        build_update_information_change(product_id, info),
        build_update_logo_change(product_id, logo_path),
    ]

    if args.dry_run:
        # Don't leak the base64 logo blob into dry-run output; summarize instead.
        preview = [dict(c) for c in change_set]
        for c in preview:
            if c["ChangeType"] == "UpdateLogo":
                details = dict(c["DetailsDocument"])
                url = details.get("LogoUrl", "")
                details["LogoUrl"] = f"{url[:40]}...[{len(url)} chars total]"
                c["DetailsDocument"] = details
        print(json.dumps(preview, indent=2))
        return 0

    import boto3  # imported lazily so --dry-run works without AWS creds

    mpc = boto3.client("marketplace-catalog", region_name="us-east-1")
    response = mpc.start_change_set(
        Catalog="AWSMarketplace",
        ChangeSet=[
            {
                "ChangeType": c["ChangeType"],
                "Entity": c["Entity"],
                "DetailsDocument": c["DetailsDocument"],
            }
            for c in change_set
        ],
        ChangeSetName=f"rebrand-{product_id[:8]}",
    )
    change_set_id = response["ChangeSetId"]
    Path(".marketplace_changeset").write_text(change_set_id + "\n")
    print(f"Change set created: {change_set_id}")
    print("Check status with: make marketplace-status")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Manual smoke test — `--dry-run` with a minimal config**

```bash
cd /tmp && mkdir -p mp-smoke && cd mp-smoke
cat > marketplace_config.yaml <<'EOF'
product_id: "abc123"
product_info:
  title: "Zulip on AWS by FOSSonCloud"
  short_description: "Short"
  long_description: "Long"
  highlights: ["one","two","three"]
  categories: ["Application Stacks"]
  search_keywords: ["zulip"]
  resources:
    - name: "Docs"
      url: "https://example.com"
  support_description: "Email support"
  sku: "OE_PATTERNS_ZULIP"
EOF
printf '\x89PNG\r\n\x1a\nFAKE' > logo.png
PYTHONPATH=/home/dylan/src/oe/patterns/aws-marketplace-utilities/scripts \
  python3 /home/dylan/src/oe/patterns/aws-marketplace-utilities/scripts/marketplace_rebrand.py --dry-run
```
Expected: JSON printed to stdout with two elements (UpdateInformation, UpdateLogo); LogoUrl summary shows "data:image/png;base64,...[N chars total]"; exit 0.

- [ ] **Step 3: Commit**

```bash
cd /home/dylan/src/oe/patterns/aws-marketplace-utilities/
git add scripts/marketplace_rebrand.py
git commit -m "feat(marketplace_rebrand): CLI entry point + --dry-run"
```

---

### Task 5: Tag utilities release 1.9.4

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add changelog entry**

Edit `CHANGELOG.md`. Insert above `# 1.9.2`:
```markdown
# 1.9.4

- scripts/marketplace_rebrand.py: new tool for FOSSonCloud rebrand — submits
  UpdateInformation + UpdateLogo change sets to the AWS Marketplace Catalog API
  driven by a `product_info:` block in the pattern repo's marketplace_config.yaml.
```

- [ ] **Step 2: Commit + tag**

```bash
cd /home/dylan/src/oe/patterns/aws-marketplace-utilities/
git add CHANGELOG.md
git commit -m "1.9.4"
git tag 1.9.4
# (user decides whether to push; typical: git push origin main --tags)
```

**Stop here for user review before pushing.** The tag must exist on the remote (`git push origin main 1.9.4`) before Phase B's Makefile `wget` can fetch the script by version.

---

## Phase B — `aws-marketplace-oe-patterns-zulip`: apply the rebrand

Working dir: `/home/dylan/src/oe/patterns/aws-marketplace-oe-patterns-zulip/`

### Task 6: Create `logo.png` at Marketplace spec

**Files:**
- Create: `logo.png`

- [ ] **Step 1: Resize + square-pad the source cloud PNG**

Use Pillow inside the devenv container (boto3 is already there; Pillow is typically included). If not, run on host with `pip install --user Pillow`.

```bash
cd /home/dylan/src/oe/patterns/aws-marketplace-oe-patterns-zulip/
python3 <<'EOF'
from PIL import Image

src = Image.open("/home/dylan/Documents/patterns/logos/fossoncloud_logoonly_transparent_nobuffer.png").convert("RGBA")
w, h = src.size
# Resize so the longest edge is 560 px (leaves padding for the 640x640 canvas)
scale = 560 / max(w, h)
new_size = (int(w * scale), int(h * scale))
resized = src.resize(new_size, Image.LANCZOS)
# Paste centered on a 640x640 transparent canvas
canvas = Image.new("RGBA", (640, 640), (0, 0, 0, 0))
x = (640 - new_size[0]) // 2
y = (640 - new_size[1]) // 2
canvas.paste(resized, (x, y), resized)
canvas.save("logo.png", "PNG", optimize=True)
print("wrote logo.png", canvas.size)
EOF
file logo.png
ls -l logo.png
```
Expected: `logo.png: PNG image data, 640 x 640, 8-bit/color RGBA`; file size well under 5 MB.

- [ ] **Step 2: Visually confirm by opening in an image viewer / browser**

Open `logo.png`. Confirm the cloud mark is centered, transparent background, no edge cropping.

- [ ] **Step 3: Commit**

```bash
git add logo.png
git commit -m "feat: add FOSSonCloud rebrand logo"
```

---

### Task 7: Extend `marketplace_config.yaml` with `product_info`

**Files:**
- Modify: `marketplace_config.yaml`

- [ ] **Step 1: Append the product_info block**

Append to the existing `marketplace_config.yaml`:

```yaml

# Rebrand metadata — consumed by scripts/marketplace_rebrand.py in utilities 1.9.4+
product_info:
  title: "Zulip on AWS by FOSSonCloud"
  short_description: >-
    Zulip on AWS by FOSSonCloud is a custom AMI + open-source AWS CloudFormation
    template that provisions a production-ready, AWS infrastructure solution for
    deploying Zulip 11.6.
  long_description: |
    Zulip on AWS by FOSSonCloud is an open-source AWS CloudFormation template that
    offers an easy-to-install AWS infrastructure solution for quickly deploying
    Zulip, using both AWS and Zulip best practices.

    Automatically configured to support auto-scaling through AWS Autoscaling Groups,
    this solution leverages an S3 bucket for user generated content between
    application servers. It also provisions an ElastiCache Redis cluster for cache,
    an Amazon MQ RabbitMQ broker for the Zulip queue worker, and an Aurora
    PostgreSQL cluster for the database. It configures SES with Easy DKIM for
    emails, and configures Route53 with convenient DNS entries.

    The template ensures multi-level security by incorporating AWS IAM for
    federated access to resources with least privilege and AWS managed keys and
    Secrets Manager to manage secrets for encryption of data at rest and in transit.

    We support multiple availability zones using an RDS Aurora Postgresql cluster
    and EC2 Auto Scaling Groups.
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
  resources:
    - name: "FOSSonCloud Product Page"
      url:  "https://fossoncloud.com/products/zulip"
    - name: "Github Source Code and Documentation"
      url:  "https://github.com/ordinaryexperts/aws-marketplace-oe-patterns-zulip"
    - name: "Zulip Homepage"
      url:  "https://zulip.com/"
  support_description: |
    Email support offered with subscription.
    https://fossoncloud.com/products/zulip
  sku: "OE_PATTERNS_ZULIP"
```

- [ ] **Step 2: Commit**

```bash
git add marketplace_config.yaml
git commit -m "feat(marketplace): add product_info block for rebrand"
```

---

### Task 8: Add Makefile targets that fetch + run the script

**Files:**
- Modify: `Makefile`
- Modify: `.gitignore`

- [ ] **Step 1: Update `.gitignore`**

Append:
```
# scripts fetched from aws-marketplace-utilities at rebrand time
scripts/marketplace_rebrand.py
scripts/marketplace_rebrand_lib.py
.marketplace_changeset
```

- [ ] **Step 2: Bump `update-common` pin to 1.9.4**

Edit `Makefile`:
```
update-common:
	wget -O common.mk https://raw.githubusercontent.com/ordinaryexperts/aws-marketplace-utilities/1.9.4/common.mk
```
(changing `1.9.2` → `1.9.4`)

- [ ] **Step 3: Add the rebrand targets**

Append to `Makefile`:
```make
REBRAND_SCRIPT_VERSION = 1.9.4
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
```

- [ ] **Step 4: Commit**

```bash
git add Makefile .gitignore
git commit -m "feat(makefile): marketplace-rebrand targets backed by utilities 1.9.4"
```

---

### Task 9: End-to-end dry run

- [ ] **Step 1: Export dev creds and dry-run**

```bash
eval "$(aws configure export-credentials --profile oe-patterns-dev --format env)"
export AWS_DEFAULT_REGION=us-east-1 AWS_REGION=us-east-1
make marketplace-rebrand-dry-run
```
Expected: JSON change set with two elements; UpdateInformation has the new title and three highlights; UpdateLogo has a summarized LogoUrl; exit 0. **No AWS call is made.**

- [ ] **Step 2: Manually sanity-check the JSON**

Confirm in the printed output:
- `ProductTitle` == `"Zulip on AWS by FOSSonCloud"`
- `Resources[0].Url` == `"https://fossoncloud.com/products/zulip"`
- `Sku` == `"OE_PATTERNS_ZULIP"`
- `UpdateLogo` entity Identifier matches `product_id` from `marketplace_config.yaml`

Fix config + re-run if anything looks off. Don't move to Task 10 until this is clean.

---

### Task 10: Submit for real, monitor, verify

- [ ] **Step 1: Submit with prod creds**

```bash
eval "$(aws configure export-credentials --profile oe-patterns-prod --format env)"
export AWS_DEFAULT_REGION=us-east-1 AWS_REGION=us-east-1
make marketplace-rebrand
```
Expected: prints `Change set created: <id>` and writes `.marketplace_changeset`. Note the change set ID.

- [ ] **Step 2: Poll status**

```bash
make marketplace-status
```
(Re-run every few minutes until `SUCCEEDED` / `FAILED` / `CANCELLED`. Typical window: 5–30 min.)

- [ ] **Step 3: On SUCCEEDED, visit the Marketplace page**

Open `https://aws.amazon.com/marketplace/pp/prodview-<productview-id>` (the Zulip product's public URL). Verify:
- Title reads "Zulip on AWS by FOSSonCloud"
- Short description starts with "Zulip on AWS by FOSSonCloud is a custom AMI..."
- Highlights updated
- Logo is the FOSSonCloud cloud mark

- [ ] **Step 4: On FAILED, inspect the error**

```bash
eval "$(aws configure export-credentials --profile oe-patterns-prod --format env)"
aws marketplace-catalog describe-change-set --catalog AWSMarketplace \
  --change-set-id "$(cat .marketplace_changeset)" --query 'ChangeSet[].ErrorDetailList' --output json
```
Fix the reported issue (typically field validation, disallowed characters, or SKU length). Re-run `make marketplace-rebrand`.

- [ ] **Step 5: Add a CHANGELOG entry and commit**

Edit `CHANGELOG.md`. Under `# Unreleased` (above `# 1.3.0`), insert:
```markdown
# Unreleased

* Rebrand AWS Marketplace listing to "Zulip on AWS by FOSSonCloud" with new FOSSonCloud logo
```

```bash
git add CHANGELOG.md
git commit -m "docs: changelog entry for FOSSonCloud rebrand"
```

---

## Follow-ups (out of scope for this plan)

- Roll the rebrand out to the other ~30 pattern repos: for each repo, (a) drop in `logo.png` (identical file), (b) append a tailored `product_info:` block, (c) copy the two Makefile targets, (d) run `make marketplace-rebrand`.
- Delete `plf_config.yaml` across the pattern repos once all listings are rebranded and the PLF process is fully retired.
- Consider adding the rebrand script to the next devenv image release so pattern Makefiles don't need the `wget` dance.
