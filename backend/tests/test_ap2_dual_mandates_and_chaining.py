"""
Comprehensive Verification Test Suite for Dual-Sided AP2 Signatures,
Machine-Readable Action Chaining, TTL Expiry Alignment, and Vault Realism.
Directly audits the architectural refinements requested for PayPal AI Hackathon 2026.
"""

import time
import pytest
from fastapi.testclient import TestClient
from backend.server import app
from backend.agents.seller_agent import seller_agent
from backend.services.mandate_evaluator import (
    ledger,
    get_authorized_mandate,
    AP2_OFFER_TTL_SEC,
)
from backend.services.crypto_mandate import (
    verify_ap2_intent_mandate,
    verify_ap2_cart_mandate,
    DEFAULT_SELLER_KID,
    DEFAULT_BUYER_KID,
    DEFAULT_SELLER_PUBLIC_KEY_HEX,
    DEFAULT_BUYER_PUBLIC_KEY_HEX,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_ledger():
    ledger.reset()


@pytest.mark.asyncio
async def test_dual_sided_ap2_mandates():
    """
    Verifies dual-sided AP2 signatures:
    - Buyer signs Intent Mandate (vct: ap2.mandate.intent.1) with buyer Ed25519 key and kid
    - Seller/Merchant signs Cart Mandate (vct: ap2.mandate.cart.1) with seller Ed25519 key and kid
    """
    neg = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="marcus-buyer-01",
        tier_id="flooring-tile",
        monthly_budget_cap=60.00,
        contractor_email="marcus@millercustomfloors.com",
    )
    assert neg["status"] == "COUNTER_OFFER"
    assert neg["offer_id"].startswith("off_solo_starter_")

    # 1. Buyer Intent Mandate verification
    intent = neg["ap2_intent_mandate"]
    assert intent["vct"] == "ap2.mandate.intent.1"
    assert intent["kid"] == DEFAULT_BUYER_KID
    assert intent["public_key"] == DEFAULT_BUYER_PUBLIC_KEY_HEX
    assert verify_ap2_intent_mandate(intent) is True

    # 2. Seller Cart Mandate verification
    cart = neg["ap2_cart_mandate"]
    assert cart["vct"] == "ap2.mandate.cart.1"
    assert cart["kid"] == DEFAULT_SELLER_KID
    assert cart["public_key"] == DEFAULT_SELLER_PUBLIC_KEY_HEX
    assert cart["amount"]["value"] == "49.99"
    assert cart["offer_id"] == neg["offer_id"]
    assert verify_ap2_cart_mandate(cart) is True

    # 3. Tampering with Cart Mandate price fails signature check
    tampered_cart = {**cart, "amount": {"value": "89.99", "currency_code": "USD"}}
    assert verify_ap2_cart_mandate(tampered_cart) is False


@pytest.mark.asyncio
async def test_machine_readable_next_action_and_offer_id_binding():
    """
    Verifies autonomous action chaining via machine-readable next_action tool calls:
    negotiate_tier_terms -> purchase_subscription (via offer_id) -> provision_telecom_line -> dispatch_zapier_mcp
    """
    # Step 1: Negotiate
    neg = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="marcus-buyer-01",
        tier_id="fieldsmith-pro",
        monthly_budget_cap=60.00,
        contractor_email="marcus@millercustomfloors.com",
    )
    assert "next_action" in neg
    next_action_1 = neg["next_action"]
    assert next_action_1["type"] == "tool_call"
    assert next_action_1["tool"] == "purchase_subscription"
    params_1 = next_action_1["parameters"]
    assert params_1["offer_id"] == neg["offer_id"]
    assert params_1["contractor_email"] == "marcus@millercustomfloors.com"

    # Step 2: Purchase using offer_id
    purchase = await seller_agent.purchase_subscription(
        offer_id=params_1["offer_id"],
        contractor_email=params_1["contractor_email"],
    )
    assert purchase["status"] == "ACTIVE"
    assert purchase["tier_id"] == "solo-starter"
    assert purchase["agreed_monthly_rate"] == 49.99
    assert purchase["vault_billing_authorized"] is True
    assert purchase["vault_customer_present"] is False
    assert purchase["payment_method"] == "paypal_vault_mit"
    assert "next_action" in purchase

    next_action_2 = purchase["next_action"]
    assert next_action_2["type"] == "tool_call"
    assert next_action_2["tool"] == "provision_telecom_line"
    params_2 = next_action_2["parameters"]
    assert params_2["subscription_id"] == purchase["subscription_id"]

    # Step 3: Telecom line provisioning
    telecom = await seller_agent.provision_telecom_line(
        subscription_id=params_2["subscription_id"],
        contractor_email=params_2["contractor_email"],
        area_code="863",
    )
    assert "next_action" in telecom
    next_action_3 = telecom["next_action"]
    assert next_action_3["type"] == "tool_call"
    assert next_action_3["tool"] == "dispatch_zapier_mcp"


@pytest.mark.asyncio
async def test_ttl_alignment_and_offer_expiry():
    """
    Verifies that the authorized registry TTL, Intent Mandate TTL, and Cart Mandate TTL
    are aligned to exactly 1800 seconds (30 minutes).
    """
    neg = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="marcus-buyer-ttl",
        tier_id="solo-starter",
        monthly_budget_cap=100.00,
        contractor_email="ttl@contractor.com",
    )
    intent = neg["ap2_intent_mandate"]
    cart = neg["ap2_cart_mandate"]
    auth = get_authorized_mandate(neg["offer_id"])

    assert intent["expires_at"] - intent["issued_at"] == AP2_OFFER_TTL_SEC
    assert cart["expires_at"] - cart["issued_at"] == AP2_OFFER_TTL_SEC
    assert abs(auth["expires_at"] - cart["expires_at"]) <= 1
    assert "T" in neg["offer_expires_at"]  # Valid ISO-8601 string


@pytest.mark.asyncio
async def test_cumulative_budget_tracking():
    """
    Verifies that purchase_subscription decrements the agent's spending cap in the ledger
    so that monthly_cap_remaining accurately tracks remaining budget across calls.
    """
    neg = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="budget-tracker-agent",
        tier_id="flooring-tile",
        monthly_budget_cap=60.00,
        contractor_email="tracker@contractor.com",
    )
    assert neg["monthly_cap_remaining"] == 10.01

    purchase = await seller_agent.purchase_subscription(
        offer_id=neg["offer_id"],
        contractor_email="tracker@contractor.com",
    )
    assert purchase["monthly_budget_cap"] == 60.00
    assert purchase["monthly_cap_remaining"] == 10.01

    # Remaining budget on ledger for this agent is now $10.01
    rem = ledger.get_remaining_budget(agent_id="budget-tracker-agent", cap=60.00)
    assert rem == 10.01


def test_agent_discovery_card_endpoint():
    """Verifies that /.well-known/agent.json publishes valid Google A2A / AP2 metadata."""
    res = client.get("/.well-known/agent.json")
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "FieldSmith Pro A2A Seller Agent"
    assert "AP2" in data["supported_protocols"]
    assert "A2A" in data["supported_protocols"]
    assert data["authentication"]["seller_kid"] == DEFAULT_SELLER_KID
    assert data["authentication"]["seller_public_key"] == DEFAULT_SELLER_PUBLIC_KEY_HEX
    assert len(data["plans"]) == 3

    # Also test /agent.json alias
    res_alias = client.get("/agent.json")
    assert res_alias.status_code == 200
    assert res_alias.json()["name"] == data["name"]
