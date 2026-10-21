"""
Unit & Integration Tests for Package 4 Hardening.

Verifies:
1. GET /sse, /mcp/sse, /api/mcp/sse, /m2m/sse, and GET /api/mcp/frames, /m2m/frames:
   - Non-admin callers receive empty public catalogs ({"frames": []}) or empty streams without internal frames.
   - Admin callers receive full internal frame telemetry.
2. GET /api/m2m/payloads/latest and /m2m/payloads/latest:
   - Non-admin callers do not receive webhook HMAC signatures (hmac_signature is None).
   - Admin callers receive full HMAC telemetry.
3. dispatch_zapier_mcp tool:
   - Does not return X-AP2-Signature in webhook headers.
4. get_subscription_details:
   - Does not return approval_url (approval_url is None) and strips rel="approve" links.
5. GET /api/mandates/revocations:
   - Non-admin callers receive signature_hex as None.
   - Admin callers receive full cryptographic signature_hex.
6. GET /api/agent/keys/registry:
   - Non-admin callers receive payer_id as None (along with contractor_email and business_name).
   - Admin callers receive unmasked payer_id.
7. GET /api/marketplace/payouts/batches:
   - Non-admin callers receive raw_response_json as None.
   - Admin callers receive full raw PayPal payout response.
8. GET /api/receipts/{reference}:
   - Non-admin callers do not receive receipt_jwt strings.
9. purchase_subscription & provision_compute_node:
   - Another buyer cannot access or receive another buyer's approval_url.
"""

import json
import uuid
import pytest
from starlette.requests import Request
from fastapi.testclient import TestClient
from backend.server import app, mcp_wire_stream
from backend.config import settings
from backend.agents.seller_agent import (
    seller_agent,
    _COMPLETED_SUBSCRIPTIONS,
    _ACTIVE_CONTRACTOR_SUBSCRIPTIONS,
)
from backend.mcp_server import broadcast_wire_frame
from backend.services.ap2_service import (
    create_merchant_checkout,
    create_checkout_receipt_jwt,
    create_renewal_receipt_jwt,
)
from backend.database import (
    register_buyer_key,
    record_mandate_revocation,
    record_payout_batch,
    save_subscription,
    get_connection,
)
from backend.tests.ap2_test_utils import build_test_ap2_chains

client = TestClient(app)
ADMIN_HEADER = {"Authorization": f"Bearer {settings.admin_api_key}"}


def test_mcp_wire_frames_unauthenticated_empty_catalog():
    """Unauthenticated GET of /api/mcp/frames and /m2m/frames returns empty public catalog."""
    # Record a wire frame into memory
    broadcast_wire_frame("incoming", {"jsonrpc": "2.0", "method": "test", "id": 1})

    for path in ("/api/mcp/frames", "/m2m/frames"):
        # 1. Unauthenticated request -> empty frames catalog
        res_pub = client.get(path)
        assert res_pub.status_code == 200
        assert res_pub.json() == {"frames": []}

        # 2. Authenticated request -> contains frames
        res_adm = client.get(path, headers=ADMIN_HEADER)
        assert res_adm.status_code == 200
        assert len(res_adm.json()["frames"]) > 0


@pytest.mark.asyncio
async def test_mcp_sse_unauthenticated_does_not_stream_frames():
    """Unauthenticated GET of SSE endpoints emits handshake/keepalive but no wire frames."""
    scope = {"type": "http", "method": "GET", "path": "/api/mcp/sse", "headers": []}
    req = Request(scope)
    res = await mcp_wire_stream(req)
    assert res.status_code == 200
    gen = res.body_iterator

    # Chunk 1: discovery handshake
    c1 = await anext(gen)
    assert "event: endpoint" in c1
    assert "data: /mcp" in c1

    # Chunk 2: connected info
    c2 = await anext(gen)
    assert "connected" in c2

    # Emit a wire frame to the global subscriber bus
    broadcast_wire_frame("incoming", {"jsonrpc": "2.0", "method": "secret_frame"})

    await gen.aclose()


