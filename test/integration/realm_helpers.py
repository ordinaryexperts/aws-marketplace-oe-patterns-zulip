"""
Helpers for bootstrapping a Zulip realm via SSM and authenticating against it.

A fresh Zulip deploy has no realm; the home page returns 404 ("No organization found")
until one is created. To run end-to-end workflow tests, we use SSM to invoke
`manage.py create_realm` on the EC2 instance, then authenticate via Zulip's API.
"""

import secrets
import string
import time
from typing import Dict, List

import requests


ADMIN_EMAIL = "admin@example.com"
ADMIN_FULL_NAME = "Test Admin"
REALM_NAME = "Test Org"
# Empty string_id means the realm is served at the root host (DnsHostname).
REALM_STRING_ID = ""


def _generate_password(length: int = 24) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _ssm_run(ssm_client, instance_id: str, commands: List[str], timeout: int = 180) -> Dict[str, str]:
    """Send a shell-script command via SSM, poll until terminal, return status + stdout/stderr."""
    response = ssm_client.send_command(
        InstanceIds=[instance_id],
        DocumentName="AWS-RunShellScript",
        Parameters={"commands": commands},
    )
    command_id = response["Command"]["CommandId"]

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(3)
        try:
            inv = ssm_client.get_command_invocation(
                CommandId=command_id,
                InstanceId=instance_id,
            )
        except ssm_client.exceptions.InvocationDoesNotExist:
            continue

        if inv["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
            return {
                "status": inv["Status"],
                "stdout": inv.get("StandardOutputContent", ""),
                "stderr": inv.get("StandardErrorContent", ""),
            }

    raise TimeoutError(f"SSM command {command_id} did not complete in {timeout}s")


def realm_is_active(base_url: str) -> bool:
    """True if the base URL is serving a Zulip realm (i.e., has a name configured)."""
    response = requests.get(f"{base_url}/api/v1/server_settings", timeout=10)
    if response.status_code != 200:
        return False
    return bool(response.json().get("realm_name"))


def _existing_realm_name(base_url: str) -> str:
    """Return the existing realm's display name, or "" if none exists."""
    try:
        response = requests.get(f"{base_url}/api/v1/server_settings", timeout=10)
        if response.status_code != 200:
            return ""
        return response.json().get("realm_name") or ""
    except requests.RequestException:
        return ""


def bootstrap_realm(ssm_client, instance_id: str, base_url: str) -> Dict[str, str]:
    """Create a Zulip realm + admin user via `manage.py create_realm` over SSM.

    Idempotency: if a realm at the root already exists, deletes it first so each
    invocation produces a fresh realm with a known password. `delete_realm`
    prompts for the realm name interactively (the `--automated` flag does not
    bypass this), so the existing name is read from the API and piped in.
    """
    password = _generate_password()
    pw_file = "/tmp/zulip-bootstrap-pw"
    existing_name = _existing_realm_name(base_url)

    setup_cmds = [
        "set -eu",
        # Ubuntu 24.04 sets fs.protected_regular=2, which blocks even root from
        # `tee`-overwriting a file in a sticky dir (/tmp) owned by another user.
        # Remove any stale password file from a prior run before writing.
        f"sudo rm -f {pw_file}",
        f"echo {password!r} | sudo tee {pw_file} >/dev/null",
        f"sudo chown zulip:zulip {pw_file}",
        f"sudo chmod 600 {pw_file}",
    ]

    if existing_name:
        # delete_realm interactively prompts "Type the name of the realm to confirm",
        # but the comparison is actually against realm.string_id (root = ""),
        # so feed an empty line.
        setup_cmds.append(
            "echo '' | sudo -u zulip "
            "/home/zulip/deployments/current/manage.py delete_realm -r '' --automated"
        )

    create_cmd = (
        f"sudo -u zulip /home/zulip/deployments/current/manage.py create_realm "
        f"--string-id= --automated --password-file={pw_file} "
        f"'{REALM_NAME}' '{ADMIN_EMAIL}' '{ADMIN_FULL_NAME}'"
    )

    commands = setup_cmds + [create_cmd, f"sudo rm -f {pw_file}"]

    result = _ssm_run(ssm_client, instance_id, commands, timeout=240)
    if result["status"] != "Success":
        raise RuntimeError(
            f"Realm bootstrap failed via SSM: {result['status']}\n"
            f"stdout: {result['stdout']}\n"
            f"stderr: {result['stderr']}"
        )

    return {
        "email": ADMIN_EMAIL,
        "password": password,
        "full_name": ADMIN_FULL_NAME,
        "realm_name": REALM_NAME,
        "realm_string_id": REALM_STRING_ID,
    }


def fetch_api_key(base_url: str, email: str, password: str) -> str:
    """Authenticate via password and return an API key."""
    response = requests.post(
        f"{base_url}/api/v1/fetch_api_key",
        data={"username": email, "password": password},
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("result") != "success":
        raise RuntimeError(f"fetch_api_key failed: {data}")
    return data["api_key"]
