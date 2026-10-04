"""
Dynamic Asymmetric Ed25519 & HMAC Cryptographic Mandate Verification Engine.
Conforms to the FIDO Alliance / AP2 (Agent Payments Protocol) Intent Mandate specification.
Binds contractor identity, business entity, monthly spending caps, and agreed rates
into canonical JSON payloads with strict drift and budget policy verification.
"""

import os
import hmac
import hashlib
import json
import time
from typing import Dict, Any, Tuple, Optional
from cryptography.hazmat.primitives.asymmetric import ed25519

import logging
from ..config import settings, ENV_PATH
import dotenv

logger = logging.getLogger("a2a_crypto")

if ENV_PATH.exists():
    dotenv.load_dotenv(ENV_PATH)

# Environment-configurable secret / keys (Zero hardcoded secrets in tracked repository)
_raw_secret = os.getenv("A2A_MANDATE_SECRET") or settings.a2a_mandate_secret
SECRET_KEY = _raw_secret.encode("utf-8") if _raw_secret else os.urandom(32)

def _load_or_generate_key(env_var_names: list) -> Tuple[ed25519.Ed25519PrivateKey, str, str]:
    """Loads a 32-byte Ed25519 private key from environment variables, or generates a secure random key."""
    for var in env_var_names:
        val = os.getenv(var) or getattr(settings, var.lower(), None)
        if val and isinstance(val, str) and len(val.strip()) == 64:
            try:
                priv = ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(val.strip()))
                pub = priv.public_key()
                return priv, priv.private_bytes_raw().hex(), pub.public_bytes_raw().hex()
            except Exception:
                pass
    # If not provided in environment, generate a true non-reproducible random key
    logger.warning(
        f"[CRYPTO_WARNING] Private key {env_var_names} not configured in .env! "
        "Generated ephemeral random Ed25519 key. This will rotate on server restart!"
    )
    priv = ed25519.Ed25519PrivateKey.generate()
    pub = priv.public_key()
    return priv, priv.private_bytes_raw().hex(), pub.public_bytes_raw().hex()

_DEFAULT_SELLER_PRIVATE_KEY, DEFAULT_SELLER_PRIVATE_KEY_HEX, DEFAULT_SELLER_PUBLIC_KEY_HEX = _load_or_generate_key(
    ["A2A_SELLER_PRIVATE_KEY"]
)
_DEFAULT_BUYER_PRIVATE_KEY, DEFAULT_BUYER_PRIVATE_KEY_HEX, DEFAULT_BUYER_PUBLIC_KEY_HEX = _load_or_generate_key(
    ["A2A_PRIVATE_KEY", "A2A_BUYER_PRIVATE_KEY"]
)

# Optional override for buyer public key from environment
_env_buyer_pub = os.getenv("A2A_BUYER_PUBLIC_KEY") or getattr(settings, "a2a_buyer_public_key", None)
if _env_buyer_pub and len(_env_buyer_pub.strip()) == 64:
    DEFAULT_BUYER_PUBLIC_KEY_HEX = _env_buyer_pub.strip().lower()

DEFAULT_SELLER_KID = "fieldsmith-seller-ed25519-v1"
DEFAULT_BUYER_KID = "marcus-buyer-ed25519-v1"

# Known / registered buyer agent public keys (kid -> public_key_hex)
# Prevents arbitrary third parties from forging mandates for known contractors
REGISTERED_BUYER_KEYS: Dict[str, str] = {
    DEFAULT_BUYER_KID: DEFAULT_BUYER_PUBLIC_KEY_HEX,
    "marcus-buyer-ed25519-v1": DEFAULT_BUYER_PUBLIC_KEY_HEX,
    "buyer-agent-01": DEFAULT_BUYER_PUBLIC_KEY_HEX,
    "marcus-buyer": DEFAULT_BUYER_PUBLIC_KEY_HEX,
    "claude-desktop-buyer": DEFAULT_BUYER_PUBLIC_KEY_HEX,
}



def register_buyer_key(kid: str, public_key_hex: str):
    """Registers or trusts a buyer agent's Ed25519 public key."""
    REGISTERED_BUYER_KEYS[kid] = public_key_hex.strip().lower()


