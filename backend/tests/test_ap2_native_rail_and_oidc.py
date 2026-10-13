"""
Unit and Integration Tests for AP2 Native Direct Rail & Identity Attestation.
Milestone S3-NATIVE (Sprint 3) / SPEC-001 v1.9.0.

Tests:
  1. OpenID Connect (OIDC) Log in with PayPal attestation token generation & verification.
  2. Fail-closed security rules on expired, tampered, or mismatched OIDC tokens.
  3. Dynamic buyer key registration with optional OIDC attestation.
  4. Post-registration identity attestation endpoint (/api/agent/identity/attest).
  5. Hardware Enclave Keystore & Passkey WebAuthn token abstraction (Rule 5).
  6. Native AP2 Gateway Direct Rail machine-to-machine checkout & charges (/v1/ap2/gateway/charges).
  7. Strict Rule 6 integer minor units arithmetic and authentic QBO v3 Purchase exports.
  8. Security regression defense: unregistered buyer key rejection, mandate revocation enforcement.
"""

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
import pytest
from fastapi.testclient import TestClient

from backend.server import app
from backend.services.paypal_oidc_service import (
    PayPalOidcService,
    _b64url_encode,
    _b64url_decode,
)
from backend.services.ap2_gateway_service import Ap2GatewayService
from backend.services.ap2_service import verify_receipt_jwt
from backend.wallet.keystore import (
    SoftwareEnclaveKeystore,
    PasskeyAttestationKeystore,
)
from backend.wallet.wallet import BuyerWallet, init_agent_key
from backend.database import (
    get_buyer_identity,
    get_buyer_key,
    record_mandate_revocation,
)
from backend.tests.ap2_test_utils import build_test_ap2_chains
from cryptography.hazmat.primitives.asymmetric import ed25519


@pytest.fixture
def client():
    return TestClient(app)


# ═════════════════════════════════════════════════════════════════════════════
# 1. PayPal OpenID Connect (OIDC) Identity Attestation Unit Tests
# ═════════════════════════════════════════════════════════════════════════════

def test_oidc_service_generate_and_verify_valid_token():
    payer_id = "PAYER-TEST-ALICE-123"
    email = "alice@business.example.com"
    nonce = "challenge-nonce-xyz-456"

    token = PayPalOidcService.generate_mock_oidc_token(
        payer_id=payer_id,
        email=email,
        nonce=nonce,
    )
    assert isinstance(token, str)
    assert len(token.split(".")) == 3

    verified = PayPalOidcService.verify_oidc_identity_attestation(
        id_token=token,
        expected_nonce=nonce,
    )
    assert verified["status"] == "ATTESTED"
    assert verified["payer_id"] == payer_id
    assert verified["email"] == email
    assert verified["email_verified"] is True
    assert verified["nonce"] == nonce
    assert verified["identity_provider"] == "paypal"


def test_oidc_service_expired_token_refused():
    token = PayPalOidcService.generate_mock_oidc_token(
        payer_id="PAYER-EXPIRED",
        email="expired@example.com",
        expires_in_seconds=-60,
    )
    with pytest.raises(ValueError, match="EXPIRED_TOKEN"):
        PayPalOidcService.verify_oidc_identity_attestation(token)


def test_oidc_service_nonce_mismatch_refused():
    token = PayPalOidcService.generate_mock_oidc_token(
        payer_id="PAYER-NONCE",
        email="nonce@example.com",
        nonce="expected-nonce-alpha",
    )
    with pytest.raises(ValueError, match="NONCE_MISMATCH"):
        PayPalOidcService.verify_oidc_identity_attestation(
            id_token=token,
            expected_nonce="different-nonce-bravo",
        )


def test_oidc_service_untrusted_issuer_refused():
    token = PayPalOidcService.generate_mock_oidc_token(
        payer_id="PAYER-ATTACKER",
        email="attacker@evil.com",
        issuer="https://evil-untrusted-idp.com",
    )
    with pytest.raises(ValueError, match="INVALID_ISSUER"):
        PayPalOidcService.verify_oidc_identity_attestation(token)


