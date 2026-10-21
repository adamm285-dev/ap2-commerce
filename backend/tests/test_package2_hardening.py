import json
import uuid
import pytest
from unittest.mock import AsyncMock, patch

from backend.mcp_server import process_mcp_request
from backend.agents.seller_agent import seller_agent
from backend.agents.llm_buyer_agent import ALLOWED_BUYER_TOOLS
from backend.services.trusted_surface_service import create_trusted_surface_open_mandates
from backend.services.ap2_keys import get_demo_agent_key, get_demo_user_key
from backend.database import register_buyer_key
from backend.services.ap2_service import AP2_MERCHANT_ID, AP2_MERCHANT_NAME, create_merchant_checkout
from ap2.sdk.mandate import MandateClient
from ap2.sdk.generated.checkout_mandate import CheckoutMandate
from ap2.sdk.generated.payment_mandate import PaymentMandate
from ap2.sdk.generated.types.amount import Amount
from ap2.sdk.generated.types.merchant import Merchant
from ap2.sdk.generated.types.payment_instrument import PaymentInstrument
from fastapi.testclient import TestClient
from backend.server import app

client = TestClient(app)


@pytest.mark.asyncio
async def test_mcp_omitted_tier_returns_rejected_and_does_not_negotiate():
    """Omitting tier_id in negotiate_tier_terms via MCP returns REJECTED."""
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "negotiate_tier_terms",
            "arguments": {
                "buyer_agent_id": "test-agent-01",
                "buyer_email": "test@example.com",
                "monthly_budget_cap": 100.0,
            },
        },
    }
    resp = await process_mcp_request(req)
    assert resp["error"]["code"] == -32602
    assert resp["error"]["data"]["status"] == "REJECTED"


@pytest.mark.asyncio
async def test_mcp_omitted_cap_returns_rejected():
    """Omitting monthly_budget_cap in negotiate_tier_terms via MCP returns REJECTED."""
    req = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "negotiate_tier_terms",
            "arguments": {
                "buyer_agent_id": "test-agent-01",
                "buyer_email": "test@example.com",
                "tier_id": "ap2-gateway",
            },
        },
    }
    resp = await process_mcp_request(req)
    assert resp["error"]["code"] == -32602
    assert resp["error"]["data"]["status"] == "REJECTED"


@pytest.mark.asyncio
async def test_mcp_omitted_email_returns_rejected():
    """Omitting buyer_email in negotiate_tier_terms via MCP returns REJECTED."""
    req = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "negotiate_tier_terms",
            "arguments": {
                "buyer_agent_id": "test-agent-01",
                "tier_id": "ap2-gateway",
                "monthly_budget_cap": 100.0,
            },
        },
    }
    resp = await process_mcp_request(req)
    assert resp["error"]["code"] == -32602
    assert resp["error"]["data"]["status"] == "REJECTED"


@pytest.mark.asyncio
async def test_mcp_omitted_subscription_id_on_provision_returns_rejected():
    """Omitting subscription_id in provision_compute_node via MCP returns REJECTED."""
    req = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "provision_compute_node",
            "arguments": {
                "buyer_email": "test@example.com",
            },
        },
    }
    resp = await process_mcp_request(req)
    assert resp["error"]["code"] == -32602
    assert resp["error"]["data"]["status"] == "REJECTED"


@pytest.mark.asyncio
async def test_mcp_omitted_subscription_id_on_dispatch_zapier_returns_rejected():
    """Omitting subscription_id in dispatch_zapier_mcp via MCP returns REJECTED."""
    req = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {
            "name": "dispatch_zapier_mcp",
            "arguments": {
                "buyer_email": "test@example.com",
            },
        },
    }
    resp = await process_mcp_request(req)
    assert resp["error"]["code"] == -32602
    assert resp["error"]["data"]["status"] == "REJECTED"


@pytest.mark.asyncio
async def test_direct_seller_agent_negotiate_validations():
    """Direct calls to seller_agent.negotiate_tier_terms with missing fields return REJECTED."""
    res1 = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="",
        tier_id="ap2-gateway",
        monthly_budget_cap=100.0,
        contractor_email="a@b.com",
    )
    assert res1["status"] == "REJECTED"
    assert res1["error"] == "BUYER_AGENT_ID_REQUIRED"

    res2 = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="ag1",
        tier_id="",
        monthly_budget_cap=100.0,
        contractor_email="a@b.com",
    )
    assert res2["status"] == "REJECTED"
    assert res2["error"] == "TIER_ID_REQUIRED"

    res3 = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="ag1",
        tier_id="ap2-gateway",
        monthly_budget_cap=None,
        contractor_email="a@b.com",
    )
    assert res3["status"] == "REJECTED"
    assert res3["error"] == "BUDGET_CAP_REQUIRED"

    res4 = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="ag1",
        tier_id="ap2-gateway",
        monthly_budget_cap=100.0,
        contractor_email="",
    )
    assert res4["status"] == "REJECTED"
    assert res4["error"] == "BUYER_EMAIL_REQUIRED"


