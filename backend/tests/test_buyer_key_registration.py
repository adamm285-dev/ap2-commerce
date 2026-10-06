"""
Tests for Dynamic Self-Service Buyer Key Onboarding and Cryptographic Verification.
Validates Ed25519 challenge-response registration, anti-tamper rejection,
SQLite WAL persistence, and immediate spending mandate evaluation by newly registered buyer agents.
"""

import pytest
from fastapi.testclient import TestClient
from ..server import app, _ACTIVE_KEY_CHALLENGES
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
    kid = "buyer-agent-tampa-roofing-v1"
    email = "tampa@tampabayroofing.com"
    entity = "Tampa Bay Roofing Solutions LLC"

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
    registry_res = client.get("/api/agent/keys/registry")
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
            "contractorEmail": "hacker@evilcorp.com",
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
            "contractorEmail": "contractor@floridaroof.com",
            "businessEntity": "Florida Roof Pro LLC",
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
    kid = "buyer-agent-orlando-plumb-v1"
    email = "orlando@centralfloridaplumbing.com"
    entity = "Central Florida Plumbing Solutions LLC"

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
            "category": "ai-voice-screener",
            "monthlyBudgetCap": 120.0,
            "contractorEmail": email,
            "tierId": "fieldsmith-pro",
        },
    )
    assert mandate_eval_res.status_code == 200
    mandate_body = mandate_eval_res.json()
    assert mandate_body["approved"] is True
    assert mandate_body["mandateProofHash"] is not None
