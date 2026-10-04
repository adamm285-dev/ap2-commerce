"""
End-to-End Autonomous Lifecycle Test Suite for FieldSmith Pro A2A Commerce.
Executes the complete multi-agent trade loop through the FastAPI REST server:
1. Opportunity Discovery & Catalog Scoping
2. Autonomous Spending Mandate Governance (HMAC verification)
3. Delegated PayPal Order / Subscription Authorization
4. Statutory KYC Telecom Provisioning (Telnyx DID line allocation)
5. Post-Payment Back-Office Automation via Zapier MCP (QBO, Jobber, Google Workspace)
6. Downstream Customer Scoping, $250 Mobilization Deposit & Bryntum Slot Locking
7. Customer Lead CRM Sync via Zapier MCP
8. Clean Mandate Ledger Reset
"""

from fastapi.testclient import TestClient
from ..server import app
from ..services.telnyx_provisioner import telnyx_provisioner
from ..config import settings

client = TestClient(app)


def test_complete_autonomous_a2a_lifecycle():
    telnyx_provisioner.reset()
    # Step 1: Health check
    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "healthy"

    # Step 2: Query Seller MCP Catalog
    res_catalog = client.get("/api/agent/catalog")
    assert res_catalog.status_code == 200
    catalog = res_catalog.json()
    assert catalog["status"] == "active"
    tier = next((t for t in catalog["trades"] if t["id"] == "flooring-tile"), None)
    assert tier is not None
    assert tier["monthlySubscription"] == 79.99

    # Step 3: Evaluate Spending Mandate ($79.99 <= $100)
    mandate_payload = {
        "buyerAgentId": "contractor-solo-buyer-marcus",
        "amount": tier["monthlySubscription"],
        "recurrence": "monthly",
        "category": "contractor-dispatch-ai",
        "monthlyBudgetCap": 100.00,
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
        "description": "FieldSmith Pro AI Voice Screener - Tile & Custom Flooring",
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
        "contractor_email": "marcus@millercustomfloors.com",
        "tier_id": "fieldsmith-pro",
        "agreed_monthly_rate": 79.99,
    }

    # Step 5: Provision Dedicated Telnyx DID anchored to Verified KYC Identity
    prov_payload = {
        "subscriptionId": sub_id,
        "contractorEmail": "marcus@millercustomfloors.com",
        "areaCode": "863",
    }
    res_prov = client.post("/api/agent/provision", json=prov_payload)
    assert res_prov.status_code == 201
    prov = res_prov.json()
    assert prov["status"] in ["ALLOCATED", "RETAINED"]
    assert prov["assignedDid"].startswith("+1863")
    allocated_did = prov["assignedDid"]
    assert prov["routingState"] == "ACTIVE_10DLC_BOUND"

    # Step 6: Trigger Autonomous Zapier MCP Contractor Onboarding Chain
    zapier_a2a_payload = {
        "workflowType": "a2a_onboarding",
        "contractorName": "Marcus Miller",
        "businessEntity": "Miller Custom Flooring LLC",
        "allocatedDid": allocated_did,
        "tradeVertical": "Tile & Custom Flooring",
        "monthlySubscriptionFee": 79.99,
        "paypalSubscriptionId": sub_id,
        "contractorEmail": "marcus@millercustomfloors.com",
    }
    res_zap_a2a = client.post("/api/mcp/zapier-sync", json=zapier_a2a_payload)
    assert res_zap_a2a.status_code == 200
    zap_a2a = res_zap_a2a.json()
    assert zap_a2a["status"] == "COMPLETED"
    assert zap_a2a["workflowType"] == "a2a_onboarding"
    assert zap_a2a["qboDraftInvoiceId"].startswith("QBO-EXP-")
    assert zap_a2a["jobberQuoteId"].startswith("JOB-ROUTING-")
    assert zap_a2a["googleCalendarEventId"].startswith("gcal_briefing_")

    # Step 7: Downstream Customer Inbound Call & Scoping Quote
    quote_payload = {
        "tradeId": "flooring-tile",
        "squareFootage": 650.0,
        "materialType": "porcelain-plank",
        "postalCode": "33813",
    }
    res_quote = client.post("/api/agent/quote", json=quote_payload)
    assert res_quote.status_code == 200
    quote = res_quote.json()
    assert quote["wasteAllowanceSqFt"] == 715.0
    assert quote["requiredDeposit"] == 250.00

    # Step 8: Lock Bryntum Territory Dispatch Slot via Verified PayPal Deposit
    lock_payload = {
        "leadId": "lead-sarah-jenkins-33813",
        "territoryZone": "Zone 2 - South Lakeland",
        "slotStartIso": "2026-10-06T10:00:00-04:00",
        "paypalTransactionId": "TXN-DEP-8849102",
    }
    res_lock = client.post("/api/agent/dispatch/lock-slot", json=lock_payload)
    assert res_lock.status_code == 200
    lock_data = res_lock.json()
    assert lock_data["success"] is True
    assert "Crew B" in lock_data["crewAssigned"]

    # Step 9: Downstream Homeowner Lead CRM Sync via Zapier MCP
    zapier_lead_payload = {
        "workflowType": "homeowner_lead",
        "leadId": "lead-sarah-jenkins-33813",
        "customerName": "Sarah Jenkins",
        "customerPhone": "+18635550199",
        "propertyAddress": "4822 Cleveland Heights Blvd, Lakeland, FL 33813",
        "depositAmount": 250.00,
        "paypalTxnId": "TXN-DEP-8849102",
    }
    res_zap_lead = client.post("/api/mcp/zapier-sync", json=zapier_lead_payload)
    assert res_zap_lead.status_code == 200
    zap_lead = res_zap_lead.json()
    assert zap_lead["status"] == "COMPLETED"
    assert zap_lead["workflowType"] == "homeowner_lead"
    assert zap_lead["jobberQuoteId"].startswith("JOB-")
    assert zap_lead["qboDraftInvoiceId"].startswith("QBO-INV-")
    assert zap_lead["googleCalendarEventId"].startswith("gcal_evt_")

    # Step 10: Reset Spending Mandate Ledger (requires Admin Authorization)
    res_reset = client.post(
        "/api/agent/spending-mandate/reset",
        json={"buyerAgentId": "contractor-solo-buyer-marcus"},
        headers={"X-Admin-Key": settings.admin_api_key},
    )
    assert res_reset.status_code == 200
    assert res_reset.json()["status"] == "reset"
    assert res_reset.json()["remaining_budget"] == 100.00
