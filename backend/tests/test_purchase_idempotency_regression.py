"""
Regression test: Purchase idempotency with APPROVAL_PENDING (replaying returns same subscription).
Verifies that even when create_subscription returns APPROVAL_PENDING with a fresh ID per call,
replaying the purchase returns the existing subscription and does NOT create a second PayPal subscription.
"""

import pytest
import uuid
from unittest.mock import AsyncMock, patch

from backend.agents.seller_agent import seller_agent, _COMPLETED_SUBSCRIPTIONS
from backend.services.paypal_service import paypal_service


@pytest.mark.asyncio
async def test_purchase_idempotency_approval_pending_replay(monkeypatch):
    """
    Monkeypatches paypal_service.create_subscription to return APPROVAL_PENDING with a new id per call.
    Replaying the purchase with the same mandate must make exactly ONE create_subscription call
    and return the identical subscription_id.
    """
    create_call_count = 0
    generated_sub_ids = []

    async def mock_create_subscription(*args, **kwargs):
        nonlocal create_call_count
        create_call_count += 1
        new_id = f"I-LIVE-MOCK-{uuid.uuid4().hex[:8]}"
        generated_sub_ids.append(new_id)
        return {
            "subscription_id": new_id,
            "id": new_id,
            "status": "APPROVAL_PENDING",
            "approval_url": f"https://www.sandbox.paypal.com/checkoutnow?token=EC-{new_id}",
            "created_time": "2026-10-09T18:00:00Z",
            "next_billing_time": "2026-11-09T18:00:00Z",
            "payer_id": "PAYER-TEST-BUYER",
            "vault_id": f"vault_tok_{new_id.lower().replace('-', '_')}",
            "payment_token": f"tok_{new_id}_pay",
            "paypal_request_id": f"req_{new_id}",
            "subscriber_country_code": "US",
        }

    monkeypatch.setattr(paypal_service, "create_subscription", mock_create_subscription)

    # 1. First negotiate an authorized mandate via negotiate_tier_terms
    email = f"idempotency-{uuid.uuid4().hex[:6]}@example.com"
    mandate_res = await seller_agent.negotiate_tier_terms(
        tier_id="ap2-gateway",
        contractor_email=email,
        buyer_agent_id="test-idempotent-buyer",
        monthly_budget_cap=150.00,
    )
    assert mandate_res["status"] == "APPROVED"
    offer_id = mandate_res["offer_id"]
    proof_hash = mandate_res["mandate_proof_hash"]

    # 2. First purchase attempt
    res1 = await seller_agent.purchase_subscription(
        tier_id="ap2-gateway",
        agreed_monthly_rate=79.99,
        mandate_proof_hash=proof_hash,
        contractor_email=email,
        offer_id=offer_id,
    )
    assert res1["status"] == "APPROVAL_PENDING"
    first_sub_id = res1["subscription_id"]
    assert create_call_count == 1
    assert first_sub_id == generated_sub_ids[0]

    # 3. Second purchase attempt (exact replay of mandate/offer)
    res2 = await seller_agent.purchase_subscription(
        tier_id="ap2-gateway",
        agreed_monthly_rate=79.99,
        mandate_proof_hash=proof_hash,
        contractor_email=email,
        offer_id=offer_id,
    )

    # Must return the existing subscription without creating another PayPal subscription
    assert create_call_count == 1, f"Expected exactly 1 call to create_subscription, got {create_call_count}"
    assert res2["status"] == "APPROVAL_PENDING"
    assert res2["subscription_id"] == first_sub_id, "Replay must return identical subscription_id"


@pytest.mark.asyncio
async def test_purchase_terminal_state_rejects_reuse():
    """
    If an existing subscription is in a terminal state (CANCELLED/EXPIRED/DENIED),
    replaying the mandate must reject reuse and not create a new subscription.
    """
    email = f"terminal-{uuid.uuid4().hex[:6]}@example.com"
    mandate_res = await seller_agent.negotiate_tier_terms(
        tier_id="ap2-gateway",
        contractor_email=email,
        buyer_agent_id="test-terminal-buyer",
        monthly_budget_cap=150.00,
    )
    assert mandate_res["status"] == "APPROVED"
    offer_id = mandate_res["offer_id"]
    proof_hash = mandate_res["mandate_proof_hash"]

    # Seed cache with terminal state
    _COMPLETED_SUBSCRIPTIONS[offer_id] = {
        "status": "CANCELLED",
        "subscription_id": "I-CANCELLED-SUB-999",
        "message": "Subscription cancelled",
    }
    _COMPLETED_SUBSCRIPTIONS[proof_hash] = _COMPLETED_SUBSCRIPTIONS[offer_id]

    res = await seller_agent.purchase_subscription(
        tier_id="ap2-gateway",
        agreed_monthly_rate=79.99,
        mandate_proof_hash=proof_hash,
        contractor_email=email,
        offer_id=offer_id,
    )

    assert res["status"] == "REJECTED"
    assert res["error"] == "MANDATE_ALREADY_REDEEMED"
    assert "already redeemed" in res["reason"].lower()