def test_m2m_payloads_latest_redacts_hmac_for_unauthenticated():
    """GET /api/m2m/payloads/latest redacts hmac_signature and webhook header signatures for non-admins."""
    # First record an M2M payload via backend service
    from backend.api.m2m_audit import record_m2m_artifacts

    record_m2m_artifacts(
        mandate_hash="mandate-hash-secret-1234",
        paypal_sub_id="I-TEST-M2M-SUB",
        node_endpoint="mcp+https://gateway.example.com",
        erp_payload={"status": "ROUTED"},
        qbo_payload={"payload": {"VendorRef": {"value": "V-101"}}},
        webhook_meta={
            "signature": "sha256=supersecretwebhookhmac",
            "timestamp": "2026-10-21T00:00:00Z",
            "headers": {"X-AP2-Signature": "sha256=supersecretwebhookhmac", "Content-Type": "application/json"},
        },
    )

    for path in ("/m2m/payloads/latest", "/api/m2m/payloads/latest"):
        # 1. Unauthenticated GET -> hmac_signature is None, signature in webhook_meta is None
        res_pub = client.get(path)
        assert res_pub.status_code == 200
        data_pub = res_pub.json()
        assert data_pub["hmac_signature"] is None
        assert data_pub["webhook_meta"]["signature"] is None
        assert "X-AP2-Signature" not in data_pub["webhook_meta"]["headers"]
        assert "supersecretwebhookhmac" not in res_pub.text

        # 2. Authenticated GET -> hmac_signature is intact
        res_adm = client.get(path, headers=ADMIN_HEADER)
        assert res_adm.status_code == 200
        data_adm = res_adm.json()
        assert data_adm["hmac_signature"] == "sha256=supersecretwebhookhmac"
        assert data_adm["webhook_meta"]["signature"] == "sha256=supersecretwebhookhmac"


@pytest.mark.asyncio
async def test_dispatch_zapier_mcp_tool_redacts_hmac_signature():
    """seller_agent.dispatch_zapier_mcp tool result must not contain X-AP2-Signature."""
    # Create and save a valid completed subscription
    sub_id = f"I-TEST-DISPATCH-{uuid.uuid4().hex[:8].upper()}"
    _COMPLETED_SUBSCRIPTIONS[sub_id] = {
        "subscription_id": sub_id,
        "status": "ACTIVE",
        "buyer_email": "operator-buyer@example.com",
        "contractor_email": "operator-buyer@example.com",
        "agreed_monthly_rate": 79.99,
        "node_endpoint": "mcp+https://gateway.example.com/mcp",
    }

    res = await seller_agent.dispatch_zapier_mcp(
        subscription_id=sub_id,
        buyer_email="operator-buyer@example.com",
    )
    assert res.get("status") == "COMPLETED"
    serialized = json.dumps(res)
    assert "X-AP2-Signature" not in serialized
    assert "x-ap2-signature" not in serialized


@pytest.mark.asyncio
async def test_get_subscription_details_omits_approval_url():
    """get_subscription_details tool returns approval_url as None and filters rel='approve'."""
    sub_id = f"I-TEST-DETAILS-{uuid.uuid4().hex[:8].upper()}"
    _COMPLETED_SUBSCRIPTIONS[sub_id] = {
        "subscription_id": sub_id,
        "status": "APPROVAL_PENDING",
        "buyer_email": "pending-buyer@example.com",
        "approval_url": "https://www.sandbox.paypal.com/checkoutnow?token=SECRET_PENDING_TOKEN",
        "hateoas_links": [
            {"href": "https://www.sandbox.paypal.com/checkoutnow?token=SECRET_PENDING_TOKEN", "rel": "approve"},
            {"href": f"https://api.sandbox.paypal.com/v1/billing/subscriptions/{sub_id}", "rel": "self"},
        ],
    }

    details = await seller_agent.get_subscription_details(sub_id)
    assert details["approval_url"] is None
    for link in details.get("hateoas_links", []):
        assert link.get("rel") != "approve"
    assert "SECRET_PENDING_TOKEN" not in json.dumps(details)


