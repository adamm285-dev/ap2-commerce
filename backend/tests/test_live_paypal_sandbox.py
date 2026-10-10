"""
Tests for Live PayPal Sandbox OAuth & Plan Verification,
Agent Discoverability (llms.txt), and Node Compliance Disclosures.
"""

import os
import pytest
import httpx
from fastapi.testclient import TestClient
from backend.server import app
from backend.config import settings
from backend.services.paypal_service import PayPalService
from backend.models import ProvisionResponse

client = TestClient(app)

LIVE_SANDBOX_ENABLED = os.environ.get("RUN_LIVE_SANDBOX") == "1"


def test_compliance_note_in_provision_response():
    resp = ProvisionResponse(
        status="ALLOCATED",
        endpoint="mcp+https://gateway-01.example.com/mcp",
        carrier="Dual-Transport FastMCP (RFC 8032)",
        routingState="ACTIVE_COMPUTE_NODE",
        subscriptionId="I-TEST-SUB-01",
    )
    assert resp.compliance_note is not None
    assert "Compute node active immediately" in resp.compliance_note
    dumped = resp.model_dump(by_alias=True)
    assert "complianceNote" in dumped
    assert "Compute node active immediately" in dumped["complianceNote"]


def test_llms_txt_endpoints():
    for endpoint in ["/llms.txt", "/.well-known/llms.txt"]:
        res = client.get(endpoint)
        assert res.status_code == 200
        assert "text/plain" in res.headers["content-type"]
        text = res.text
        assert "AP2 Autonomous Seller Node Protocol" in text
        assert "PayPal Sandbox demo for the PayPal AI Hackathon" in text
        assert "FastMCP Tools Catalog" in text
        assert "Dynamic Buyer Key Registration" in text


@pytest.mark.asyncio
async def test_live_paypal_sandbox_oauth_token():
    """Verify live OAuth2 token acquisition from PayPal Sandbox REST API."""
    if not LIVE_SANDBOX_ENABLED:
        pytest.skip("Live PayPal sandbox tests disabled unless RUN_LIVE_SANDBOX=1 is set")
    if not settings.paypal_client_id or not settings.paypal_client_secret:
        pytest.skip("PayPal client ID/secret not configured")

    svc = PayPalService()
    svc.mock_mode = False

    token = await svc.get_access_token()
    assert token is not None
    assert len(token) > 20
    assert not token.startswith("MOCK_")


@pytest.mark.asyncio
async def test_live_paypal_sandbox_billing_plans():
    """Verify all 3 configured billing plans exist and are accessible in PayPal Sandbox."""
    if not LIVE_SANDBOX_ENABLED:
        pytest.skip("Live PayPal sandbox tests disabled unless RUN_LIVE_SANDBOX=1 is set")
    if not settings.paypal_client_id or not settings.paypal_client_secret:
        pytest.skip("PayPal client ID/secret not configured")

    svc = PayPalService()
    svc.mock_mode = False
    token = await svc.get_access_token()
    assert token is not None

    plan_ids = [
        settings.paypal_plan_id_solo,
        settings.paypal_plan_id_pro,
        settings.paypal_plan_id_dispatch,
    ]

    async with httpx.AsyncClient() as http_client:
        for plan_id in plan_ids:
            if not plan_id:
                continue
            res = await http_client.get(
                f"{svc.base_url}/v1/billing/plans/{plan_id}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )
            assert res.status_code == 200, f"Plan {plan_id} lookup failed: {res.text}"
            data = res.json()
            assert data.get("id") == plan_id
            assert data.get("status") in ["ACTIVE", "CREATED"]


@pytest.mark.asyncio
async def test_proactive_oauth_token_caching_and_refresh():
    """Verify proactive token caching, 9-hour expiry tracking, and forced refresh."""
    import datetime
    svc = PayPalService()
    svc.mock_mode = False

    # Mock response data for testing caching logic without hitting live rate limits
    svc._cached_token = "MOCK_CACHED_TOKEN_A"
    svc._token_expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)

    # 1. Active cache returns token immediately without network call
    token1 = await svc.get_access_token()
    assert token1 == "MOCK_CACHED_TOKEN_A"

    # 2. Sync accessor also returns cached token
    sync_token = svc.get_sync_access_token()
    assert sync_token == "MOCK_CACHED_TOKEN_A"

    # 3. Near-expiration (< 5 min) invalidates cache and triggers refresh
    svc._token_expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=2)
    # If in mock mode, will return synthetic token; in live mode, refreshes
    svc.mock_mode = True
    refreshed_token = await svc.get_access_token()
    assert refreshed_token.startswith("MOCK_BEARER_TOKEN_")
    assert refreshed_token != "MOCK_CACHED_TOKEN_A"


def test_official_paypal_agent_toolkit_integration():
    """Verify that official paypal_agent_toolkit queries live subscription plans and details."""
    if not LIVE_SANDBOX_ENABLED:
        pytest.skip("Live PayPal sandbox tests disabled unless RUN_LIVE_SANDBOX=1 is set")
    if not settings.paypal_client_id or not settings.paypal_client_secret:
        pytest.skip("PayPal Sandbox credentials not configured for live toolkit test")

    svc = PayPalService()
    svc.mock_mode = False

    plans = svc.list_plans_via_toolkit()
    assert plans is not None
    assert len(plans) >= 3
    plan_ids = [p.get("id") for p in plans]
    for expected_id in ["P-68L14988XW5641721NLCRSFQ", "P-4KA989014W524233ANLCRSFQ", "P-77627096S5279500YNLCRSFY"]:
        assert expected_id in plan_ids

    detail = svc.show_plan_details_via_toolkit("P-4KA989014W524233ANLCRSFQ")
    assert detail is not None
    assert detail.get("id") == "P-4KA989014W524233ANLCRSFQ"
    assert detail.get("status") in ["ACTIVE", "CREATED"]


def test_official_paypal_agent_toolkit_subscription_lookup():
    """Verify official toolkit can query live subscription details on PayPal Sandbox."""
    if not LIVE_SANDBOX_ENABLED:
        pytest.skip("Live PayPal sandbox tests disabled unless RUN_LIVE_SANDBOX=1 is set")
    if not settings.paypal_client_id or not settings.paypal_client_secret:
        pytest.skip("PayPal Sandbox credentials not configured for live toolkit test")

    svc = PayPalService()
    svc.mock_mode = False

    sub = svc.show_subscription_details_via_toolkit("I-XM0DGNAYF04E")
    if sub is None:
        pytest.skip("PayPal Sandbox subscription fixture I-XM0DGNAYF04E expired or was purged by Sandbox TTL")

    assert sub is not None
    assert "id" in sub
    assert sub.get("status") in ["APPROVAL_PENDING", "ACTIVE", "APPROVED"]


