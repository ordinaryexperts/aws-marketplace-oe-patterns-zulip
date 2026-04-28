# Marketplace Reprice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable `marketplace_reprice.py` tool that flattens an Offer's `UsageBasedPricingTerm` rate card to a single per-hour price (per pattern config), then apply it to Zulip as the smoke test before rolling out to the other 7 patterns.

**Architecture:** Mirrors the existing `marketplace_rebrand.py` design. (1) In `aws-marketplace-utilities`, add `scripts/marketplace_reprice.py` (CLI) + `scripts/marketplace_reprice_lib.py` (pure helpers) + tests. The script reads `marketplace_config.yaml`, discovers (or accepts) the offer ID for the product, fetches the offer's current `UsageBasedPricingTerm`, mutates every `Price` to the configured flat value, and submits an `UpdatePricingTerms` change set against the `Offer@1.0` entity. (2) In `aws-marketplace-oe-patterns-zulip`, add `flat_price` to `marketplace_config.yaml`, add `marketplace-reprice{,-dry-run}` Makefile targets that fetch the script (same pattern as `marketplace_rebrand`), and verify end-to-end on the Zulip offer.

**Tech Stack:** Python 3.12, boto3, PyYAML, pytest, AWS Marketplace Catalog API (`Offer@1.0` entity, `UpdatePricingTerms` change type), Docker devenv image.

**Why separate from `marketplace_rebrand.py`:** different entity (`Offer@1.0` vs `AmiProduct@1.0`), different lifecycle (rebrand is one-shot, repricing recurs), different failure modes. Bundling would force every reprice to also touch product info, which is wrong.

---

## File Structure

**`aws-marketplace-utilities` (new release, e.g. 1.10.0):**
- Create: `scripts/marketplace_reprice.py` — CLI entry point (arg parse, AWS calls, dry-run)
- Create: `scripts/marketplace_reprice_lib.py` — pure helpers (config loading, offer discovery, change-set builder)
- Create: `scripts/tests/test_marketplace_reprice_lib.py` — pytest unit tests
- Modify: `CHANGELOG.md` — new release entry

**`aws-marketplace-oe-patterns-zulip`:**
- Modify: `marketplace_config.yaml` — add `flat_price: "0.02"` (and optionally `offer_id` for explicit pinning)
- Modify: `Makefile` — add `marketplace-reprice` + `marketplace-reprice-dry-run` targets; bump `REBRAND_SCRIPT_VERSION` consumer to also fetch the reprice script (or use a separate `REPRICE_SCRIPT_VERSION` for cleanliness)
- Modify: `.gitignore` — ignore the downloaded `scripts/marketplace_reprice*.py`
- Modify: `CHANGELOG.md` — `# Unreleased` entry for repricing

---

## Phase A — `aws-marketplace-utilities`: build the tool

Working dir: `/home/dylan/src/oe/patterns/aws-marketplace-utilities/`

### Task 1: Scaffold + `load_flat_price` helper

**Files:**
- Create: `scripts/marketplace_reprice_lib.py`
- Create: `scripts/tests/test_marketplace_reprice_lib.py`

- [ ] **Step 1: Create the lib module with a placeholder**

File: `scripts/marketplace_reprice_lib.py`
```python
"""Pure helpers for marketplace_reprice — no AWS SDK calls, no I/O."""
from __future__ import annotations

from typing import Any


def load_flat_price(config: dict[str, Any]) -> str:
    """Extract and validate flat_price from a marketplace_config dict.

    Returns the price as a string (the API wants strings, not floats).
    Raises ValueError if missing or not a non-empty string.
    """
    raise NotImplementedError  # fleshed out below
```

- [ ] **Step 2: Write failing tests**

