"""
Unit tests for ContractorCopilot agent reasoner.
Tests diagnosis, proposal, and autonomous A2A execution via MCP tools.
"""

import pytest
from backend.agents.contractor_copilot import ContractorCopilot


@pytest.mark.asyncio
async def test_copilot_diagnosis_intent():
    copilot = ContractorCopilot()
    resp = await copilot.handle_message("Did I miss any calls today on the jobsite?")
    assert resp["phase"] == "DIAGNOSIS"
    assert "missed" in resp["reply"].lower()
    assert resp["telemetry"]["missed_calls"] == 8
    assert resp["telemetry"]["estimated_lost_revenue"] == 6200.00
    assert len(resp["suggested_actions"]) > 0


@pytest.mark.asyncio
async def test_copilot_proposal_intent():
    copilot = ContractorCopilot()
    resp = await copilot.handle_message("Find me an AI answering service solution")
    assert resp["phase"] == "PROPOSAL"
    assert "fieldsmith pro" in resp["reply"].lower()
    assert "$79.99" in resp["reply"]
    assert resp["proposal"] is not None
    assert resp["proposal"]["monthly_price"] == 79.99
    assert resp["proposal"]["budget_cap"] == 100.00


@pytest.mark.asyncio
async def test_copilot_approval_and_a2a_execution():
    copilot = ContractorCopilot(area_code="863")
    resp = await copilot.handle_message("Yes, approve and setup ($79.99/mo via PayPal)")
    assert resp["phase"] == "COMPLETED"
    assert "autonomous a2a setup complete" in resp["reply"].lower()
    exec_result = resp["execution_result"]
    assert exec_result["status"] == "SUCCESS"
    assert exec_result["assigned_did"].startswith("+1")
    assert len(exec_result["protocol_trace"]) == 4

    # Verify step 1: spending mandate
    step1 = exec_result["protocol_trace"][0]
    assert step1["method"] == "tools/call:evaluate_spending_mandate"
    assert step1["decision"] == "APPROVED"
    assert round(step1["remaining_budget"], 2) == 20.01

    # Verify step 3: telecom line
    step3 = exec_result["protocol_trace"][2]
    assert step3["method"] == "tools/call:provision_telecom_line"
    assert "Telnyx" in step3["carrier"]

    # Verify step 4: zapier sync
    step4 = exec_result["protocol_trace"][3]
    assert step4["method"] == "tools/call:dispatch_zapier_mcp"
    assert step4["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_copilot_audit_intent():
    copilot = ContractorCopilot()
    resp = await copilot.handle_message("Inspect A2A Protocol Audit Trail")
    assert resp["phase"] == "AUDIT"
    assert "hmac-sha256" in resp["reply"].lower()
    assert "paypal subscriptions" in resp["reply"].lower()
    assert "telnyx 10dlc" in resp["reply"].lower()
    assert resp["action_type"] == "INSPECT_AUDIT_TRAIL"


@pytest.mark.asyncio
async def test_copilot_navigation_and_budget_intents():
    copilot = ContractorCopilot()
    # Fleet ledger navigation
    resp_ledger = await copilot.handle_message("View in FieldSmith Fleet Ledger")
    assert resp_ledger["phase"] == "NAVIGATION"
    assert "fleet ledger" in resp_ledger["reply"].lower()
    assert resp_ledger["action_type"] == "NAVIGATE_FLEET_LEDGER"

    # Bryntum timeline navigation
    resp_timeline = await copilot.handle_message("Check Bryntum Telephony Timeline")
    assert resp_timeline["phase"] == "NAVIGATION"
    assert "timeline" in resp_timeline["reply"].lower()
    assert resp_timeline["action_type"] == "NAVIGATE_BRYNTUM"

    # Budget cap inquiry
    resp_budget = await copilot.handle_message("What's my monthly budget cap?")
    assert "$100.00" in resp_budget["reply"]
    assert "spending mandate" in resp_budget["reply"].lower()