def test_oidc_service_unverified_email_refused():
    # Craft token with email_verified = False, but valid signature
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    claims = {
        "iss": "https://api.sandbox.paypal.com",
        "sub": "PAYER-UNVERIFIED",
        "email": "unverified@example.com",
        "email_verified": False,
        "exp": now + 3600,
    }
    h_b64 = _b64url_encode(json.dumps(header).encode("utf-8"))
    c_b64 = _b64url_encode(json.dumps(claims).encode("utf-8"))
    signing_input = f"{h_b64}.{c_b64}".encode("ascii")
    mock_secret = b"mock-paypal-oidc-secret-key-32bytes"
    sig = _b64url_encode(hmac.new(mock_secret, signing_input, hashlib.sha256).digest())
    token = f"{h_b64}.{c_b64}.{sig}"

    with pytest.raises(ValueError, match="EMAIL_NOT_VERIFIED"):
        PayPalOidcService.verify_oidc_identity_attestation(token)


def test_oidc_service_forged_signature_refused():
    token = PayPalOidcService.generate_mock_oidc_token(
        payer_id="PAYER-ATTACKER",
        email="attacker@example.com",
    )
    tampered_token = token[:-6] + "xxxxxx"
    with pytest.raises(ValueError, match="INVALID_SIGNATURE"):
        PayPalOidcService.verify_oidc_identity_attestation(tampered_token)


def test_oidc_service_alg_none_refused():
    now = int(time.time())
    header = {"alg": "none", "typ": "JWT"}
    claims = {
        "iss": "https://api.sandbox.paypal.com",
        "sub": "PAYER-ATTACKER",
        "email": "attacker@example.com",
        "email_verified": True,
        "exp": now + 3600,
    }
    h_b64 = _b64url_encode(json.dumps(header).encode("utf-8"))
    c_b64 = _b64url_encode(json.dumps(claims).encode("utf-8"))
    none_token = f"{h_b64}.{c_b64}."
    with pytest.raises(ValueError, match="UNSUPPORTED_ALGORITHM"):
        PayPalOidcService.verify_oidc_identity_attestation(none_token)


def test_oidc_service_malformed_token_refused():
    with pytest.raises(ValueError, match="INVALID_ID_TOKEN"):
        PayPalOidcService.verify_oidc_identity_attestation("")

    with pytest.raises(ValueError, match="INVALID_ID_TOKEN_FORMAT"):
        PayPalOidcService.verify_oidc_identity_attestation("not.a.valid.jwt.format")


# ═════════════════════════════════════════════════════════════════════════════
# 2. Buyer Key Registration with OIDC Attestation Tests
# ═════════════════════════════════════════════════════════════════════════════