File: `scripts/tests/test_marketplace_reprice_lib.py`
```python
import pytest
from scripts.marketplace_reprice_lib import load_flat_price


def test_load_flat_price_happy_path():
    assert load_flat_price({"flat_price": "0.02"}) == "0.02"


def test_load_flat_price_missing_raises():
    with pytest.raises(ValueError, match="flat_price"):
        load_flat_price({})


def test_load_flat_price_empty_raises():
    with pytest.raises(ValueError, match="flat_price"):
        load_flat_price({"flat_price": ""})


def test_load_flat_price_non_string_raises():
    # A YAML float would be a footgun: "0.20" != "0.2" after str(float).
    # Force authors to quote the value.
    with pytest.raises(ValueError, match="string"):
        load_flat_price({"flat_price": 0.02})
```

- [ ] **Step 3: Run tests, expect 4 failures (NotImplementedError + missing imports)**

```bash
cd /home/dylan/src/oe/patterns/aws-marketplace-utilities
python3 -m pytest scripts/tests/test_marketplace_reprice_lib.py -v
```
Expected: 4 failed.

- [ ] **Step 4: Implement `load_flat_price`**

Replace the placeholder in `scripts/marketplace_reprice_lib.py`:
```python
def load_flat_price(config: dict[str, Any]) -> str:
    val = config.get("flat_price")
    if val is None or val == "":
        raise ValueError("config missing required 'flat_price' field")
    if not isinstance(val, str):
        raise ValueError(
            f"'flat_price' must be a quoted string in YAML "
            f"(got {type(val).__name__}: {val!r})"
        )
    return val
```

- [ ] **Step 5: Run tests, expect all pass**

```bash
python3 -m pytest scripts/tests/test_marketplace_reprice_lib.py -v
```
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add scripts/marketplace_reprice_lib.py scripts/tests/test_marketplace_reprice_lib.py
git commit -m "feat(marketplace_reprice): scaffold lib + load_flat_price"
```

---

### Task 2: `flatten_usage_pricing` — pure rate-card mutator

**Files:**
- Modify: `scripts/marketplace_reprice_lib.py`
- Modify: `scripts/tests/test_marketplace_reprice_lib.py`

This function takes the offer's existing `UsageBasedPricingTerm` (as returned by `describe-entity`) and a target price string, and returns a new term with every `Price` set to that target. Pure read-modify-write; no AWS calls.

- [ ] **Step 1: Write failing tests**

Append to `scripts/tests/test_marketplace_reprice_lib.py`:
```python
from scripts.marketplace_reprice_lib import flatten_usage_pricing


def _sample_term():
    return {
        "Type": "UsageBasedPricingTerm",
        "CurrencyCode": "USD",
        "RateCards": [
            {
                "RateCard": [
                    {"DimensionKey": "m5.large", "Price": "0.02"},
                    {"DimensionKey": "m5.xlarge", "Price": "0.03"},
                    {"DimensionKey": "m5.24xlarge", "Price": "0.73"},
                ]
            }
        ],
    }


def test_flatten_sets_every_price():
    flat = flatten_usage_pricing(_sample_term(), "0.02")
    prices = [d["Price"] for d in flat["RateCards"][0]["RateCard"]]
    assert prices == ["0.02", "0.02", "0.02"]


def test_flatten_preserves_dimension_keys_and_currency():
    flat = flatten_usage_pricing(_sample_term(), "0.02")
    keys = [d["DimensionKey"] for d in flat["RateCards"][0]["RateCard"]]
    assert keys == ["m5.large", "m5.xlarge", "m5.24xlarge"]
    assert flat["CurrencyCode"] == "USD"
    assert flat["Type"] == "UsageBasedPricingTerm"


def test_flatten_does_not_mutate_input():
    original = _sample_term()
    flatten_usage_pricing(original, "0.02")
    # Original third dimension was 0.73 — confirm untouched
    assert original["RateCards"][0]["RateCard"][2]["Price"] == "0.73"


def test_flatten_rejects_non_usage_term():
    bogus = {"Type": "FixedUpfrontPricingTerm"}
    with pytest.raises(ValueError, match="UsageBasedPricingTerm"):
        flatten_usage_pricing(bogus, "0.02")
