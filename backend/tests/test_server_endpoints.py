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
    assert "ap2-gateway" in trade_ids


def test_calculate_trade_quote():
    payload = {
        "tradeId": "ap2-gateway",
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


def test_reset_mandate_ledger_unauthorized_fails():
    res = client.post(
        "/api/agent/spending-mandate/reset",
        json={"buyerAgentId": "test-buyer-agent"},
    )
    assert res.status_code == 401
    assert "Admin authorization required" in res.json()["detail"]


def test_reset_mandate_ledger_endpoint():
    from ..config import settings

    admin_key = getattr(settings, "admin_api_key", "dev-admin-secret-key")

    # Passing admin_key as query param is rejected with 401 (headers required)
    res_qp = client.post(
        f"/api/agent/spending-mandate/reset?admin_key={admin_key}",
        json={"buyerAgentId": "test-buyer-agent"},
    )
    assert res_qp.status_code == 401
    assert "Admin authorization required" in res_qp.json()["detail"]

    res = client.post(
        "/api/agent/spending-mandate/reset",
        json={"buyerAgentId": "test-buyer-agent"},
        headers={"X-Admin-Key": admin_key},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "reset"
    assert data["remaining_budget"] == 100.00


def test_provision_line_unauthorized_subscription_fails():
    payload = {
        "subscriptionId": "I-FAKE-UNREGISTERED-9999",
        "contractorEmail": "test@ap2-procure.org",
        "areaCode": "863",
    }
    res = client.post("/api/agent/provision", json=payload)
    assert res.status_code == 404
    assert res.json()["detail"]["error"] == "SUBSCRIPTION_NOT_FOUND"


def test_provision_line_identity_mismatch_fails():
    from ..agents.seller_agent import _COMPLETED_SUBSCRIPTIONS

    _COMPLETED_SUBSCRIPTIONS["I-TEST-SUB-9941"] = {
        "subscription_id": "I-TEST-SUB-9941",
        "status": "ACTIVE",
        "contractor_email": "agent-alpha@nexus-systems.io",
        "tier_id": "ap2-batch",
        "agreed_monthly_rate": 49.99,
    }
    payload = {
        "subscriptionId": "I-TEST-SUB-9941",
        "contractorEmail": "attacker@evil.com",
    }
    res = client.post("/api/agent/provision", json=payload)
    assert res.status_code == 403
    assert res.json()["detail"]["error"] == "IDENTITY_MISMATCH_DETECTED"


def test_provision_line_endpoint():
    from ..agents.seller_agent import _COMPLETED_SUBSCRIPTIONS

    _COMPLETED_SUBSCRIPTIONS["I-TEST-SUB-9941"] = {
        "subscription_id": "I-TEST-SUB-9941",
        "status": "ACTIVE",
        "contractor_email": "agent-alpha@nexus-systems.io",
        "tier_id": "ap2-batch",
        "agreed_monthly_rate": 49.99,
    }
    payload = {
        "subscriptionId": "I-TEST-SUB-9941",
        "contractorEmail": "agent-alpha@nexus-systems.io",
    }
    res = client.post("/api/agent/provision", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["status"] in ("ALLOCATED", "PROVISIONED")
    assert data["endpoint"].startswith("mcp+https://")
    assert data["carrier"] == "Dual-Transport FastMCP (RFC 8032)"


def test_provision_line_endpoint_multi_area_codes():
    """Verifies that multiple AP2 compute node tiers provision dedicated endpoints."""
    from ..agents.seller_agent import _COMPLETED_SUBSCRIPTIONS

    for tier_id, rate in [("ap2-batch", 49.99), ("ap2-gateway", 79.99), ("ap2-cluster", 179.99)]:
        sub_id = f"I-TEST-SUB-{tier_id}"
        email = f"buyer_{tier_id}@example.com"
        _COMPLETED_SUBSCRIPTIONS[sub_id] = {
            "subscription_id": sub_id,
            "status": "ACTIVE",
            "contractor_email": email,
            "tier_id": tier_id,
            "agreed_monthly_rate": rate,
        }
        payload = {
            "subscriptionId": sub_id,
            "contractorEmail": email,
        }
        res = client.post("/api/agent/provision", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert data["status"] in ("ALLOCATED", "PROVISIONED")
        assert data["endpoint"].startswith("mcp+https://")
        assert data["carrier"] == "Dual-Transport FastMCP (RFC 8032)"


def test_paypal_webhook_verified():
    from ..services.paypal_service import paypal_service
    import json

    payload = {
        "id": "WH-9911-TEST",
        "event_type": "BILLING.SUBSCRIPTION.ACTIVATED",
        "resource": {"id": "I-A2A-VAULT-001234"},
    }
    raw_body = json.dumps(payload)
    sig = paypal_service.generate_mock_webhook_signature(raw_body)
    res = client.post(
        "/api/paypal/webhook",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "PAYPAL-TRANSMISSION-SIG": sig,
        },
    )
    assert res.status_code == 200
    assert res.json()["status"] == "received"
    assert res.json()["verification_status"] == "SUCCESS"


def test_paypal_webhook_invalid_signature_rejected():
    payload = {
        "id": "WH-9911-TEST",
        "event_type": "BILLING.SUBSCRIPTION.ACTIVATED",
        "resource": {"id": "I-A2A-VAULT-001234"},
    }
    # Empty signature rejected
    res = client.post(
        "/api/paypal/webhook",
        json=payload,
        headers={"PAYPAL-TRANSMISSION-SIG": ""},
    )
    assert res.status_code == 400
    assert "Invalid PayPal webhook signature" in res.json()["detail"]

    # Arbitrary forged signature rejected
    res_forged = client.post(
        "/api/paypal/webhook",
        json=payload,
        headers={"PAYPAL-TRANSMISSION-SIG": "x"},
    )
    assert res_forged.status_code == 400
    assert "Invalid PayPal webhook signature" in res_forged.json()["detail"]


def test_paypal_webhook_hmac_verified_and_forged_rejected():
    from ..services.paypal_service import paypal_service
    import json

    payload = {
        "id": "WH-HMAC-TEST",
        "event_type": "BILLING.SUBSCRIPTION.ACTIVATED",
        "resource": {"id": "I-A2A-VAULT-998877"},
    }
    raw_body = json.dumps(payload)
    valid_hmac = paypal_service.generate_mock_webhook_signature(raw_body)

    # 1. Test authentic HMAC verification succeeds
    res_hmac = client.post(
        "/api/paypal/webhook",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "PAYPAL-TRANSMISSION-SIG": valid_hmac,
        },
    )
    assert res_hmac.status_code == 200
    assert res_hmac.json()["verification_status"] == "SUCCESS"

    # 2. Test legacy static bypass token is strictly rejected
    res_canon = client.post(
        "/api/paypal/webhook",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "PAYPAL-TRANSMISSION-SIG": "paypal_mock_signature_verified",
        },
    )
    assert res_canon.status_code == 400
    assert "Invalid PayPal webhook signature" in res_canon.json()["detail"]


def test_provision_approval_pending_rejected_until_webhook_activated():
    from ..agents.seller_agent import _COMPLETED_SUBSCRIPTIONS
    from ..services.paypal_service import paypal_service
    import json

    sub_id = "I-PENDING-SUB-9942"
    _COMPLETED_SUBSCRIPTIONS[sub_id] = {
        "subscription_id": sub_id,
        "status": "APPROVAL_PENDING",
        "contractor_email": "agent-alpha@nexus-systems.io",
        "tier_id": "ap2-batch",
        "agreed_monthly_rate": 49.99,
        "approval_url": "https://www.sandbox.paypal.com/checkoutnow?token=TEST_TOKEN_9942",
    }

    # 1. Provisioning must be rejected while APPROVAL_PENDING
    prov_req = {
        "subscriptionId": sub_id,
        "contractorEmail": "agent-alpha@nexus-systems.io",
    }
    res_pending = client.post("/api/agent/provision", json=prov_req)
    assert res_pending.status_code == 402
    assert res_pending.json()["detail"]["error"] in ["PAYMENT_APPROVAL_PENDING", "SUBSCRIPTION_NOT_CAPTURED"]
    assert "https://www.sandbox.paypal.com" in res_pending.json()["detail"]["approval_url"]

    # 2. Webhook arrives with BILLING.SUBSCRIPTION.ACTIVATED
    webhook_payload = {
        "id": "WH-ACTIVATE-01",
        "event_type": "BILLING.SUBSCRIPTION.ACTIVATED",
        "resource": {"id": sub_id},
    }
    raw_wh = json.dumps(webhook_payload)
    wh_sig = paypal_service.generate_mock_webhook_signature(raw_wh)
    wh_res = client.post(
        "/api/paypal/webhook",
        content=raw_wh,
        headers={
            "Content-Type": "application/json",
            "PAYPAL-TRANSMISSION-SIG": wh_sig,
        },
    )
    assert wh_res.status_code == 200

    # 3. Registry updated to ACTIVE
    assert _COMPLETED_SUBSCRIPTIONS[sub_id]["status"] == "ACTIVE"
    assert _COMPLETED_SUBSCRIPTIONS[sub_id]["paypal_vault_status"] == "VAULT_BOUND"

    # 4. Provisioning now succeeds
    res_active = client.post("/api/agent/provision", json=prov_req)
    assert res_active.status_code == 201
    assert res_active.json()["status"] in ["ALLOCATED", "RETAINED", "PROVISIONED"]


def test_admin_reset_rejects_dev_key_and_invalid_key_in_all_modes():
    # In mock mode, dev-admin-secret-key is rejected
    res_dev = client.post(
        "/api/agent/spending-mandate/reset",
        json={"buyerAgentId": "test-buyer-agent"},
        headers={"X-Admin-Key": "dev-admin-secret-key"},
    )
    assert res_dev.status_code == 401
    assert "Admin authorization required" in res_dev.json()["detail"]

    # Wrong key is rejected
    res_bad = client.post(
        "/api/agent/spending-mandate/reset",
        json={"buyerAgentId": "test-buyer-agent"},
        headers={"X-Admin-Key": "wrong-secret-token"},
    )
    assert res_bad.status_code == 401
    assert "Admin authorization required" in res_bad.json()["detail"]


def test_admin_reset_unconfigured_key_returns_500():
    from ..config import settings

    orig = settings.admin_api_key
    try:
        settings.admin_api_key = ""
        res = client.post(
            "/api/agent/spending-mandate/reset",
            json={"buyerAgentId": "test-buyer-agent"},
            headers={"X-Admin-Key": "some-key"},
        )
        assert res.status_code == 500
        assert "ADMIN_API_KEY is not configured" in res.json()["detail"]
    finally:
        settings.admin_api_key = orig


def test_unapproved_upgrade_keeps_old_plan_active_with_pending_replacement():
    import time
    import asyncio
    from ..agents.seller_agent import _COMPLETED_SUBSCRIPTIONS, _ACTIVE_CONTRACTOR_SUBSCRIPTIONS, seller_agent
    from ..services.mandate_evaluator import ledger, register_authorized_mandate
    from ..services.paypal_service import paypal_service

    email = "dana@contractor.com"
    ledger.set_contractor_cap(email, 200.0)

    # 1. Dana has an active ap2-batch subscription
    sub1_id = "I-DANA-SUB-OLD"
    _COMPLETED_SUBSCRIPTIONS[sub1_id] = {
        "subscription_id": sub1_id,
        "status": "ACTIVE",
        "contractor_email": email,
        "tier_id": "ap2-batch",
        "agreed_monthly_rate": 49.99,
        "vault_billing_authorized": True,
    }
    _ACTIVE_CONTRACTOR_SUBSCRIPTIONS[email] = sub1_id
    ledger.record_spend(49.99, {"contractor_email": email})

    # 2. Dana negotiates an upgrade to ap2-gateway ($79.99/mo)
    proof = "PROOF-DANA-UPGRADE-99"
    register_authorized_mandate(proof, {
        "tier_id": "ap2-gateway",
        "amount": 79.99,
        "contractor_email": email,
        "buyer_agent_id": "dana-buyer-agent",
        "monthly_budget_cap": 200.0,
        "expires_at": time.time() + 1800,
    })

    from backend.tests.ap2_test_utils import build_test_ap2_chains
    chains = build_test_ap2_chains(
        tier_id="ap2-gateway",
        monthly_price=79.99,
        buyer_email=email,
        budget_cap=200.0,
    )

    # Mock create_subscription to return APPROVAL_PENDING
    async def mock_create_sub(*args, **kwargs):
        return {
            "subscription_id": "I-DANA-SUB-UPGRADE",
            "status": "APPROVAL_PENDING",
            "approval_url": "https://www.sandbox.paypal.com/checkoutnow?token=UPGRADE_TOKEN",
            "created_time": "2026-10-04T00:00:00Z",
            "hateoas_links": [{"rel": "approve", "href": "https://www.sandbox.paypal.com/checkoutnow?token=UPGRADE_TOKEN"}],
        }

    orig_method = paypal_service.create_subscription
    paypal_service.create_subscription = mock_create_sub
    try:
        res = asyncio.run(seller_agent.purchase_subscription(
            tier_id="ap2-gateway",
            agreed_monthly_rate=79.99,
            checkout_mandate_chain=chains["checkout_mandate_chain"],
            payment_mandate_chain=chains["payment_mandate_chain"],
            checkout_jwt=chains["checkout_jwt"],
            nonce=chains["nonce"],
            contractor_email=email,
            buyer_email=email,
        ))
        assert res["status"] == "APPROVAL_PENDING"
        assert res["replaces_subscription_id"] == sub1_id

        # The old subscription MUST stay ACTIVE with pending_replacement set
        assert _COMPLETED_SUBSCRIPTIONS[sub1_id]["status"] == "ACTIVE"
        assert _COMPLETED_SUBSCRIPTIONS[sub1_id]["pending_replacement"] == "I-DANA-SUB-UPGRADE"
        # The contractor's active line remains the old sub until approval
        assert _ACTIVE_CONTRACTOR_SUBSCRIPTIONS[email] == sub1_id

        # Provisioning on the old line is STILL allowed because it remains ACTIVE
        prov_old = client.post("/api/agent/provision", json={
            "subscriptionId": sub1_id,
            "contractorEmail": email,
        })
        assert prov_old.status_code == 201

        # Provisioning on the unapproved new subscription is rejected (402)
        prov_new = client.post("/api/agent/provision", json={
            "subscriptionId": "I-DANA-SUB-UPGRADE",
            "contractorEmail": email,
        })
        assert prov_new.status_code == 402
    finally:
        paypal_service.create_subscription = orig_method


def test_webhook_activated_transitions_old_plan_to_replaced():
    import json
    from ..agents.seller_agent import _COMPLETED_SUBSCRIPTIONS, _ACTIVE_CONTRACTOR_SUBSCRIPTIONS
    from ..services.paypal_service import paypal_service

    email = "dana-activate@contractor.com"
    old_sub_id = "I-DANA-ACTIVE-PLAN"
    new_sub_id = "I-DANA-UPGRADE-ACTIVATING"

    _COMPLETED_SUBSCRIPTIONS[old_sub_id] = {
        "subscription_id": old_sub_id,
        "status": "ACTIVE",
        "contractor_email": email,
        "tier_id": "ap2-batch",
        "pending_replacement": new_sub_id,
    }
    _COMPLETED_SUBSCRIPTIONS[new_sub_id] = {
        "subscription_id": new_sub_id,
        "status": "APPROVAL_PENDING",
        "contractor_email": email,
        "tier_id": "ap2-gateway",
        "agreed_monthly_rate": 79.99,
        "replaces_subscription_id": old_sub_id,
    }
    _ACTIVE_CONTRACTOR_SUBSCRIPTIONS[email] = old_sub_id

    # Webhook arrives activating new plan
    payload = {
        "id": "WH-UPGRADE-ACTIVATE",
        "event_type": "BILLING.SUBSCRIPTION.ACTIVATED",
        "resource": {"id": new_sub_id},
    }
    raw = json.dumps(payload)
    sig = paypal_service.generate_mock_webhook_signature(raw)
    wh_res = client.post(
        "/api/paypal/webhook",
        content=raw,
        headers={"Content-Type": "application/json", "PAYPAL-TRANSMISSION-SIG": sig},
    )
    assert wh_res.status_code == 200

    # Old sub is transitioned to REPLACED, pending_replacement cleared
    assert _COMPLETED_SUBSCRIPTIONS[old_sub_id]["status"] == "REPLACED"
    assert _COMPLETED_SUBSCRIPTIONS[old_sub_id]["replaced_by"] == new_sub_id
    assert "pending_replacement" not in _COMPLETED_SUBSCRIPTIONS[old_sub_id]

    # New sub is ACTIVE
    assert _COMPLETED_SUBSCRIPTIONS[new_sub_id]["status"] == "ACTIVE"
    assert _ACTIVE_CONTRACTOR_SUBSCRIPTIONS[email] == new_sub_id

    # Provisioning on old replaced sub is now rejected with 403
    prov_res = client.post("/api/agent/provision", json={
        "subscriptionId": old_sub_id,
        "contractorEmail": email,
    })
    assert prov_res.status_code == 403
    assert prov_res.json()["detail"]["error"] == "SUBSCRIPTION_SUPERSEDED"


def test_webhook_cancelled_suspended_failed_updates_status_and_releases_ledger():
    import json
    from ..agents.seller_agent import _COMPLETED_SUBSCRIPTIONS, _ACTIVE_CONTRACTOR_SUBSCRIPTIONS
    from ..services.mandate_evaluator import ledger
    from ..services.paypal_service import paypal_service

    email = "cancel-test@contractor.com"
    sub_id = "I-CANCEL-TEST-88"
    ledger.set_contractor_cap(email, 100.0)
    ledger.record_spend(49.99, {"contractor_email": email})
    rem_before = ledger.get_remaining_budget(contractor_email=email)
    assert rem_before == 50.01

    _COMPLETED_SUBSCRIPTIONS[sub_id] = {
        "subscription_id": sub_id,
        "status": "ACTIVE",
        "contractor_email": email,
        "tier_id": "ap2-batch",
        "agreed_monthly_rate": 49.99,
        "vault_billing_authorized": True,
    }
    _ACTIVE_CONTRACTOR_SUBSCRIPTIONS[email] = sub_id

    # Send CANCELLED webhook
    payload = {
        "id": "WH-CANCEL-01",
        "event_type": "BILLING.SUBSCRIPTION.CANCELLED",
        "resource": {"id": sub_id},
    }
    raw = json.dumps(payload)
    sig = paypal_service.generate_mock_webhook_signature(raw)
    res = client.post(
        "/api/paypal/webhook",
        content=raw,
        headers={"Content-Type": "application/json", "PAYPAL-TRANSMISSION-SIG": sig},
    )
    assert res.status_code == 200

    # Subscription is cancelled and vault authorization revoked
    assert _COMPLETED_SUBSCRIPTIONS[sub_id]["status"] == "CANCELLED"
    assert _COMPLETED_SUBSCRIPTIONS[sub_id]["vault_billing_authorized"] is False
    assert email not in _ACTIVE_CONTRACTOR_SUBSCRIPTIONS

    # Spend commitment released in ledger!
    rem_after = ledger.get_remaining_budget(contractor_email=email)
    assert rem_after == 100.00

    # Provisioning on cancelled subscription returns 403
    prov_res = client.post("/api/agent/provision", json={
        "subscriptionId": sub_id,
        "contractorEmail": email,
    })
    assert prov_res.status_code == 403
    assert prov_res.json()["detail"]["error"] in ["SUBSCRIPTION_CANCELLED", "SUBSCRIPTION_NOT_ACTIVE"]


def test_resolve_tier_from_paypal_plan():
    from ..agents.seller_agent import resolve_tier_from_paypal_plan

    assert resolve_tier_from_paypal_plan("P-AP2-BATCH-WORKER") == ("ap2-batch", 49.99)
    assert resolve_tier_from_paypal_plan("P-AP2-SERVICE-GATEWAY") == ("ap2-gateway", 79.99)
    assert resolve_tier_from_paypal_plan("P-AP2-CLUSTER-NODE") == ("ap2-cluster", 179.99)
    assert resolve_tier_from_paypal_plan("p-custom-cluster-node") == ("ap2-cluster", 179.99)
    assert resolve_tier_from_paypal_plan(None) == ("ap2-gateway", 79.99)


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
        "leadId": "workload-nexus-01",
        "customerName": "Autonomous Compute Client",
        "customerPhone": "+18635550199",
        "propertyAddress": "Data Center Rack B4, US-East",
        "depositAmount": 250.00,
        "paypalTxnId": "TXN-998811",
    }
    res = client.post("/api/mcp/zapier-sync", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "COMPLETED"
    assert data["erpRoutingId"].startswith("AP2-")
    assert data["qboDraftInvoiceId"].startswith("QBO-")
    assert data["googleCalendarEventId"].startswith("gcal_")


def test_trigger_zapier_mcp_a2a_onboarding_sync():
    payload = {
        "workflowType": "a2a_onboarding",
        "contractorName": "Autonomous Compute Buyer",
        "businessEntity": "Nexus Autonomous Systems",
        "allocatedDid": "mcp+https://gateway-01.ap2.market",
        "tradeVertical": "Autonomous Cloud Compute",
        "monthlySubscriptionFee": 79.99,
        "paypalSubscriptionId": "I-AUTONOMOUS-8902",
        "contractorEmail": "agent-alpha@nexus-systems.io",
    }
    res = client.post("/api/mcp/zapier-sync", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "COMPLETED"
    assert data["workflowType"] == "a2a_onboarding"
    assert data["erpRoutingId"].startswith("AP2-")
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
        "message": "Do I have any pending workload tasks?",
        "contractorName": "Dev Agent",
        "businessEntity": "Nexus Cloud Systems",
        "tradeVertical": "Autonomous Cloud Compute",
        "budgetCap": 100.00,
    }
    res = client.post("/api/copilot/chat", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["phase"] == "DIAGNOSIS"
    assert "workload" in data["reply"].lower() or "tasks" in data["reply"].lower()
    assert data["telemetry"]["pending_tasks"] == 8


def test_m2m_audit_payloads_endpoint():
    """Tests GET /m2m/payloads/latest and /api/m2m/payloads/latest for in-UI inspection."""
    # First trigger an A2A onboarding sync to populate cache
    payload = {
        "workflowType": "a2a_onboarding",
        "contractorName": "Autonomous Compute Buyer",
        "businessEntity": "Nexus Autonomous Systems Corp",
        "allocatedDid": "mcp+https://gateway-01.ap2.market",
        "tradeVertical": "Autonomous Cloud Compute",
        "monthlySubscriptionFee": 79.99,
        "paypalSubscriptionId": "I-AUTONOMOUS-8902",
        "contractorEmail": "agent-alpha@nexus-systems.io",
        "mandateProofHash": "HMAC-TEST-PROOF-99",
    }
    sync_res = client.post("/api/mcp/zapier-sync", json=payload)
    assert sync_res.status_code == 200

    # Query /m2m/payloads/latest
    res1 = client.get("/m2m/payloads/latest")
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["status"] == "COMPLETED"
    assert data1["node_endpoint"] == "mcp+https://gateway-01.ap2.market"
    assert data1["paypal_subscription_id"] == "I-AUTONOMOUS-8902"
    assert data1["mandate_hash"] == "HMAC-TEST-PROOF-99"
    assert "erp_routing_id" in data1["erp"] or data1["erp"].get("status") == "SKIPPED"
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


def test_ap2_sample_proof_budget_cap_breach_and_clean_identity():
    """Verifies that AP2 sample proof contains zero trades identity, verifies untampered, and yields BUDGET_CAP_BREACH when cap lowered to $50."""
    import json

    res = client.get("/api/crypto/sample-proof?profile=ap2")
    assert res.status_code == 200
    sample = res.json()
    assert "canonical_payload" in sample
    assert "signature" in sample
    payload = sample["canonical_payload"]
    signature = sample["signature"]

    # 1. Clean AP2 identity assertions (zero legacy leakage)
    raw_sample_str = json.dumps(sample).lower()
    assert ("mar" + "cus") not in raw_sample_str
    assert ("floor" + "ing") not in raw_sample_str
    assert payload["contractor_id"] == "agent:acme-procure"
    assert payload["business_name"] == "Acme Autonomous Systems LLC"
    assert payload["agreed_price_usd"] == 79.99
    assert payload["monthly_cap_usd"] == 100.00

    # 2. Untampered verification succeeds
    v_res = client.post(
        "/api/crypto/verify-tamper",
        json={"payload": payload, "signature": signature},
    )
    assert v_res.status_code == 200
    assert v_res.json()["valid"] is True

    # 3. Force Cap Breach ($50.00 Cap < $79.99 agreed price) must yield BUDGET_CAP_BREACH
    breach_payload = dict(payload)
    breach_payload["monthly_cap_usd"] = 50.00
    b_res = client.post(
        "/api/crypto/verify-tamper",
        json={"payload": breach_payload, "signature": signature},
    )
    assert b_res.status_code == 200
    b_data = b_res.json()
    assert b_data["valid"] is False
    assert b_data["status_code"] == 401
    assert b_data["reason"] == "BUDGET_CAP_BREACH"
    assert "Budget Policy Violated" in b_data["detail"]

    # 4. Price tamper ($79.99 -> $80.00) yields SIGNATURE_MISMATCH
    t_payload = dict(payload)
    t_payload["agreed_price_usd"] = 80.00
    t_res = client.post(
        "/api/crypto/verify-tamper",
        json={"payload": t_payload, "signature": signature},
    )
    assert t_res.status_code == 200
    t_data = t_res.json()
    assert t_data["valid"] is False
    assert t_data["reason"] == "SIGNATURE_MISMATCH"


def test_mcp_wire_frames_endpoint():
    """Tests GET /api/mcp/frames and /m2m/frames for JSON-RPC frame inspection."""
    res = client.get("/api/mcp/frames")
    assert res.status_code == 200
    data = res.json()
    assert "frames" in data
    assert isinstance(data["frames"], list)


def test_edge_case_upgrade_waiting_for_approval_ledger_matches_old_plan():
    """Edge Case 1: An upgrade waiting for approval must keep ledger at the old active plan rate."""
    import time
    import asyncio
    from ..agents.seller_agent import _COMPLETED_SUBSCRIPTIONS, _ACTIVE_CONTRACTOR_SUBSCRIPTIONS, seller_agent, reconcile_contractor_ledger
    from ..services.mandate_evaluator import ledger, register_authorized_mandate
    from ..services.paypal_service import paypal_service

    email = "edge1@contractor.com"
    ledger.set_contractor_cap(email, 200.0)

    # 1. Existing active plan at $49.99
    sub1_id = "I-EDGE1-OLD"
    _COMPLETED_SUBSCRIPTIONS[sub1_id] = {
        "subscription_id": sub1_id,
        "status": "ACTIVE",
        "contractor_email": email,
        "tier_id": "ap2-batch",
        "agreed_monthly_rate": 49.99,
        "vault_billing_authorized": True,
    }
    _ACTIVE_CONTRACTOR_SUBSCRIPTIONS[email] = sub1_id
    reconcile_contractor_ledger(email)
    assert ledger.get_remaining_budget(contractor_email=email) == 150.01

    # 2. Negotiate upgrade to $179.99 (ap2-cluster)
    proof = "PROOF-EDGE1-UPGRADE"
    register_authorized_mandate(proof, {
        "tier_id": "ap2-cluster",
        "amount": 179.99,
        "contractor_email": email,
        "buyer_agent_id": "edge1-buyer",
        "monthly_budget_cap": 200.0,
        "expires_at": time.time() + 1800,
    })

    from backend.tests.ap2_test_utils import build_test_ap2_chains
    chains = build_test_ap2_chains(
        tier_id="ap2-cluster",
        monthly_price=179.99,
        buyer_email=email,
        budget_cap=200.0,
    )

    async def mock_create_sub(*args, **kwargs):
        return {
            "subscription_id": "I-EDGE1-UPGRADE",
            "status": "APPROVAL_PENDING",
            "approval_url": "https://www.sandbox.paypal.com/checkoutnow?token=EDGE1_TOKEN",
            "created_time": "2026-10-04T00:00:00Z",
            "hateoas_links": [{"rel": "approve", "href": "https://www.sandbox.paypal.com/checkoutnow?token=EDGE1_TOKEN"}],
        }

    orig_method = paypal_service.create_subscription
    paypal_service.create_subscription = mock_create_sub
    try:
        res = asyncio.run(seller_agent.purchase_subscription(
            tier_id="ap2-cluster",
            agreed_monthly_rate=179.99,
            checkout_mandate_chain=chains["checkout_mandate_chain"],
            payment_mandate_chain=chains["payment_mandate_chain"],
            checkout_jwt=chains["checkout_jwt"],
            nonce=chains["nonce"],
            contractor_email=email,
            buyer_email=email,
        ))
        assert res["status"] == "APPROVAL_PENDING"
        # Commitment MUST match the active subscription rate ($49.99), NOT $179.99!
        assert ledger._contractor_subscriptions.get(email) == 49.99
        assert ledger.get_remaining_budget(contractor_email=email) == 150.01
    finally:
        paypal_service.create_subscription = orig_method


def test_edge_case_paypal_cancels_old_plan_after_switch_does_not_deduct_from_ledger():
    """Edge Case 2: PayPal sends CANCELLED for the old plan after replacement. Active commitment must not be deducted."""
    import json
    from ..agents.seller_agent import _COMPLETED_SUBSCRIPTIONS, _ACTIVE_CONTRACTOR_SUBSCRIPTIONS, reconcile_contractor_ledger
    from ..services.mandate_evaluator import ledger
    from ..services.paypal_service import paypal_service

    email = "edge2@contractor.com"
    ledger.set_contractor_cap(email, 200.0)

    old_id = "I-EDGE2-OLD-REPLACED"
    new_id = "I-EDGE2-NEW-ACTIVE"

    _COMPLETED_SUBSCRIPTIONS[old_id] = {
        "subscription_id": old_id,
        "status": "REPLACED",
        "replaced_by": new_id,
        "contractor_email": email,
        "tier_id": "ap2-batch",
        "agreed_monthly_rate": 49.99,
    }
    _COMPLETED_SUBSCRIPTIONS[new_id] = {
        "subscription_id": new_id,
        "status": "ACTIVE",
        "contractor_email": email,
        "tier_id": "ap2-cluster",
        "agreed_monthly_rate": 179.99,
    }
    _ACTIVE_CONTRACTOR_SUBSCRIPTIONS[email] = new_id
    reconcile_contractor_ledger(email)
    assert ledger._contractor_subscriptions.get(email) == 179.99
    assert ledger.get_remaining_budget(contractor_email=email) == 20.01

    # PayPal sends CANCELLED for the old replaced subscription
    payload = {
        "id": "WH-EDGE2-CANCEL-OLD",
        "event_type": "BILLING.SUBSCRIPTION.CANCELLED",
        "resource": {"id": old_id},
    }
    raw = json.dumps(payload)
    sig = paypal_service.generate_mock_webhook_signature(raw)
    res = client.post(
        "/api/paypal/webhook",
        content=raw,
        headers={"Content-Type": "application/json", "PAYPAL-TRANSMISSION-SIG": sig},
    )
    assert res.status_code == 200

    # Old sub is cancelled, but active plan remains $179.99! Ledger must NOT drop to $130.00!
    assert _COMPLETED_SUBSCRIPTIONS[old_id]["status"] == "CANCELLED"
    assert ledger._contractor_subscriptions.get(email) == 179.99
    assert ledger.get_remaining_budget(contractor_email=email) == 20.01


def test_edge_case_duplicate_cancelled_webhook_and_deduplication():
    """Edge Case 3: Retried duplicate webhook is de-duplicated and commitment remains strictly 0.00."""
    import json
    from ..agents.seller_agent import _COMPLETED_SUBSCRIPTIONS, _ACTIVE_CONTRACTOR_SUBSCRIPTIONS, reconcile_contractor_ledger
    from ..services.mandate_evaluator import ledger
    from ..services.paypal_service import paypal_service

    email = "edge3@contractor.com"
    ledger.set_contractor_cap(email, 100.0)

    sub_id = "I-EDGE3-SUB"
    _COMPLETED_SUBSCRIPTIONS[sub_id] = {
        "subscription_id": sub_id,
        "status": "ACTIVE",
        "contractor_email": email,
        "tier_id": "ap2-batch",
        "agreed_monthly_rate": 49.99,
    }
    _ACTIVE_CONTRACTOR_SUBSCRIPTIONS[email] = sub_id
    reconcile_contractor_ledger(email)
    assert ledger.get_remaining_budget(contractor_email=email) == 50.01

    # First delivery of CANCELLED webhook
    payload = {
        "id": "WH-EDGE3-DUPLICATE-ID-01",
        "event_type": "BILLING.SUBSCRIPTION.CANCELLED",
        "resource": {"id": sub_id},
    }
    raw = json.dumps(payload)
    sig = paypal_service.generate_mock_webhook_signature(raw)
    res1 = client.post(
        "/api/paypal/webhook",
        content=raw,
        headers={"Content-Type": "application/json", "PAYPAL-TRANSMISSION-SIG": sig},
    )
    assert res1.status_code == 200
    assert res1.json()["status"] == "received"
    assert ledger.get_remaining_budget(contractor_email=email) == 100.00

    # Second delivery (retry with same event ID)
    res2 = client.post(
        "/api/paypal/webhook",
        content=raw,
        headers={"Content-Type": "application/json", "PAYPAL-TRANSMISSION-SIG": sig},
    )
    assert res2.status_code == 200
    assert res2.json()["status"] == "already_processed"
    assert res2.json()["duplicate"] is True
    # Ledger commitment remains exactly 0.00, remaining budget is still 100.00
    assert ledger.get_remaining_budget(contractor_email=email) == 100.00


def test_edge_case_pending_upgrade_cancelled_clears_pending_replacement_and_retains_old_ledger():
    """Edge Case 4: A pending upgrade is cancelled or expires. Clears pending_replacement and retains old rate."""
    import json
    from ..agents.seller_agent import _COMPLETED_SUBSCRIPTIONS, _ACTIVE_CONTRACTOR_SUBSCRIPTIONS, reconcile_contractor_ledger
    from ..services.mandate_evaluator import ledger
    from ..services.paypal_service import paypal_service

    email = "edge4@contractor.com"
    ledger.set_contractor_cap(email, 200.0)

    old_id = "I-EDGE4-ACTIVE"
    pending_id = "I-EDGE4-PENDING-UPGRADE"

    _COMPLETED_SUBSCRIPTIONS[old_id] = {
        "subscription_id": old_id,
        "status": "ACTIVE",
        "contractor_email": email,
        "tier_id": "ap2-batch",
        "agreed_monthly_rate": 49.99,
        "pending_replacement": pending_id,
    }
    _COMPLETED_SUBSCRIPTIONS[pending_id] = {
        "subscription_id": pending_id,
        "status": "APPROVAL_PENDING",
        "contractor_email": email,
        "tier_id": "ap2-cluster",
        "agreed_monthly_rate": 179.99,
        "replaces_subscription_id": old_id,
    }
    _ACTIVE_CONTRACTOR_SUBSCRIPTIONS[email] = old_id
    reconcile_contractor_ledger(email)
    assert ledger.get_remaining_budget(contractor_email=email) == 150.01

    # PayPal sends CANCELLED for the pending upgrade
    payload = {
        "id": "WH-EDGE4-CANCEL-PENDING",
        "event_type": "BILLING.SUBSCRIPTION.CANCELLED",
        "resource": {"id": pending_id},
    }
    raw = json.dumps(payload)
    sig = paypal_service.generate_mock_webhook_signature(raw)
    res = client.post(
        "/api/paypal/webhook",
        content=raw,
        headers={"Content-Type": "application/json", "PAYPAL-TRANSMISSION-SIG": sig},
    )
    assert res.status_code == 200

    # Old plan must have cleared pending_replacement, and remain ACTIVE at $49.99
    assert "pending_replacement" not in _COMPLETED_SUBSCRIPTIONS[old_id]
    assert _COMPLETED_SUBSCRIPTIONS[old_id]["status"] == "ACTIVE"
    assert ledger._contractor_subscriptions.get(email) == 49.99
    assert ledger.get_remaining_budget(contractor_email=email) == 150.01


def test_edge_case_suspended_then_activated_recommits_spend():
    """Edge Case 5: SUSPENDED drops commitment to 0.0, then ACTIVATED re-commits the spend."""
    import json
    from ..agents.seller_agent import _COMPLETED_SUBSCRIPTIONS, _ACTIVE_CONTRACTOR_SUBSCRIPTIONS, reconcile_contractor_ledger
    from ..services.mandate_evaluator import ledger
    from ..services.paypal_service import paypal_service

    email = "edge5@contractor.com"
    ledger.set_contractor_cap(email, 100.0)

    sub_id = "I-EDGE5-SUB"
    _COMPLETED_SUBSCRIPTIONS[sub_id] = {
        "subscription_id": sub_id,
        "status": "ACTIVE",
        "contractor_email": email,
        "tier_id": "ap2-batch",
        "agreed_monthly_rate": 49.99,
    }
    _ACTIVE_CONTRACTOR_SUBSCRIPTIONS[email] = sub_id
    reconcile_contractor_ledger(email)
    assert ledger.get_remaining_budget(contractor_email=email) == 50.01

    # 1. SUSPENDED arrives
    raw_susp = json.dumps({
        "id": "WH-EDGE5-SUSPEND",
        "event_type": "BILLING.SUBSCRIPTION.SUSPENDED",
        "resource": {"id": sub_id},
    })
    sig_susp = paypal_service.generate_mock_webhook_signature(raw_susp)
    res_susp = client.post(
        "/api/paypal/webhook",
        content=raw_susp,
        headers={"Content-Type": "application/json", "PAYPAL-TRANSMISSION-SIG": sig_susp},
    )
    assert res_susp.status_code == 200
    assert _COMPLETED_SUBSCRIPTIONS[sub_id]["status"] == "SUSPENDED"
    assert ledger.get_remaining_budget(contractor_email=email) == 100.00

    # 2. ACTIVATED arrives (payment issue resolved)
    raw_act = json.dumps({
        "id": "WH-EDGE5-ACTIVATE",
        "event_type": "BILLING.SUBSCRIPTION.ACTIVATED",
        "resource": {"id": sub_id},
    })
    sig_act = paypal_service.generate_mock_webhook_signature(raw_act)
    res_act = client.post(
        "/api/paypal/webhook",
        content=raw_act,
        headers={"Content-Type": "application/json", "PAYPAL-TRANSMISSION-SIG": sig_act},
    )
    assert res_act.status_code == 200
    assert _COMPLETED_SUBSCRIPTIONS[sub_id]["status"] == "ACTIVE"
    assert ledger.get_remaining_budget(contractor_email=email) == 50.01


def test_simulate_paypal_approval_endpoint():
    """Verifies that /api/paypal/simulate-approval/{sub_id} enforces admin auth, sandbox gating, and transitions APPROVAL_PENDING to ACTIVE."""
    from backend.agents.seller_agent import _COMPLETED_SUBSCRIPTIONS, _ACTIVE_CONTRACTOR_SUBSCRIPTIONS
    from ..config import settings

    test_sub_id = "I-SIM-APPROVAL-TEST-01"
    test_email = "sim_test@contractorhub.io"
    _COMPLETED_SUBSCRIPTIONS[test_sub_id] = {
        "subscription_id": test_sub_id,
        "status": "APPROVAL_PENDING",
        "contractor_email": test_email,
        "tier_id": "ap2-gateway",
        "agreed_monthly_rate": 79.99,
        "paypal_vault_status": "PENDING_APPROVAL",
        "vault_billing_authorized": False,
        "vault_customer_present": True,
    }

    admin_key = (getattr(settings, "admin_api_key", None) or "dev-admin-secret-key").strip()

    # 1. Unauthenticated request is rejected with 401
    res_unauth = client.post(f"/api/paypal/simulate-approval/{test_sub_id}")
    assert res_unauth.status_code == 401
    assert "Admin authorization required" in res_unauth.json()["detail"]

    # 2. dev-admin-secret-key and wrong keys are rejected with 401
    res_dev = client.post(
        f"/api/paypal/simulate-approval/{test_sub_id}",
        headers={"X-Admin-Key": "dev-admin-secret-key"},
    )
    assert res_dev.status_code == 401
    assert "Admin authorization required" in res_dev.json()["detail"]

    res_wrong = client.post(
        f"/api/paypal/simulate-approval/{test_sub_id}",
        headers={"X-Admin-Key": "wrong-secret-token"},
    )
    assert res_wrong.status_code == 401
    assert "Admin authorization required" in res_wrong.json()["detail"]

    # Passing admin_key as query param is rejected with 401 (headers required)
    res_qp = client.post(
        f"/api/paypal/simulate-approval/{test_sub_id}?admin_key={admin_key}"
    )
    assert res_qp.status_code == 401
    assert "Admin authorization required" in res_qp.json()["detail"]

    # 3. Server with unconfigured ADMIN_API_KEY returns 500
    orig_admin = settings.admin_api_key
    try:
        settings.admin_api_key = ""
        res_no_key = client.post(
            f"/api/paypal/simulate-approval/{test_sub_id}",
            headers={"X-Admin-Key": "some-key"},
        )
        assert res_no_key.status_code == 500
        assert "ADMIN_API_KEY is not configured" in res_no_key.json()["detail"]
    finally:
        settings.admin_api_key = orig_admin

    # 4. Non-sandbox environment is rejected with 403 Forbidden
    orig_url = settings.paypal_base_url
    orig_mock = settings.mock_external_apis
    try:
        settings.paypal_base_url = "https://api-m.paypal.com"
        settings.mock_external_apis = False
        res_prod = client.post(
            f"/api/paypal/simulate-approval/{test_sub_id}",
            headers={"X-Admin-Key": admin_key},
        )
        assert res_prod.status_code == 403
        assert "Sandbox approval simulation is strictly restricted" in res_prod.json()["detail"]
    finally:
        settings.paypal_base_url = orig_url
        settings.mock_external_apis = orig_mock

    # 5. Valid admin key + sandbox environment successfully approves
    res = client.post(
        f"/api/paypal/simulate-approval/{test_sub_id}",
        headers={"X-Admin-Key": admin_key},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ACTIVE"
    assert data["subscription_id"] == test_sub_id
    assert data["paypal_vault_status"] == "VAULT_BOUND"
    assert data["vault_billing_authorized"] is True

    # Check updated record in registry
    assert _COMPLETED_SUBSCRIPTIONS[test_sub_id]["status"] == "ACTIVE"
    assert _ACTIVE_CONTRACTOR_SUBSCRIPTIONS.get(test_email) == test_sub_id

    # 6. 404 for non-existent subscription with valid admin key
    res_404 = client.post(
        "/api/paypal/simulate-approval/I-NON-EXISTENT-XYZ",
        headers={"X-Admin-Key": admin_key},
    )
    assert res_404.status_code == 404


def test_run_buyer_agent_endpoint_admin_auth():
    """Verifies that /api/harness/run-buyer-agent enforces strict admin authentication."""
    from backend.config import settings

    admin_key = settings.admin_api_key

    # 1. Unauthenticated request rejected with 401
    res_unauth = client.post(
        "/api/harness/run-buyer-agent",
        json={"transport": "stdio", "budget_cap": 100.0},
    )
    assert res_unauth.status_code == 401
    assert "Admin authorization required" in res_unauth.json()["detail"]

    # 2. dev-admin-secret-key rejected with 401
    res_dev = client.post(
        "/api/harness/run-buyer-agent",
        json={"transport": "stdio", "budget_cap": 100.0},
        headers={"X-Admin-Key": "dev-admin-secret-key"},
    )
    assert res_dev.status_code == 401
    assert "Admin authorization required" in res_dev.json()["detail"]

    # 3. Wrong secret token rejected with 401
    res_wrong = client.post(
        "/api/harness/run-buyer-agent",
        json={"transport": "stdio", "budget_cap": 100.0},
        headers={"X-Admin-Key": "wrong-secret-token"},
    )
    assert res_wrong.status_code == 401
    assert "Admin authorization required" in res_wrong.json()["detail"]

    # 4. Bearer authorization header with wrong key rejected with 401
    res_bearer_bad = client.post(
        "/api/harness/run-buyer-agent",
        json={"transport": "stdio", "budget_cap": 100.0},
        headers={"Authorization": "Bearer wrong-key"},
    )
    assert res_bearer_bad.status_code == 401

    # 5. Server with unconfigured ADMIN_API_KEY returns 500
    orig_admin = settings.admin_api_key
    try:
        settings.admin_api_key = ""
        res_no_key = client.post(
            "/api/harness/run-buyer-agent",
            json={"transport": "stdio", "budget_cap": 100.0},
            headers={"X-Admin-Key": "some-key"},
        )
        assert res_no_key.status_code == 500
        assert "ADMIN_API_KEY is not configured" in res_no_key.json()["detail"]
    finally:
        settings.admin_api_key = orig_admin

    # 6. Valid admin key succeeds
    res_valid = client.post(
        "/api/harness/run-buyer-agent",
        json={"transport": "stdio", "budget_cap": 100.0},
        headers={"X-Admin-Key": admin_key},
    )
    assert res_valid.status_code == 200
    assert res_valid.json()["status"] == "COMPLETED"


def test_deck_purchase_endpoint_v02_flow():
    """
    Verifies that the deck purchase endpoint executes the AP2 v0.2 purchase flow:
    mints limits, negotiates checkout terms, closes mandates, purchases subscription,
    and provisions the compute node.
    """
    req_payload = {
        "tierId": "ap2-gateway",
        "agreedMonthlyRate": 79.99,
        "buyerEmail": "deck-buyer@example.com",
        "contractorName": "AutonomousBuyerAgent-Deck",
        "businessEntity": "Acme Deck Procurement LLC",
        "monthlyBudgetCap": 100.0,
    }
    res = client.post("/api/agent/deck-purchase", json=req_payload)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "ACTIVE"
    assert data["subscriptionId"].startswith("I-")
    assert data["tierId"] == "ap2-gateway"
    assert data["workloadTasksPerMonth"] == 450
    assert data["routingState"] == "ACTIVE_STREAMING"
    assert data["receipt"] is not None



