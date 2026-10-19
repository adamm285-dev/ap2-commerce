"""
Request-shape verification tests for PayPalService live REST methods.
Verifies HTTP method, URL path, Authorization header, and JSON body for:
- verify_subscription (GET /v1/billing/subscriptions/{id})
- stop_subscription (POST /v1/billing/subscriptions/{id}/cancel and /suspend)
- create_payout_batch (POST /v1/payments/payouts)
Runs strictly with no outbound network calls (rule 9).
"""

import asyncio
import json
import httpx
import pytest

from backend.services.paypal_service import paypal_service


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def fake_paypal_api(monkeypatch):
    """Live-mode PayPal service with only the HTTP layer replaced. Returns the requests it was sent."""
    state = {"sent": [], "response_code": 200, "response_json": {}}

    async def token(*args, **kwargs):
        return "regression-token"

    async def respond(self, request, *args, **kwargs):
        state["sent"].append(request)
        code = state["response_code"]
        if code == 204:
            return httpx.Response(204, request=request)
        return httpx.Response(code, json=state["response_json"], request=request)

    monkeypatch.setattr(paypal_service, "mock_mode", False)
    monkeypatch.setattr(paypal_service, "client_id", "")  # skip the Agent Toolkit branch, use direct REST
    monkeypatch.setattr(paypal_service, "get_access_token", token)
    monkeypatch.setattr(httpx.AsyncClient, "send", respond)
    return state


def test_live_verify_subscription_request_shape(fake_paypal_api):
    sub_id = "I-VERIFY-SHAPE-001"
    fake_paypal_api["response_code"] = 200
    fake_paypal_api["response_json"] = {
        "id": sub_id,
        "status": "ACTIVE",
        "plan_id": "P-TESTPLAN001",
    }

    res = _run(paypal_service.verify_subscription(sub_id))

    assert len(fake_paypal_api["sent"]) == 1
    req = fake_paypal_api["sent"][0]
    assert req.method == "GET"
    assert req.url.path == f"/v1/billing/subscriptions/{sub_id}"
    assert req.headers["Authorization"] == "Bearer regression-token"
    assert req.content == b""
    assert res["id"] == sub_id
    assert res["status"] == "ACTIVE"


@pytest.mark.parametrize("action,expected_status", [("cancel", "CANCELLED"), ("suspend", "SUSPENDED")])
def test_live_stop_subscription_request_shape(fake_paypal_api, action, expected_status):
    sub_id = "I-STOP-SHAPE-002"
    reason = "Mandate revoked by owner"
    fake_paypal_api["response_code"] = 204

    res = _run(paypal_service.stop_subscription(sub_id, action, reason))

    assert len(fake_paypal_api["sent"]) == 1
    req = fake_paypal_api["sent"][0]
    body = json.loads(req.content)
    assert req.method == "POST"
    assert req.url.path == f"/v1/billing/subscriptions/{sub_id}/{action}"
    assert req.headers["Authorization"] == "Bearer regression-token"
    assert req.headers["Content-Type"] == "application/json"
    assert body == {"reason": reason}
    assert res["subscription_id"] == sub_id
    assert res["action"] == action
    assert res["status"] == expected_status
    assert res["mock_mode"] is False


def test_live_create_payout_batch_request_shape(fake_paypal_api):
    sender_batch_id = "BATCH-SHAPE-003"
    items = [
        {
            "recipient_type": "EMAIL",
            "amount": {"value": "42.50", "currency": "USD"},
            "receiver": "operator-node-1@example.com",
            "note": "Monthly compute node payout",
            "sender_item_id": "ITEM-SHAPE-001",
        }
    ]
    email_subject = "AP2 Node Operator Settlement"
    email_message = "Settlement for period 2026-10."
    fake_paypal_api["response_code"] = 201
    fake_paypal_api["response_json"] = {
        "batch_header": {
            "payout_batch_id": "PAYOUTBATCH-LIVE-001",
            "batch_status": "PENDING",
            "sender_batch_header": {
                "sender_batch_id": sender_batch_id,
                "email_subject": email_subject,
                "email_message": email_message,
            },
        }
    }

    res = _run(
        paypal_service.create_payout_batch(
            sender_batch_id=sender_batch_id,
            items=items,
            email_subject=email_subject,
            email_message=email_message,
        )
    )

    assert len(fake_paypal_api["sent"]) == 1
    req = fake_paypal_api["sent"][0]
    body = json.loads(req.content)
    assert req.method == "POST"
    assert req.url.path == "/v1/payments/payouts"
    assert req.headers["Authorization"] == "Bearer regression-token"
    assert req.headers["Content-Type"] == "application/json"
    assert body["sender_batch_header"] == {
        "sender_batch_id": sender_batch_id,
        "email_subject": email_subject,
        "email_message": email_message,
        "recipient_type": "EMAIL",
    }
    assert body["items"] == items
    assert res["batch_header"]["payout_batch_id"] == "PAYOUTBATCH-LIVE-001"