```

- [ ] **Step 2: Run, expect failure (function not defined)**

```bash
python3 -m pytest scripts/tests/test_marketplace_reprice_lib.py -v
```

- [ ] **Step 3: Implement**

Append to `scripts/marketplace_reprice_lib.py`:
```python
import copy as _copy


def flatten_usage_pricing(term: dict[str, Any], flat_price: str) -> dict[str, Any]:
    """Return a deep copy of the UsageBasedPricingTerm with every Price replaced.

    Preserves DimensionKey, CurrencyCode, and overall structure. Does not mutate
    the input.
    """
    if term.get("Type") != "UsageBasedPricingTerm":
        raise ValueError(
            f"flatten_usage_pricing expected Type=UsageBasedPricingTerm, "
            f"got {term.get('Type')!r}"
        )
    out = _copy.deepcopy(term)
    for rate_card in out.get("RateCards", []):
        for dim in rate_card.get("RateCard", []):
            dim["Price"] = flat_price
    return out
```

- [ ] **Step 4: Run tests, expect all pass**

```bash
python3 -m pytest scripts/tests/test_marketplace_reprice_lib.py -v
```
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/marketplace_reprice_lib.py scripts/tests/test_marketplace_reprice_lib.py
git commit -m "feat(marketplace_reprice): flatten_usage_pricing rate-card mutator"
```

---

### Task 3: `build_update_pricing_change` — assemble the change-set entry

**Files:**
- Modify: `scripts/marketplace_reprice_lib.py`
- Modify: `scripts/tests/test_marketplace_reprice_lib.py`

Builds the full change-set element to pass to `start-change-set`. Wraps a single `UsageBasedPricingTerm` (already flattened) in the `DetailsDocument` envelope per the AWS spec.

- [ ] **Step 1: Write failing test**

Append to `scripts/tests/test_marketplace_reprice_lib.py`:
```python
from scripts.marketplace_reprice_lib import build_update_pricing_change


def test_build_update_pricing_change_shape():
    flat_term = {
        "Type": "UsageBasedPricingTerm",
        "CurrencyCode": "USD",
        "RateCards": [
            {
                "RateCard": [
                    {"DimensionKey": "m5.large", "Price": "0.02"},
                ]
            }
        ],
    }
    change = build_update_pricing_change("offer-abc-123", flat_term)
    assert change["ChangeType"] == "UpdatePricingTerms"
    assert change["Entity"] == {"Identifier": "offer-abc-123", "Type": "Offer@1.0"}
    details = change["DetailsDocument"]
    assert details["PricingModel"] == "Usage"
    assert details["Terms"] == [flat_term]
```

- [ ] **Step 2: Run, expect failure**

- [ ] **Step 3: Implement**

Append to `scripts/marketplace_reprice_lib.py`:
```python
def build_update_pricing_change(
    offer_id: str, flat_term: dict[str, Any]
) -> dict[str, Any]:
    return {
        "ChangeType": "UpdatePricingTerms",
        "Entity": {"Identifier": offer_id, "Type": "Offer@1.0"},
        "DetailsDocument": {
            "PricingModel": "Usage",
            "Terms": [flat_term],
        },
    }
```

- [ ] **Step 4: Run tests, expect 9 passed**

- [ ] **Step 5: Commit**

```bash
git add scripts/marketplace_reprice_lib.py scripts/tests/test_marketplace_reprice_lib.py
git commit -m "feat(marketplace_reprice): build_update_pricing_change builder"
```

---

### Task 4: CLI entry point with `--dry-run`, offer discovery, and config override

**Files:**
- Create: `scripts/marketplace_reprice.py`

