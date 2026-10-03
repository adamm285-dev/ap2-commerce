"""
Tests for Back-Office Export Engines (Jobber CRM & QuickBooks Online).
Verifies authentic Jobber GraphQL/REST schema formatting, QBO API v3 Expense structures,
HMAC-SHA256 webhook signatures, and the /api/export/backoffice endpoint.
"""

import pytest
import hmac
import hashlib
import json
from fastapi.testclient import TestClient
from backend.server import app
from backend.services.backoffice.jobber_exporter import jobber_exporter
from backend.services.backoffice.qbo_exporter import qbo_exporter
from backend.services.backoffice.webhook_dispatcher import webhook_dispatcher
from backend.services.zapier_mcp_dispatcher import zapier_mcp_dispatcher
from backend.models import ZapierSyncRequest
from backend.config import settings

client = TestClient(app)


def test_jobber_graphql_client_mutation_format():
    """Verifies Jobber GraphQL v2 client mutation matches schema with custom telephony fields."""
    mutation = jobber_exporter.format_client_graphql_mutation(
        contractor_name="Marcus Miller",
        business_entity="Miller Custom Flooring LLC",
        contractor_email="marcus@millercustomfloors.com",
        allocated_did="+1 (863) 267-8902",
        trade_vertical="Tile & Custom Flooring",
        paypal_subscription_id="I-AUTONOMOUS-8902",
        mandate_proof_hash="0530c4b618a5f1cd287477bf9d551bff52c100eeaf1811de3036fa2c4bb29560",
    )

    assert "mutation ClientCreate($input: ClientCreateInput!)" in mutation["query"]
    assert mutation["operationName"] == "ClientCreate"

    variables = mutation["variables"]["input"]
    assert variables["firstName"] == "Marcus"
    assert variables["lastName"] == "Miller"
    assert variables["companyName"] == "Miller Custom Flooring LLC"
    assert variables["isCompany"] is True
    assert variables["phones"][0]["number"] == "+1 (863) 267-8902"

    # Verify custom fields for telephony routing
    custom_fields = {cf["customFieldId"]: cf["valueText"] for cf in variables["customFields"]}
    assert custom_fields["cf_fieldsmith_did"] == "+1 (863) 267-8902"
    assert custom_fields["cf_screening_vertical"] == "Tile & Custom Flooring"
    assert custom_fields["cf_routing_state"] == "10DLC_BOUND_INBOUND_ONLY"
    assert custom_fields["cf_paypal_subscription_id"] == "I-AUTONOMOUS-8902"
    assert "0530c4b6" in custom_fields["cf_a2a_mandate_proof"]


def test_jobber_graphql_job_mutation_format():
    """Verifies Jobber GraphQL v2 recurring job mutation contains dispatch instructions."""
    job = jobber_exporter.format_job_graphql_mutation(
        client_id="Z2lkOi8vSm9iYmVyL0NsaWVudC8xMDA=",
        business_entity="Miller Custom Flooring LLC",
        trade_vertical="Tile & Custom Flooring",
        allocated_did="+1 (863) 267-8902",
        monthly_fee=79.99,
        paypal_subscription_id="I-AUTONOMOUS-8902",
    )

    assert "mutation JobCreate($input: JobCreateInput!)" in job["query"]
    assert job["variables"]["input"]["jobType"] == "RECURRING"
    assert job["variables"]["input"]["lineItems"][0]["unitPrice"] == 79.99
    assert "+1 (863) 267-8902" in job["variables"]["input"]["instructions"]
    assert "PayPal Subscriptions" in job["variables"]["input"]["instructions"]


def test_jobber_rest_client_payload_format():
    """Verifies Jobber REST v2 client payload structure."""
    rest_pkg = jobber_exporter.format_rest_client_payload(
        contractor_name="Marcus Miller",
        business_entity="Miller Custom Flooring LLC",
        contractor_email="marcus@millercustomfloors.com",
        allocated_did="+1 (863) 267-8902",
        trade_vertical="Tile & Custom Flooring",
        paypal_subscription_id="I-AUTONOMOUS-8902",
        mandate_proof_hash="PROOF-HASH-1234",
    )

    client_data = rest_pkg["client"]
    assert client_data["first_name"] == "Marcus"
    assert client_data["last_name"] == "Miller"
    assert client_data["is_company"] is True
    assert client_data["custom_fields"]["fieldsmith_ai_inbound_did"] == "+1 (863) 267-8902"
    assert client_data["custom_fields"]["routing_mode"] == "10DLC_BOUND_INBOUND_ONLY"