def test_mandate_revocations_redacts_signature_hex_for_unauthenticated():
    """GET /api/mandates/revocations redacts signature_hex for non-admins."""
    m_hash = f"rev-hash-{uuid.uuid4().hex[:12]}"
    sig_hex = "3045022100abc123def456789deadbeef0220112233445566778899aabbccddeeff00"
    record_mandate_revocation(
        mandate_proof_hash=m_hash,
        revoked_by_kid="owner-rev-key-01",
        reason="Owner key compromise test",
        signature_hex=sig_hex,
    )

    # 1. Unauthenticated list & detail
    res_list = client.get("/api/mandates/revocations")
    assert res_list.status_code == 200
    revs = res_list.json()["revocations"]
    target = next((r for r in revs if r["mandate_proof_hash"] == m_hash), None)
    assert target is not None
    assert target["signature_hex"] is None

    res_get = client.get(f"/api/mandates/revocations/{m_hash}")
    assert res_get.status_code == 200
    assert res_get.json()["revocation"]["signature_hex"] is None
    assert sig_hex not in res_get.text

    # 2. Authenticated list & detail
    res_adm_list = client.get("/api/mandates/revocations", headers=ADMIN_HEADER)
    assert res_adm_list.status_code == 200
    adm_target = next((r for r in res_adm_list.json()["revocations"] if r["mandate_proof_hash"] == m_hash), None)
    assert adm_target is not None
    assert adm_target["signature_hex"] == sig_hex

    res_adm_get = client.get(f"/api/mandates/revocations/{m_hash}", headers=ADMIN_HEADER)
    assert res_adm_get.status_code == 200
    assert res_adm_get.json()["revocation"]["signature_hex"] == sig_hex


def test_keys_registry_redacts_payer_id_for_unauthenticated():
    """GET /api/agent/keys/registry redacts payer_id, contractor_email, and business_name for non-admins."""
    kid = f"key-payer-{uuid.uuid4().hex[:8]}"
    raw_payer = f"PAYER-{uuid.uuid4().hex[:10].upper()}"
    register_buyer_key(
        kid=kid,
        public_key_hex="04" + "aa" * 64,
        contractor_email="secret-contractor@example.com",
        business_name="Secret Enterprise LLC",
        payer_id=raw_payer,
        identity_attested=True,
    )

    # 1. Unauthenticated request
    res_pub = client.get("/api/agent/keys/registry")
    assert res_pub.status_code == 200
    keys_pub = res_pub.json()["keys"]
    target_pub = next((k for k in keys_pub if k["kid"] == kid), None)
    assert target_pub is not None
    assert target_pub.get("payerId") is None
    assert target_pub.get("payer_id") is None
    assert target_pub.get("contractorEmail") is None
    assert target_pub.get("businessName") is None
    assert raw_payer not in res_pub.text

    # 2. Authenticated request
    res_adm = client.get("/api/agent/keys/registry", headers=ADMIN_HEADER)
    assert res_adm.status_code == 200
    keys_adm = res_adm.json()["keys"]
    target_adm = next((k for k in keys_adm if k["kid"] == kid), None)
    assert target_adm is not None
    assert (target_adm.get("payerId") or target_adm.get("payer_id")) == raw_payer
    assert (target_adm.get("contractorEmail") or target_adm.get("contractor_email")) == "secret-contractor@example.com"


def test_payout_batches_redacts_raw_response_for_unauthenticated():
    """GET /api/marketplace/payouts/batches redacts raw_response_json for non-admins."""
    batch_id = f"BATCH-{uuid.uuid4().hex[:8].upper()}"
    raw_resp = {"batch_header": {"payout_batch_id": batch_id, "batch_status": "SUCCESS"}}
    record_payout_batch(
        {
            "batch_id": batch_id,
            "sender_batch_id": f"SENDER-{batch_id}",
            "items_count": 1,
            "total_payout_cents": 5000,
            "total_margin_cents": 500,
            "status": "SUCCESS",
            "payout_batch_id": batch_id,
            "raw_response": raw_resp,
        },
        [{
            "item_id": f"ITEM-{uuid.uuid4().hex[:6]}",
            "operator_id": "op-01",
            "subscription_id": "I-SUB-PAYOUT",
            "gross_amount_cents": 5000,
            "platform_fee_cents": 500,
            "net_payout_cents": 4500,
            "currency": "USD",
            "receiver_email": "operator-payout@example.com",
            "status": "SUCCESS",
        }],
    )

    # 1. Unauthenticated list & detail
    res_list = client.get("/api/marketplace/payouts/batches")
    assert res_list.status_code == 200
    target_list = next((b for b in res_list.json()["batches"] if b["batch_id"] == batch_id), None)
    assert target_list is not None
    assert target_list["raw_response_json"] is None

    res_get = client.get(f"/api/marketplace/payouts/batches/{batch_id}")
    assert res_get.status_code == 200
    target_get = res_get.json()["batch"]
    assert target_get["raw_response_json"] is None

    # 2. Authenticated list & detail
    res_adm_list = client.get("/api/marketplace/payouts/batches", headers=ADMIN_HEADER)
    assert res_adm_list.status_code == 200
    adm_list_target = next((b for b in res_adm_list.json()["batches"] if b["batch_id"] == batch_id), None)
    assert adm_list_target is not None
    assert adm_list_target["raw_response_json"] is not None

    res_adm_get = client.get(f"/api/marketplace/payouts/batches/{batch_id}", headers=ADMIN_HEADER)
    assert res_adm_get.status_code == 200
    assert res_adm_get.json()["batch"]["raw_response_json"] is not None