def is_trusted_buyer_key(kid: Optional[str], public_key_hex: Optional[str]) -> bool:
    """Checks if the (kid, public_key_hex) pair matches a registered buyer key."""
    if not kid or not public_key_hex:
        return False
    expected = REGISTERED_BUYER_KEYS.get(kid)
    if not expected:
        return False
    return expected.strip().lower() == public_key_hex.strip().lower()


def generate_ed25519_keypair() -> Tuple[str, str]:
    """Generates a raw 32-byte hex-encoded (private_key, public_key) pair for an autonomous agent."""
    priv = ed25519.Ed25519PrivateKey.generate()
    pub = priv.public_key()
    return priv.private_bytes_raw().hex(), pub.public_bytes_raw().hex()


def canonicalize_mandate_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Standardizes payload fields to prevent cross-language (JS <-> Python) JSON serialization drifts.
    Whole-number floats (e.g. 100.0) are normalized to integers (100) since JavaScript JSON.stringify
    drops trailing .0, while fractional floats (e.g. 89.01) retain 2-decimal precision.
    """
    normalized = {}
    for k, v in payload.items():
        if isinstance(v, (int, float)):
            f_val = float(v)
            if f_val.is_integer():
                normalized[k] = int(f_val)
            else:
                normalized[k] = round(f_val, 2)
        else:
            normalized[k] = v
    return normalized


def generate_dynamic_mandate_proof(
    contractor_id: str,
    business_name: str,
    monthly_cap_usd: float,
    agreed_price_usd: float,
    nonce: str,
    buyer_private_key_hex: Optional[str] = None,
    secret_key: bytes = SECRET_KEY,
) -> Dict[str, Any]:
    """
    Generates an AP2-aligned cryptographically signed spending authorization proof.
    By default, uses asymmetric Ed25519 so the buyer agent signs with its private key
    and the seller verifies with the buyer's public key (guaranteeing non-repudiation).
    """
    timestamp = int(time.time())
    priv_hex = buyer_private_key_hex or os.getenv("A2A_PRIVATE_KEY") or DEFAULT_BUYER_PRIVATE_KEY_HEX
    priv_key = ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(priv_hex))
    pub_key = priv_key.public_key()
    pub_hex = pub_key.public_bytes_raw().hex()

    raw_payload = {
        "vct": "ap2.mandate.intent.1",
        "contractor_id": contractor_id,
        "business_name": business_name,
        "monthly_cap_usd": monthly_cap_usd,
        "agreed_price_usd": agreed_price_usd,
        "nonce": nonce,
        "timestamp": timestamp,
        "public_key": pub_hex,
        "kid": DEFAULT_BUYER_KID,
    }
    canonical_payload = canonicalize_mandate_payload(raw_payload)
    encoded_bytes = json.dumps(canonical_payload, sort_keys=True).encode("utf-8")

    # Asymmetric Ed25519 signature
    signature = priv_key.sign(encoded_bytes).hex()

    return {
        "canonical_payload": canonical_payload,
        "signature": signature,
        "public_key": pub_hex,
        "kid": DEFAULT_BUYER_KID,
        "algorithm": "Ed25519",
        "vct": "ap2.mandate.intent.1",
    }


def _ap2_signing_bytes(mandate: Dict[str, Any]) -> bytes:
    """Canonical bytes of an AP2 Mandate, excluding the signature itself."""
    body = {k: v for k, v in mandate.items() if k != "signature"}
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_ap2_intent_mandate(
    mandate: Dict[str, Any], private_key_hex: Optional[str] = None
) -> Dict[str, Any]:
    """Returns a copy of the AP2 Intent Mandate with Ed25519 `public_key` and `signature` attached."""
    priv_hex = private_key_hex or os.getenv("A2A_PRIVATE_KEY") or DEFAULT_BUYER_PRIVATE_KEY_HEX
    priv_key = ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(priv_hex))
    signed = {
        **mandate,
        "kid": mandate.get("kid", DEFAULT_BUYER_KID),
        "signature_alg": "Ed25519",
        "public_key": priv_key.public_key().public_bytes_raw().hex(),
    }
    signed["signature"] = priv_key.sign(_ap2_signing_bytes(signed)).hex()
    return signed


def verify_ap2_intent_mandate(mandate: Dict[str, Any]) -> bool:
    """Verifies the Ed25519 signature of an AP2 Intent Mandate against its embedded public key."""
    try:
        pub_hex = mandate.get("public_key")
        sig_hex = mandate.get("signature")
        if not pub_hex or not sig_hex:
            return False
        verifier = ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex))
        verifier.verify(bytes.fromhex(sig_hex), _ap2_signing_bytes(mandate))
        return True
    except Exception:
        return False


def sign_ap2_cart_mandate(
    cart: Dict[str, Any], private_key_hex: Optional[str] = None
) -> Dict[str, Any]:
    """
    Returns a copy of the AP2 Cart Mandate (merchant offer) with Ed25519 `public_key` and `signature` attached.
    Signed by the Merchant/Seller to bind the negotiated tier, price, and expiration.
    """
    priv_hex = private_key_hex or os.getenv("A2A_SELLER_PRIVATE_KEY") or DEFAULT_SELLER_PRIVATE_KEY_HEX
    priv_key = ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(priv_hex))
    signed = {
        **cart,
        "vct": "ap2.mandate.cart.1",
        "kid": cart.get("kid", DEFAULT_SELLER_KID),
        "signature_alg": "Ed25519",
        "public_key": priv_key.public_key().public_bytes_raw().hex(),
    }
    signed["signature"] = priv_key.sign(_ap2_signing_bytes(signed)).hex()
    return signed


def verify_ap2_cart_mandate(cart: Dict[str, Any]) -> bool:
    """Verifies the Ed25519 signature of an AP2 Cart Mandate against its embedded public key."""
    try:
        pub_hex = cart.get("public_key")
        sig_hex = cart.get("signature")
        if not pub_hex or not sig_hex:
            return False
        verifier = ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex))
        verifier.verify(bytes.fromhex(sig_hex), _ap2_signing_bytes(cart))
        return True
    except Exception:
        return False



def verify_mandate_proof(
    payload: Dict[str, Any],
    signature: str,
    public_key_hex: Optional[str] = None,
    max_drift_sec: int = 300,
    secret_key: bytes = SECRET_KEY,
) -> Tuple[bool, str]:
    """
    Verifies the authenticity, time-validity, and financial guardrails of an inbound mandate proof.
    Supports asymmetric Ed25519 verification (AP2 standard) and HMAC-SHA256 fallback.
    Returns (True, "VERIFIED") or (False, REASON).
    """
    current_time = int(time.time())
    payload_time = payload.get("timestamp", 0)

    if abs(current_time - payload_time) > max_drift_sec:
        return False, "TIMESTAMP_EXPIRED"

    if payload.get("agreed_price_usd", 0) > payload.get("monthly_cap_usd", 0):
        return False, "BUDGET_CAP_BREACH"

    canonical_payload = canonicalize_mandate_payload(payload)
    encoded_bytes = json.dumps(canonical_payload, sort_keys=True).encode("utf-8")

    # 1. Asymmetric Ed25519 Verification (AP2 standard)
    pub_hex = public_key_hex or payload.get("public_key")
    if pub_hex and len(signature) == 128:  # 64-byte Ed25519 signature is 128 hex chars
        try:
            pub_bytes = bytes.fromhex(pub_hex)
            sig_bytes = bytes.fromhex(signature)
            verifier = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)
            verifier.verify(sig_bytes, encoded_bytes)
            return True, "VERIFIED"
        except Exception:
            return False, "SIGNATURE_MISMATCH"

    # 2. Symmetric HMAC-SHA256 Verification (Legacy fallback)
    try:
        expected_sig = hmac.new(secret_key, encoded_bytes, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected_sig, signature):
            return True, "VERIFIED"
    except Exception:
        pass

    return False, "SIGNATURE_MISMATCH"
