"""
Cryptographic Mandate Revocation Service for AP2 v0.2 / SPEC-001 v1.9.0.
Provides an authentic cryptographic revocation status list for AP2 Open Payment Mandates.

Enforces:
1. Verify First: Signature must verify against the registered owner public key in buyer_keys.
2. Fail Closed: Unregistered keys, malformed signatures, or forged payloads are rejected.
3. Automated Cancellation: Active PayPal subscriptions bound to the revoked mandate are
   immediately stopped and the buyer's active ledger is reconciled.
"""

from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..database import (
    get_buyer_identity,
    get_buyer_key,
    get_buyer_key_email,
    get_connection,
    get_mandate_revocation,
    is_mandate_revoked,
    list_revoked_mandates,
    list_subscriptions,
    record_mandate_revocation,
    set_recurring_mandate_status,
)
from .crypto_mandate import (
    verify_ed25519_challenge_signature,
    verify_es256_challenge_signature,
)
from .paypal_service import paypal_service

logger = logging.getLogger("mandate_revocation_service")


def _parse_ts_to_seconds(ts_val: Any) -> Optional[float]:
    if ts_val is None:
        return None
    if isinstance(ts_val, (int, float)):
        return float(ts_val)
    if isinstance(ts_val, str):
        try:
            return float(ts_val)
        except ValueError:
            pass
        try:
            dt = datetime.datetime.fromisoformat(ts_val.replace("Z", "+00:00"))
            return dt.timestamp()
        except Exception:
            pass
    return None


