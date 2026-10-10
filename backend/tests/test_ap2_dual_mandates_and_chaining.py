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
    build_ap2_intent_mandate,
    build_buyer_intent_mandate,
    AP2_OFFER_TTL_SEC,
    AP2_INTENT_MANDATE_TTL_SEC,
    AP2_CART_OFFER_TTL_SEC,
)
from backend.services.crypto_mandate import (
    sign_ap2_intent_mandate,
    verify_ap2_intent_mandate,
    verify_ap2_cart_mandate,
    DEFAULT_SELLER_KID,
    DEFAULT_BUYER_KID,
    DEFAULT_SELLER_PUBLIC_KEY_HEX,
    DEFAULT_BUYER_PUBLIC_KEY_HEX,
)
from backend.tests.ap2_test_utils import build_test_ap2_chains

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_ledger():
    ledger.reset()
    from backend.agents.seller_agent import (
        _COMPLETED_SUBSCRIPTIONS,
        _ACTIVE_CONTRACTOR_SUBSCRIPTIONS,
    )
    _COMPLETED_SUBSCRIPTIONS.clear()
    _ACTIVE_CONTRACTOR_SUBSCRIPTIONS.clear()
    yield
    ledger.reset()
    _COMPLETED_SUBSCRIPTIONS.clear()
    _ACTIVE_CONTRACTOR_SUBSCRIPTIONS.clear()