The CLI:
- Reads `marketplace_config.yaml` (path overridable)
- Resolves the offer ID via this precedence: `--offer-id` flag > `offer_id` in config > auto-discover via `list-entities`
- If auto-discover finds 0 or multiple offers (and no override), fails with a useful error listing the offer IDs found
- Fetches the offer's `UsageBasedPricingTerm`
- Asserts exactly one such term exists (fail loudly otherwise — we don't silently flatten across multiple pricing schemes)
- Calls `flatten_usage_pricing` + `build_update_pricing_change`
- `--dry-run`: prints the change-set JSON, no AWS write call
- Otherwise: submits via `start-change-set`, writes `.marketplace_changeset_pricing` (separate file from rebrand to avoid clobbering)

- [ ] **Step 1: Write the CLI**

File: `scripts/marketplace_reprice.py`
```python
#!/usr/bin/env python3
"""Flatten an AWS Marketplace Offer's UsageBasedPricingTerm to a single price.

Reads marketplace_config.yaml for product_id and flat_price. Discovers the
offer for that product (or honors offer_id / --offer-id), fetches its current
pricing, mutates every Price to the configured flat value, and submits an
UpdatePricingTerms change set.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from marketplace_reprice_lib import (
    build_update_pricing_change,
    flatten_usage_pricing,
    load_flat_price,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--config-path",
        default="marketplace_config.yaml",
        help="Path to marketplace_config.yaml (default: ./marketplace_config.yaml)",
    )
    p.add_argument(
        "--offer-id",
        default=None,
        help="Override the offer ID (skips auto-discovery and config offer_id)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the change-set JSON and exit without calling start-change-set",
    )
    return p.parse_args(argv)


def _resolve_offer_id(mpc, product_id: str, config: dict, cli_offer_id: str | None) -> str:
    if cli_offer_id:
        return cli_offer_id
    if config.get("offer_id"):
        return config["offer_id"]
    resp = mpc.list_entities(
        Catalog="AWSMarketplace",
        EntityType="Offer",
        FilterList=[{"Name": "ProductId", "ValueList": [product_id]}],
    )
    offers = resp.get("EntitySummaryList", [])
    if not offers:
        raise SystemExit(f"ERROR: no Offer entity found for product_id={product_id}")
    if len(offers) > 1:
        ids = [o["EntityId"] for o in offers]
        raise SystemExit(
            f"ERROR: multiple offers found for product_id={product_id}: {ids}\n"
            f"Set 'offer_id' in marketplace_config.yaml or pass --offer-id."
        )
    return offers[0]["EntityId"]


def _extract_usage_term(details: dict) -> dict:
    terms = details.get("Terms", [])
    usage = [t for t in terms if t.get("Type") == "UsageBasedPricingTerm"]
    if len(usage) == 0:
        raise SystemExit("ERROR: offer has no UsageBasedPricingTerm — cannot reprice")
    if len(usage) > 1:
        raise SystemExit(
            f"ERROR: offer has {len(usage)} UsageBasedPricingTerms; expected 1"
        )
    return usage[0]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = yaml.safe_load(Path(args.config_path).read_text())
    except FileNotFoundError:
        print(f"ERROR: config file not found: {args.config_path}", file=sys.stderr)
        return 2
    if not isinstance(config, dict):
        print(f"ERROR: config is not a YAML mapping: {args.config_path}", file=sys.stderr)
        return 2

    product_id = config.get("product_id")
    if not product_id:
        print("ERROR: config missing product_id", file=sys.stderr)
        return 2

    try:
        flat_price = load_flat_price(config)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    import boto3  # imported lazily so module-load is cheap and dry-run-friendly
    mpc = boto3.client("marketplace-catalog", region_name="us-east-1")

    offer_id = _resolve_offer_id(mpc, product_id, config, args.offer_id)
    print(f"Using offer: {offer_id}", file=sys.stderr)

    ent = mpc.describe_entity(Catalog="AWSMarketplace", EntityId=offer_id)
    details = ent["DetailsDocument"]
    if isinstance(details, str):
        details = json.loads(details)

    usage_term = _extract_usage_term(details)
    flat_term = flatten_usage_pricing(usage_term, flat_price)

    # Sanity report — show before/after range so the operator can spot
    # an unintended price increase before it ships.
    old_prices = sorted(set(float(d["Price"]) for d in usage_term["RateCards"][0]["RateCard"]))
    n = len(flat_term["RateCards"][0]["RateCard"])
    if old_prices:
        old_lo, old_hi = old_prices[0], old_prices[-1]
        new_p = float(flat_price)
        direction = (
            "raises" if new_p > old_hi else
            "lowers" if new_p < old_lo else
            "spans" if old_lo < new_p < old_hi else
            "no-op"
        )
        print(
            f"Flattening {n} dimensions: was ${old_lo:.2f}-${old_hi:.2f} "
            f"-> ${flat_price} ({direction})",
            file=sys.stderr,
        )

    change = build_update_pricing_change(offer_id, flat_term)

    if args.dry_run:
        print(json.dumps([change], indent=2))
        return 0

    response = mpc.start_change_set(
        Catalog="AWSMarketplace",
        ChangeSet=[
            {
                "ChangeType": change["ChangeType"],
                "Entity": change["Entity"],
                "DetailsDocument": change["DetailsDocument"],
            }
        ],
        ChangeSetName=f"reprice-{offer_id[:8]}",
    )
    cs_id = response["ChangeSetId"]
    Path(".marketplace_changeset_pricing").write_text(cs_id + "\n")
    print(f"Change set created: {cs_id}")
    print("Check status with: make marketplace-status")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Lint / syntax check**

```bash
cd /home/dylan/src/oe/patterns/aws-marketplace-utilities
python3 -c "import ast; ast.parse(open('scripts/marketplace_reprice.py').read())"
```
Expected: no output (silent success).

- [ ] **Step 3: Manual smoke test of `_extract_usage_term` + `_resolve_offer_id` indirectly via dry-run**

Wait until Phase B Task 7 — `--dry-run` requires AWS creds because offer discovery and `describe-entity` are both AWS calls. (We chose this over a separate mock to keep the script simple.)

- [ ] **Step 4: Commit**

```bash
git add scripts/marketplace_reprice.py
git commit -m "feat(marketplace_reprice): CLI entry point with offer discovery + dry-run"
```

---

### Task 5: Tag utilities release `1.10.0`

**Files:**
- Modify: `CHANGELOG.md`

Bumping to `1.10.0` (vs `1.9.x`) reflects a new feature surface. The Makefile pin in Task 7 hard-codes `1.10.0` to match.

- [ ] **Step 1: Add changelog entry**

Edit `CHANGELOG.md`. Insert above the most recent entry:
```markdown
# 1.10.0

- scripts/marketplace_reprice.py: new tool that flattens an Offer's
  UsageBasedPricingTerm to a single per-hour price (per-pattern config),
  then submits an UpdatePricingTerms change set. Companion to
  marketplace_rebrand.py — same fetch-via-Makefile pattern.
```

- [ ] **Step 2: Commit + tag**

```bash
git add CHANGELOG.md
git commit -m "1.10.0"
git tag 1.10.0
# user pushes: git push origin <branch> 1.10.0
```

**Stop here for user push before Phase B's Makefile `wget` can resolve.**

---

## Phase B — `aws-marketplace-oe-patterns-zulip`: smoke-test on Zulip

Working dir: `/home/dylan/src/oe/patterns/aws-marketplace-oe-patterns-zulip/`

### Task 6: Add `flat_price` to `marketplace_config.yaml`

**Files:**
- Modify: `marketplace_config.yaml`

- [ ] **Step 1: Append the field**

Append to `marketplace_config.yaml`:
```yaml

# Repricing — consumed by scripts/marketplace_reprice.py in utilities 1.10.0+.
# All UsageBasedPricingTerm dimensions in the offer will be set to this value.
# Quote the value to keep it as a string (the API rejects floats).
flat_price: "0.02"
```

(Optionally also add `offer_id: "50inkrlevynwjw9rqbf2ivfo6"` for explicit pinning. Zulip has only one offer, so auto-discovery works without it.)

- [ ] **Step 2: Commit**

```bash
git add marketplace_config.yaml
git commit -m "feat(marketplace): add flat_price for repricing"
```

---

### Task 7: Add Makefile targets + `.gitignore` entries

**Files:**
- Modify: `Makefile`
- Modify: `.gitignore`

- [ ] **Step 1: Update `.gitignore`**

Append to the existing rebrand block:
```
scripts/marketplace_reprice.py
scripts/marketplace_reprice_lib.py
.marketplace_changeset_pricing
```

- [ ] **Step 2: Add reprice targets to `Makefile`**

Append to `Makefile`. Reuse `REBRAND_SCRIPT_VERSION` if you want both scripts pinned to the same utilities version (cleaner), or introduce a separate `REPRICE_SCRIPT_VERSION` if you want to bump them independently. Plan assumes shared:

```make
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
```

Bump `REBRAND_SCRIPT_VERSION` to `1.10.0`:
```
REBRAND_SCRIPT_VERSION = 1.10.0
```

- [ ] **Step 3: Commit**

```bash
git add Makefile .gitignore
git commit -m "feat(makefile): marketplace-reprice targets backed by utilities 1.10.0"
```

---

### Task 8: End-to-end dry run

- [ ] **Step 1: Export prod creds and dry-run**

`marketplace-reprice-dry-run` needs AWS creds (it calls `list-entities` and `describe-entity`). Use prod since that's where the listings live.

```bash
eval "$(aws configure export-credentials --profile oe-patterns-prod --format env)"
export AWS_DEFAULT_REGION=us-east-1 AWS_REGION=us-east-1
make marketplace-reprice-dry-run
```

Expected stdout: a JSON array with one element of `ChangeType=UpdatePricingTerms`, `Entity.Identifier=50inkrlevynwjw9rqbf2ivfo6`, `Entity.Type=Offer@1.0`. The `DetailsDocument.Terms[0].RateCards[0].RateCard` should contain 67 dimensions, each with `"Price": "0.02"`. Stderr should show `Using offer: 50ink...` and `Flattened 67 dimensions to $0.02`.

- [ ] **Step 2: Manually sanity-check the JSON**

Pipe through `jq` to confirm:
```bash
make marketplace-reprice-dry-run 2>/dev/null | jq '
  .[0]
  | {
      type: .ChangeType,
      offer: .Entity.Identifier,
      pricing_model: .DetailsDocument.PricingModel,
      n_dims: (.DetailsDocument.Terms[0].RateCards[0].RateCard | length),
      n_at_002: (.DetailsDocument.Terms[0].RateCards[0].RateCard | map(select(.Price == "0.02")) | length),
      sample_dims: (.DetailsDocument.Terms[0].RateCards[0].RateCard[:3])
    }
'
```
Expected: `n_dims == 67`, `n_at_002 == 67`, `pricing_model == "Usage"`. Sample dimensions should preserve original `DimensionKey` values (e.g., `m5.large`, `c5.18xlarge`).

Do NOT proceed to Task 9 until both checks are clean. If anything is off, fix in `aws-marketplace-utilities`, tag a patch (e.g., `1.10.1`), bump the Makefile pin, re-run.

---

### Task 9: Submit for real, monitor, verify

- [ ] **Step 1: Submit**

```bash
eval "$(aws configure export-credentials --profile oe-patterns-prod --format env)"
export AWS_DEFAULT_REGION=us-east-1 AWS_REGION=us-east-1
make marketplace-reprice
```
Expected: prints `Change set created: <id>`; writes `.marketplace_changeset_pricing`.

- [ ] **Step 2: Poll status**

```bash
aws marketplace-catalog describe-change-set \
  --catalog AWSMarketplace \
  --change-set-id "$(cat .marketplace_changeset_pricing)" \
  --query '{Status:Status,Failure:FailureCode,Errors:ChangeSet[].ErrorDetailList}' \
  --output json
```
Re-run every few minutes until `Status` is `SUCCEEDED`, `FAILED`, or `CANCELLED`. Typical window: 5–15 min for pricing changes.

- [ ] **Step 3: On `SUCCEEDED`, verify the live offer**

Re-fetch and tally:
```bash
aws marketplace-catalog describe-entity \
  --catalog AWSMarketplace \
  --entity-id 50inkrlevynwjw9rqbf2ivfo6 \
  --query 'DetailsDocument.Terms[?Type==`UsageBasedPricingTerm`].RateCards[0].RateCard[]' \
  --output json \
  | python3 -c "import json,sys; r=json.load(sys.stdin); n02=sum(1 for d in r if d['Price']=='0.02'); print(f'{n02}/{len(r)} at \$0.02')"
```
Expected: `67/67 at $0.02`.

- [ ] **Step 4: On `FAILED`, inspect the error and iterate**

```bash
aws marketplace-catalog describe-change-set \
  --catalog AWSMarketplace \
  --change-set-id "$(cat .marketplace_changeset_pricing)" \
  --query 'ChangeSet[].ErrorDetailList' \
  --output json
```
Common causes: a non-pricing term being included by mistake; a malformed `Price` value (must be a string like `"0.02"`, not float `0.02`); offer in a state that doesn't accept updates (e.g., a change set is already in flight). Fix in utilities, retag, re-run.

- [ ] **Step 5: Update CHANGELOG**

Edit `CHANGELOG.md`. Under `# Unreleased`:
```markdown
# Unreleased

* Rebrand AWS Marketplace listing to "Zulip on AWS by FOSSonCloud" with new FOSSonCloud logo
* Flatten Marketplace pricing to $0.02/hr across all instance dimensions
```
(Keep the existing rebrand line if not yet committed.)

```bash
git add CHANGELOG.md
git commit -m "docs: changelog entry for flat $0.02 pricing"
```

---

## Follow-ups (out of scope for this plan)

After Zulip is verified live at flat $0.02, roll out to the other 7 affected listings. Per repo:

1. `git checkout -b feature/marketplace-reprice`
2. Add `flat_price: "0.02"` to `marketplace_config.yaml`. For PeerTube, also set `offer_id: "<active-offer-id>"` to avoid the broken duplicate offer (`07d81d54-1771-457b-b922-34283a872db7` per the Apr 2026 catalog scan — confirm before submitting).
3. Copy the same Makefile + `.gitignore` blocks (and bump `REBRAND_SCRIPT_VERSION` to `1.10.0`).
4. `make marketplace-reprice-dry-run` → confirm `n_dims` matches the seller portal numbers (40, 58, 67 vary by repo).
5. `make marketplace-reprice` → poll until `SUCCEEDED` → verify with the `describe-entity` tally command above.
6. Add a `# Unreleased` CHANGELOG entry; commit and PR.

Affected repos (per Apr 2026 scan):

| Repo | Offer ID | Dims | Notes |
|---|---|---|---|
| `aws-marketplace-oe-patterns-discourse` | (look up) | 67 | Public |
| `aws-marketplace-oe-patterns-pixelfed` | (look up) | 67 | Public, has issues |
| `aws-marketplace-oe-patterns-wordpress-main` | (look up) | 67 | Public, has issues |
| `aws-marketplace-oe-patterns-consul-democracy` | (look up) | 67 | Public |
| `aws-marketplace-oe-patterns-bluesky-pds` | (look up) | 40 | Public, has issues |
| `aws-marketplace-oe-patterns-peertube` | `4b0e2889-01ca-46e9-9f02-54b48010ddc4` (Public) | 40 | **set offer_id explicitly** — broken twin offer also exists |
| `aws-marketplace-oe-patterns-drupal` | (look up) | 58 | Restricted, has $0.01 entries — flattening to $0.02 is a price **increase**. Confirm dry-run stderr says `(raises)` or `(spans)` before submitting; double-check with stakeholder if unsure. |

Double-check per-product offer IDs with `aws marketplace-catalog list-entities --catalog AWSMarketplace --entity-type Offer --filter-list 'Name=ProductId,ValueList=<product-id>'` before each submit.

Already at flat $0.02 (no action): Mastodon, Jitsi, Open WebUI.

Consider promoting `marketplace_reprice.py` (and `marketplace_rebrand.py`) into the next devenv image release so pattern Makefiles don't need the `wget` dance.
