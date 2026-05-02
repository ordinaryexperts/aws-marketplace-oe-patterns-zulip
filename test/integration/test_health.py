"""
Health and basic-connectivity tests for Zulip.
Validates infrastructure and application health against a deployed pattern stack.
"""

import socket
import ssl
import time
from urllib.parse import urlparse

import pytest
import requests


class TestZulipHealth:
    """Application-level health and API checks."""

    def test_https_accessible(self, base_url):
        """Home page is reachable over HTTPS.

        A fresh deploy with no realm returns 404 ("No organization found"); after
        bootstrap (see test_workflows.py) it returns 200/302. Accept all three.
        """
        response = requests.get(base_url, timeout=30, allow_redirects=False)
        assert response.status_code in (200, 302, 404), \
            f"Home page returned unexpected status {response.status_code} at {base_url}"
        assert response.url.startswith("https://"), \
            "Zulip should be served over HTTPS"

    def test_homepage_has_zulip_branding(self, base_url):
        """Home page HTML contains 'Zulip' branding."""
        response = requests.get(base_url, timeout=30, allow_redirects=True)
        body = response.text
        assert "Zulip" in body, "Home page HTML missing 'Zulip' branding"

    def test_server_settings_api(self, base_url, config):
        """`/api/v1/server_settings` returns the expected Zulip version."""
        response = requests.get(
            f"{base_url}/api/v1/server_settings",
            timeout=10,
        )
        assert response.status_code == 200, \
            f"server_settings returned {response.status_code}"

        data = response.json()
        assert data.get("result") == "success", \
            f"server_settings result not success: {data.get('result')}"
        assert "zulip_version" in data, \
            "server_settings missing 'zulip_version'"

        expected = config["application"]["expected_version"]
        actual = data["zulip_version"]
        assert actual == expected, \
            f"Version mismatch. Expected {expected}, got {actual}"

    def test_push_notifications_enabled(self, base_url):
        """Server reports push notifications enabled (we deploy with that flag on)."""
        response = requests.get(
            f"{base_url}/api/v1/server_settings",
            timeout=10,
        )
        data = response.json()
        assert data.get("push_notifications_enabled") is True, \
            "Expected push_notifications_enabled=True in server_settings"

    def test_response_time(self, base_url, config):
        """Home page responds within configured SLO."""
        max_seconds = config["test"]["max_response_time_seconds"]

        start = time.time()
        response = requests.get(base_url, timeout=30, allow_redirects=False)
        elapsed = time.time() - start

        assert response.status_code in (200, 302, 404)
        assert elapsed < max_seconds, \
            f"Response time {elapsed:.2f}s exceeds {max_seconds}s SLO"

    def test_ssl_certificate(self, base_url):
        """SSL certificate validates against the system trust store."""
        parsed = urlparse(base_url)
        hostname = parsed.hostname
        port = parsed.port or 443

        context = ssl.create_default_context()
        try:
            with socket.create_connection((hostname, port), timeout=10) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()
                    assert cert, "No SSL certificate returned"
        except ssl.SSLError as e:
            pytest.fail(f"SSL certificate validation failed: {e}")

    def test_security_headers(self, base_url):
        """Important security headers are set by Zulip's nginx config."""
        response = requests.get(base_url, timeout=10, allow_redirects=False)
        headers = response.headers

        assert headers.get("X-Frame-Options") == "DENY", \
            f"X-Frame-Options expected DENY, got {headers.get('X-Frame-Options')}"
        assert headers.get("X-Content-Type-Options") == "nosniff", \
            f"X-Content-Type-Options expected nosniff, got {headers.get('X-Content-Type-Options')}"
        assert "Strict-Transport-Security" in headers, \
            "HSTS header missing"


class TestZulipInfrastructure:
    """AWS infrastructure-level checks against the deployed CloudFormation stack."""

    def test_cloudformation_stack_exists(self, cloudformation_client, stack_name):
        response = cloudformation_client.describe_stacks(StackName=stack_name)
        assert len(response["Stacks"]) == 1, \
            f"Expected 1 stack, got {len(response['Stacks'])}"

        status = response["Stacks"][0]["StackStatus"]
        assert status in ("CREATE_COMPLETE", "UPDATE_COMPLETE"), \
            f"Stack status unexpected: {status}"

    def test_stack_outputs(self, stack_outputs):
        """Required stack outputs are present and non-empty."""
        required = ["DnsSiteUrlOutput", "SiteUrlOutput", "VpcIdOutput"]
        for key in required:
            assert key in stack_outputs, f"Stack output '{key}' missing"
            assert stack_outputs[key], f"Stack output '{key}' is empty"

    def test_ec2_instance_running(self, ec2_client, instance_id):
        response = ec2_client.describe_instances(InstanceIds=[instance_id])
        instance = response["Reservations"][0]["Instances"][0]
        assert instance["State"]["Name"] == "running", \
            f"Instance state: {instance['State']['Name']}"

    def test_instance_has_valid_ami(self, ec2_client, instance_id):
        response = ec2_client.describe_instances(InstanceIds=[instance_id])
        ami_id = response["Reservations"][0]["Instances"][0]["ImageId"]
        assert ami_id.startswith("ami-"), f"Invalid AMI ID format: {ami_id}"