def test_buyer_key_registration_with_oidc_attestation(client):
    priv_key = ed25519.Ed25519PrivateKey.generate()
    pub_hex = priv_key.public_key().public_bytes_raw().hex()
    kid = f"buyer-oidc-{uuid.uuid4().hex[:8]}"

    # 1. Fetch challenge nonce
    ch_resp = client.get("/api/agent/keys/challenge")
    assert ch_resp.status_code == 200
    challenge_nonce = ch_resp.json()["challenge"]

    # 2. Sign challenge nonce
    sig_hex = priv_key.sign(challenge_nonce.encode("utf-8")).hex()

    # 3. Create matching OIDC attestation token bound to challenge nonce
    payer_id = f"PAYER-{uuid.uuid4().hex[:10].upper()}"
    oidc_token = PayPalOidcService.generate_mock_oidc_token(
        payer_id=payer_id,
        email="attested-contractor@enterprise.com",
        nonce=challenge_nonce,
    )

    # 4. Register key with OIDC attestation
    reg_payload = {
        "kid": kid,
        "publicKeyHex": pub_hex,
        "contractorEmail": "attested-contractor@enterprise.com",
        "businessEntity": "Attested Autonomous Corp",
        "challenge": challenge_nonce,
        "challengeSignature": sig_hex,
        "oidcIdToken": oidc_token,
    }
    resp = client.post("/api/agent/keys/register", json=reg_payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "REGISTERED"
    assert data["identityAttested"] is True
    assert data["payerId"] == payer_id
    assert data["identityProvider"] == "paypal"

    # 5. Verify database persistence
    identity = get_buyer_identity(kid)
    assert identity is not None
    assert identity["identity_attested"] is True
    assert identity["payer_id"] == payer_id
    assert identity["identity_provider"] == "paypal"


def test_buyer_key_registration_with_invalid_oidc_refused(client):
    priv_key = ed25519.Ed25519PrivateKey.generate()
    pub_hex = priv_key.public_key().public_bytes_raw().hex()
    kid = f"buyer-bad-oidc-{uuid.uuid4().hex[:8]}"

    ch_resp = client.get("/api/agent/keys/challenge")
    challenge_nonce = ch_resp.json()["challenge"]
    sig_hex = priv_key.sign(challenge_nonce.encode("utf-8")).hex()

    # Expired OIDC token
    bad_oidc_token = PayPalOidcService.generate_mock_oidc_token(
        payer_id="PAYER-BAD",
        email="bad@example.com",
        nonce=challenge_nonce,
        expires_in_seconds=-10,
    )

    resp = client.post(
        "/api/agent/keys/register",
        json={
            "kid": kid,
            "publicKeyHex": pub_hex,
            "contractorEmail": "bad@example.com",
            "businessEntity": "Bad Corp",
            "challenge": challenge_nonce,
            "challengeSignature": sig_hex,
            "oidcIdToken": bad_oidc_token,
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "INVALID_IDENTITY_ATTESTATION"


# ═════════════════════════════════════════════════════════════════════════════
# 3. Post-Registration Identity Attestation Endpoint Tests
# ═════════════════════════════════════════════════════════════════════════════

def test_post_registration_identity_attest(client):
    priv_key = ed25519.Ed25519PrivateKey.generate()
    pub_hex = priv_key.public_key().public_bytes_raw().hex()
    kid = f"buyer-post-attest-{uuid.uuid4().hex[:8]}"

    # Register key without OIDC initially
    ch_resp = client.get("/api/agent/keys/challenge")
    challenge_nonce = ch_resp.json()["challenge"]
    sig_hex = priv_key.sign(challenge_nonce.encode("utf-8")).hex()

    reg_resp = client.post(
        "/api/agent/keys/register",
        json={
            "kid": kid,
            "publicKeyHex": pub_hex,
            "contractorEmail": "contractor-post@example.com",
            "businessEntity": "Post Attest LLC",
            "challenge": challenge_nonce,
            "challengeSignature": sig_hex,
        },
    )
    assert reg_resp.status_code == 201
    assert reg_resp.json()["identityAttested"] is False

    # Now attest identity via POST /api/agent/identity/attest
    payer_id = f"PAYER-{uuid.uuid4().hex[:10].upper()}"
    attest_chal = client.get("/api/agent/keys/challenge").json()["challenge"]
    attest_sig = priv_key.sign(attest_chal.encode("utf-8")).hex()
    oidc_token = PayPalOidcService.generate_mock_oidc_token(
        payer_id=payer_id,
        email="contractor-post@example.com",
        nonce=attest_chal,
    )

    attest_resp = client.post(
        "/api/agent/identity/attest",
        json={
            "kid": kid,
            "oidcIdToken": oidc_token,
            "challenge": attest_chal,
            "challengeSignature": attest_sig,
        },
    )
    assert attest_resp.status_code == 200
    attest_data = attest_resp.json()
    assert attest_data["status"] == "ATTESTED"
    assert attest_data["kid"] == kid
    assert attest_data["payerId"] == payer_id
    assert attest_data["identityAttested"] is True

    # Retrieve attestation via GET endpoint
    get_resp = client.get(f"/api/agent/identity/attestation/{kid}")
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["payerId"] == payer_id
    assert get_data["identityAttested"] is True


def test_identity_attest_unregistered_key_refused(client):
    oidc_token = PayPalOidcService.generate_mock_oidc_token(
        payer_id="PAYER-GHOST",
        email="ghost@example.com",
    )
    resp = client.post(
        "/api/agent/identity/attest",
        json={
            "kid": "non-existent-kid-9999",
            "oidcIdToken": oidc_token,
        },
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"] == "KEY_NOT_FOUND"


# ═════════════════════════════════════════════════════════════════════════════
# 4. Hardware Enclave & Passkey Keystore Abstraction Unit Tests
# ═════════════════════════════════════════════════════════════════════════════

def test_software_enclave_keystore():
    keystore = SoftwareEnclaveKeystore.generate(crv="P-256")
    assert keystore.algorithm == "ES256"
    assert keystore.kid.startswith("wallet-enclave-")

    pub_jwk = keystore.export_public(as_dict=True)
    assert pub_jwk["kty"] == "EC"
    assert pub_jwk["crv"] == "P-256"
    assert "d" not in pub_jwk  # Rule 5: Private key never in public export

    # Sign JWT claims inside enclave boundary
    claims = {"sub": "buyer_01", "aud": "merchant_node", "amount": 7999}
    signed_jwt = keystore.sign_jwt(claims)
    assert isinstance(signed_jwt, str)
    assert len(signed_jwt.split(".")) == 3

    # Sign raw data
    raw_sig = keystore.sign_raw(b"ap2-hardware-enclave-data")
    assert isinstance(raw_sig, bytes)
    assert len(raw_sig) > 0

    # Ensure private key is masked in string representations
    repr_str = repr(keystore)
    assert repr_str.startswith("<SoftwareEnclaveKeystore")
    assert "status='PROTECTED'" in repr_str
    assert "private" not in repr_str.lower()
    assert '"d"' not in repr_str


def test_passkey_attestation_keystore():
    keystore = PasskeyAttestationKeystore()
    assert keystore.algorithm == "ES256"
    assert keystore.credential_id is not None
    assert len(keystore.credential_id) > 10

    attestation = keystore.get_webauthn_attestation()
    assert attestation["user_verified"] is True
    assert attestation["user_present"] is True
    assert "authenticator_data_b64" in attestation
    assert "public_key" in attestation

    signed_jwt = keystore.sign_jwt({"action": "direct_charge"})
    assert isinstance(signed_jwt, str)
    header_json = json.loads(_b64url_decode(signed_jwt.split(".")[0]).decode("utf-8"))
    assert header_json.get("fido2_cred") == keystore.credential_id


def test_buyer_wallet_keystore_integration(tmp_path):
    wallet_dir = tmp_path / "test_wallet"
    init_agent_key(wallet_dir)
    wallet = BuyerWallet(directory=wallet_dir)

    keystore = wallet.get_keystore()
    assert isinstance(keystore, SoftwareEnclaveKeystore)
    assert keystore.algorithm == "ES256"
    assert keystore.export_public() is not None


# ═════════════════════════════════════════════════════════════════════════════
# 5. AP2 Native Direct Rail Gateway Charge Execution Tests
# ═════════════════════════════════════════════════════════════════════════════

def test_direct_ap2_gateway_charge_success(client):
    # 1. Build authentic AP2 mandate chains ($79.99 gateway tier)
    chains = build_test_ap2_chains(tier_id="ap2-gateway", monthly_price=79.99, budget_cap=100.0, vault_id="vault_paypal_buyer_mit")

    # 2. Execute direct machine-to-machine charge
    charge_req = {
        "cartMandateJwt": chains["checkout_mandate_chain"],
        "paymentMandateJwt": chains["payment_mandate_chain"],
        "buyerKeyId": chains["owner_key"].kid,
        "paymentSourceId": "vault_paypal_buyer_mit",
        "metadata": {"workload": "Autonomous AP2 Direct Rail Ingestion"},
    }

    resp = client.post("/v1/ap2/gateway/charges", json=charge_req)
    assert resp.status_code == 201
    data = resp.json()

    # Rule 6 Verification: Integer minor units
    assert data["status"] == "CAPTURED"
    assert data["amountCents"] == 7999
    assert data["amountFormatted"] == "$79.99"
    assert data["currency"] == "USD"
    assert data["buyerKeyId"] == chains["owner_key"].kid
    assert data["paypalCaptureId"].startswith("CAP-")

    # Verify merchant receipt JWT
    receipt_jwt = data["merchantReceiptJwt"]
    assert receipt_jwt is not None
    verified_receipt = verify_receipt_jwt(receipt_jwt)
    assert verified_receipt.get("status") == "Success"

    # Verify authentic QuickBooks Online v3 Purchase payload
    qbo_payload = data["qboPayload"]
    assert qbo_payload is not None
    purchase = qbo_payload["Purchase"]
    assert purchase["TotalAmt"] == 79.99
    assert purchase["AccountRef"]["value"] == "99"
    assert purchase["Line"][0]["AccountBasedExpenseLineDetail"]["AccountRef"]["value"] == "6300"

    # 3. Retrieve charge via GET /v1/ap2/gateway/charges/{charge_id}
    charge_id = data["chargeId"]
    get_resp = client.get(f"/v1/ap2/gateway/charges/{charge_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["chargeId"] == charge_id
    assert get_resp.json()["amountCents"] == 7999

    # 4. List charges via GET /v1/ap2/gateway/charges
    list_resp = client.get("/v1/ap2/gateway/charges")
    assert list_resp.status_code == 200
    charges = list_resp.json()["charges"]
    assert any(c["chargeId"] == charge_id for c in charges)


def test_direct_ap2_gateway_charge_unregistered_key_refusal(client):
    chains = build_test_ap2_chains(tier_id="ap2-batch", monthly_price=49.99)
    resp = client.post(
        "/v1/ap2/gateway/charges",
        json={
            "cartMandateJwt": chains["checkout_mandate_chain"],
            "paymentMandateJwt": chains["payment_mandate_chain"],
            "buyerKeyId": "unregistered-intruder-agent-key",
        },
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"] == "UNREGISTERED_BUYER_KEY"


def test_direct_ap2_gateway_charge_revoked_mandate_refusal(client):
    chains = build_test_ap2_chains(tier_id="ap2-batch", monthly_price=49.99)
    chk_hash = chains["checkout_hash"]

    # Cryptographically revoke the mandate hash
    record_mandate_revocation(
        mandate_proof_hash=chk_hash,
        revoked_by_kid="admin-key",
        reason="Security audit compromise revocation",
        signature_hex="aa" * 64,
    )

    resp = client.post(
        "/v1/ap2/gateway/charges",
        json={
            "cartMandateJwt": chains["checkout_mandate_chain"],
            "paymentMandateJwt": chains["payment_mandate_chain"],
            "buyerKeyId": chains["owner_key"].kid,
        },
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "MANDATE_REVOKED"


def test_direct_ap2_gateway_charge_tampered_amount_refusal(client):
    chains = build_test_ap2_chains(tier_id="ap2-gateway", monthly_price=79.99)

    # Tamper with the payment mandate token string
    tampered_jwt = chains["payment_mandate_chain"] + "tamper_byte"

    resp = client.post(
        "/v1/ap2/gateway/charges",
        json={
            "cartMandateJwt": chains["checkout_mandate_chain"],
            "paymentMandateJwt": tampered_jwt,
            "buyerKeyId": chains["owner_key"].kid,
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "INVALID_MANDATE"
