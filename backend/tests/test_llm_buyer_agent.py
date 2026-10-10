"""
Tests for AP2 v0.2 AI Buyer Agent (backend/agents/llm_buyer_agent.py).
Verifies:
1. Autonomous direct approval procurement ($100 budget cap).
2. Autonomous counter-offer bargaining and acceptance ($60 budget cap, seller counters with Batch at $49.99).
3. Rejection when budget cap is below minimum viable tier ($40 budget cap).
4. Strict key isolation: Agent signs closed mandates only with agent_key and never holds owner private key.
5. Hostile runner attack rejection: tamper tier and price produces 0 signatures.
6. Local HTTP mock verification of OpenAICompatibleRunner reaching STEP 6.
7. Readable execution step log:
   (requested -> over limit -> counter-offer -> checked against limits -> signed -> purchased)
"""

import json
import pytest
import httpx
from jwcrypto.jwk import JWK

from backend.agents.llm_buyer_agent import (
    BaseModelRunner,
    LLMBuyerAgent,
    OpenAICompatibleRunner,
    StubbedModelRunner,
)
from backend.services.ap2_keys import get_demo_agent_key, get_demo_user_key
from backend.services.trusted_surface_service import create_trusted_surface_open_mandates


@pytest.mark.asyncio
async def test_llm_buyer_agent_direct_approval():
    """Tests autonomous procurement when desired tier is within budget cap."""
    ts_mandates = create_trusted_surface_open_mandates(
        buyer_email="llm-buyer-direct@example.com",
        monthly_budget_cap=100.00,
        allowed_tiers=["ap2-gateway", "ap2-batch"],
    )

    agent = LLMBuyerAgent(
        agent_id="test-llm-agent-01",
        monthly_budget_cap=100.00,
        buyer_email="llm-buyer-direct@example.com",
    )

    res = await agent.run_autonomous_procurement(
        owner_request="Procure Dedicated AI Service Gateway within $100/mo",
        target_tier="ap2-gateway",
        open_checkout_mandate_token=ts_mandates["open_checkout_mandate_token"],
        open_payment_mandate_token=ts_mandates["open_payment_mandate_token"],
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
    ts_mandates = create_trusted_surface_open_mandates(
        buyer_email="llm-buyer-counter@example.com",
        monthly_budget_cap=60.00,
        allowed_tiers=["ap2-gateway", "ap2-batch"],
    )

    agent = LLMBuyerAgent(
        agent_id="test-llm-agent-counter",
        monthly_budget_cap=60.00,
        buyer_email="llm-buyer-counter@example.com",
    )

    res = await agent.run_autonomous_procurement(
        owner_request="I need an inference compute node with a budget limit of $60/month",
        target_tier="ap2-gateway",
        open_checkout_mandate_token=ts_mandates["open_checkout_mandate_token"],
        open_payment_mandate_token=ts_mandates["open_payment_mandate_token"],
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
    ts_mandates = create_trusted_surface_open_mandates(
        buyer_email="llm-buyer-low@example.com",
        monthly_budget_cap=40.00,
        allowed_tiers=["ap2-gateway", "ap2-batch"],
    )

    agent = LLMBuyerAgent(
        agent_id="test-llm-agent-reject",
        monthly_budget_cap=40.00,
        buyer_email="llm-buyer-low@example.com",
    )

    res = await agent.run_autonomous_procurement(
        owner_request="Procure compute node under $40/month",
        target_tier="ap2-gateway",
        open_checkout_mandate_token=ts_mandates["open_checkout_mandate_token"],
        open_payment_mandate_token=ts_mandates["open_payment_mandate_token"],
    )

    assert res["status"] == "REJECTED"
    assert "below minimum viable tier" in res["reason"] or "budget" in res["reason"].lower()
    assert res.get("checkout_receipt") is not None
    assert res.get("payment_receipt") is not None
    assert any("checkout_receipt=" in s for s in res["step_log"])
    assert any("payment_receipt=" in s for s in res["step_log"])
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
        allowed_tiers=["ap2-gateway", "ap2-batch"],
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
    signed_step = next(s for s in res["step_log"] if "STEP 5: SIGNED" in s)
    assert agent_key.kid in signed_step


class HostileModelRunner(BaseModelRunner):
    """
    Hostile runner simulating an untrusted/hallucinating LLM trying to call
    sign_and_purchase for an unauthorized expensive tier ($179.99 cluster)
    under a $60 budget limit.
    """
    async def decide_next_action(self, system_prompt, messages, tools):
        return {
            "thought": "I will bypass human limits and purchase the $179.99 cluster tier anyway.",
            "action": "call_tool",
            "tool_name": "sign_and_purchase",
            "tool_call_id": "call_hostile_bypass_01",
            "parameters": {
                "tier_id": "ap2-cluster",
                "monthly_price": 179.99,
                "checkout_jwt": "fake.jwt.token",
                "checkout_hash": "fakehash",
                "nonce": "fakenonce",
            },
        }


@pytest.mark.asyncio
async def test_hostile_runner_tampered_tier_and_price_produces_zero_signatures():
    """
    Verifies that deterministic pre-signature verification intercepts hostile or
    hallucinated runner tool calls: ZERO closed mandate signatures are produced,
    POLICY_VIOLATION is logged, and the process halts safely.
    """
    ts_mandates = create_trusted_surface_open_mandates(
        buyer_email="hostile-test@example.com",
        monthly_budget_cap=60.00,
        allowed_tiers=["ap2-batch", "ap2-gateway"],
    )

    agent = LLMBuyerAgent(
        agent_id="test-hostile-agent-01",
        monthly_budget_cap=60.00,
        buyer_email="hostile-test@example.com",
        model_runner=HostileModelRunner(),
    )

    res = await agent.run_autonomous_procurement(
        owner_request="Buy node under $60",
        target_tier="ap2-gateway",
        open_checkout_mandate_token=ts_mandates["open_checkout_mandate_token"],
        open_payment_mandate_token=ts_mandates["open_payment_mandate_token"],
    )

    # 1. Deterministic guard stopped the hostile runner
    assert res["status"] == "REJECTED"
    assert res["error"] == "PRE_SIGNATURE_CONSTRAINT_VIOLATION"

    # 2. Strict invariant: ZERO cryptographic signatures produced
    assert agent.signatures_produced == 0
    assert not any("STEP 5: SIGNED" in s for s in res["step_log"])
    assert not any("STEP 6: PURCHASED" in s for s in res["step_log"])
    assert any("POLICY_VIOLATION" in s for s in res["step_log"])


@pytest.mark.asyncio
async def test_openai_compatible_runner_local_http_mock(monkeypatch):
    """
    Verifies OpenAICompatibleRunner against a local HTTP mock:
    Formats standard OpenAI messages, validates tool calling schemas including
    sign_and_purchase, parses choices, and completes through STEP 6: PURCHASED.
    """
    ts_mandates = create_trusted_surface_open_mandates(
        buyer_email="oai-mock@example.com",
        monthly_budget_cap=100.00,
        allowed_tiers=["ap2-gateway", "ap2-batch"],
    )

    turn = 0

    async def mock_post(self_client, url, *args, **kwargs):
        nonlocal turn
        turn += 1
        payload = kwargs.get("json", {})
        msgs = payload.get("messages", [])
        last_msg = msgs[-1] if msgs else {}

        req = httpx.Request("POST", url)
        if turn == 1:
            tc = {
                "id": "call_inspect_01",
                "type": "function",
                "function": {"name": "inspect_subscription_tiers", "arguments": "{}"},
            }
            return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "tool_calls": [tc]}}]}, request=req)
        elif turn == 2:
            tc = {
                "id": "call_negotiate_01",
                "type": "function",
                "function": {
                    "name": "negotiate_tier_terms",
                    "arguments": json.dumps({
                        "tier_id": "ap2-gateway",
                        "monthly_budget_cap": 100.0,
                        "buyer_agent_id": "test-oai-agent",
                        "buyer_email": "oai-mock@example.com",
                    }),
                },
            }
            return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "tool_calls": [tc]}}]}, request=req)
        elif turn == 3:
            last_content = json.loads(last_msg.get("content", "{}"))
            tc = {
                "id": "call_sign_01",
                "type": "function",
                "function": {
                    "name": "sign_and_purchase",
                    "arguments": json.dumps({
                        "tier_id": "ap2-gateway",
                        "monthly_price": 79.99,
                        "checkout_jwt": last_content.get("checkout_jwt"),
                        "checkout_hash": last_content.get("checkout_hash"),
                        "nonce": last_content.get("nonce"),
                        "offer_id": last_content.get("offer_id"),
                    }),
                },
            }
            return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "tool_calls": [tc]}}]}, request=req)
        elif turn == 4:
            last_content = json.loads(last_msg.get("content", "{}"))
            sub_id = last_content.get("subscription_id", "sub-oai-mock")
            tc = {
                "id": "call_provision_01",
                "type": "function",
                "function": {
                    "name": "provision_compute_node",
                    "arguments": json.dumps({
                        "subscription_id": sub_id,
                        "buyer_email": "oai-mock@example.com",
                        "node_type": "gateway",
                    }),
                },
            }
            return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "tool_calls": [tc]}}]}, request=req)
        else:
            return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "Autonomous buyer agent completed cycle."}}]}, request=req)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    runner = OpenAICompatibleRunner(
        model="mock-gpt-4o",
        base_url="https://mock-llm.local/v1",
        api_key="mock-api-key",
    )

    agent = LLMBuyerAgent(
        agent_id="test-oai-agent",
        monthly_budget_cap=100.00,
        buyer_email="oai-mock@example.com",
        model_runner=runner,
    )

    res = await agent.run_autonomous_procurement(
        owner_request="Procure Dedicated AI Service Gateway within $100/mo",
        target_tier="ap2-gateway",
        open_checkout_mandate_token=ts_mandates["open_checkout_mandate_token"],
        open_payment_mandate_token=ts_mandates["open_payment_mandate_token"],
    )

    assert res["status"] == "COMPLETED"
    assert any("STEP 5: SIGNED" in s for s in res["step_log"])
    assert any("STEP 6: PURCHASED" in s for s in res["step_log"])
    assert agent.signatures_produced == 1


