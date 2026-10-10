"""
Tests for Back-Office Export Engines (QuickBooks Online & Webhook Dispatcher).
Verifies authentic QBO API v3 Expense structures,
HMAC-SHA256 webhook signatures, SSRF security controls, and the /api/export/backoffice endpoint.
"""

import pytest
import hmac
import hashlib
import json
from fastapi.testclient import TestClient
from backend.server import app
from backend.services.backoffice.qbo_exporter import qbo_exporter
from backend.services.backoffice.webhook_dispatcher import webhook_dispatcher
from backend.services.zapier_mcp_dispatcher import zapier_mcp_dispatcher
from backend.models import ZapierSyncRequest
from backend.config import settings

client = TestClient(app)


def test_qbo_purchase_expense_format():
    """Verifies QuickBooks Online API v3 Purchase/Expense object structure."""
    qbo_pkg = qbo_exporter.format_purchase_expense_payload(
        contractor_name="Nexus Autonomous Buyer",
        business_entity="Nexus Autonomous Systems Corp",
        contractor_email="agent-alpha@example.com",
        monthly_fee=79.99,
        paypal_subscription_id="I-AUTONOMOUS-8902",
        allocated_did="mcp+https://gateway-01.example.com/mcp",
        mandate_proof_hash="PROOF-HASH-5678",
        trade_vertical="Dedicated AI Service Gateway",
        txn_date="2026-10-03",
    )

    purchase = qbo_pkg["Purchase"]
    assert purchase["PaymentType"] == "CreditCard"
    assert purchase["TotalAmt"] == 79.99
    assert purchase["CurrencyRef"]["value"] == "USD"
    assert purchase["EntityRef"]["name"] == "AP2 Autonomous Node Network Inc."
    assert purchase["EntityRef"]["type"] == "Vendor"
    assert "mcp+https://gateway-01.example.com/mcp" in purchase["PrivateNote"]
    assert "I-AUTONOMOUS-8902" in purchase["PrivateNote"]
    assert "PROOF-HASH-5678" in purchase["PrivateNote"]

    # Verify line item mapped to Software & Subscriptions account 6300
    line_item = purchase["Line"][0]
    assert line_item["DetailType"] == "AccountBasedExpenseLineDetail"
    assert line_item["Amount"] == 79.99
    assert line_item["AccountBasedExpenseLineDetail"]["AccountRef"]["value"] == "6300"
    assert "Software" in line_item["AccountBasedExpenseLineDetail"]["AccountRef"]["name"]


def test_qbo_vendor_payload_format():
    """Verifies QBO API v3 Vendor representation for AP2 Autonomous Node Network Inc."""
    vendor = qbo_exporter.format_vendor_payload()
    assert vendor["Vendor"]["DisplayName"] == "AP2 Autonomous Node Network Inc."
    assert vendor["Vendor"]["PrimaryEmailAddr"]["Address"] == "billing@example.com"
    assert vendor["Vendor"]["PrimaryPhone"]["FreeFormNumber"] == "+1 (800) 555-0199"


