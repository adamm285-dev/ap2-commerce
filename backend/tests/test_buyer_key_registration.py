"""
Tests for Dynamic Self-Service Buyer Key Onboarding and Cryptographic Verification.
Validates Ed25519 challenge-response registration, anti-tamper rejection,
SQLite WAL persistence, and immediate spending mandate evaluation by newly registered buyer agents.
"""

import pytest
from fastapi.testclient import TestClient
from ..server import app, _ACTIVE_KEY_CHALLENGES
from ..config import settings
from ..services.crypto_mandate import (
    generate_ed25519_keypair,
    sign_ed25519_message,
    generate_dynamic_mandate_proof,
    REGISTERED_BUYER_KEYS,
)
from ..database import get_buyer_key, list_buyer_key_records

client = TestClient(app)


def test_get_buyer_key_challenge():
    """GET /api/agent/keys/challenge returns a fresh 64-hex-char cryptographic nonce."""
    res = client.get("/api/agent/keys/challenge")
    assert res.status_code == 200
    data = res.json()
    assert "challenge" in data
    assert len(data["challenge"]) == 64
    assert data["algorithm"] == "Ed25519"
    assert data["expiresIn"] == 300
    assert data["challenge"] in _ACTIVE_KEY_CHALLENGES


def test_successful_buyer_key_registration():
    """POST /api/agent/keys/register accepts valid challenge signature and enrolls buyer key."""
    priv_hex, pub_hex = generate_ed25519_keypair()
    kid = "buyer-agent-tampa-compute-v1"
    email = "tampa@example.com"
    entity = "Demo Bay Compute LLC"

    # 1. Fetch challenge nonce
    chal_res = client.get("/api/agent/keys/challenge")
    assert chal_res.status_code == 200
    challenge = chal_res.json()["challenge"]

    # 2. Cryptographically sign challenge nonce with private key
    sig_hex = sign_ed25519_message(challenge, priv_hex)

    # 3. Register buyer key
    reg_res = client.post(
        "/api/agent/keys/register",
        json={
            "kid": kid,
            "publicKeyHex": pub_hex,
            "contractorEmail": email,
            "businessEntity": entity,
            "challenge": challenge,
            "challengeSignature": sig_hex,
            "monthlyBudgetCap": 150.0,
        },
    )
    assert reg_res.status_code == 201
    body = reg_res.json()
    assert body["status"] == "REGISTERED"
    assert body["kid"] == kid
    assert body["publicKeyHex"] == pub_hex.lower()
    assert body["verified"] is True
    assert body["contractorEmail"] == email

    # 4. Verify presence in SQLite database
    db_pub = get_buyer_key(kid)
    assert db_pub is not None
    assert db_pub == pub_hex.lower()

    # 5. Verify presence in registry endpoint
    public_res = client.get("/api/agent/keys/registry")
    assert public_res.status_code == 200
    public_entry = next((k for k in public_res.json()["keys"] if k["kid"] == kid), None)
    assert public_entry is not None
    assert public_entry["contractorEmail"] is None

    registry_res = client.get("/api/agent/keys/registry", headers={"X-Admin-Key": settings.admin_api_key})
    assert registry_res.status_code == 200
    keys = registry_res.json()["keys"]
    enrolled = next((k for k in keys if k["kid"] == kid), None)
    assert enrolled is not None
    assert enrolled["publicKeyHex"] == pub_hex.lower()
    assert enrolled["contractorEmail"] == email


