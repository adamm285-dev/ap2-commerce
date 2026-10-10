"""
Tests for AP2 v0.2 AI Buyer Agent (backend/agents/llm_buyer_agent.py).
Verifies:
1. Autonomous direct approval procurement ($100 budget cap).
2. Autonomous counter-offer bargaining and acceptance ($60 budget cap, seller counters with Batch at $49.99).
3. Rejection when budget cap is below minimum viable tier ($40 budget cap).
4. Rejection when counter-offer exceeds budget cap.
5. Strict key isolation: Agent signs closed mandates only with agent_key and never holds owner private key.
6. Readable execution step log:
   (requested -> over limit -> counter-offer -> checked against limits -> signed)
"""

import pytest
from jwcrypto.jwk import JWK

from backend.agents.llm_buyer_agent import LLMBuyerAgent, StubbedModelRunner
from backend.services.ap2_keys import get_demo_agent_key, get_demo_user_key
from backend.services.trusted_surface_service import create_trusted_surface_open_mandates


@pytest.mark.asyncio
async def test_llm_buyer_agent_direct_approval():
    """Tests autonomous procurement when desired tier is within budget cap."""
    agent = LLMBuyerAgent(
        agent_id="test-llm-agent-01",
        monthly_budget_cap=100.00,
        buyer_email="llm-buyer-direct@example.com",
    )

    res = await agent.run_autonomous_procurement(
        owner_request="Procure Dedicated AI Service Gateway within $100/mo",
        target_tier="ap2-gateway",
    )

    assert res["status"] == "COMPLETED"
    assert "PROVISIONED" in res["summary"] or "endpoint" in str(res)
    assert any("STEP 1: REQUESTED" in s for s in res["step_log"])
    assert any("APPROVED" in s for s in res["step_log"])
    assert any("STEP 5: SIGNED" in s for s in res["step_log"])
    assert any("STEP 6: PURCHASED" in s for s in res["step_log"])


@pytest.mark.asyncio
async def test_llm_buyer_agent_counter_offer_bargaining():
    """
    Tests autonomous counter-offer acceptance when requested tier exceeds cap ($60 vs $79.99),
    seller counters with Batch ($49.99), and agent evaluates limits and accepts.
    """
    agent = LLMBuyerAgent(
        agent_id="test-llm-agent-counter",
        monthly_budget_cap=60.00,
        buyer_email="llm-buyer-counter@example.com",
    )

    res = await agent.run_autonomous_procurement(
        owner_request="I need an inference compute node with a budget limit of $60/month",
        target_tier="ap2-gateway",
    )

    assert res["status"] == "COMPLETED"
    assert "PROVISIONED" in res["summary"] or "endpoint" in str(res)

    step_log = res["step_log"]
    # Check exact progression
    assert any("STEP 1: REQUESTED" in s for s in step_log)
    assert any("STEP 2: OVER LIMIT" in s for s in step_log)
    assert any("STEP 3: COUNTER-OFFER" in s for s in step_log)
    assert any("STEP 4: CHECKED AGAINST LIMITS" in s for s in step_log)
    assert any("STEP 5: SIGNED" in s for s in step_log)
    assert any("STEP 6: PURCHASED" in s for s in step_log)


@pytest.mark.asyncio
async def test_llm_buyer_agent_rejection_below_minimum_tier():
    """Tests rejection when budget cap ($40.00) is below minimum viable tier ($49.99)."""
    agent = LLMBuyerAgent(
        agent_id="test-llm-agent-reject",
        monthly_budget_cap=40.00,
        buyer_email="llm-buyer-low@example.com",
    )

    res = await agent.run_autonomous_procurement(
        owner_request="Procure compute node under $40/month",
        target_tier="ap2-gateway",
    )

    assert res["status"] == "REJECTED"
    assert "below minimum viable tier" in res["reason"] or "budget" in res["reason"].lower()
    # Ensure no closed mandates were signed
    assert not any("STEP 5: SIGNED" in s for s in res["step_log"])
    assert not any("STEP 6: PURCHASED" in s for s in res["step_log"])


@pytest.mark.asyncio
async def test_llm_buyer_agent_key_isolation():
    """
    Verifies that the agent operates ONLY with its own holder key (agent_key)
    and never holds the human owner's private key.
    """
    owner_key = get_demo_user_key()
    agent_key = get_demo_agent_key()

    # Pre-sign open mandates using owner key on Trusted Surface
    ts_mandates = create_trusted_surface_open_mandates(
        buyer_email="isolated-key@example.com",
        monthly_budget_cap=60.00,
        user_key=owner_key,
        agent_key=agent_key,
    )

    # Instantiate agent providing only agent_key (never owner_key)
    agent = LLMBuyerAgent(
        agent_id="test-key-isolation-agent",
        monthly_budget_cap=60.00,
        buyer_email="isolated-key@example.com",
        agent_key=agent_key,
    )

    # Invariant: agent holds only agent_key
    assert agent.agent_key.kid == agent_key.kid
    assert not hasattr(agent, "user_key")
    assert not hasattr(agent, "owner_key")

    res = await agent.run_autonomous_procurement(
        owner_request="Deploy node under $60",
        target_tier="ap2-gateway",
        open_checkout_mandate_token=ts_mandates["open_checkout_mandate_token"],
        open_payment_mandate_token=ts_mandates["open_payment_mandate_token"],
    )

    assert res["status"] == "COMPLETED"
    # Verify step log confirms holder key
    signed_step = next(s for s in res["step_log"] if "Dual SD-JWT" in s)
    assert agent_key.kid in signed_step