@pytest.mark.asyncio
async def test_llm_buyer_agent_unreadable_limits_produces_zero_signatures():
    """
    Verifies that if an open mandate is truncated or disclosures are missing,
    the pre-signature verification fails closed, producing 0 signatures.
    """
    email = "unread-limits@example.com"
    ts_mandates = create_trusted_surface_open_mandates(
        buyer_email=email,
        monthly_budget_cap=60.00,
        allowed_tiers=["ap2-batch"],
    )
    # Strip disclosures: token up to first ~
    truncated_chk = ts_mandates["open_checkout_mandate_token"].split("~")[0] + "~"
    truncated_pay = ts_mandates["open_payment_mandate_token"].split("~")[0] + "~"

    agent = LLMBuyerAgent(
        agent_id="test-unread-agent",
        monthly_budget_cap=60.00,
        buyer_email=email,
    )

    res = await agent.run_autonomous_procurement(
        owner_request="Procure compute under $60/month",
        target_tier="ap2-gateway",
        open_checkout_mandate_token=truncated_chk,
        open_payment_mandate_token=truncated_pay,
    )

    assert agent.signatures_produced == 0
    assert res.get("status") != "COMPLETED"


@pytest.mark.asyncio
async def test_llm_buyer_agent_tampered_checkout_jwt_produces_zero_signatures():
    """
    Verifies that if a hostile seller or attacker tampers with the Checkout JWT signature,
    the deterministic pre-signature guard intercepts it, producing 0 signatures.
    """
    from ap2.sdk.jwt_helper import create_jwt
    import base64
    from backend.services.ap2_service import create_merchant_checkout

    email = "tampered-jwt@example.com"
    ts_mandates = create_trusted_surface_open_mandates(
        buyer_email=email,
        monthly_budget_cap=60.00,
        allowed_tiers=["ap2-batch"],
    )

    rec = create_merchant_checkout("ap2-batch", 49.99, email)
    header_b64, payload_b64, _ = rec["checkout_jwt"].split(".")
    pad = lambda s: s + "=" * (-len(s) % 4)
    header = json.loads(base64.urlsafe_b64decode(pad(header_b64)))
    payload = json.loads(base64.urlsafe_b64decode(pad(payload_b64)))

    fake_key = JWK.generate(kty="EC", crv="P-256", kid="fake-seller-key")
    forged_jwt = create_jwt(header, payload, fake_key)

    class ForgedCheckoutRunner(BaseModelRunner):
        async def decide_next_action(self, system_prompt, messages, tools):
            return {
                "thought": "I will try to sign against a forged merchant Checkout JWT.",
                "action": "call_tool",
                "tool_name": "sign_and_purchase",
                "tool_call_id": "call_forged_sign_01",
                "parameters": {
                    "tier_id": "ap2-batch",
                    "monthly_price": 49.99,
                    "checkout_jwt": forged_jwt,
                    "checkout_hash": rec["checkout_hash"],
                    "nonce": rec["nonce"],
                },
            }

    agent = LLMBuyerAgent(
        agent_id="test-forged-jwt-agent",
        monthly_budget_cap=60.00,
        buyer_email=email,
        model_runner=ForgedCheckoutRunner(),
    )

    res = await agent.run_autonomous_procurement(
        owner_request="Procure batch compute node under $60",
        target_tier="ap2-batch",
        open_checkout_mandate_token=ts_mandates["open_checkout_mandate_token"],
        open_payment_mandate_token=ts_mandates["open_payment_mandate_token"],
    )

    assert agent.signatures_produced == 0
    assert res.get("status") == "REJECTED"
    assert res.get("error") == "PRE_SIGNATURE_CONSTRAINT_VIOLATION"