def test_rejected_registration_tampered_signature():
    """POST /api/agent/keys/register rejects invalid / forged signatures with HTTP 401."""
    priv_hex, pub_hex = generate_ed25519_keypair()
    other_priv, _ = generate_ed25519_keypair()

    chal_res = client.get("/api/agent/keys/challenge")
    challenge = chal_res.json()["challenge"]

    # Signed with the WRONG private key
    forged_sig = sign_ed25519_message(challenge, other_priv)

    reg_res = client.post(
        "/api/agent/keys/register",
        json={
            "kid": "forged-buyer-agent",
            "publicKeyHex": pub_hex,
            "contractorEmail": "hacker@example.com",
            "businessEntity": "Evil Corp LLC",
            "challenge": challenge,
            "challengeSignature": forged_sig,
        },
    )
    assert reg_res.status_code == 401
    detail = reg_res.json().get("detail", {})
    assert detail.get("error") == "INVALID_CHALLENGE_SIGNATURE"


def test_rejected_registration_expired_challenge():
    """POST /api/agent/keys/register rejects stale challenges (>300s) with HTTP 400."""
    priv_hex, pub_hex = generate_ed25519_keypair()
    chal_res = client.get("/api/agent/keys/challenge")
    challenge = chal_res.json()["challenge"]

    # Artificially expire the challenge timestamp
    _ACTIVE_KEY_CHALLENGES[challenge] = 0.0

    sig_hex = sign_ed25519_message(challenge, priv_hex)

    reg_res = client.post(
        "/api/agent/keys/register",
        json={
            "kid": "expired-chal-agent",
            "publicKeyHex": pub_hex,
            "contractorEmail": "contractor@example.com",
            "businessEntity": "Demo Cloud Ops LLC",
            "challenge": challenge,
            "challengeSignature": sig_hex,
        },
    )
    assert reg_res.status_code == 400
    detail = reg_res.json().get("detail", {})
    assert detail.get("error") == "CHALLENGE_EXPIRED"


def test_newly_registered_buyer_key_can_evaluate_mandate():
    """A newly onboarded buyer agent can immediately sign and evaluate spending mandates."""
    priv_hex, pub_hex = generate_ed25519_keypair()
    kid = "buyer-agent-orlando-cluster-v1"
    email = "orlando@example.com"
    entity = "Demo Cluster Systems LLC"

    # 1. Onboard buyer agent
    chal_res = client.get("/api/agent/keys/challenge")
    challenge = chal_res.json()["challenge"]
    sig_hex = sign_ed25519_message(challenge, priv_hex)

    reg_res = client.post(
        "/api/agent/keys/register",
        json={
            "kid": kid,
            "publicKeyHex": pub_hex,
            "contractorEmail": email,
            "businessEntity": entity,
            "challenge": challenge,
            "challengeSignature": sig_hex,
            "monthlyBudgetCap": 120.0,
        },
    )
    assert reg_res.status_code == 201

    # 2. Buyer agent autonomously constructs and signs a spending mandate under its new kid
    mandate_eval_res = client.post(
        "/api/agent/spending-mandate/evaluate",
        json={
            "buyerAgentId": kid,
            "amount": 79.99,
            "recurrence": "monthly",
            "category": "autonomous-node-service",
            "monthlyBudgetCap": 120.0,
            "contractorEmail": email,
            "tierId": "ap2-gateway",
        },
    )
    assert mandate_eval_res.status_code == 200
    mandate_body = mandate_eval_res.json()
    assert mandate_body["approved"] is True
    assert mandate_body["mandateProofHash"] is not None


def test_rejected_registration_reserved_key_id():
    """POST /api/agent/keys/register rejects attempts to overwrite system-reserved key IDs with HTTP 403."""
    priv_hex, pub_hex = generate_ed25519_keypair()
    chal_res = client.get("/api/agent/keys/challenge")
    challenge = chal_res.json()["challenge"]
    sig_hex = sign_ed25519_message(challenge, priv_hex)

    reg_res = client.post(
        "/api/agent/keys/register",
        json={
            "kid": "ap2-seller-ed25519-v1",
            "publicKeyHex": pub_hex,
            "contractorEmail": "hacker@example.com",
            "businessEntity": "Rogue Agent LLC",
            "challenge": challenge,
            "challengeSignature": sig_hex,
        },
    )
    assert reg_res.status_code == 403
    assert reg_res.json().get("detail", {}).get("error") == "RESERVED_KEY_ID"