def test_qbo_purchase_expense_format():
    """Verifies QuickBooks Online API v3 Purchase/Expense object structure."""
    qbo_pkg = qbo_exporter.format_purchase_expense_payload(
        contractor_name="Marcus Miller",
        business_entity="Miller Custom Flooring LLC",
        contractor_email="marcus@millercustomfloors.com",
        monthly_fee=79.99,
        paypal_subscription_id="I-AUTONOMOUS-8902",
        allocated_did="+1 (863) 267-8902",
        mandate_proof_hash="PROOF-HASH-5678",
        trade_vertical="Tile & Custom Flooring",
        txn_date="2026-10-03",
    )

    purchase = qbo_pkg["Purchase"]
    assert purchase["PaymentType"] == "CreditCard"
    assert purchase["TotalAmt"] == 79.99
    assert purchase["CurrencyRef"]["value"] == "USD"
    assert purchase["EntityRef"]["name"] == "FieldSmith Pro Inc."
    assert purchase["EntityRef"]["type"] == "Vendor"
    assert "+1 (863) 267-8902" in purchase["PrivateNote"]
    assert "I-AUTONOMOUS-8902" in purchase["PrivateNote"]
    assert "PROOF-HASH-5678" in purchase["PrivateNote"]

    # Verify line item mapped to Software & Subscriptions account 6300
    line_item = purchase["Line"][0]
    assert line_item["DetailType"] == "AccountBasedExpenseLineDetail"
    assert line_item["Amount"] == 79.99
    assert line_item["AccountBasedExpenseLineDetail"]["AccountRef"]["value"] == "6300"
    assert "Software" in line_item["AccountBasedExpenseLineDetail"]["AccountRef"]["name"]


def test_qbo_vendor_payload_format():
    """Verifies QBO API v3 Vendor representation for FieldSmith Pro."""
    vendor = qbo_exporter.format_vendor_payload()
    assert vendor["Vendor"]["DisplayName"] == "FieldSmith Pro Inc."
    assert vendor["Vendor"]["PrimaryEmailAddr"]["Address"] == "billing@fieldsmith.pro"
    assert vendor["Vendor"]["PrimaryPhone"]["FreeFormNumber"] == "+1 (863) 802-6000"


@pytest.mark.asyncio
async def test_webhook_dispatcher_signing_and_dry_run():
    """Verifies HMAC-SHA256 signature generation and dry-run headers."""
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
    assert res["signature"].startswith("sha256=")

    # Manually compute expected signature to verify cryptographic parity
    payload_bytes = json.dumps(sample_payload, sort_keys=True).encode("utf-8")
    expected_hex = hmac.new(
        settings.a2a_mandate_secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()
    assert res["signature"] == f"sha256={expected_hex}"
    assert res["headers"]["X-FieldSmith-Signature"] == f"sha256={expected_hex}"
    assert res["headers"]["X-FieldSmith-Event"] == "a2a.subscription.provisioned"


@pytest.mark.asyncio
async def test_zapier_mcp_dispatcher_exports_authentic_payloads():
    """Verifies that ZapierMcpDispatcher attaches both Jobber and QBO export packages."""
    req = ZapierSyncRequest(
        workflowType="a2a_onboarding",
        contractorName="Marcus Miller",
        businessEntity="Miller Custom Flooring LLC",
        allocatedDid="+1 (863) 267-8902",
        tradeVertical="Tile & Custom Flooring",
        monthlySubscriptionFee=79.99,
        paypalSubscriptionId="I-AUTONOMOUS-8902",
        contractorEmail="marcus@millercustomfloors.com",
        mandateProofHash="HMAC-VERIFIED-HASH",
    )

    resp = await zapier_mcp_dispatcher.execute_downline_sync(req)
    assert resp.status == "COMPLETED"
    assert resp.workflow_type == "a2a_onboarding"
    assert resp.jobber_quote_id.startswith("JOB-ROUTING-")
    assert resp.qbo_draft_invoice_id.startswith("QBO-EXP-")

    # Verify authentic Jobber package is present
    assert resp.jobber_payload is not None
    assert resp.jobber_payload["entity"] == "Jobber_CRM"
    assert "clientCreate" in resp.jobber_payload["graphql"]["client_create"]["query"]
    assert "jobCreate" in resp.jobber_payload["graphql"]["job_create"]["query"]
    assert resp.jobber_payload["rest"]["method"] == "POST"

    # Verify authentic QBO package is present
    assert resp.qbo_payload is not None
    assert resp.qbo_payload["entity"] == "QuickBooks_Online"
    assert resp.qbo_payload["payload"]["Purchase"]["TotalAmt"] == 79.99
    assert resp.qbo_payload["payload"]["Purchase"]["Line"][0]["AccountBasedExpenseLineDetail"]["AccountRef"]["value"] == "6300"


def test_api_export_backoffice_endpoint():
    """Verifies HTTP POST /api/export/backoffice returns complete authentic packages."""
    payload = {
        "workflowType": "a2a_onboarding",
        "contractorName": "Marcus Miller",
        "businessEntity": "Miller Custom Flooring LLC",
        "allocatedDid": "+1 (863) 267-8902",
        "tradeVertical": "Tile & Custom Flooring",
        "monthlySubscriptionFee": 79.99,
        "paypalSubscriptionId": "I-AUTONOMOUS-8902",
        "contractorEmail": "marcus@millercustomfloors.com",
        "mandateProofHash": "0530c4b618a5f1cd287477bf9d551bff52c100eeaf1811de3036fa2c4bb29560",
    }
    res = client.post("/api/export/backoffice", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "COMPLETED"
    assert data["jobberPayload"] is not None
    assert data["qboPayload"] is not None
    assert data["jobberPayload"]["routing_summary"]["allocated_did"] == "+1 (863) 267-8902"
    assert data["qboPayload"]["account_mapping"]["expense_account"].startswith("6300")
