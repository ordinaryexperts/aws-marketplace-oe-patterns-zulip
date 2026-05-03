"""
Post-realm workflow tests for Zulip.

These tests depend on the `realm_credentials` fixture, which bootstraps a fresh
realm + admin user via SSM (`manage.py create_realm`). They exercise:

- realm landing page (login form replaces the "No organization found" 404)
- API authentication (`fetch_api_key`)
- sending and reading messages via the REST API
"""

import pytest
import requests


class TestZulipRealmActive:
    """Tests that require an active Zulip realm at `base_url`."""

    def test_realm_reported_in_server_settings(self, base_url, realm_credentials):
        """`/api/v1/server_settings` reports the bootstrapped realm name."""
        response = requests.get(f"{base_url}/api/v1/server_settings", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data.get("realm_name") == realm_credentials["realm_name"], \
            f"Expected realm_name={realm_credentials['realm_name']}, got {data.get('realm_name')}"

    def test_login_page_serves_200(self, base_url, realm_credentials):
        """`/login/` returns 200 once a realm exists (was 404 pre-bootstrap)."""
        response = requests.get(f"{base_url}/login/", timeout=10, allow_redirects=False)
        assert response.status_code == 200, \
            f"/login/ returned {response.status_code}, expected 200"

    def test_homepage_redirects_to_app_or_login(self, base_url, realm_credentials):
        """Home page should serve the realm (200) instead of the 404 'No organization found'."""
        response = requests.get(base_url, timeout=10, allow_redirects=False)
        assert response.status_code in (200, 302), \
            f"Home page returned {response.status_code}, expected 200 or 302"


class TestZulipApi:
    """Authenticated REST API checks."""

    def test_fetch_api_key(self, api_key):
        """API key is non-empty (fixture computed it via fetch_api_key)."""
        assert api_key, "fetch_api_key returned an empty key"
        assert len(api_key) >= 16, f"Suspiciously short API key: {api_key!r}"

    def test_get_own_user(self, base_url, realm_credentials, api_key):
        """`/api/v1/users/me` returns the bootstrapped admin user.

        Zulip 12.0's default `email_address_visibility` masks the public `email`
        field as `userN@<realm-domain>`; the real address comes back in
        `delivery_email` (visible to the user themselves and to admins).
        """
        response = requests.get(
            f"{base_url}/api/v1/users/me",
            auth=(realm_credentials["email"], api_key),
            timeout=10,
        )
        assert response.status_code == 200, \
            f"/users/me returned {response.status_code}: {response.text[:200]}"
        data = response.json()
        assert data["result"] == "success"
        assert data["full_name"] == realm_credentials["full_name"]
        assert data.get("delivery_email") == realm_credentials["email"], \
            f"delivery_email mismatch: {data.get('delivery_email')} vs {realm_credentials['email']}"
        # The admin user we created should be a realm owner.
        assert data.get("is_owner") is True, \
            f"Bootstrapped admin should be realm owner, got is_owner={data.get('is_owner')}"

    def test_send_message_to_self(self, base_url, realm_credentials, api_key):
        """Send a direct message to self via the REST API.

        Uses `user_id` rather than email since Zulip 12.0 masks the user's
        canonical email and rejects the masked form as a recipient.
        """
        me = requests.get(
            f"{base_url}/api/v1/users/me",
            auth=(realm_credentials["email"], api_key),
            timeout=10,
        ).json()
        my_id = me["user_id"]

        response = requests.post(
            f"{base_url}/api/v1/messages",
            auth=(realm_credentials["email"], api_key),
            data={
                "type": "direct",
                "to": f"[{my_id}]",
                "content": "integration test ping",
            },
            timeout=10,
        )
        assert response.status_code == 200, \
            f"send-message returned {response.status_code}: {response.text[:200]}"
        data = response.json()
        assert data["result"] == "success", f"send-message result: {data}"
        assert "id" in data, "Expected message id in response"

    def test_get_messages(self, base_url, realm_credentials, api_key):
        """Retrieve recent messages — must include the one we just sent."""
        response = requests.get(
            f"{base_url}/api/v1/messages",
            auth=(realm_credentials["email"], api_key),
            params={
                "anchor": "newest",
                "num_before": 5,
                "num_after": 0,
                "narrow": '[]',
            },
            timeout=10,
        )
        assert response.status_code == 200, \
            f"get-messages returned {response.status_code}: {response.text[:200]}"
        data = response.json()
        assert data["result"] == "success"
        contents = [m.get("content", "") for m in data.get("messages", [])]
        assert any("integration test ping" in c for c in contents), \
            f"Expected ping message in retrieved set; got: {contents!r}"