def test_rejected_registration_key_collision():
    """POST /api/agent/keys/register rejects overwriting an existing registered key ID with HTTP 409."""
    priv_hex, pub_hex = generate_ed25519_keypair()
    kid = "unique-test-buyer-001"
    email = "unique@example.com"
    entity = "Demo Unique Node LLC"

    # Register first time
    chal_res = client.get("/api/agent/keys/challenge")
    challenge = chal_res.json()["challenge"]
    sig_hex = sign_ed25519_message(challenge, priv_hex)
    reg_res1 = client.post(
        "/api/agent/keys/register",
        json={
            "kid": kid,
            "publicKeyHex": pub_hex,
            "contractorEmail": email,
            "businessEntity": entity,
            "challenge": challenge,
            "challengeSignature": sig_hex,
        },
    )
    assert reg_res1.status_code == 201

    # Attempt to overwrite with a different key
    other_priv, other_pub = generate_ed25519_keypair()
    chal_res2 = client.get("/api/agent/keys/challenge")
    challenge2 = chal_res2.json()["challenge"]
    sig_hex2 = sign_ed25519_message(challenge2, other_priv)
    reg_res2 = client.post(
        "/api/agent/keys/register",
        json={
            "kid": kid,
            "publicKeyHex": other_pub,
            "contractorEmail": "intruder@example.com",
            "businessEntity": "Intruder LLC",
            "challenge": challenge2,
            "challengeSignature": sig_hex2,
        },
    )
    assert reg_res2.status_code == 409
    assert reg_res2.json().get("detail", {}).get("error") == "KEY_ALREADY_EXISTS"


def test_rejected_registration_unissued_challenge():
    """POST /api/agent/keys/register rejects challenges not issued by the server with HTTP 400."""
    priv_hex, pub_hex = generate_ed25519_keypair()
    fake_challenge = "f" * 64
    sig_hex = sign_ed25519_message(fake_challenge, priv_hex)

    reg_res = client.post(
        "/api/agent/keys/register",
        json={
            "kid": "unissued-chal-agent",
            "publicKeyHex": pub_hex,
            "contractorEmail": "contractor@example.com",
            "businessEntity": "Valid Hub LLC",
            "challenge": fake_challenge,
            "challengeSignature": sig_hex,
        },
    )
    assert reg_res.status_code == 400
    assert reg_res.json().get("detail", {}).get("error") == "INVALID_CHALLENGE"


def test_rejected_registration_single_use_consumed_challenge():
    """POST /api/agent/keys/register burns challenge on use; replaying same challenge is rejected with HTTP 400."""
    priv_hex, pub_hex = generate_ed25519_keypair()
    chal_res = client.get("/api/agent/keys/challenge")
    challenge = chal_res.json()["challenge"]
    sig_hex = sign_ed25519_message(challenge, priv_hex)

    # First registration consumes challenge
    reg1 = client.post(
        "/api/agent/keys/register",
        json={
            "kid": "single-use-agent-01",
            "publicKeyHex": pub_hex,
            "contractorEmail": "burn1@example.com",
            "businessEntity": "Burn Test LLC",
            "challenge": challenge,
            "challengeSignature": sig_hex,
        },
    )
    assert reg1.status_code == 201

    # Second registration with same challenge must be rejected as already consumed
    reg2 = client.post(
        "/api/agent/keys/register",
        json={
            "kid": "single-use-agent-02",
            "publicKeyHex": pub_hex,
            "contractorEmail": "burn2@example.com",
            "businessEntity": "Burn Test LLC",
            "challenge": challenge,
            "challengeSignature": sig_hex,
        },
    )
    assert reg2.status_code == 400
    assert reg2.json().get("detail", {}).get("error") == "INVALID_CHALLENGE"