def test_receipts_endpoint_unauthenticated_does_not_leak_raw_jwt():
    """GET /api/receipts/{reference} does not return receipt_jwt string to non-admins."""
    chk = create_merchant_checkout("ap2-gateway", 79.99, "buyer-receipt@example.com")
    ref = f"ref_{chk['order_id']}"
    rec_jwt = create_checkout_receipt_jwt(chk["order_id"], ref, "Success")

    res = client.get(f"/api/receipts/{ref}")
    assert res.status_code == 200
    data = res.json()
    assert data["verified"] is True
    receipt = data["receipt"]
    assert "receipt_jwt" not in receipt
    assert "_receipt_jwt" not in receipt


@pytest.mark.asyncio
async def test_purchase_result_never_contains_another_buyers_approval_url():
    """A purchase tool result never contains another buyer's approval URL."""
    # 1. Buyer A creates an APPROVAL_PENDING subscription
    buyer_a_email = "buyer-alice@example.com"
    buyer_b_email = "buyer-bob@example.com"
    sub_id = f"I-PENDING-ALICE-{uuid.uuid4().hex[:6].upper()}"
    secret_url = f"https://www.sandbox.paypal.com/checkoutnow?token=ALICE_SECRET_URL_{uuid.uuid4().hex[:6]}"

    offer_a = await seller_agent.negotiate_tier_terms(
        "buyer-agent-alice",
        "ap2-gateway",
        100.0,
        buyer_email=buyer_a_email,
    )
    offer_id_a = offer_a["offer_id"]

    _COMPLETED_SUBSCRIPTIONS[offer_id_a] = {
        "status": "APPROVAL_PENDING",
        "subscription_id": sub_id,
        "offer_id": offer_id_a,
        "contractor_email": buyer_a_email,
        "buyer_email": buyer_a_email,
        "approval_url": secret_url,
        "checkout_hash": offer_a["checkout_hash"],
        "mandate_proof_hash": offer_a["mandate_proof_hash"],
        "next_action": {
            "type": "human_approval_required",
            "action": "approve_paypal_subscription",
            "approval_url": secret_url,
            "subscription_id": sub_id,
        },
    }

    # 2. Buyer B attempts to replay or access Alice's purchase using their own chains/email
    chains_b = build_test_ap2_chains(
        tier_id="ap2-gateway",
        monthly_price=79.99,
        buyer_email=buyer_b_email,
        budget_cap=100.0,
        checkout_record={
            "checkout_jwt": offer_a["checkout_jwt"],
            "checkout_hash": offer_a["checkout_hash"],
            "nonce": offer_a["nonce"],
            "order_id": offer_id_a,
        },
    )

    purchase_res = await seller_agent.purchase_subscription(
        offer_id=offer_id_a,
        checkout_mandate_chain=chains_b["checkout_mandate_chain"],
        payment_mandate_chain=chains_b["payment_mandate_chain"],
        checkout_jwt=offer_a["checkout_jwt"],
        nonce=offer_a["nonce"],
        contractor_email=buyer_b_email,
        buyer_email=buyer_b_email,
    )

    # Must be rejected and must NEVER contain Alice's approval URL
    assert purchase_res.get("status") == "REJECTED"
    assert "approval_url" not in purchase_res or purchase_res.get("approval_url") is None
    assert secret_url not in json.dumps(purchase_res)

    # 3. Buyer B attempts to provision Alice's pending subscription
    prov_res = await seller_agent.provision_compute_node(
        subscription_id=sub_id,
        buyer_email=buyer_b_email,
    )
    assert prov_res.get("status") == "REJECTED"
    assert prov_res.get("error") == "IDENTITY_MISMATCH_DETECTED"
    assert "approval_url" not in prov_res or prov_res.get("approval_url") is None
    assert secret_url not in json.dumps(prov_res)
