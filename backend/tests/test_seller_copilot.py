"""
Unit tests for SellerCopilot agent reasoner.
Tests diagnosis, proposal, and autonomous A2A execution via MCP tools.
"""

import pytest
from backend.agents.seller_copilot import SellerCopilot


@pytest.mark.asyncio
async def test_copilot_diagnosis_intent():
    copilot = SellerCopilot()
    resp = await copilot.handle_message("Check pending workload queue today")
    assert resp["phase"] == "DIAGNOSIS"
    assert "workload" in resp["reply"].lower() or "pending tasks" in resp["reply"].lower()
    assert resp["telemetry"]["pending_tasks"] == 8
    assert resp["telemetry"]["estimated_lost_revenue"] == 6200.00
    assert len(resp["suggested_actions"]) > 0


@pytest.mark.asyncio
async def test_copilot_proposal_intent():
    copilot = SellerCopilot()
    resp = await copilot.handle_message("Find me an autonomous compute node solution")
    assert resp["phase"] == "PROPOSAL"
    assert "gateway" in resp["reply"].lower()
    assert "$79.99" in resp["reply"]
    assert resp["proposal"] is not None
    assert resp["proposal"]["monthly_price"] == 79.99
    assert resp["proposal"]["budget_cap"] == 100.00


@pytest.mark.asyncio
async def test_copilot_approval_and_a2a_execution():
    from backend.agents.seller_agent import _COMPLETED_SUBSCRIPTIONS
    from backend.services.ap2_service import verify_receipt_jwt

    copilot = SellerCopilot()
    resp = await copilot.handle_message("Yes, approve and setup ($79.99/mo via PayPal)")
    assert resp["phase"] == "COMPLETED"
    assert "autonomous a2a setup complete" in resp["reply"].lower()
    exec_result = resp["execution_result"]
    assert exec_result["status"] == "SUCCESS"
    assert exec_result["assigned_did"].startswith("mcp+https://")
    assert len(exec_result["protocol_trace"]) == 4

    # Verify AP2 v0.2 receipts on the completed purchase and in _COMPLETED_SUBSCRIPTIONS
    sub_id = exec_result["subscription_id"]
    assert sub_id in _COMPLETED_SUBSCRIPTIONS
    stored_sub = _COMPLETED_SUBSCRIPTIONS[sub_id]
    chk_receipt = exec_result.get("checkout_receipt")
    pay_receipt = exec_result.get("payment_receipt")
    assert chk_receipt and chk_receipt == stored_sub.get("checkout_receipt")
    assert pay_receipt and pay_receipt == stored_sub.get("payment_receipt")
    assert verify_receipt_jwt(chk_receipt)["status"] == "Success"
    assert verify_receipt_jwt(pay_receipt)["status"] == "Success"

    # Verify step 1: spending mandate
    step1 = exec_result["protocol_trace"][0]
    assert step1["method"] == "tools/call:evaluate_spending_mandate"
    assert step1["decision"] == "APPROVED"
    assert round(step1["remaining_budget"], 2) == 20.01

    # Verify step 2: PayPal subscription & receipts
    step2 = exec_result["protocol_trace"][1]
    assert step2["subscription_id"] == sub_id
    assert step2["checkout_receipt"] == chk_receipt
    assert step2["payment_receipt"] == pay_receipt

    # Verify step 3: compute node
    step3 = exec_result["protocol_trace"][2]
    assert step3["method"] == "tools/call:provision_compute_node"
    assert "MCP" in step3["carrier"]

    # Verify step 4: zapier sync
    step4 = exec_result["protocol_trace"][3]
    assert step4["method"] == "tools/call:dispatch_zapier_mcp"
    assert step4["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_copilot_rejection_stops_without_purchase():
    from backend.agents.seller_agent import _COMPLETED_SUBSCRIPTIONS

    before = set(_COMPLETED_SUBSCRIPTIONS)
    copilot = SellerCopilot(budget_cap=10.00)
    resp = await copilot.handle_message("yes")
    assert resp["phase"] == "REJECTED"
    assert "rejected" in resp["reply"].lower()
    assert "10.00" in resp["reply"] or "exceeds" in resp["reply"].lower()
    exec_result = resp["execution_result"]
    assert exec_result["status"] == "REJECTED"
    assert len(exec_result["protocol_trace"]) == 1
    assert exec_result["protocol_trace"][0]["decision"] == "REJECTED"
    assert set(_COMPLETED_SUBSCRIPTIONS) == before


@pytest.mark.asyncio
async def test_copilot_audit_intent():
    copilot = SellerCopilot()
    resp = await copilot.handle_message("Inspect A2A Protocol Audit Trail")
    assert resp["phase"] == "AUDIT"
    assert "rfc 8032" in resp["reply"].lower()
    assert "paypal subscriptions" in resp["reply"].lower()
    assert "mcp over https" in resp["reply"].lower()
    assert resp["action_type"] == "INSPECT_AUDIT_TRAIL"


@pytest.mark.asyncio
async def test_copilot_navigation_and_budget_intents():
    copilot = SellerCopilot()
    # Fleet ledger navigation
    resp_ledger = await copilot.handle_message("View in AP2 Fleet Ledger")
    assert resp_ledger["phase"] == "NAVIGATION"
    assert "fleet ledger" in resp_ledger["reply"].lower()
    assert resp_ledger["action_type"] == "NAVIGATE_FLEET_LEDGER"

    # Timeline navigation
    resp_timeline = await copilot.handle_message("Check Bryntum Dispatch Timeline")
    assert resp_timeline["phase"] == "NAVIGATION"
    assert "timeline" in resp_timeline["reply"].lower()
    assert resp_timeline["action_type"] == "NAVIGATE_BRYNTUM"

    # Budget query
    resp_budget = await copilot.handle_message("What's my monthly budget cap?")
    assert resp_budget["phase"] == "PROPOSAL"
    assert "$100.00" in resp_budget["reply"]