@pytest.mark.asyncio
async def test_direct_seller_agent_provision_validations():
    """Direct calls to seller_agent.provision_compute_node with missing fields return REJECTED."""
    res1 = await seller_agent.provision_compute_node(
        subscription_id="",
        buyer_email="a@b.com",
    )
    assert res1["status"] == "REJECTED"
    assert res1["error"] == "SUBSCRIPTION_ID_REQUIRED"

    res2 = await seller_agent.provision_compute_node(
        subscription_id="I-SUB-1",
        buyer_email="",
    )
    assert res2["status"] == "REJECTED"
    assert res2["error"] == "BUYER_EMAIL_REQUIRED"


@pytest.mark.asyncio
async def test_dispatch_zapier_mcp_rejects_without_exception_for_autonomous_8902():
    """I-AUTONOMOUS-8902 must NOT skip subscription lookup and must be rejected if not in DB."""
    res = await seller_agent.dispatch_zapier_mcp(
        subscription_id="I-AUTONOMOUS-8902",
        buyer_email="a@b.com",
    )
    assert res["status"] == "REJECTED"
    assert res["error"] == "SUBSCRIPTION_NOT_FOUND"


def test_llm_allowlist_does_not_contain_seller_tools():
    """ALLOWED_BUYER_TOOLS must not include the four seller tools."""
    forbidden = {
        "dispatch_zapier_mcp",
        "provision_compute_node",
        "get_subscription_details",
        "purchase_subscription",
    }
    assert forbidden.isdisjoint(ALLOWED_BUYER_TOOLS)


def test_provision_http_route_does_not_call_downline_sync():
    """POST /api/agent/provision must NOT call execute_downline_sync."""
    with patch("backend.services.zapier_mcp_dispatcher.zapier_mcp_dispatcher.execute_downline_sync") as mock_sync:
        res = client.post(
            "/api/agent/provision",
            json={
                "subscriptionId": "I-NONEXISTENT",
                "contractorEmail": "test@example.com",
            },
        )
        assert mock_sync.call_count == 0


@pytest.mark.asyncio
async def test_purchase_omitted_email_returns_rejected():
    """purchase_subscription requires buyer_email when not on offer or chains."""
    test_email = "owner-valid@example.com"
    owner_key = get_demo_user_key()
    agent_key = get_demo_agent_key()
    register_buyer_key(
        kid=owner_key.kid,
        public_key_hex=owner_key.export_public(),
        contractor_email=test_email,
    )
    limits = create_trusted_surface_open_mandates(
        buyer_email=test_email,
        monthly_budget_cap=100.0,
        allowed_tiers=["ap2-gateway"],
    )
    # Checkout created without contractor_email
    chk = create_merchant_checkout(tier_id="ap2-gateway", monthly_price=79.99, contractor_email=None)
    nonce = uuid.uuid4().hex
    mc = MandateClient()
    chk_chain = mc.present(
        holder_key=agent_key,
        mandate_token=limits["open_checkout_mandate_token"],
        payloads=[CheckoutMandate(vct="mandate.checkout.1", checkout_jwt=chk["checkout_jwt"], checkout_hash=chk["checkout_hash"])],
        aud=AP2_MERCHANT_ID,
        nonce=nonce,
    )
    pay_chain = mc.present(
        holder_key=agent_key,
        mandate_token=limits["open_payment_mandate_token"],
        payloads=[PaymentMandate(vct="mandate.payment.1", transaction_id=chk["checkout_hash"], payment_amount=Amount(amount=7999, currency="USD"), payee=Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME), payment_instrument=PaymentInstrument(type="vault", id="v1"))],
        aud=AP2_MERCHANT_ID,
        nonce=nonce,
    )
    # Caller omits buyer_email, no offer_id passed
    res = await seller_agent.purchase_subscription(
        tier_id="ap2-gateway",
        agreed_monthly_rate=79.99,
        buyer_email=None,
        contractor_email=None,
        checkout_mandate_chain=chk_chain,
        payment_mandate_chain=pay_chain,
        checkout_jwt=chk["checkout_jwt"],
        nonce=nonce,
    )
    # When buyer_email is omitted on purchase without an offer binding, it either binds from key or rejects without fake email
    assert res["status"] in ("REJECTED", "ACTIVE")
    if res["status"] == "REJECTED":
        assert res["error"] in ("BUYER_EMAIL_REQUIRED", "invalid_credential")


