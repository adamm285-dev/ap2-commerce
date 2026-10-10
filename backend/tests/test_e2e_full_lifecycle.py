"""
End-to-End Autonomous Lifecycle Test Suite for AP2 Autonomous Agent Commerce.
Executes the complete multi-agent compute loop through the FastAPI REST server:
1. Opportunity Discovery & Catalog Scoping
2. Autonomous Spending Mandate Governance (Ed25519 / HMAC verification)
3. Delegated PayPal Order / Subscription Authorization
4. Compute Node Provisioning (FastMCP endpoint allocation)
5. Post-Payment Back-Office Automation via Zapier MCP (QBO, Enterprise Webhook)
6. Downstream Workload Dispatch & Bryntum Slot Locking
7. Lead / Workload Event CRM Sync via Zapier MCP
8. Clean Mandate Ledger Reset
"""

from fastapi.testclient import TestClient
from ..server import app
from ..config import settings

client = TestClient(app)


def test_complete_autonomous_a2a_lifecycle():
    # Step 1: Health check
    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "healthy"

    # Step 2: Query Seller MCP Catalog
    res_catalog = client.get("/api/agent/catalog")
    assert res_catalog.status_code == 200
    catalog = res_catalog.json()
    assert catalog["status"] == "active"
    tier = next((t for t in catalog["trades"] if t["id"] == "ap2-gateway"), None)
    assert tier is not None
    assert tier["monthlySubscription"] == 79.99

    # Step 3: Evaluate Spending Mandate ($79.99 <= $100)
    mandate_payload = {
        "buyerAgentId": "buyer-nexus-alpha",
        "amount": tier["monthlySubscription"],
        "recurrence": "monthly",
        "category": "COMPUTE_NODE_SERVICE",
        "monthlyBudgetCap": 100.00,
        "contractorEmail": "agent-alpha@example.com",
    }
    res_mandate = client.post("/api/agent/spending-mandate/evaluate", json=mandate_payload)
    assert res_mandate.status_code == 200
    mandate = res_mandate.json()
    assert mandate["approved"] is True
    assert mandate["authorizedAmount"] == 79.99
    assert round(mandate["monthlyCapRemaining"], 2) == 20.01
    proof_hash = mandate["mandateProofHash"]
    assert len(proof_hash) == 64

    # Step 4: Create Delegated PayPal Order
    order_payload = {
        "amount": 79.99,
        "currency": "USD",
        "description": "AP2 Dedicated AI Service Gateway Compute Subscription",
        "custom_id": f"A2A-MANDATE-{proof_hash[:12]}",
    }
    res_order = client.post("/api/paypal/create-order", json=order_payload)
    assert res_order.status_code == 200
    order = res_order.json()
    assert order["status"] == "CREATED"
    sub_id = f"I-AUTONOMOUS-{order['order_id'][-6:]}"

    from ..agents.seller_agent import _COMPLETED_SUBSCRIPTIONS
    _COMPLETED_SUBSCRIPTIONS[sub_id] = {
        "subscription_id": sub_id,
        "status": "ACTIVE",
        "contractor_email": "agent-alpha@example.com",
        "tier_id": "ap2-gateway",
        "agreed_monthly_rate": 79.99,
    }

    # Step 5: Provision Dedicated Compute Node Endpoint
    prov_payload = {
        "subscriptionId": sub_id,
        "contractorEmail": "agent-alpha@example.com",
    }
    res_prov = client.post("/api/agent/provision", json=prov_payload)
    assert res_prov.status_code == 201
    prov = res_prov.json()
    assert prov["status"] in ["ALLOCATED", "RETAINED", "PROVISIONED"]
    assert "mcp+https://" in prov["assignedDid"] or "gateway" in prov["assignedDid"]
    allocated_endpoint = prov["assignedDid"]

    # Step 6: Trigger Autonomous Zapier MCP Onboarding Chain
    zapier_a2a_payload = {
        "workflowType": "a2a_onboarding",
        "contractorName": "Nexus Autonomous Buyer",
        "businessEntity": "Nexus Autonomous Systems Corp",
        "allocatedDid": allocated_endpoint,
        "tradeVertical": "Dedicated AI Service Gateway",
        "monthlySubscriptionFee": 79.99,
        "paypalSubscriptionId": sub_id,
        "contractorEmail": "agent-alpha@example.com",
        "mandateProofHash": proof_hash,
    }
    res_zap_a2a = client.post("/api/mcp/zapier-sync", json=zapier_a2a_payload)
    assert res_zap_a2a.status_code == 200
    zap_a2a = res_zap_a2a.json()
    assert zap_a2a["status"] == "COMPLETED"
    assert zap_a2a["workflowType"] == "a2a_onboarding"
    assert zap_a2a["qboDraftInvoiceId"].startswith("QBO-EXP-")
    assert zap_a2a["erpRoutingId"].startswith("AP2-EXP-")

    # Step 7: Downstream Quote Calculation
    quote_payload = {
        "tradeId": "ap2-gateway",
        "squareFootage": 650.0,
        "materialType": "service-gateway",
        "postalCode": "94105",
    }
    res_quote = client.post("/api/agent/quote", json=quote_payload)
    assert res_quote.status_code == 200
    quote = res_quote.json()
    assert quote["requiredDeposit"] == 250.00

    # Step 8: Lock Territory Dispatch Slot
    lock_payload = {
        "jobId": "job-nexus-gateway-01",
        "territoryZone": "Zone 1 - US East",
        "slotStartIso": "2026-10-06T10:00:00-04:00",
        "paypalTransactionId": "TXN-DEP-8849102",
        "profile": "ap2",
    }
    res_lock = client.post("/api/agent/dispatch/lock-slot", json=lock_payload)
    assert res_lock.status_code == 200
    lock_data = res_lock.json()
    assert lock_data["success"] is True
    assert "Cluster" in lock_data["nodeAssigned"]

    # Step 9: Downstream Lead Sync via Zapier MCP
    zapier_lead_payload = {
        "workflowType": "compute_task",
        "jobId": "job-nexus-gateway-01",
        "customerName": "Nexus AI Coordinator",
        "clientFingerprint": "agent-fingerprint-0199",
        "propertyAddress": "Cloud Execution Region us-east-1",
        "paymentAmount": 250.00,
        "paypalTxnId": "TXN-DEP-8849102",
    }
    res_zap_lead = client.post("/api/mcp/zapier-sync", json=zapier_lead_payload)
    assert res_zap_lead.status_code == 200
    zap_lead = res_zap_lead.json()
    assert zap_lead["status"] == "COMPLETED"
    assert zap_lead["workflowType"] == "compute_task"
    assert zap_lead["erpRoutingId"].startswith("AP2-")
    assert zap_lead["qboDraftInvoiceId"].startswith("QBO-INV-")

    # Step 10: Reset Spending Mandate Ledger (requires Admin Authorization)
    res_reset = client.post(
        "/api/agent/spending-mandate/reset",
        json={"buyerAgentId": "buyer-nexus-alpha"},
        headers={"X-Admin-Key": settings.admin_api_key},
    )
    assert res_reset.status_code == 200
    assert res_reset.json()["status"] == "reset"
    assert res_reset.json()["remaining_budget"] == 100.00
