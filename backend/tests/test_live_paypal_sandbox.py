"""
Tests for Live PayPal Sandbox OAuth & Plan Verification,
Agent Discoverability (llms.txt), and Telecom Compliance Disclosures.
"""

import pytest
import httpx
from fastapi.testclient import TestClient
from backend.server import app
from backend.config import settings
from backend.services.paypal_service import PayPalService
from backend.models import ProvisionResponse

client = TestClient(app)


def test_compliance_note_in_provision_response():
    resp = ProvisionResponse(
        status="ALLOCATED",
        assignedDid="+18635550100",
        carrier="Telnyx",
        routingState="ACTIVE",
        subscriptionId="I-TEST-SUB-01",
    )
    assert resp.compliance_note is not None
    assert "Voice routing active immediately" in resp.compliance_note
    assert "A2P 10DLC messaging active upon campaign vetting" in resp.compliance_note
    dumped = resp.model_dump(by_alias=True)
    assert "complianceNote" in dumped
    assert "Voice routing active immediately" in dumped["complianceNote"]


def test_llms_txt_endpoints():
    for endpoint in ["/llms.txt", "/.well-known/llms.txt"]:
        res = client.get(endpoint)
        assert res.status_code == 200
        assert "text/plain" in res.headers["content-type"]
        text = res.text
        assert "FieldSmith Pro A2A Autonomous Commerce Protocol" in text
        assert "PayPal Sandbox demo for the PayPal AI Hackathon" in text
        assert "FastMCP Tools Catalog" in text
        assert "Dynamic Buyer Key Registration" in text
        assert "10DLC Messaging Timeline" in text


@pytest.mark.asyncio
async def test_live_paypal_sandbox_oauth_token():
    """Verify live OAuth2 token acquisition from PayPal Sandbox REST API."""
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
