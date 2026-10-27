"""
PayPal OpenID Connect (OIDC) Identity Attestation Service.
SPEC-001 v1.9.0 / Milestone S3-NATIVE (Sprint 3).

Enables Log in with PayPal (Identity API / OIDC) attestation binding
verified PayPal payer accounts (payer_id / sub) to registered AP2 buyer keys.
Verifies cryptographic nonces against the seller key challenge and enforces
verified email status to prevent identity spoofing.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import math
import time
from typing import Any, Dict, Optional

from ..config import settings

logger = logging.getLogger("paypal_oidc_service")

# Canonical PayPal OpenID Connect token issuers
VALID_PAYPAL_ISSUERS = {
    "https://www.paypal.com",
    "https://api.sandbox.paypal.com",
    "https://identity.paypal.com",
}


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data_str: str) -> bytes:
    padded = data_str + "=" * ((4 - len(data_str) % 4) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


class PayPalOidcService:
    """Provides OpenID Connect verification and mock generation for Log in with PayPal attestation."""

    @staticmethod
    def generate_mock_oidc_token(
        payer_id: str,
        email: str,
        nonce: Optional[str] = None,
        client_id: Optional[str] = None,
        issuer: str = "https://api.sandbox.paypal.com",
        expires_in_seconds: int = 3600,
    ) -> str:
        """
        Generates a signed OpenID Connect ID token for Log in with PayPal in mock/sandbox mode.
        """
        # MOCK(M-023): OpenID Connect (OIDC) ID token generated and simulated in mock mode
        now = int(time.time())
        header = {
            "alg": "HS256",
            "typ": "JWT",
            "kid": "mock-paypal-oidc-key-1",
        }
        claims = {
            "iss": issuer,
            "sub": str(payer_id).strip(),
            "aud": client_id or "demo-paypal-client-id",
            "email": str(email).strip().lower(),
            "email_verified": True,
            "iat": now,
            "exp": now + expires_in_seconds,
        }
        if nonce:
            claims["nonce"] = str(nonce).strip()

        header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        payload_b64 = _b64url_encode(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")

        mock_secret = b"mock-paypal-oidc-secret-key-32bytes"
        sig = hmac.new(mock_secret, signing_input, hashlib.sha256).digest()
        sig_b64 = _b64url_encode(sig)

        return f"{header_b64}.{payload_b64}.{sig_b64}"

    @classmethod
    def verify_oidc_identity_attestation(
        cls,
        id_token: str,
        expected_nonce: Optional[str] = None,
        expected_client_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Verifies a PayPal OpenID Connect ID token and returns the attested identity claims.
        Fails closed on missing claims, expired tokens, untrusted issuers, or nonce mismatches.
        """
        if not id_token or not isinstance(id_token, str):
            raise ValueError("INVALID_ID_TOKEN: Token must be a non-empty string.")

        parts = id_token.strip().split(".")
        if len(parts) != 3:
            raise ValueError("INVALID_ID_TOKEN_FORMAT: Expected standard 3-part JWT.")

        header_b64, payload_b64, sig_b64 = parts

        # 0. Header & algorithm verification (Strict algorithm whitelist, reject "none")
        try:
            header_bytes = _b64url_decode(header_b64)
            header = json.loads(header_bytes.decode("utf-8"))
        except Exception as e:
            raise ValueError(f"MALFORMED_ID_TOKEN_HEADER: Could not decode header: {e}")

        alg = header.get("alg")
        if not alg or alg != "HS256":
            raise ValueError(f"UNSUPPORTED_ALGORITHM: Algorithm '{alg}' is not permitted.")

        # Fail closed outside mock mode: HS256 mock secret is strictly prohibited in live mode (Rule 9)
        if not settings.mock_external_apis:
            raise ValueError(
                "LIVE_OIDC_NOT_CONFIGURED: Production RS256 verification against PayPal JWKS keys is not yet configured. "
                "HS256 mock tokens are strictly forbidden when settings.mock_external_apis is false."
            )

        # 0.5 Cryptographic signature verification (Fail closed: Rule 1 & Rule 2)
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        mock_secret = b"mock-paypal-oidc-secret-key-32bytes"
        expected_sig = hmac.new(mock_secret, signing_input, hashlib.sha256).digest()
        try:
            actual_sig = _b64url_decode(sig_b64)
        except Exception as e:
            raise ValueError(f"INVALID_SIGNATURE_ENCODING: Could not decode signature: {e}")

        if not hmac.compare_digest(actual_sig, expected_sig):
            raise ValueError("INVALID_SIGNATURE: OIDC ID token cryptographic signature verification failed.")

        try:
            payload_bytes = _b64url_decode(payload_b64)
            claims = json.loads(payload_bytes.decode("utf-8"))
        except Exception as e:
            raise ValueError(f"MALFORMED_ID_TOKEN_PAYLOAD: Could not decode claims: {e}")

        # 1. Issuer verification (must be recognized PayPal domain)
        issuer = claims.get("iss")
        if not issuer or issuer not in VALID_PAYPAL_ISSUERS:
            raise ValueError(f"INVALID_ISSUER: Token issuer '{issuer}' is not an authorized PayPal OIDC provider.")

        # 2. Expiration, issued-at, and not-before verification
        now = time.time()
        exp = claims.get("exp")
        if exp is None or not isinstance(exp, (int, float)) or not math.isfinite(exp):
            raise ValueError("INVALID_EXPIRATION: Token missing valid finite 'exp' claim.")
        if exp < now:
            raise ValueError("EXPIRED_TOKEN: Identity attestation token has expired.")

        iat = claims.get("iat")
        if iat is not None:
            if not isinstance(iat, (int, float)) or not math.isfinite(iat):
                raise ValueError("INVALID_IAT: 'iat' claim must be a numeric timestamp.")
            if iat > now + 300:
                raise ValueError("FUTURE_TOKEN: Token 'iat' timestamp is in the future beyond allowed clock skew.")
            if exp <= iat:
                raise ValueError("INVALID_TOKEN_LIFESPAN: Token expiration 'exp' must be strictly after 'iat'.")
            if exp - iat > 86400 * 30:
                raise ValueError("EXCESSIVE_TOKEN_LIFESPAN: Token lifespan exceeds maximum allowed limit of 30 days.")

        nbf = claims.get("nbf")
        if nbf is not None:
            if not isinstance(nbf, (int, float)) or not math.isfinite(nbf):
                raise ValueError("INVALID_NBF: 'nbf' claim must be a numeric timestamp.")
            if nbf > now + 300:
                raise ValueError("TOKEN_NOT_YET_VALID: Token 'nbf' timestamp is in the future.")

        # 3. Payer ID (subject) validation
        sub = claims.get("sub")
        if not sub or not isinstance(sub, str) or len(sub.strip()) < 3:
            raise ValueError("MISSING_SUBJECT: Token missing valid PayPal Payer ID ('sub').")

        # 4. Verified email enforcement (Fail closed: Rule 2)
        email_verified = claims.get("email_verified")
        if email_verified is not True:
            raise ValueError("EMAIL_NOT_VERIFIED: PayPal identity requires a verified email address.")

        email = claims.get("email")
        if not email or not isinstance(email, str) or "@" not in email:
            raise ValueError("MISSING_EMAIL: Token missing valid email address.")

        # 5. Nonce verification against challenge
        token_nonce = claims.get("nonce")
        if token_nonce is not None and not isinstance(token_nonce, str):
            raise ValueError("INVALID_NONCE: Nonce must be a string.")

        if expected_nonce:
            if not token_nonce or token_nonce.strip() != expected_nonce.strip():
                raise ValueError(
                    f"NONCE_MISMATCH: Token nonce '{token_nonce}' does not match expected challenge nonce '{expected_nonce}'."
                )

        # 6. Audience verification (Fail closed on missing or mismatched audience)
        token_aud = claims.get("aud")
        if not token_aud or not isinstance(token_aud, str) or not token_aud.strip():
            raise ValueError("MISSING_AUDIENCE: Token missing valid 'aud' claim.")
        configured_client_id = (getattr(settings, "paypal_client_id", None) or "").strip()
        if expected_client_id:
            allowed_audiences = {expected_client_id.strip()}
        else:
            allowed_audiences = {a for a in (configured_client_id, "demo-paypal-client-id") if a}
        if token_aud.strip() not in allowed_audiences:
            target_aud = expected_client_id or configured_client_id or "demo-paypal-client-id"
            raise ValueError(f"AUDIENCE_MISMATCH: Token audience '{token_aud}' does not match '{target_aud}'.")

        logger.info(
            f"[PayPal OIDC] Successfully verified identity attestation for Payer ID '{sub}' ({email})"
        )

        return {
            "status": "ATTESTED",
            "payer_id": sub.strip(),
            "email": email.strip().lower(),
            "email_verified": True,
            "nonce": claims.get("nonce"),
            "identity_provider": "paypal",
            "claims": claims,
        }
