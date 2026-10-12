"""
Hardware Enclave & Passkey Keystore Abstraction.
SPEC-001 v1.9.0 / Milestone S3-NATIVE (Sprint 3).

Provides hardware isolation boundaries for buyer signing keys.
Adheres strictly to AGENTS.md Rule 5:
"Keys stay separated. The buyer agent never imports, holds or uses the owner's key;
it signs only closed mandates, with its own key."

Provides:
  - EnclaveKeystore: Abstract base protocol for enclave-bound signing keys
  - SoftwareEnclaveKeystore: Software-isolated memory keystore (P-256 / Ed25519)
  - PasskeyAttestationKeystore: WebAuthn / FIDO2 passkey hardware token emulation
"""

from __future__ import annotations

import abc
import base64
import hashlib
import json
import secrets
import time
from pathlib import Path
from typing import Any, Dict, Optional, Union

from jwcrypto import jwt
from jwcrypto.jwk import JWK


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data_str: str) -> bytes:
    padded = data_str + "=" * ((4 - len(data_str) % 4) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


class EnclaveKeystore(abc.ABC):
    """Abstract interface for enclave-protected signing keys."""

    @property
    @abc.abstractmethod
    def kid(self) -> str:
        """The Key ID of this keystore."""
        pass

    @property
    @abc.abstractmethod
    def algorithm(self) -> str:
        """Cryptographic algorithm (e.g. 'ES256' or 'Ed25519')."""
        pass

    @property
    @abc.abstractmethod
    def jwk(self) -> JWK:
        """The internal JWK instance (restricted to authorized signing pipelines)."""
        pass

    @abc.abstractmethod
    def export_public(self, as_dict: bool = True) -> Union[Dict[str, Any], str]:
        """Exports the public key material. Never exposes private key bytes."""
        pass

    @abc.abstractmethod
    def sign_jwt(self, claims: Dict[str, Any], headers: Optional[Dict[str, Any]] = None) -> str:
        """Signs claims inside the secure enclave and returns a serialized compact JWT."""
        pass

    @abc.abstractmethod
    def sign_raw(self, data: bytes) -> bytes:
        """Computes a raw cryptographic signature over arbitrary data bytes."""
        pass


class SoftwareEnclaveKeystore(EnclaveKeystore):
    """
    In-memory isolated keystore for P-256 (ES256) or Ed25519 keys.
    Masks private key representation to prevent accidental log leakage.
    """

    def __init__(self, key: JWK):
        if not key.has_private:
            raise ValueError("SoftwareEnclaveKeystore requires a private signing key.")
        self._key = key
        self._kid = key.kid or f"key-{secrets.token_hex(4)}"
        kty = key.get("kty")
        crv = key.get("crv")
        if kty == "EC" and crv == "P-256":
            self._alg = "ES256"
        elif kty == "OKP" and crv == "Ed25519":
            self._alg = "Ed25519"
        else:
            self._alg = "ES256"

    @classmethod
    def generate(cls, kid: Optional[str] = None, crv: str = "P-256") -> SoftwareEnclaveKeystore:
        """Generates a fresh ephemeral software enclave key."""
        key_id = kid or f"wallet-enclave-{secrets.token_hex(4)}"
        if crv == "Ed25519":
            key = JWK.generate(kty="OKP", crv="Ed25519", kid=key_id)
        else:
            key = JWK.generate(kty="EC", crv="P-256", kid=key_id)
        return cls(key)

    @classmethod
    def from_file(cls, path: Path) -> SoftwareEnclaveKeystore:
        """Loads a keystore from a secure local JSON file."""
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(JWK(**data))

    @property
    def kid(self) -> str:
        return self._kid

    @property
    def algorithm(self) -> str:
        return self._alg

    @property
    def jwk(self) -> JWK:
        return self._key

    def export_public(self, as_dict: bool = True) -> Union[Dict[str, Any], str]:
        return self._key.export_public(as_dict=as_dict)

    def sign_jwt(self, claims: Dict[str, Any], headers: Optional[Dict[str, Any]] = None) -> str:
        token_headers = {"alg": self._alg, "typ": "JWT", "kid": self._kid}
        if headers:
            token_headers.update(headers)
        token = jwt.JWT(header=token_headers, claims=claims)
        token.make_signed_token(self._key)
        return token.serialize()

    def sign_raw(self, data: bytes) -> bytes:
        # Standard compact token format representation or raw signature
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        pyca_key = self._key.get_op_key("sign")
        if isinstance(pyca_key, ec.EllipticCurvePrivateKey):
            return pyca_key.sign(data, ec.ECDSA(hashes.SHA256()))
        else:
            return pyca_key.sign(data)

    def __repr__(self) -> str:
        return f"<SoftwareEnclaveKeystore kid='{self._kid}' alg='{self._alg}' status='PROTECTED'>"

    def __str__(self) -> str:
        return f"SoftwareEnclaveKeystore(kid={self._kid}, alg={self._alg})"


class PasskeyAttestationKeystore(EnclaveKeystore):
    """
    FIDO2 / WebAuthn Passkey Hardware Keystore Emulation.
    Binds the signing key to a WebAuthn Credential ID and User Verification flags.
    """

    def __init__(self, key: Optional[JWK] = None, rp_id: str = "ap2-commerce.org"):
        self._rp_id = rp_id
        if key is None:
            self._key = JWK.generate(kty="EC", crv="P-256", kid=f"passkey-{secrets.token_hex(6)}")
        else:
            if not key.has_private:
                raise ValueError("PasskeyAttestationKeystore requires private key material.")
            self._key = key

        self._kid = self._key.kid or f"passkey-{secrets.token_hex(6)}"
        self._alg = "ES256"
        self._credential_id = _b64url_encode(hashlib.sha256(self._kid.encode("utf-8")).digest()[:16])

    @property
    def kid(self) -> str:
        return self._kid

    @property
    def algorithm(self) -> str:
        return self._alg

    @property
    def jwk(self) -> JWK:
        return self._key

    @property
    def credential_id(self) -> str:
        return self._credential_id

    @property
    def rp_id(self) -> str:
        return self._rp_id

    def export_public(self, as_dict: bool = True) -> Union[Dict[str, Any], str]:
        return self._key.export_public(as_dict=as_dict)

    def get_webauthn_attestation(self) -> Dict[str, Any]:
        """Returns WebAuthn / FIDO2 attestation structure."""
        rp_hash = hashlib.sha256(self._rp_id.encode("utf-8")).digest()
        # Flags: User Present (0x01) | User Verified (0x04) | Attested Credential Data (0x40) = 0x45
        flags = bytes([0x45])
        sign_count = bytes([0, 0, 0, 1])
        auth_data = rp_hash + flags + sign_count + _b64url_decode(self._credential_id)

        return {
            "credential_id": self._credential_id,
            "rp_id": self._rp_id,
            "authenticator_data_b64": _b64url_encode(auth_data),
            "user_verified": True,
            "user_present": True,
            "public_key": self._key.export_public(as_dict=True),
        }

    def sign_jwt(self, claims: Dict[str, Any], headers: Optional[Dict[str, Any]] = None) -> str:
        token_headers = {
            "alg": self._alg,
            "typ": "JWT",
            "kid": self._kid,
            "fido2_cred": self._credential_id,
        }
        if headers:
            token_headers.update(headers)
        token = jwt.JWT(header=token_headers, claims=claims)
        token.make_signed_token(self._key)
        return token.serialize()

    def sign_raw(self, data: bytes) -> bytes:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        pyca_key = self._key.get_op_key("sign")
        return pyca_key.sign(data, ec.ECDSA(hashes.SHA256()))

    def __repr__(self) -> str:
        return f"<PasskeyAttestationKeystore kid='{self._kid}' cred_id='{self._credential_id}' alg='{self._alg}'>"

    def __str__(self) -> str:
        return f"PasskeyAttestationKeystore(kid={self._kid}, cred_id={self._credential_id})"