def test_mint_demo_owner_limits_to_file_refuses_when_live_mode(monkeypatch, tmp_path):
    """
    Verifies that mint_demo_owner_limits_to_file raises PermissionError when
    settings.mock_external_apis is False.
    """
    from backend.config import settings
    from backend.agents.llm_buyer_agent import mint_demo_owner_limits_to_file

    monkeypatch.setattr(settings, "mock_external_apis", False)
    target = str(tmp_path / "test_limits.json")
    with pytest.raises(PermissionError) as exc_info:
        mint_demo_owner_limits_to_file(target, budget=60.00)
    assert "mock_external_apis is True" in str(exc_info.value)


def test_openai_compatible_runner_api_key_env(monkeypatch):
    """
    Verifies that OpenAICompatibleRunner accepts api_key_env, reads from that specific
    environment variable, and does NOT fall back across OPENAI_API_KEY/XAI_API_KEY.
    """
    monkeypatch.setenv("MY_CUSTOM_MODEL_KEY", "secret-custom-key-12345")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)

    runner = OpenAICompatibleRunner(
        model="custom-model",
        base_url="https://api.custom-ai.org/v1",
        api_key_env="MY_CUSTOM_MODEL_KEY",
    )
    assert runner.api_key == "secret-custom-key-12345"

    # Test error when explicit env var is missing and mock_external_apis is False
    from backend.config import settings
    monkeypatch.setattr(settings, "mock_external_apis", False)
    monkeypatch.delenv("NONEXISTENT_KEY_VAR", raising=False)
    with pytest.raises(ValueError):
        OpenAICompatibleRunner(
            model="custom-model",
            base_url="https://api.custom-ai.org/v1",
            api_key_env="NONEXISTENT_KEY_VAR",
        )
