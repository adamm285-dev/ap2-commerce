"""
Integration tests for FastAPI REST endpoints matching openapi.yaml contract.
"""

from fastapi.testclient import TestClient
from ..server import app

client = TestClient(app)


def test_health_check_endpoint():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["mock_mode"] is True


def test_get_trade_catalog():
    res = client.get("/api/agent/catalog")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "active"
    assert len(data["trades"]) >= 3
    trade_ids = [t["id"] for t in data["trades"]]
    assert "flooring-tile" in trade_ids


def test_calculate_trade_quote():
    payload = {
        "tradeId": "flooring-tile",
        "squareFootage": 600,
        "materialType": "porcelain-plank",
        "postalCode": "33813",
    }
    res = client.post("/api/agent/quote", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["wasteAllowanceSqFt"] == 660.0
    assert data["requiredDeposit"] == 250.00
    assert "credited against final invoice" in data["depositPolicy"]


def test_evaluate_spending_mandate_endpoint():
    payload = {
        "buyerAgentId": "test-buyer-agent",
        "amount": 79.99,
        "recurrence": "monthly",
        "category": "contractor-dispatch-ai",
        "monthlyBudgetCap": 100.00,
    }
    res = client.post("/api/agent/spending-mandate/evaluate", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["approved"] is True
    assert data["authorizedAmount"] == 79.99
    assert len(data["mandateProofHash"]) == 64


def test_reset_mandate_ledger_endpoint():
    res = client.post(
        "/api/agent/spending-mandate/reset",
        json={"buyerAgentId": "test-buyer-agent"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "reset"
    assert data["remaining_budget"] == 100.00


def test_provision_line_endpoint():
    payload = {
        "subscriptionId": "I-TEST-SUB-9941",
        "contractorEmail": "test@floorsmith.pro",
        "areaCode": "863",
    }
    res = client.post("/api/agent/provision", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "ALLOCATED"
    assert data["assignedDid"].startswith("+1863")
    assert data["routingState"] == "ACTIVE_10DLC_BOUND"


def test_provision_line_endpoint_multi_area_codes():
    """Verifies that any US area code (Atlanta, Dallas, Chicago, Denver) provisions dedicated numbers matching that market."""
    for ac in ["404", "214", "312", "303"]:
        payload = {
            "subscriptionId": f"I-TEST-SUB-{ac}",
            "contractorEmail": f"contractor_{ac}@example.com",
            "areaCode": ac,
        }
        res = client.post("/api/agent/provision", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "ALLOCATED"
        assert data["assignedDid"].startswith(f"+1{ac}")
        assert data["routingState"] == "ACTIVE_10DLC_BOUND"


def test_lock_dispatch_slot():
    payload = {
        "leadId": "lead-sarah-jenkins",
        "territoryZone": "Zone 2 - South Lakeland",
        "slotStartIso": "2026-10-06T10:00:00-04:00",
        "paypalTransactionId": "TXN-998811",
    }
    res = client.post("/api/agent/dispatch/lock-slot", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "Crew B" in data["crewAssigned"]


def test_trigger_zapier_mcp_sync():
    payload = {
        "leadId": "lead-sarah-jenkins",
        "customerName": "Sarah Jenkins",
        "customerPhone": "+18635550199",
        "propertyAddress": "4822 Cleveland Heights Blvd, Lakeland, FL 33813",
        "depositAmount": 250.00,
        "paypalTxnId": "TXN-998811",
    }
    res = client.post("/api/mcp/zapier-sync", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "COMPLETED"
    assert data["jobberQuoteId"].startswith("JOB-")
    assert data["qboDraftInvoiceId"].startswith("QBO-")
    assert data["googleCalendarEventId"].startswith("gcal_")


def test_trigger_zapier_mcp_a2a_onboarding_sync():
    payload = {
        "workflowType": "a2a_onboarding",
        "contractorName": "Marcus Miller",
        "businessEntity": "Miller Custom Flooring LLC",
        "allocatedDid": "+1 (863) 267-8902",
        "tradeVertical": "Tile & Custom Flooring",
        "monthlySubscriptionFee": 79.99,
        "paypalSubscriptionId": "I-AUTONOMOUS-8902",
        "contractorEmail": "marcus@millercustomfloors.com",
    }
    res = client.post("/api/mcp/zapier-sync", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "COMPLETED"
    assert data["workflowType"] == "a2a_onboarding"
    assert data["jobberQuoteId"].startswith("JOB-ROUTING-")
    assert data["qboDraftInvoiceId"].startswith("QBO-EXP-")
    assert data["googleCalendarEventId"].startswith("gcal_briefing_")


def test_create_paypal_order_mock():
    payload = {
        "amount": 250.00,
        "currency": "USD",
        "description": "Mobilization Deposit",
    }
    res = client.post("/api/paypal/create-order", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "CREATED"
    assert data["mock_mode"] is True
    assert "ORDER-MOCK-" in data["order_id"]


def test_mcp_endpoint_http():
    """Tests the standard /mcp JSON-RPC 2.0 endpoint over HTTP."""
    payload = {
        "jsonrpc": "2.0",
        "id": 99,
        "method": "tools/list",
        "params": {},
    }
    res = client.post("/mcp", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == 99
    assert len(data["result"]["tools"]) >= 4


def test_copilot_chat_endpoint_http():
    """Tests the /api/copilot/chat endpoint over HTTP."""
    payload = {
        "message": "Did I miss any calls today?",
        "contractorName": "Marcus Miller",
        "businessEntity": "Miller Custom Flooring LLC",
        "tradeVertical": "Tile & Custom Flooring",
        "areaCode": "863",
        "budgetCap": 100.00,
    }
    res = client.post("/api/copilot/chat", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["phase"] == "DIAGNOSIS"
    assert "missed" in data["reply"].lower()
    assert data["telemetry"]["missed_calls"] == 8


def test_m2m_audit_payloads_endpoint():
    """Tests GET /m2m/payloads/latest and /api/m2m/payloads/latest for in-UI inspection."""
    # First trigger an A2A onboarding sync to populate cache
    payload = {
        "workflowType": "a2a_onboarding",
        "contractorName": "Marcus Miller",
        "businessEntity": "Miller Custom Flooring LLC",
        "allocatedDid": "+1 (863) 267-8902",
        "tradeVertical": "Tile & Custom Flooring",
        "monthlySubscriptionFee": 79.99,
        "paypalSubscriptionId": "I-AUTONOMOUS-8902",
        "contractorEmail": "marcus@millercustomfloors.com",
        "mandateProofHash": "HMAC-TEST-PROOF-99",
    }
    sync_res = client.post("/api/mcp/zapier-sync", json=payload)
    assert sync_res.status_code == 200

    # Query /m2m/payloads/latest
    res1 = client.get("/m2m/payloads/latest")
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["status"] == "COMPLETED"
    assert data1["telecom_did"] == "+1 (863) 267-8902"
    assert data1["paypal_subscription_id"] == "I-AUTONOMOUS-8902"
    assert data1["mandate_hash"] == "HMAC-TEST-PROOF-99"
    assert "graphql" in data1["jobber"]
    assert "client_create" in data1["jobber"]["graphql"]
    assert "payload" in data1["quickbooks"]
    assert "webhook_meta" in data1

    # Query /api/m2m/payloads/latest (alias route)
    res2 = client.get("/api/m2m/payloads/latest")
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["mandate_hash"] == "HMAC-TEST-PROOF-99"
    assert data2["status"] == "COMPLETED"


def test_crypto_sample_and_tamper_verification_endpoints():
    """Tests sample proof generation, tamper detection, and verification endpoints."""
    # 1. Fetch sample proof
    res = client.get("/api/crypto/sample-proof")
    assert res.status_code == 200
    sample = res.json()
    assert "canonical_payload" in sample
    assert "signature" in sample
    payload = sample["canonical_payload"]
    signature = sample["signature"]

    # 2. Verify untampered proof
    v_res = client.post(
        "/api/crypto/verify-tamper",
        json={"payload": payload, "signature": signature},
    )
    assert v_res.status_code == 200
    v_data = v_res.json()
    assert v_data["valid"] is True
    assert v_data["status_code"] == 200
    assert "200 OK" in v_data["detail"]

    # 3. Tamper price: $79.99 -> $80.00
    tampered_payload = dict(payload)
    tampered_payload["agreed_price_usd"] = 80.00
    t_res = client.post(
        "/api/crypto/verify-tamper",
        json={"payload": tampered_payload, "signature": signature},
    )
    assert t_res.status_code == 200  # API returns response with valid=False, status_code=401 in body
    t_data = t_res.json()
    assert t_data["valid"] is False
    assert t_data["status_code"] == 401
    assert "401 Signature Mismatch" in t_data["detail"]


def test_mcp_wire_frames_endpoint():
    """Tests GET /api/mcp/frames and /m2m/frames for JSON-RPC frame inspection."""
    res = client.get("/api/mcp/frames")
    assert res.status_code == 200
    data = res.json()
    assert "frames" in data
    assert isinstance(data["frames"], list)