@pytest.mark.asyncio
async def test_webhook_dispatcher_signing_and_dry_run():
    """Verifies HMAC-SHA256 signature generation with isolated derived secret and dry-run headers."""
    sample_payload = {
        "event": "a2a.subscription.provisioned",
        "sub_id": "I-TEST-1234",
        "monthly_fee": 79.99,
    }
    res = await webhook_dispatcher.dispatch(
        payload=sample_payload,
        target_url=None,  # Dry run
        event_type="a2a.subscription.provisioned",
    )

    assert res["dry_run"] is True
    assert res["dispatched"] is False
    # Signature is isolated to HTTP headers and not leaked directly in response dict
    assert "signature" not in res

    # Manually compute expected signature using isolated derived secret
    payload_bytes = json.dumps(sample_payload, sort_keys=True).encode("utf-8")
    expected_secret = hashlib.sha256(
        (settings.a2a_mandate_secret + ":webhook_isolation").encode("utf-8")
    ).hexdigest()
    expected_hex = hmac.new(
        expected_secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()
    assert res["headers"]["X-AP2-Signature"] == f"sha256={expected_hex}"
    assert res["headers"]["X-AP2-Event"] == "a2a.subscription.provisioned"


@pytest.mark.asyncio
async def test_webhook_dispatcher_ssrf_protection():
    """Verifies that webhook dispatcher rejects malicious SSRF targets and permits whitelisted domains."""
    from backend.services.backoffice.webhook_dispatcher import is_url_permitted

    # Blocked targets: metadata, private IPs, non-whitelisted domains
    assert not is_url_permitted("http://169.254.169.254/computeMetadata/v1/")
    assert not is_url_permitted("http://169.254.1.1/secret")
    assert not is_url_permitted("http://10.0.0.1:8080/admin")
    assert not is_url_permitted("http://192.168.1.1/router")
    assert not is_url_permitted("http://172.16.0.5/api")
    assert not is_url_permitted("https://evil-attacker-site.com/steal")
    assert not is_url_permitted("ftp://hooks.zapier.com/test")
    assert not is_url_permitted("")

    # Allowed targets: automation platforms
    assert is_url_permitted("https://hooks.zapier.com/hooks/catch/123/abc")
    assert is_url_permitted("https://hook.us1.make.com/webhooks/123")
    assert is_url_permitted("https://maker.ifttt.com/trigger/event/json/with/key/xyz")
    assert is_url_permitted("https://webhook.site/00000000-0000-0000-0000-000000000000")
    assert is_url_permitted("https://eo12345.m.pipedream.net")

    # Live dispatch to blocked target returns SSRF error without firing HTTP request
    res = await webhook_dispatcher.dispatch(
        payload={"test": 1},
        target_url="http://169.254.169.254/latest/meta-data/",
    )
    assert res["dispatched"] is False
    assert "SSRF security policy" in res["error"]


@pytest.mark.asyncio
async def test_zapier_mcp_dispatcher_exports_authentic_payloads():
    """Verifies that ZapierMcpDispatcher attaches QBO export packages."""
    req = ZapierSyncRequest(
        workflowType="a2a_onboarding",
        contractorName="Nexus Autonomous Buyer",
        businessEntity="Nexus Autonomous Systems Corp",
        allocatedDid="mcp+https://gateway-01.example.com/mcp",
        tradeVertical="Dedicated AI Service Gateway",
        monthlySubscriptionFee=79.99,
        paypalSubscriptionId="I-AUTONOMOUS-8902",
        contractorEmail="agent-alpha@example.com",
        mandateProofHash="HMAC-VERIFIED-HASH",
    )

    resp = await zapier_mcp_dispatcher.execute_downline_sync(req)
    assert resp.status == "COMPLETED"
    assert resp.workflow_type == "a2a_onboarding"
    assert resp.erp_routing_id.startswith("AP2-EXP-")
    assert resp.qbo_draft_invoice_id.startswith("QBO-EXP-")

    # Verify authentic QBO package is present
    assert resp.qbo_payload is not None
    assert resp.qbo_payload["entity"] == "QuickBooks_Online"
    assert resp.qbo_payload["payload"]["Purchase"]["TotalAmt"] == 79.99
    assert resp.qbo_payload["payload"]["Purchase"]["Line"][0]["AccountBasedExpenseLineDetail"]["AccountRef"]["value"] == "6300"


def test_api_export_backoffice_endpoint():
    """Verifies HTTP POST /api/export/backoffice returns complete authentic packages."""
    payload = {
        "workflowType": "a2a_onboarding",
        "contractorName": "Nexus Autonomous Buyer",
        "businessEntity": "Nexus Autonomous Systems Corp",
        "allocatedDid": "mcp+https://gateway-01.example.com/mcp",
        "tradeVertical": "Dedicated AI Service Gateway",
        "monthlySubscriptionFee": 79.99,
        "paypalSubscriptionId": "I-AUTONOMOUS-8902",
        "contractorEmail": "agent-alpha@example.com",
        "mandateProofHash": "0530c4b618a5f1cd287477bf9d551bff52c100eeaf1811de3036fa2c4bb29560",
    }
    res = client.post("/api/export/backoffice", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "COMPLETED"
    assert data["qboPayload"] is not None
    assert data["qboPayload"]["account_mapping"]["expense_account"].startswith("6300")