@pytest.mark.asyncio
async def test_dual_sided_ap2_mandates():
    """
    Verifies dual-sided AP2 signatures:
    - Buyer signs Intent Mandate (vct: ap2.mandate.intent.1) with buyer Ed25519 key and kid
    - Seller/Merchant signs Cart Mandate (vct: ap2.mandate.cart.1) with seller Ed25519 key and kid
    """
    neg = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="buyer-01",
        tier_id="ap2-gateway",
        monthly_budget_cap=60.00,
        contractor_email="buyer@ap2-procure.org",
    )
    assert neg["status"] == "COUNTER_OFFER"
    assert neg["offer_id"].startswith("off_ap2_batch_")

    # 1. Buyer Intent Mandate verification
    intent = neg["ap2_intent_mandate"]
    assert intent["vct"] == "ap2.mandate.intent.1"
    assert intent["attestation"] == "seller_attested"
    assert intent["kid"] == DEFAULT_SELLER_KID
    assert intent["public_key"] == DEFAULT_SELLER_PUBLIC_KEY_HEX
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
    negotiate_tier_terms -> purchase_subscription (via offer_id) -> provision_compute_node -> dispatch_zapier_mcp
    """
    # Step 1: Negotiate
    neg = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="buyer-01",
        tier_id="ap2-gateway",
        monthly_budget_cap=60.00,
        contractor_email="buyer@ap2-procure.org",
    )
    assert "next_action" in neg
    next_action_1 = neg["next_action"]
    assert next_action_1["type"] == "tool_call"
    assert next_action_1["tool"] == "purchase_subscription"
    params_1 = next_action_1["parameters"]
    assert params_1["offer_id"] == neg["offer_id"]

    # Step 2: Purchase using offer_id and AP2 v0.2 chains
    chains1 = build_test_ap2_chains(
        tier_id="ap2-batch",
        monthly_price=49.99,
        buyer_email="buyer@ap2-procure.org",
        budget_cap=60.0,
        checkout_record={
            "checkout_jwt": neg["checkout_jwt"],
            "checkout_hash": neg["checkout_hash"],
            "nonce": neg["nonce"],
            "order_id": neg["offer_id"],
        },
    )
    purchase = await seller_agent.purchase_subscription(
        offer_id=params_1["offer_id"],
        tier_id="ap2-batch",
        agreed_monthly_rate=49.99,
        contractor_email="buyer@ap2-procure.org",
        buyer_email="buyer@ap2-procure.org",
        checkout_mandate_chain=chains1["checkout_mandate_chain"],
        payment_mandate_chain=chains1["payment_mandate_chain"],
        checkout_jwt=neg["checkout_jwt"],
        nonce=neg["nonce"],
    )
    assert purchase["status"] == "ACTIVE"
    assert purchase["tier_id"] == "ap2-batch"
    assert purchase["agreed_monthly_rate"] == 49.99
    assert purchase["vault_billing_authorized"] is True
    assert purchase["vault_customer_present"] is False
    assert purchase["payment_method"] == "paypal_vault_mit"
    assert "next_action" in purchase

    next_action_2 = purchase["next_action"]
    assert next_action_2["type"] == "tool_call"
    assert next_action_2["tool"] == "provision_compute_node"
    params_2 = next_action_2["parameters"]
    assert params_2["subscription_id"] == purchase["subscription_id"]

    # Step 3: Compute node provisioning
    node = await seller_agent.provision_compute_node(
        subscription_id=params_2["subscription_id"],
        buyer_email=params_2.get("buyer_email") or params_2.get("contractor_email") or "buyer@ap2-procure.org",
    )
    assert node["status"] == "PROVISIONED"
    assert node["endpoint"].startswith("mcp+https://")
    assert "next_action" in node
    next_action_3 = node["next_action"]
    assert next_action_3["type"] == "tool_call"
    assert next_action_3["tool"] == "dispatch_zapier_mcp"


@pytest.mark.asyncio
async def test_ttl_alignment_and_offer_expiry():
    """
    Verifies that the authorized registry TTL, Intent Mandate TTL, and Cart Mandate TTL
    are aligned to exactly 1800 seconds (30 minutes).
    """
    neg = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="buyer-ttl",
        tier_id="ap2-batch",
        monthly_budget_cap=100.00,
        contractor_email="ttl@buyer.com",
    )
    intent = neg["ap2_intent_mandate"]
    cart = neg["ap2_cart_mandate"]
    auth = get_authorized_mandate(neg["offer_id"])

    assert intent["expires_at"] - intent["issued_at"] == AP2_INTENT_MANDATE_TTL_SEC
    assert cart["expires_at"] - cart["issued_at"] == AP2_CART_OFFER_TTL_SEC
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
        tier_id="ap2-gateway",
        monthly_budget_cap=60.00,
        contractor_email="tracker@buyer.com",
    )
    assert neg["monthly_cap_remaining"] == 10.01

    chains = build_test_ap2_chains(
        tier_id="ap2-batch",
        monthly_price=49.99,
        buyer_email="tracker@buyer.com",
        budget_cap=60.0,
        checkout_record={
            "checkout_jwt": neg["checkout_jwt"],
            "checkout_hash": neg["checkout_hash"],
            "nonce": neg["nonce"],
            "order_id": neg["offer_id"],
        },
    )
    purchase = await seller_agent.purchase_subscription(
        offer_id=neg["offer_id"],
        tier_id="ap2-batch",
        agreed_monthly_rate=49.99,
        contractor_email="tracker@buyer.com",
        buyer_email="tracker@buyer.com",
        checkout_mandate_chain=chains["checkout_mandate_chain"],
        payment_mandate_chain=chains["payment_mandate_chain"],
        checkout_jwt=neg["checkout_jwt"],
        nonce=neg["nonce"],
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
    assert data["name"].startswith("AP2 Autonomous Seller Node")
    assert "AP2" in data["supported_protocols"]
    assert "A2A" in data["supported_protocols"]
    assert data["authentication"]["seller_kid"] == DEFAULT_SELLER_KID
    assert data["authentication"]["seller_public_key"] == DEFAULT_SELLER_PUBLIC_KEY_HEX
    assert len(data["plans"]) == 3

    # Also test /agent.json alias
    res_alias = client.get("/agent.json")
    assert res_alias.status_code == 200
    assert res_alias.json()["name"] == data["name"]


@pytest.mark.asyncio
async def test_buyer_signed_intent_mandate_acceptance():
    """Verifies that negotiate_tier_terms accepts and binds a buyer-signed AP2 Intent Mandate."""
    custom_mandate = build_buyer_intent_mandate(
        buyer_agent_id="claude-desktop-buyer",
        amount=60.00,
        recurrence="monthly",
        category="autonomous-node-service",
        tier_id="ap2-gateway",
        contractor_email="buyer@ap2-procure.org",
    )
    assert verify_ap2_intent_mandate(custom_mandate) is True

    neg = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="claude-desktop-buyer",
        tier_id="ap2-gateway",
        monthly_budget_cap=60.00,
        contractor_email="buyer@ap2-procure.org",
        buyer_intent_mandate=custom_mandate,
    )
    assert neg["status"] == "COUNTER_OFFER"
    assert neg["offer_id"] is not None
    assert neg["ap2_intent_mandate"] == custom_mandate

    chains = build_test_ap2_chains(
        tier_id="ap2-batch",
        monthly_price=49.99,
        buyer_email="buyer@ap2-procure.org",
        budget_cap=60.0,
        checkout_record={
            "checkout_jwt": neg["checkout_jwt"],
            "checkout_hash": neg["checkout_hash"],
            "nonce": neg["nonce"],
            "order_id": neg["offer_id"],
        },
    )
    purchase = await seller_agent.purchase_subscription(
        offer_id=neg["offer_id"],
        tier_id="ap2-batch",
        agreed_monthly_rate=49.99,
        contractor_email="buyer@ap2-procure.org",
        buyer_email="buyer@ap2-procure.org",
        checkout_mandate_chain=chains["checkout_mandate_chain"],
        payment_mandate_chain=chains["payment_mandate_chain"],
        checkout_jwt=neg["checkout_jwt"],
        nonce=neg["nonce"],
    )
    assert purchase["status"] == "ACTIVE"
    assert purchase["agreed_monthly_rate"] == 49.99
    assert purchase["ap2_intent_mandate"] == custom_mandate


@pytest.mark.asyncio
async def test_tampered_buyer_signed_intent_mandate_rejected():
    """Verifies that a tampered buyer-signed mandate is rejected by negotiate_tier_terms."""
    custom_mandate = build_buyer_intent_mandate(
        buyer_agent_id="claude-desktop-buyer",
        amount=60.00,
        recurrence="monthly",
        category="autonomous-node-service",
        tier_id="ap2-gateway",
        contractor_email="buyer@ap2-procure.org",
    )
    tampered = dict(custom_mandate)
    tampered["amount"] = {"value": "999.00", "currency_code": "USD"}

    neg = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="claude-desktop-buyer",
        tier_id="ap2-gateway",
        monthly_budget_cap=60.00,
        contractor_email="buyer@ap2-procure.org",
        buyer_intent_mandate=tampered,
    )
    assert neg["status"] == "REJECTED"
    assert neg["error"] == "INVALID_BUYER_INTENT_MANDATE"


@pytest.mark.asyncio
async def test_buyer_signed_intent_mandate_identity_mismatch():
    """Verifies that a buyer-signed mandate with conflicting contractor email is rejected."""
    custom_mandate = build_buyer_intent_mandate(
        buyer_agent_id="claude-desktop-buyer",
        amount=60.00,
        recurrence="monthly",
        category="autonomous-node-service",
        tier_id="ap2-gateway",
        contractor_email="attacker@evil.com",
    )

    neg = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="claude-desktop-buyer",
        tier_id="ap2-gateway",
        monthly_budget_cap=60.00,
        contractor_email="buyer@ap2-procure.org",
        buyer_intent_mandate=custom_mandate,
    )
    assert neg["status"] == "REJECTED"
    assert neg["error"] == "IDENTITY_MISMATCH_DETECTED"


@pytest.mark.asyncio
async def test_untrusted_buyer_key_rejected():
    """Verifies that an intent mandate signed by an unregistered/untrusted key is rejected."""
    custom_mandate = build_buyer_intent_mandate(
        buyer_agent_id="hacker-buyer-01",
        amount=60.00,
        recurrence="monthly",
        category="autonomous-node-service",
        tier_id="ap2-gateway",
        contractor_email="buyer@ap2-procure.org",
    )
    custom_mandate["kid"] = "untrusted-rogue-key"
    custom_mandate = sign_ap2_intent_mandate(custom_mandate)

    neg = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="hacker-buyer-01",
        tier_id="ap2-gateway",
        monthly_budget_cap=60.00,
        contractor_email="buyer@ap2-procure.org",
        buyer_intent_mandate=custom_mandate,
    )
    assert neg["status"] == "REJECTED"
    assert neg["error"] == "UNTRUSTED_BUYER_KEY"


@pytest.mark.asyncio
async def test_expired_buyer_mandate_rejected():
    """Verifies that an expired buyer intent mandate is rejected with MANDATE_EXPIRED."""
    custom_mandate = build_buyer_intent_mandate(
        buyer_agent_id="claude-desktop-buyer",
        amount=60.00,
        recurrence="monthly",
        category="autonomous-node-service",
        tier_id="ap2-gateway",
        contractor_email="buyer@ap2-procure.org",
    )
    custom_mandate["expires_at"] = time.time() - 3600  # Expired 1 hour ago
    custom_mandate = sign_ap2_intent_mandate(custom_mandate)

    neg = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="claude-desktop-buyer",
        tier_id="ap2-gateway",
        monthly_budget_cap=60.00,
        contractor_email="buyer@ap2-procure.org",
        buyer_intent_mandate=custom_mandate,
    )
    assert neg["status"] == "REJECTED"
    assert neg["error"] == "MANDATE_EXPIRED"


@pytest.mark.asyncio
async def test_unauthorized_category_buyer_mandate_rejected():
    """Verifies that a buyer intent mandate for an unauthorized merchant category is rejected."""
    custom_mandate = build_buyer_intent_mandate(
        buyer_agent_id="claude-desktop-buyer",
        amount=60.00,
        recurrence="monthly",
        category="GAMING_VIRTUAL_CURRENCY",
        tier_id="ap2-gateway",
        contractor_email="buyer@ap2-procure.org",
    )
    custom_mandate = sign_ap2_intent_mandate(custom_mandate)

    neg = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="claude-desktop-buyer",
        tier_id="ap2-gateway",
        monthly_budget_cap=60.00,
        contractor_email="buyer@ap2-procure.org",
        buyer_intent_mandate=custom_mandate,
    )
    assert neg["status"] == "REJECTED"
    assert neg["error"] == "UNAUTHORIZED_CATEGORY"


@pytest.mark.asyncio
async def test_signed_cap_overrides_unsigned_param():
    """
    Verifies that the signed budget cap inside the buyer mandate strictly overrides
    any caller-supplied unsigned monthly_budget_cap parameter (Test B security fix).
    """
    custom_mandate = build_buyer_intent_mandate(
        buyer_agent_id="claude-desktop-buyer",
        amount=60.00,  # Signed cap: $60.00/mo
        recurrence="monthly",
        category="autonomous-node-service",
        tier_id="ap2-gateway",
        contractor_email="buyer@ap2-procure.org",
    )

    # Caller tries to pass an inflated unsigned monthly_budget_cap of $200.00
    neg = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="claude-desktop-buyer",
        tier_id="ap2-gateway",
        monthly_budget_cap=200.00,
        contractor_email="buyer@ap2-procure.org",
        buyer_intent_mandate=custom_mandate,
    )
    assert neg["status"] == "COUNTER_OFFER"
    assert neg["counter_offer_tier_id"] == "ap2-batch"
    assert neg["next_action"]["parameters"]["tier_id"] == "ap2-batch"
    assert neg["counter_offer_amount"] == 49.99
    assert neg["monthly_budget_cap"] == 60.00  # Enforced signed cap!


@pytest.mark.asyncio
async def test_provision_compute_node_subscription_validation():
    """
    Verifies that provision_compute_node checks subscription existence and identity binding.
    """
    # 1. Non-existent subscription ID is rejected
    res_unknown = await seller_agent.provision_compute_node(
        subscription_id="SUB-NONEXISTENT-9999",
        buyer_email="buyer@ap2-procure.org",
    )
    assert res_unknown["status"] == "REJECTED"
    assert res_unknown["error"] == "SUBSCRIPTION_NOT_FOUND"

    # 2. Existing subscription with mismatched contractor email is rejected
    neg = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="buyer-01",
        tier_id="ap2-batch",
        monthly_budget_cap=60.00,
        contractor_email="buyer@ap2-procure.org",
    )
    chains = build_test_ap2_chains(
        tier_id="ap2-batch",
        monthly_price=49.99,
        buyer_email="buyer@ap2-procure.org",
        budget_cap=60.0,
        checkout_record={
            "checkout_jwt": neg["checkout_jwt"],
            "checkout_hash": neg["checkout_hash"],
            "nonce": neg["nonce"],
            "order_id": neg["offer_id"],
        },
    )
    purchase = await seller_agent.purchase_subscription(
        offer_id=neg["offer_id"],
        tier_id="ap2-batch",
        agreed_monthly_rate=49.99,
        contractor_email="buyer@ap2-procure.org",
        buyer_email="buyer@ap2-procure.org",
        checkout_mandate_chain=chains["checkout_mandate_chain"],
        payment_mandate_chain=chains["payment_mandate_chain"],
        checkout_jwt=neg["checkout_jwt"],
        nonce=neg["nonce"],
    )
    assert purchase["status"] == "ACTIVE"
    sub_id = purchase["subscription_id"]

    res_mismatch = await seller_agent.provision_compute_node(
        subscription_id=sub_id,
        buyer_email="attacker@evil.com",
    )
    assert res_mismatch["status"] == "REJECTED"
    assert res_mismatch["error"] == "IDENTITY_MISMATCH_DETECTED"


@pytest.mark.asyncio
async def test_missing_expires_at_rejected():
    """Verifies that a buyer intent mandate without expires_at is rejected."""
    custom_mandate = build_buyer_intent_mandate(
        buyer_agent_id="claude-desktop-buyer",
        amount=60.00,
        recurrence="monthly",
        category="autonomous-node-service",
        tier_id="ap2-gateway",
        contractor_email="buyer@ap2-procure.org",
    )
    custom_mandate.pop("expires_at", None)
    custom_mandate = sign_ap2_intent_mandate(custom_mandate)

    neg = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="claude-desktop-buyer",
        tier_id="ap2-gateway",
        monthly_budget_cap=60.00,
        contractor_email="buyer@ap2-procure.org",
        buyer_intent_mandate=custom_mandate,
    )
    assert neg["status"] == "REJECTED"
    assert neg["error"] == "MANDATE_EXPIRED"


@pytest.mark.asyncio
async def test_missing_payer_email_rejected():
    """Verifies that a buyer intent mandate without payer.email is rejected."""
    custom_mandate = build_buyer_intent_mandate(
        buyer_agent_id="claude-desktop-buyer",
        amount=60.00,
        recurrence="monthly",
        category="autonomous-node-service",
        tier_id="ap2-gateway",
        contractor_email="buyer@ap2-procure.org",
    )
    custom_mandate["payer"] = {}
    custom_mandate = sign_ap2_intent_mandate(custom_mandate)

    neg = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="claude-desktop-buyer",
        tier_id="ap2-gateway",
        monthly_budget_cap=60.00,
        contractor_email="buyer@ap2-procure.org",
        buyer_intent_mandate=custom_mandate,
    )
    assert neg["status"] == "REJECTED"
    assert neg["error"] == "MISSING_PAYER_EMAIL"


@pytest.mark.asyncio
async def test_provision_compute_node_synthetic_id_rejected():
    """Verifies that arbitrary I-A2A- or I-AUTONOMOUS- IDs cannot bypass provisioning validation."""
    res_fake = await seller_agent.provision_compute_node(
        subscription_id="I-A2A-0000001",
        buyer_email="attacker@example.com",
    )
    assert res_fake["status"] == "REJECTED"
    assert res_fake["error"] == "SUBSCRIPTION_NOT_FOUND"


@pytest.mark.asyncio
async def test_repo_seed_cannot_forge_mandate():
    """Verifies that signing with an untrusted seed is rejected as UNTRUSTED_BUYER_KEY."""
    import hashlib
    from cryptography.hazmat.primitives.asymmetric import ed25519
    old_seed = hashlib.sha256(b"legacy_untrusted_buyer_seed_2026").digest()
    old_priv = ed25519.Ed25519PrivateKey.from_private_bytes(old_seed)

    custom_mandate = build_buyer_intent_mandate(
        buyer_agent_id="claude-desktop-buyer",
        amount=500.00,
        recurrence="monthly",
        category="autonomous-node-service",
        tier_id="ap2-cluster",
        contractor_email="buyer@ap2-procure.org",
    )
    forged = sign_ap2_intent_mandate(custom_mandate, private_key_hex=old_priv.private_bytes_raw().hex())

    neg = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="claude-desktop-buyer",
        tier_id="ap2-cluster",
        monthly_budget_cap=500.00,
        contractor_email="buyer@ap2-procure.org",
        buyer_intent_mandate=forged,
    )
    assert neg["status"] == "REJECTED"
    assert neg["error"] == "UNTRUSTED_BUYER_KEY"


@pytest.mark.asyncio
async def test_consecutive_purchases_budget_accounting():
    """
    Verifies that multiple test purchases for the same buyer maintain
    an accurate active monthly commitment without erroneously deducting down to 0.0.
    """
    neg1 = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="claude-desktop-buyer",
        tier_id="ap2-batch",
        monthly_budget_cap=60.00,
        contractor_email="buyer@ap2-procure.org",
    )
    chains1 = build_test_ap2_chains(
        tier_id="ap2-batch",
        monthly_price=49.99,
        buyer_email="buyer@ap2-procure.org",
        budget_cap=60.0,
        checkout_record={
            "checkout_jwt": neg1["checkout_jwt"],
            "checkout_hash": neg1["checkout_hash"],
            "nonce": neg1["nonce"],
            "order_id": neg1["offer_id"],
        },
    )
    p1 = await seller_agent.purchase_subscription(
        offer_id=neg1["offer_id"],
        tier_id="ap2-batch",
        agreed_monthly_rate=49.99,
        contractor_email="buyer@ap2-procure.org",
        buyer_email="buyer@ap2-procure.org",
        checkout_mandate_chain=chains1["checkout_mandate_chain"],
        payment_mandate_chain=chains1["payment_mandate_chain"],
        checkout_jwt=neg1["checkout_jwt"],
        nonce=neg1["nonce"],
    )
    assert p1["status"] == "ACTIVE"
    assert p1["monthly_cap_remaining"] == 10.01

    # Second negotiation for the identical tier returns ALREADY_SUBSCRIBED
    neg2 = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="claude-desktop-buyer",
        tier_id="ap2-batch",
        monthly_budget_cap=60.00,
        contractor_email="buyer@ap2-procure.org",
    )
    assert neg2["status"] == "ALREADY_SUBSCRIBED"
    assert neg2["subscription_id"] == p1["subscription_id"]

    # Replay of the existing offer returns the active subscription idempotently
    p2 = await seller_agent.purchase_subscription(
        offer_id=neg1["offer_id"],
        tier_id="ap2-batch",
        agreed_monthly_rate=49.99,
        contractor_email="buyer@ap2-procure.org",
        buyer_email="buyer@ap2-procure.org",
        checkout_mandate_chain=chains1["checkout_mandate_chain"],
        payment_mandate_chain=chains1["payment_mandate_chain"],
        checkout_jwt=neg1["checkout_jwt"],
        nonce=neg1["nonce"],
    )
    assert p2["status"] == "ACTIVE"
    assert p2["monthly_cap_remaining"] == 10.01


@pytest.mark.asyncio
async def test_rapid_consecutive_offers_retain_isolated_mandates():
    """
    Verifies that when two offers are negotiated rapidly within the same 5-minute window
    for the same buyer agent and email, each offer retains a unique HMAC proof hash
    and independent offer_id. Purchasing offer 1 returns offer 1's exact offer_id and cart mandate.
    """
    neg1 = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="buyer-01",
        tier_id="ap2-gateway",
        monthly_budget_cap=60.00,
        contractor_email="buyer@ap2-procure.org",
    )
    neg2 = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="buyer-01",
        tier_id="ap2-gateway",
        monthly_budget_cap=60.00,
        contractor_email="buyer@ap2-procure.org",
    )

    # Offers must have distinct offer_ids and distinct proof hashes
    assert neg1["offer_id"] != neg2["offer_id"]
    assert neg1["mandate_proof_hash"] != neg2["mandate_proof_hash"]

    # Purchase offer 1
    chains1 = build_test_ap2_chains(
        tier_id="ap2-batch",
        monthly_price=49.99,
        buyer_email="buyer@ap2-procure.org",
        budget_cap=60.0,
        checkout_record={
            "checkout_jwt": neg1["checkout_jwt"],
            "checkout_hash": neg1["checkout_hash"],
            "nonce": neg1["nonce"],
            "order_id": neg1["offer_id"],
        },
    )
    p1 = await seller_agent.purchase_subscription(
        offer_id=neg1["offer_id"],
        tier_id="ap2-batch",
        agreed_monthly_rate=49.99,
        contractor_email="buyer@ap2-procure.org",
        buyer_email="buyer@ap2-procure.org",
        checkout_mandate_chain=chains1["checkout_mandate_chain"],
        payment_mandate_chain=chains1["payment_mandate_chain"],
        checkout_jwt=neg1["checkout_jwt"],
        nonce=neg1["nonce"],
    )
    assert p1["status"] == "ACTIVE"
    assert p1["offer_id"] == neg1["offer_id"]
    assert p1["mandate_proof_hash"] == neg1["mandate_proof_hash"]
    assert p1["ap2_cart_mandate"]["offer_id"] == neg1["offer_id"]
    assert p1["ap2_cart_mandate"]["cart_id"] == neg1["ap2_cart_mandate"]["cart_id"]
    assert p1["offer_id"] != neg2["offer_id"]

    # Purchase offer 2 independently
    chains2 = build_test_ap2_chains(
        tier_id="ap2-batch",
        monthly_price=49.99,
        buyer_email="buyer@ap2-procure.org",
        budget_cap=60.0,
        checkout_record={
            "checkout_jwt": neg2["checkout_jwt"],
            "checkout_hash": neg2["checkout_hash"],
            "nonce": neg2["nonce"],
            "order_id": neg2["offer_id"],
        },
    )
    p2 = await seller_agent.purchase_subscription(
        offer_id=neg2["offer_id"],
        tier_id="ap2-batch",
        agreed_monthly_rate=49.99,
        contractor_email="buyer@ap2-procure.org",
        buyer_email="buyer@ap2-procure.org",
        checkout_mandate_chain=chains2["checkout_mandate_chain"],
        payment_mandate_chain=chains2["payment_mandate_chain"],
        checkout_jwt=neg2["checkout_jwt"],
        nonce=neg2["nonce"],
    )
    assert p2["status"] == "ACTIVE"
    assert p2["offer_id"] == neg2["offer_id"]
    assert p2["mandate_proof_hash"] == neg2["mandate_proof_hash"]
    assert p2["ap2_cart_mandate"]["offer_id"] == neg2["offer_id"]


@pytest.mark.asyncio
async def test_budget_exhausted_machine_readable_rejection():
    """
    Verifies that when a negotiation is rejected due to budget exhaustion
    (e.g., remaining budget $10.01 is below the minimum viable $49.99 tier),
    the seller agent returns machine-readable error: "BUDGET_EXHAUSTED"
    and identifies the active_subscription_id consuming the budget.
    """
    neg1 = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="buyer-01",
        tier_id="ap2-batch",
        monthly_budget_cap=60.00,
        contractor_email="buyer@ap2-procure.org",
    )
    chains1 = build_test_ap2_chains(
        tier_id="ap2-batch",
        monthly_price=49.99,
        buyer_email="buyer@ap2-procure.org",
        budget_cap=60.0,
        checkout_record={
            "checkout_jwt": neg1["checkout_jwt"],
            "checkout_hash": neg1["checkout_hash"],
            "nonce": neg1["nonce"],
            "order_id": neg1["offer_id"],
        },
    )
    p1 = await seller_agent.purchase_subscription(
        offer_id=neg1["offer_id"],
        tier_id="ap2-batch",
        agreed_monthly_rate=49.99,
        contractor_email="buyer@ap2-procure.org",
        buyer_email="buyer@ap2-procure.org",
        checkout_mandate_chain=chains1["checkout_mandate_chain"],
        payment_mandate_chain=chains1["payment_mandate_chain"],
        checkout_jwt=neg1["checkout_jwt"],
        nonce=neg1["nonce"],
    )
    active_sub_id = p1["subscription_id"]
    assert active_sub_id.startswith("I-A2A-VAULT-")

    neg_low = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="buyer-01",
        tier_id="ap2-gateway",
        monthly_budget_cap=10.01,
        contractor_email="buyer@ap2-procure.org",
    )
    assert neg_low["status"] == "REJECTED"
    assert neg_low["approved"] is False
    assert neg_low["error"] == "BUDGET_EXHAUSTED"
    assert neg_low["active_subscription_id"] == active_sub_id
    assert neg_low["counter_offer_available"] is False


@pytest.mark.asyncio
async def test_negotiate_same_plan_returns_already_subscribed():
    """
    Verifies Guard 1: When a subscriber is actively subscribed to a tier,
    negotiating for the identical tier returns ALREADY_SUBSCRIBED and the existing subscription_id.
    """
    email = "buyer@ap2-procure.org"

    # Step 1: Buy Batch Worker
    neg1 = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="buyer-01",
        tier_id="ap2-batch",
        monthly_budget_cap=60.00,
        contractor_email=email,
    )
    chains1 = build_test_ap2_chains(
        tier_id="ap2-batch",
        monthly_price=49.99,
        buyer_email=email,
        budget_cap=60.0,
        checkout_record={
            "checkout_jwt": neg1["checkout_jwt"],
            "checkout_hash": neg1["checkout_hash"],
            "nonce": neg1["nonce"],
            "order_id": neg1["offer_id"],
        },
    )
    p1 = await seller_agent.purchase_subscription(
        offer_id=neg1["offer_id"],
        tier_id="ap2-batch",
        agreed_monthly_rate=49.99,
        contractor_email=email,
        buyer_email=email,
        checkout_mandate_chain=chains1["checkout_mandate_chain"],
        payment_mandate_chain=chains1["payment_mandate_chain"],
        checkout_jwt=neg1["checkout_jwt"],
        nonce=neg1["nonce"],
    )
    sub1_id = p1["subscription_id"]

    # Step 2: Renegotiate for the identical tier
    neg_same = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="buyer-01",
        tier_id="ap2-batch",
        monthly_budget_cap=60.00,
        contractor_email=email,
    )
    assert neg_same["status"] == "ALREADY_SUBSCRIBED"
    assert neg_same["error"] == "ALREADY_SUBSCRIBED"
    assert neg_same["subscription_id"] == sub1_id
    assert neg_same["active_subscription_id"] == sub1_id
    assert neg_same.get("approved") is False
    assert "already actively subscribed" in neg_same["reason"]


@pytest.mark.asyncio
async def test_negotiate_counter_offer_guard_no_better_offer():
    """
    Verifies Guard 2: When subscriber is already actively subscribed to Batch Worker ($49.99)
    with a $60 cap, requesting an upgrade to Service Gateway ($79.99) cannot be afforded,
    and rather than counter-offering the plan already held, the seller returns NO_BETTER_OFFER.
    """
    email = "subscriber@ap2-procure.org"

    # Step 1: Subscribe to Batch Worker
    neg1 = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="buyer-02",
        tier_id="ap2-batch",
        monthly_budget_cap=60.00,
        contractor_email=email,
    )
    chains1 = build_test_ap2_chains(
        tier_id="ap2-batch",
        monthly_price=49.99,
        buyer_email=email,
        budget_cap=60.0,
        checkout_record={
            "checkout_jwt": neg1["checkout_jwt"],
            "checkout_hash": neg1["checkout_hash"],
            "nonce": neg1["nonce"],
            "order_id": neg1["offer_id"],
        },
    )
    p1 = await seller_agent.purchase_subscription(
        offer_id=neg1["offer_id"],
        tier_id="ap2-batch",
        agreed_monthly_rate=49.99,
        contractor_email=email,
        buyer_email=email,
        checkout_mandate_chain=chains1["checkout_mandate_chain"],
        payment_mandate_chain=chains1["payment_mandate_chain"],
        checkout_jwt=neg1["checkout_jwt"],
        nonce=neg1["nonce"],
    )
    sub1_id = p1["subscription_id"]

    # Step 2: Asks for Gateway ($79.99) under $60 cap
    neg_gateway = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="buyer-02",
        tier_id="ap2-gateway",
        monthly_budget_cap=60.00,
        contractor_email=email,
    )
    assert neg_gateway["status"] == "NO_BETTER_OFFER"
    assert neg_gateway["error"] == "NO_BETTER_OFFER"
    assert neg_gateway["current_subscription_id"] == sub1_id
    assert neg_gateway["current_tier_id"] == "ap2-batch"
    assert neg_gateway.get("counter_offer_available") is not True
    assert "already subscribed to the highest viable plan" in neg_gateway["reason"]


@pytest.mark.asyncio
async def test_plan_change_upgrade_retains_phone_number_and_replaces_old_sub():
    """
    Verifies the complete Plan Change upgrade path:
    1. Subscriber starts on Batch Worker ($49.99) under $200 cap and provisions compute node.
    2. Subscriber upgrades to Cluster Node ($179.99/mo).
    3. The purchase marks Batch Worker REPLACED and sets replaces_subscription_id.
    4. Provisioning the new Cluster Node allocates with cluster quota (1,200 tasks).
    5. Active spend is $179.99/mo, with $20.01 headroom remaining.
    """
    email = "dana@ap2-procure.org"

    # Step 1: Initial Batch Worker subscription & provisioning
    neg1 = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="dana-buyer",
        tier_id="ap2-batch",
        monthly_budget_cap=200.00,
        contractor_email=email,
    )
    chains1 = build_test_ap2_chains(
        tier_id="ap2-batch",
        monthly_price=49.99,
        buyer_email=email,
        budget_cap=200.0,
        checkout_record={
            "checkout_jwt": neg1["checkout_jwt"],
            "checkout_hash": neg1["checkout_hash"],
            "nonce": neg1["nonce"],
            "order_id": neg1["offer_id"],
        },
    )
    p1 = await seller_agent.purchase_subscription(
        offer_id=neg1["offer_id"],
        tier_id="ap2-batch",
        agreed_monthly_rate=49.99,
        contractor_email=email,
        buyer_email=email,
        checkout_mandate_chain=chains1["checkout_mandate_chain"],
        payment_mandate_chain=chains1["payment_mandate_chain"],
        checkout_jwt=neg1["checkout_jwt"],
        nonce=neg1["nonce"],
    )
    sub1_id = p1["subscription_id"]

    prov1 = await seller_agent.provision_compute_node(
        subscription_id=sub1_id,
        buyer_email=email,
    )
    assert prov1["status"] == "PROVISIONED"
    assert prov1["workload_tasks_per_month"] == 125

    # Step 2: Negotiate upgrade to Cluster Node ($179.99/mo)
    neg_upgrade = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="dana-buyer",
        tier_id="ap2-cluster",
        monthly_budget_cap=200.00,
        contractor_email=email,
    )
    assert neg_upgrade["status"] == "APPROVED"
    assert neg_upgrade["replaces_subscription_id"] == sub1_id

    # Step 3: Purchase upgrade
    chains_upgrade = build_test_ap2_chains(
        tier_id="ap2-cluster",
        monthly_price=179.99,
        buyer_email=email,
        budget_cap=200.0,
        checkout_record={
            "checkout_jwt": neg_upgrade["checkout_jwt"],
            "checkout_hash": neg_upgrade["checkout_hash"],
            "nonce": neg_upgrade["nonce"],
            "order_id": neg_upgrade["offer_id"],
        },
    )
    p_upgrade = await seller_agent.purchase_subscription(
        offer_id=neg_upgrade["offer_id"],
        tier_id="ap2-cluster",
        agreed_monthly_rate=179.99,
        contractor_email=email,
        buyer_email=email,
        checkout_mandate_chain=chains_upgrade["checkout_mandate_chain"],
        payment_mandate_chain=chains_upgrade["payment_mandate_chain"],
        checkout_jwt=neg_upgrade["checkout_jwt"],
        nonce=neg_upgrade["nonce"],
    )
    sub2_id = p_upgrade["subscription_id"]
    assert p_upgrade["status"] == "ACTIVE"
    assert p_upgrade["replaces_subscription_id"] == sub1_id
    assert p_upgrade["monthly_cap_remaining"] == 20.01

    from backend.agents.seller_agent import _COMPLETED_SUBSCRIPTIONS, _ACTIVE_CONTRACTOR_SUBSCRIPTIONS
    assert _COMPLETED_SUBSCRIPTIONS[sub1_id]["status"] == "REPLACED"
    assert _COMPLETED_SUBSCRIPTIONS[sub1_id]["replaced_by"] == sub2_id
    assert _ACTIVE_CONTRACTOR_SUBSCRIPTIONS[email] == sub2_id

    # Step 4: Provision new subscription -> Allocates Cluster node with 1200 tasks
    prov2 = await seller_agent.provision_compute_node(
        subscription_id=sub2_id,
        buyer_email=email,
    )
    assert prov2["status"] == "PROVISIONED"
    assert prov2["node_type"] == "cluster"
    assert prov2["workload_tasks_per_month"] == 1200


@pytest.mark.asyncio
async def test_provision_rejects_superseded_subscription():
    """
    Verifies that calling provision_compute_node with a replaced/superseded subscription
    is rejected with SUBSCRIPTION_SUPERSEDED error.
    """
    email = "buyer@ap2-procure.org"

    # Buy plan 1
    neg1 = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="buyer-01",
        tier_id="ap2-batch",
        monthly_budget_cap=100.00,
        contractor_email=email,
    )
    chains1 = build_test_ap2_chains(
        tier_id="ap2-batch",
        monthly_price=49.99,
        buyer_email=email,
        budget_cap=100.0,
        checkout_record={
            "checkout_jwt": neg1["checkout_jwt"],
            "checkout_hash": neg1["checkout_hash"],
            "nonce": neg1["nonce"],
            "order_id": neg1["offer_id"],
        },
    )
    p1 = await seller_agent.purchase_subscription(
        offer_id=neg1["offer_id"],
        tier_id="ap2-batch",
        agreed_monthly_rate=49.99,
        contractor_email=email,
        buyer_email=email,
        checkout_mandate_chain=chains1["checkout_mandate_chain"],
        payment_mandate_chain=chains1["payment_mandate_chain"],
        checkout_jwt=neg1["checkout_jwt"],
        nonce=neg1["nonce"],
    )
    sub1_id = p1["subscription_id"]

    # Buy plan 2 (upgrade to gateway, replaces plan 1)
    neg2 = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="buyer-01",
        tier_id="ap2-gateway",
        monthly_budget_cap=100.00,
        contractor_email=email,
    )
    chains2 = build_test_ap2_chains(
        tier_id="ap2-gateway",
        monthly_price=79.99,
        buyer_email=email,
        budget_cap=100.0,
        checkout_record={
            "checkout_jwt": neg2["checkout_jwt"],
            "checkout_hash": neg2["checkout_hash"],
            "nonce": neg2["nonce"],
            "order_id": neg2["offer_id"],
        },
    )
    p2 = await seller_agent.purchase_subscription(
        offer_id=neg2["offer_id"],
        tier_id="ap2-gateway",
        agreed_monthly_rate=79.99,
        contractor_email=email,
        buyer_email=email,
        checkout_mandate_chain=chains2["checkout_mandate_chain"],
        payment_mandate_chain=chains2["payment_mandate_chain"],
        checkout_jwt=neg2["checkout_jwt"],
        nonce=neg2["nonce"],
    )
    sub2_id = p2["subscription_id"]

    # Attempt to provision the replaced plan 1
    prov_old = await seller_agent.provision_compute_node(
        subscription_id=sub1_id,
        buyer_email=email,
    )
    assert prov_old["status"] == "REJECTED"
    assert prov_old["error"] == "SUBSCRIPTION_SUPERSEDED"

    # Provision the active plan 2
    prov_active = await seller_agent.provision_compute_node(
        subscription_id=sub2_id,
        buyer_email=email,
    )
    assert prov_active["status"] == "PROVISIONED"
    assert prov_active["node_type"] == "gateway"
    assert prov_active["workload_tasks_per_month"] == 450


@pytest.mark.asyncio
async def test_multiple_rapid_purchases_worst_case_in_process():
    """
    Verifies the worst-case scenario:
    Three offers generated prior to any purchase. When bought in sequence,
    each replaces the previous one so active spend is ALWAYS <= cap ($49.99 <= $60).
    """
    email = "buyer@ap2-procure.org"

    neg_a = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="buyer-01", tier_id="ap2-batch",
        monthly_budget_cap=60.00, contractor_email=email,
    )
    neg_b = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="buyer-01", tier_id="ap2-batch",
        monthly_budget_cap=60.00, contractor_email=email,
    )
    neg_c = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="buyer-01", tier_id="ap2-batch",
        monthly_budget_cap=60.00, contractor_email=email,
    )

    chains_a = build_test_ap2_chains(
        tier_id="ap2-batch",
        monthly_price=49.99,
        buyer_email=email,
        budget_cap=60.0,
        checkout_record={
            "checkout_jwt": neg_a["checkout_jwt"],
            "checkout_hash": neg_a["checkout_hash"],
            "nonce": neg_a["nonce"],
            "order_id": neg_a["offer_id"],
        },
    )
    p_a = await seller_agent.purchase_subscription(
        offer_id=neg_a["offer_id"],
        tier_id="ap2-batch",
        agreed_monthly_rate=49.99,
        contractor_email=email,
        buyer_email=email,
        checkout_mandate_chain=chains_a["checkout_mandate_chain"],
        payment_mandate_chain=chains_a["payment_mandate_chain"],
        checkout_jwt=neg_a["checkout_jwt"],
        nonce=neg_a["nonce"],
    )
    assert p_a["status"] == "ACTIVE"

    chains_b = build_test_ap2_chains(
        tier_id="ap2-batch",
        monthly_price=49.99,
        buyer_email=email,
        budget_cap=60.0,
        checkout_record={
            "checkout_jwt": neg_b["checkout_jwt"],
            "checkout_hash": neg_b["checkout_hash"],
            "nonce": neg_b["nonce"],
            "order_id": neg_b["offer_id"],
        },
    )
    p_b = await seller_agent.purchase_subscription(
        offer_id=neg_b["offer_id"],
        tier_id="ap2-batch",
        agreed_monthly_rate=49.99,
        contractor_email=email,
        buyer_email=email,
        checkout_mandate_chain=chains_b["checkout_mandate_chain"],
        payment_mandate_chain=chains_b["payment_mandate_chain"],
        checkout_jwt=neg_b["checkout_jwt"],
        nonce=neg_b["nonce"],
    )
    assert p_b["status"] == "ACTIVE"
    assert p_b["replaces_subscription_id"] == p_a["subscription_id"]

    chains_c = build_test_ap2_chains(
        tier_id="ap2-batch",
        monthly_price=49.99,
        buyer_email=email,
        budget_cap=60.0,
        checkout_record={
            "checkout_jwt": neg_c["checkout_jwt"],
            "checkout_hash": neg_c["checkout_hash"],
            "nonce": neg_c["nonce"],
            "order_id": neg_c["offer_id"],
        },
    )
    p_c = await seller_agent.purchase_subscription(
        offer_id=neg_c["offer_id"],
        tier_id="ap2-batch",
        agreed_monthly_rate=49.99,
        contractor_email=email,
        buyer_email=email,
        checkout_mandate_chain=chains_c["checkout_mandate_chain"],
        payment_mandate_chain=chains_c["payment_mandate_chain"],
        checkout_jwt=neg_c["checkout_jwt"],
        nonce=neg_c["nonce"],
    )
    assert p_c["status"] == "ACTIVE"
    assert p_c["replaces_subscription_id"] == p_b["subscription_id"]

    from backend.agents.seller_agent import _COMPLETED_SUBSCRIPTIONS, _ACTIVE_CONTRACTOR_SUBSCRIPTIONS
    assert _COMPLETED_SUBSCRIPTIONS[p_a["subscription_id"]]["status"] == "REPLACED"
    assert _COMPLETED_SUBSCRIPTIONS[p_b["subscription_id"]]["status"] == "REPLACED"
    assert _COMPLETED_SUBSCRIPTIONS[p_c["subscription_id"]]["status"] == "ACTIVE"
    assert _ACTIVE_CONTRACTOR_SUBSCRIPTIONS[email] == p_c["subscription_id"]

    # Active recurring spend is strictly $49.99, within $60 cap
    assert ledger.get_remaining_budget(contractor_email=email, cap=60.00) == 10.01
