"""
AP2 v0.2 Key Management Service.
Handles ES256 (ECDSA P-256) JWK key generation, resolution, and public key presentation
for Google AP2 v0.2 Protocol conformance.

Merchant keys are loaded strictly from the environment and never written to disk or git.
Demo user and agent keys are generated ephemerally or cached in-memory per process.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any, Dict, Optional

from jwcrypto.jwk import JWK
from ..config import settings

logger = logging.getLogger("ap2_keys")

_MERCHANT_KEY: Optional[JWK] = None
_DEMO_USER_KEY: Optional[JWK] = None
_DEMO_AGENT_KEY: Optional[JWK] = None


def get_merchant_key() -> JWK:
    """
    Returns the merchant ES256 private key for signing Checkout JWTs and receipts.
    Loaded from AP2_MERCHANT_PRIVATE_KEY_JWK environment variable if provided;
    otherwise lazily creates a transient in-memory P-256 key for mock/testing.
    Never persists or logs the private key.
    """
    global _MERCHANT_KEY
    if _MERCHANT_KEY is not None:
        return _MERCHANT_KEY

    raw_env_key = settings.ap2_merchant_private_key_jwk or os.environ.get("AP2_MERCHANT_PRIVATE_KEY_JWK", "")
    if raw_env_key.strip():
        try:
            _MERCHANT_KEY = JWK.from_json(raw_env_key.strip())
            logger.info("Loaded merchant ES256 key from environment.")
            return _MERCHANT_KEY
        except Exception as e:
            logger.warning(f"Failed to parse AP2_MERCHANT_PRIVATE_KEY_JWK from environment: {e}")

    # Generate ephemeral merchant key for test / sandbox / mock mode
    kid = settings.ap2_merchant_key_id or "ap2-merchant-key-1"
    _MERCHANT_KEY = JWK.generate(kty="EC", crv="P-256", kid=kid)
    logger.info(f"Initialized ephemeral in-memory ES256 merchant key with kid '{kid}'.")
    return _MERCHANT_KEY


def get_merchant_public_key() -> JWK:
    """Returns the merchant ES256 public key (JWK) for signature verification."""
    priv = get_merchant_key()
    return JWK.from_json(priv.export_public())


def get_merchant_public_jwk() -> Dict[str, Any]:
    """Returns the merchant public key as a standard JWK dictionary."""
    return get_merchant_key().export_public(as_dict=True)


def generate_ephemeral_key(kid: Optional[str] = None) -> JWK:
    """Generates a fresh ephemeral ES256 (P-256) JWK key pair."""
    key_id = kid or f"ephemeral-{uuid.uuid4().hex[:8]}"
    return JWK.generate(kty="EC", crv="P-256", kid=key_id)


def get_demo_user_key() -> JWK:
    """
    Returns the in-memory ES256 key representing the Human Trusted Surface.
    Used for minting root Open Checkout and Open Payment mandates.
    """
    global _DEMO_USER_KEY
    if _DEMO_USER_KEY is None:
        _DEMO_USER_KEY = JWK.generate(kty="EC", crv="P-256", kid="demo-human-trusted-surface")
    return _DEMO_USER_KEY


def get_demo_agent_key() -> JWK:
    """
    Returns the in-memory ES256 key representing the Autonomous Buyer Agent.
    Bound to `cnf.jwk` in open mandates and used to sign closed mandates.
    """
    global _DEMO_AGENT_KEY
    if _DEMO_AGENT_KEY is None:
        _DEMO_AGENT_KEY = JWK.generate(kty="EC", crv="P-256", kid="demo-autonomous-buyer-agent")
    return _DEMO_AGENT_KEY


def jwk_to_cnf(key: JWK) -> Dict[str, Any]:
    """Wraps a public JWK in a RFC 7800 Confirmation claim (`cnf.jwk`)."""
    pub_dict = key.export_public(as_dict=True)
    return {"jwk": pub_dict}
