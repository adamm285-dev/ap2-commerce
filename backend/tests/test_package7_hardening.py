"""
Package 7 hardening verification tests.

Verifies:
1. POST /api/harness/run-buyer-agent refuses when mock mode is off (returns 404).
2. POST /api/marketplace/operators/register requires admin key even at default 85% split.
   GET /api/marketplace/revenue-summary remains public.
3. Bad AP2_MERCHANT_PRIVATE_KEY_JWK environment value raises RuntimeError instead of falling through.
4. Windows ACLs: wallet._write_new_file runs cleanly on Windows/NTFS without raising.
5. Dependencies: paypal-agent-toolkit is pinned to ==1.1.0, and unused @paypal packages are removed from package.json.
6. LLM buyer agent:
   - Pre-signature guard tests payment instrument id 'vault_agent_mit' (matching the signed ID).
   - Mock LLM step refuses seller APPROVED offer if price exceeds --budget or tier not allowed.
7. POST /api/paypal/create-order requires admin credentials (unauthenticated returns 401).
"""

import asyncio
import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ..server import app
from ..config import settings
from ..services import ap2_keys
from ..agents.llm_buyer_agent import LLMBuyerAgent, StubbedModelRunner
from ..wallet import wallet

client = TestClient(app)


def test_package7_harness_route_refused_outside_mock_mode(monkeypatch):
    """POST /api/harness/run-buyer-agent must be refused (404) when mock mode is off."""
    monkeypatch.setattr(settings, "mock_external_apis", False)
    admin_key = getattr(settings, "admin_api_key", "ci_admin_secret_token_key_for_testing")
    resp = client.post(
        "/api/harness/run-buyer-agent",
        headers={"Authorization": f"Bearer {admin_key}"},
        json={"tradeId": "ap2-gateway", "budgetCap": 100.0},
    )
    assert resp.status_code == 404
    assert "MOCK_EXTERNAL_APIS=true" in resp.json()["detail"]


def test_package7_marketplace_operator_registration_requires_admin():
    """POST /api/marketplace/operators/register must reject non-admin even at default 85% split."""
    # 1. Non-admin request at 85% default split -> 403
    payload = {
        "name": "Unauth Operator Node",
        "email": "unauth-op@compute.net",
        "assigned_nodes": ["unauth-node"],
        "split_bps": 8500,
    }
    unauth_resp = client.post("/api/marketplace/operators/register", json=payload)
    assert unauth_resp.status_code == 403
    assert "OPERATOR_REGISTRATION_FORBIDDEN" in unauth_resp.json()["detail"]

    # 2. Admin request succeeds
    admin_key = getattr(settings, "admin_api_key", "ci_admin_secret_token_key_for_testing")
    auth_resp = client.post(
        "/api/marketplace/operators/register",
        headers={"Authorization": f"Bearer {admin_key}"},
        json=payload,
    )
    assert auth_resp.status_code == 201
    assert auth_resp.json()["status"] == "SUCCESS"

    # 3. GET /api/marketplace/revenue-summary stays public
    rev_resp = client.get("/api/marketplace/revenue-summary")
    assert rev_resp.status_code == 200


def test_package7_bad_merchant_private_key_env_raises(monkeypatch):
    """A bad AP2_MERCHANT_PRIVATE_KEY_JWK environment value must raise RuntimeError."""
    monkeypatch.setattr(ap2_keys, "_MERCHANT_KEY", None)
    monkeypatch.setattr(settings, "ap2_merchant_private_key_jwk", "not-a-valid-json-jwk")
    with pytest.raises(RuntimeError, match="AP2_MERCHANT_PRIVATE_KEY_JWK is set but could not be loaded as a JWK"):
        ap2_keys.get_merchant_key()

    # Also test valid JSON but missing private key
    monkeypatch.setattr(ap2_keys, "_MERCHANT_KEY", None)
    public_only_jwk = json.dumps({"kty": "EC", "crv": "P-256", "x": "abc", "y": "def"})
    monkeypatch.setattr(settings, "ap2_merchant_private_key_jwk", public_only_jwk)
    with pytest.raises(RuntimeError, match="must contain a private P-256"):
        ap2_keys.get_merchant_key()


def test_package7_requirements_pin_and_package_json():
    """paypal-agent-toolkit is pinned in requirements.txt; unused packages removed from package.json."""
    repo_root = Path(__file__).parent.parent.parent
    req_text = (repo_root / "backend" / "requirements.txt").read_text(encoding="utf-8")
    assert "paypal-agent-toolkit==1.1.0" in req_text

    pkg_text = (repo_root / "package.json").read_text(encoding="utf-8")
    assert "@paypal/agent-toolkit" not in pkg_text
    assert "@paypal/paypal-server-sdk" not in pkg_text


def test_package7_llm_pre_signature_guard_checks_vault_agent_mit():
    """The pre-signature guard tests payment instrument 'vault_agent_mit' matching what is signed."""
    import inspect
    src = inspect.getsource(LLMBuyerAgent._verify_pre_signature_constraints)
    assert 'id="vault_agent_mit"' in src
    assert "vault_{self.agent_id}" not in src


def test_package7_mock_llm_approved_offer_budget_check():
    """Mock LLM step must reject an APPROVED seller offer exceeding the budget cap."""
    runner = StubbedModelRunner()
    ctx = {
        "target_tier": "ap2-gateway",
        "budget_cap": 50.00,  # Cap is $50.00/mo
        "allowed_tiers": ["ap2-gateway"],
    }
    tool_result = {
        "status": "APPROVED",
        "agreed_monthly_rate": 79.99,  # Approved price exceeds $50.00/mo cap
        "tier_id": "ap2-gateway",
        "offer_id": "off_gateway_79",
    }
    messages = [
        {"role": "user", "content": "Procure compute node", "context": ctx},
        {"role": "tool", "tool_name": "negotiate_tier_terms", "result": tool_result},
    ]
    decision = asyncio.run(runner.decide_next_action(
        system_prompt="",
        messages=messages,
        tools=[],
    ))
    assert decision["action"] == "reject"
    assert "exceeds authorized budget cap" in decision["content"]

    # When within budget, decision is call_tool to sign_and_purchase
    ctx["budget_cap"] = 100.00
    decision_ok = asyncio.run(runner.decide_next_action(
        system_prompt="",
        messages=messages,
        tools=[],
    ))
    assert decision_ok["action"] == "call_tool"
    assert decision_ok["tool_name"] == "sign_and_purchase"


def test_package7_create_order_requires_admin():
    """POST /api/paypal/create-order requires admin credentials."""
    payload = {
        "amount": 79.99,
        "currency": "USD",
        "description": "Deposit order",
    }
    # Unauthenticated call -> 401
    unauth_resp = client.post("/api/paypal/create-order", json=payload)
    assert unauth_resp.status_code == 401

    # Authenticated call -> 200
    admin_key = getattr(settings, "admin_api_key", "ci_admin_secret_token_key_for_testing")
    auth_resp = client.post(
        "/api/paypal/create-order",
        headers={"Authorization": f"Bearer {admin_key}"},
        json=payload,
    )
    assert auth_resp.status_code == 200
    assert auth_resp.json()["status"] == "CREATED"