def resolve_mandate_owner(
    mandate_hash: str, db_path: Optional[Path] = None
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Resolves the contractor email, buyer_key_id, and creation timestamp bound to a mandate proof hash.
    Returns (contractor_email, buyer_key_id, created_at).
    """
    clean = mandate_hash.strip()
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        # 1. Check subscriptions table
        cur.execute(
            "SELECT contractor_email, raw_details_json, created_at FROM subscriptions WHERE mandate_proof_hash = ? OR subscription_id = ? LIMIT 1",
            (clean, clean),
        )
        row = cur.fetchone()
        if row and row["contractor_email"]:
            owner_kid = None
            if row.get("raw_details_json"):
                try:
                    rd = json.loads(row["raw_details_json"])
                    if isinstance(rd, dict):
                        owner_kid = rd.get("owner_kid") or rd.get("kid") or rd.get("buyer_key_id")
                        if not owner_kid and "raw_details_json" in rd:
                            try:
                                nested = json.loads(rd["raw_details_json"]) if isinstance(rd["raw_details_json"], str) else rd["raw_details_json"]
                                if isinstance(nested, dict):
                                    owner_kid = nested.get("owner_kid") or nested.get("kid") or nested.get("buyer_key_id")
                            except Exception:
                                pass
                        if not owner_kid and isinstance(rd.get("ap2_intent_mandate"), dict):
                            owner_kid = rd["ap2_intent_mandate"].get("kid")
                except Exception:
                    pass
            return row["contractor_email"].strip().lower(), owner_kid, row.get("created_at")

        # 1.5 Check recurring_mandates table (stores verified owner-signed open payment mandate)
        cur.execute(
            "SELECT buyer_email, open_payment_mandate_token, created_at FROM recurring_mandates WHERE mandate_hash = ? OR subscription_id = ? LIMIT 1",
            (clean, clean),
        )
        row = cur.fetchone()
        if row and row["buyer_email"]:
            owner_kid = None
            if row.get("open_payment_mandate_token"):
                try:
                    import base64
                    raw_token = row["open_payment_mandate_token"].strip()
                    if "~~" in raw_token:
                        raw_token = raw_token.split("~~")[0]
                    if raw_token.endswith("~"):
                        raw_token = raw_token[:-1]
                    parts = raw_token.split(".")
                    if len(parts) >= 2:
                        header_b64 = parts[0]
                        rem = len(header_b64) % 4
                        if rem:
                            header_b64 += "=" * (4 - rem)
                        hdr = json.loads(base64.urlsafe_b64decode(header_b64).decode("utf-8"))
                        owner_kid = hdr.get("kid")
                except Exception:
                    pass
            return row["buyer_email"].strip().lower(), owner_kid, row.get("created_at")

        # 2. Check authorized_mandates table
        cur.execute(
            "SELECT contractor_email, details_json, registered_at FROM authorized_mandates WHERE proof_hash = ? OR lookup_key = ? OR offer_id = ? LIMIT 1",
            (clean, clean, clean),
        )
        row = cur.fetchone()
        if row and row["contractor_email"]:
            owner_kid = None
            if row.get("details_json"):
                try:
                    dj = json.loads(row["details_json"])
                    if isinstance(dj, dict):
                        owner_kid = dj.get("owner_kid") or dj.get("kid")
                        if not owner_kid and isinstance(dj.get("ap2_mandate"), dict):
                            owner_kid = dj["ap2_mandate"].get("kid")
                except Exception:
                    pass
            reg_at = str(row.get("registered_at")) if row.get("registered_at") else None
            return row["contractor_email"].strip().lower(), owner_kid, reg_at

        # 3. Check direct_charges table
        cur.execute(
            "SELECT buyer_key_id, created_at FROM direct_charges WHERE mandate_id = ? LIMIT 1",
            (clean,),
        )
        row = cur.fetchone()
        if row and row["buyer_key_id"]:
            return None, row["buyer_key_id"].strip(), row.get("created_at")

        return None, None, None
    finally:
        conn.close()


def canonical_revocation_message(mandate_proof_hash: str, timestamp_iso: str, reason: str) -> str:
    """Constructs the canonical payload string for cryptographic revocation signature."""
    return f"REVOKE:{mandate_proof_hash.strip()}:{timestamp_iso.strip()}:{reason.strip()}"


def verify_revocation_signature(
    mandate_proof_hash: str,
    kid: str,
    timestamp_iso: str,
    reason: str,
    signature: str,
    db_path: Optional[Path] = None,
) -> Tuple[bool, str]:
    """
    Verifies that the revocation request is signed by the registered owner of the key `kid`.
    Supports Ed25519 and ES256 (P-256) registered keys.
    """
    if not mandate_proof_hash or not kid or not timestamp_iso or not signature:
        return False, "INVALID_ARGUMENT: mandate_proof_hash, kid, timestamp_iso, and signature are required."

    pub_key_record = get_buyer_key(kid, db_path=db_path)
    if not pub_key_record:
        return False, f"KEY_NOT_FOUND: Key ID '{kid}' is not registered in the buyer key registry."

    message = canonical_revocation_message(mandate_proof_hash, timestamp_iso, reason)
    clean_pub = pub_key_record.strip()

    if clean_pub.startswith("{"):
        try:
            jwk_dict = json.loads(clean_pub)
            valid = verify_es256_challenge_signature(
                challenge=message,
                signature_str=signature,
                public_key_jwk=jwk_dict,
            )
            if not valid:
                return False, "SIGNATURE_VERIFICATION_FAILED: ES256 revocation signature did not match registered owner key."
            return True, "VERIFIED"
        except Exception as e:
            return False, f"MALFORMED_KEY_OR_SIG: {e}"
    else:
        valid = verify_ed25519_challenge_signature(
            challenge=message,
            signature_hex=signature,
            public_key_hex=clean_pub,
        )
        if not valid:
            return False, "SIGNATURE_VERIFICATION_FAILED: Ed25519 revocation signature did not match registered owner key."
        return True, "VERIFIED"


async def revoke_mandate(
    mandate_proof_hash: str,
    kid: str,
    reason: str,
    signature: str,
    timestamp_iso: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Cryptographically revokes an AP2 Open Mandate.
    1. Verifies owner signature against registered buyer keys.
    2. Validates timestamp freshness and mandate ownership authorization.
    3. Records the revocation in the SQLite revoked_mandates status list.
    4. Automatically stops any active PayPal subscriptions bound to this mandate.
    5. Reconciles contractor ledgers and marks compute nodes stopped.
    """
    clean_hash = mandate_proof_hash.strip()
    clean_kid = kid.strip()
    clean_reason = (reason or "Owner manual revocation").strip()
    now_iso = timestamp_iso or datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Rule 2: Minimum hash length enforcement (fail closed against short prefix attacks)
    if len(clean_hash) < 16:
        raise ValueError(
            f"INVALID_MANDATE_HASH: Mandate proof hash '{clean_hash}' must be at least 16 characters (got {len(clean_hash)})."
        )

    # -1. Idempotency check: If already revoked, return immutable tombstone
    if is_mandate_revoked(clean_hash, db_path=db_path):
        existing = get_mandate_revocation(clean_hash, db_path=db_path)
        logger.info(f"[REVOCATION] Mandate {clean_hash} was already cryptographically revoked; preserving original tombstone.")
        return {
            "status": "ALREADY_REVOKED",
            "mandate_proof_hash": clean_hash,
            "revoked_by_kid": existing.get("revoked_by_kid") if existing else clean_kid,
            "revocation_id": existing.get("revocation_id") if existing else "rev_existing",
            "revoked_at": existing.get("revoked_at") if existing else now_iso,
            "reason": existing.get("reason") if existing else clean_reason,
            "stopped_subscriptions": [],
            "idempotent": True,
        }

    # 0. Validate timestamp freshness if provided (max 300s skew)
    if timestamp_iso:
        try:
            ts = datetime.datetime.fromisoformat(timestamp_iso.strip().replace("Z", "+00:00"))
            now_dt = datetime.datetime.now(datetime.timezone.utc)
            skew = abs((now_dt - ts).total_seconds())
            if skew > 300:
                raise ValueError(
                    f"REVOCATION_TIMESTAMP_OUT_OF_BOUNDS: Timestamp '{timestamp_iso}' clock skew ({skew:.1f}s) exceeds 300s limit."
                )
        except ValueError as e:
            if "REVOCATION_TIMESTAMP" in str(e):
                raise
            raise ValueError(f"INVALID_TIMESTAMP_FORMAT: {e}")

    # 1. Verify owner signature
    valid, msg = verify_revocation_signature(
        mandate_proof_hash=clean_hash,
        kid=clean_kid,
        timestamp_iso=now_iso,
        reason=clean_reason,
        signature=signature,
        db_path=db_path,
    )
    if not valid:
        logger.warning(f"[SECURITY] Mandate revocation signature rejected for {clean_hash}: {msg}")
        raise ValueError(msg)

    # 1.5 Verify mandate ownership authorization (Fail closed against unauthorized cross-tenant revocation)
    target_email, target_kid, target_created_at = resolve_mandate_owner(clean_hash, db_path=db_path)
    if not target_email and not target_kid:
        from ..agents.seller_agent import _COMPLETED_SUBSCRIPTIONS
        for s_id, s_data in _COMPLETED_SUBSCRIPTIONS.items():
            if isinstance(s_data, dict):
                p_hash = (s_data.get("mandate_proof_hash") or "").strip()
                chk_h = (s_data.get("checkout_hash") or "").strip()
                sub_id_str = str(s_data.get("subscription_id") or s_id).strip()
                if clean_hash in (p_hash, chk_h, s_id, sub_id_str):
                    target_email = (s_data.get("contractor_email") or "").strip().lower()
                    target_created_at = s_data.get("created_at")
                    target_kid = s_data.get("owner_kid") or s_data.get("kid")
                    if not target_kid and isinstance(s_data.get("ap2_intent_mandate"), dict):
                        target_kid = s_data["ap2_intent_mandate"].get("kid")
                    if not target_kid and sub_id_str:
                        _, sub_kid, _ = resolve_mandate_owner(sub_id_str, db_path=db_path)
                        if sub_kid:
                            target_kid = sub_kid
                    break

    # Fail closed: If no mandate or subscription exists matching clean_hash, refuse (F1)
    if not target_email and not target_kid:
        raise ValueError(
            f"MANDATE_NOT_FOUND: No registered mandate or subscription found matching hash '{clean_hash}'."
        )

    signer_email = get_buyer_key_email(clean_kid, db_path=db_path)
    if target_email:
        if not signer_email or signer_email.strip().lower() != target_email:
            raise ValueError(
                f"UNAUTHORIZED_REVOCATION: Key ID '{clean_kid}' ({signer_email or 'unbound'}) is not authorized to revoke mandates belonging to '{target_email}'."
            )
        # Check identity attestation: unverified keys cannot revoke mandates by self-asserted email alone.
        # If the key is not the proven creator key (target_kid), it MUST be identity-attested (F2).
        if not target_kid or clean_kid != target_kid:
            buyer_ident = get_buyer_identity(clean_kid, db_path=db_path) or {}
            is_attested = bool(buyer_ident.get("identity_attested"))
            if not is_attested:
                raise ValueError(
                    f"UNAUTHORIZED_REVOCATION: Key ID '{clean_kid}' is not identity-attested. Self-asserted email cannot authorize mandate revocation."
                )
    elif target_kid:
        if clean_kid != target_kid:
            raise ValueError(
                f"UNAUTHORIZED_REVOCATION: Key ID '{clean_kid}' is not authorized to revoke mandates issued by '{target_kid}'."
            )

    # 2. Record revocation in persistent status list
    record = record_mandate_revocation(
        mandate_proof_hash=clean_hash,
        revoked_by_kid=clean_kid,
        reason=clean_reason,
        signature_hex=signature.strip(),
        revoked_at=now_iso,
        db_path=db_path,
    )

    # 3. Locate bound subscriptions and auto-cancel them
    from ..agents.seller_agent import _COMPLETED_SUBSCRIPTIONS
    from ..server import _apply_subscription_stop

    cancelled_subs: List[str] = []
    seen_sub_ids: set[str] = set()

    # Check in-memory / SQLite proxy subscriptions
    for sub_id, sub in list(_COMPLETED_SUBSCRIPTIONS.items()):
        if not isinstance(sub, dict):
            continue
        real_sub_id = sub.get("subscription_id") or sub_id
        if real_sub_id in seen_sub_ids:
            continue

        sub_proof = (sub.get("mandate_proof_hash") or "").strip()
        sub_chk = (sub.get("checkout_hash") or "").strip()
        sub_offer = (sub.get("offer_id") or "").strip()

        # Exact matching only (Rule 1 & Rule 2: never prefix match)
        if clean_hash in (sub_proof, sub_chk, sub_offer):
            seen_sub_ids.add(real_sub_id)
            if sub.get("status") in ("ACTIVE", "APPROVAL_PENDING"):
                try:
                    await paypal_service.stop_subscription(
                        real_sub_id,
                        action="cancel",
                        reason=f"MANDATE_REVOKED: {clean_reason}",
                    )
                except Exception as e:
                    logger.error(f"Failed to cancel remote PayPal subscription {real_sub_id}: {e}")

                set_recurring_mandate_status(real_sub_id, "CANCELLED", f"MANDATE_REVOKED: {clean_reason}", db_path=db_path)
                _apply_subscription_stop(real_sub_id, "CANCELLED")
                cancelled_subs.append(real_sub_id)
                logger.info(f"[REVOCATION] Auto-cancelled subscription {real_sub_id} bound to revoked mandate {clean_hash}")

    return {
        "status": "REVOKED",
        "revocation_id": record["revocation_id"],
        "mandate_proof_hash": clean_hash,
        "revoked_by_kid": clean_kid,
        "revoked_at": now_iso,
        "reason": clean_reason,
        "cancelled_subscriptions": cancelled_subs,
    }