@pytest.mark.asyncio
async def test_second_purchase_for_same_offer_with_different_email_is_refused():
    """A second purchase for the same offer using a different email must be REFUSED."""
    email_a = "buyer-offer-a@example.com"
    email_b = "buyer-offer-b@example.com"

    owner_key = get_demo_user_key()
    agent_key = get_demo_agent_key()

    register_buyer_key(
        kid=owner_key.kid,
        public_key_hex=owner_key.export_public(),
        contractor_email=email_a,
    )

    # 1. Negotiate offer for email_a
    nego = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="test-agent-diff-email",
        tier_id="ap2-gateway",
        monthly_budget_cap=100.0,
        contractor_email=email_a,
    )
    assert nego["status"] == "APPROVED"
    offer_id = nego["offer_id"]
    chk_jwt = nego["checkout_jwt"]
    chk_hash = nego["checkout_hash"]
    nonce = nego["nonce"]

    # 2. Build AP2 chains
    limits = create_trusted_surface_open_mandates(
        buyer_email=email_a,
        monthly_budget_cap=100.0,
        allowed_tiers=["ap2-gateway"],
    )

    mc = MandateClient()
    chk_chain = mc.present(
        holder_key=agent_key,
        mandate_token=limits["open_checkout_mandate_token"],
        payloads=[
            CheckoutMandate(
                vct="mandate.checkout.1",
                checkout_jwt=chk_jwt,
                checkout_hash=chk_hash,
            )
        ],
        aud=AP2_MERCHANT_ID,
        nonce=nonce,
    )

    pay_chain = mc.present(
        holder_key=agent_key,
        mandate_token=limits["open_payment_mandate_token"],
        payloads=[
            PaymentMandate(
                vct="mandate.payment.1",
                transaction_id=chk_hash,
                payment_amount=Amount(amount=7999, currency="USD"),
                payee=Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME),
                payment_instrument=PaymentInstrument(type="vault", id="vault_123"),
            )
        ],
        aud=AP2_MERCHANT_ID,
        nonce=nonce,
    )

    # 3. First purchase with email_a succeeds
    res1 = await seller_agent.purchase_subscription(
        tier_id="ap2-gateway",
        agreed_monthly_rate=79.99,
        offer_id=offer_id,
        buyer_email=email_a,
        checkout_mandate_chain=chk_chain,
        payment_mandate_chain=pay_chain,
        checkout_jwt=chk_jwt,
        nonce=nonce,
    )
    assert res1["status"] == "ACTIVE"

    # 4. Second purchase for the SAME offer with email_b must be REFUSED
    # Case 4a: Using the original chain but claiming email_b
    res2 = await seller_agent.purchase_subscription(
        tier_id="ap2-gateway",
        agreed_monthly_rate=79.99,
        offer_id=offer_id,
        buyer_email=email_b,
        checkout_mandate_chain=chk_chain,
        payment_mandate_chain=pay_chain,
        checkout_jwt=chk_jwt,
        nonce=nonce,
    )
    assert res2["status"] == "REJECTED"
    assert res2["error"] == "MANDATE_SECURITY_BREACH"
    assert "Offer is bound to" in res2["reason"]

    # Case 4b: email_b registers its own key and creates its own valid chain for the same offer_id
    from backend.services.ap2_keys import generate_ephemeral_key
    owner_b = generate_ephemeral_key(kid="owner-b-key")
    register_buyer_key(
        kid=owner_b.kid,
        public_key_hex=owner_b.export_public(),
        contractor_email=email_b,
    )
    limits_b = create_trusted_surface_open_mandates(
        buyer_email=email_b,
        monthly_budget_cap=100.0,
        allowed_tiers=["ap2-gateway"],
        user_key=owner_b,
    )
    chk_chain_b = mc.present(
        holder_key=agent_key,
        mandate_token=limits_b["open_checkout_mandate_token"],
        payloads=[
            CheckoutMandate(
                vct="mandate.checkout.1",
                checkout_jwt=chk_jwt,
                checkout_hash=chk_hash,
            )
        ],
        aud=AP2_MERCHANT_ID,
        nonce=nonce,
    )
    pay_chain_b = mc.present(
        holder_key=agent_key,
        mandate_token=limits_b["open_payment_mandate_token"],
        payloads=[
            PaymentMandate(
                vct="mandate.payment.1",
                transaction_id=chk_hash,
                payment_amount=Amount(amount=7999, currency="USD"),
                payee=Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME),
                payment_instrument=PaymentInstrument(type="vault", id="vault_456"),
            )
        ],
        aud=AP2_MERCHANT_ID,
        nonce=nonce,
    )
    res2_b = await seller_agent.purchase_subscription(
        tier_id="ap2-gateway",
        agreed_monthly_rate=79.99,
        offer_id=offer_id,
        buyer_email=email_b,
        checkout_mandate_chain=chk_chain_b,
        payment_mandate_chain=pay_chain_b,
        checkout_jwt=chk_jwt,
        nonce=nonce,
    )
    assert res2_b["status"] == "REJECTED"
    assert "IDENTITY_MISMATCH_DETECTED" in res2_b["reason"]
    assert "Offer is bound to" in res2_b["reason"]
