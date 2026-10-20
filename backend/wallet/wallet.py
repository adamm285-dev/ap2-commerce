"""
AP2 v0.2 Buyer Wallet.

The wallet is the buyer agent's signing boundary. It runs as its own process (for example
as a second MCP server next to the seller in Claude Desktop) and holds exactly one private
key: the buyer agent's own P-256 key. It never holds the owner's key or the merchant's key.

Inputs it trusts, all local files written at setup time:
  - owner_limits.json:    owner-signed AP2 v0.2 Open Checkout and Open Payment mandates
  - owner_public.jwk:     the owner's pinned public key (verifies owner_limits.json)
  - merchant_public.jwk:  the merchant's pinned public key (verifies Checkout JWTs)
  - merchant_keys.json:   optional map of merchant_id -> pinned public JWK for multi-merchant limits

The wallet signs a closed Checkout + Payment mandate pair only after the merchant-signed
Checkout JWT passes every owner constraint, evaluated with the vendored Google AP2 SDK.
Tier, price, merchant and nonce are read from the merchant-signed checkout, never from
the caller, so an LLM relaying the checkout cannot change what gets signed.

Pessimistic Reservation Architecture:
A signed checkout chain is recorded in ledger.json at signing time and counts against the
owner's budget and purchase count until the mandate expires. The wallet operates client-side
and cannot know whether a signed checkout settles immediately or is abandoned. Releasing
reserved budget on an error receipt would allow budget bypass (signing -> tampering ->
obtaining an error receipt -> releasing reservation -> honest retry settling for free).
A true release path requires terminal merchant-voided receipts not present in AP2 v0.2.
Because rejections on the seller do not burn the mandate, honest retries can settle
against the existing reservation without double-counting. Callers that want a pre-flight
check without reserving budget can call preview_checkout (dry-run mode), and recurring
renewals can be synchronized into ledger.json via merchant-signed renewal receipts
(record_renewal_receipt).

This module deliberately imports nothing from the seller side (agents, services, database).
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from jwcrypto.jwk import JWK

from ap2.sdk.constraints import (
    MandateContext,
    check_checkout_constraints,
    check_payment_constraints,
)
from ap2.sdk.generated.checkout_mandate import CheckoutMandate
from ap2.sdk.generated.open_checkout_mandate import (
    AllowedMerchants,
    LineItems,
    OpenCheckoutMandate,
)
from ap2.sdk.generated.open_payment_mandate import (
    AgentRecurrence,
    AllowedPayees,
    AmountRange,
    Budget,
    OpenPaymentMandate,
)
from ap2.sdk.generated.payment_mandate import PaymentMandate
from ap2.sdk.generated.types.amount import Amount
from ap2.sdk.generated.types.checkout import Checkout
from ap2.sdk.generated.types.merchant import Merchant
from ap2.sdk.generated.types.payment_instrument import PaymentInstrument
from ap2.sdk.jwt_helper import verify_jwt
from ap2.sdk.mandate import MandateClient, SdJwtMandate

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_WALLET_DIR = ROOT_DIR / ".ap2_local" / "wallet"

AGENT_KEY_FILE = "agent_key.jwk"
OWNER_LIMITS_FILE = "owner_limits.json"
OWNER_PUBLIC_KEY_FILE = "owner_public.jwk"
MERCHANT_PUBLIC_KEY_FILE = "merchant_public.jwk"
MERCHANT_KEYS_FILE = "merchant_keys.json"
LEDGER_FILE = "ledger.json"

PAYMENT_INSTRUMENT = PaymentInstrument(type="paypal_vault", id="vault_agent_mit")


class WalletRefusal(Exception):
    """The wallet refused to act. `code` is stable and machine-readable."""

    def __init__(
        self,
        code: str,
        reason: str,
        message: Optional[str] = None,
        escalation: Optional[Dict[str, Any]] = None,
    ):
        msg = message or reason
        super().__init__(f"{code}: {msg}")
        self.code = code
        self.reason = reason
        self.message = msg
        self.escalation = escalation

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "status": "REFUSED",
            "error": self.code,
            "reason": self.reason,
            "message": self.message,
        }
        if self.escalation is not None:
            result["escalation"] = self.escalation
        return result


def wallet_dir() -> Path:
    """Wallet state directory: AP2_WALLET_DIR, else <repo>/.ap2_local/wallet."""
    raw = os.environ.get("AP2_WALLET_DIR", "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_WALLET_DIR


def _write_new_file(path: Path, text: str) -> None:
    """Creates a file exclusively (never overwrites) and restricts it to the owner where supported."""
    with open(path, "x", encoding="utf-8") as f:
        f.write(text)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def init_agent_key(directory: Optional[Path] = None) -> Dict[str, Any]:
    """
    Creates the buyer agent's P-256 key if it does not exist yet and returns its public JWK.
    An existing key is validated and reused, never overwritten.
    """
    d = Path(directory) if directory else wallet_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / AGENT_KEY_FILE
    if not path.exists():
        key = JWK.generate(kty="EC", crv="P-256", kid=f"wallet-agent-{secrets.token_hex(4)}")
        _write_new_file(path, key.export_private())
    return _load_key(path, "buyer agent key", private=True).export_public(as_dict=True)


def _read_json(path: Path, what: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise WalletRefusal(
            "WALLET_NOT_CONFIGURED",
            f"Missing {what} ({path.name}). Run: python scripts/setup_claude_desktop_demo.py",
        )
    except (OSError, ValueError) as e:
        raise WalletRefusal("WALLET_FILE_UNREADABLE", f"Could not read {what} ({path.name}): {e}")


def _validate_jwk_dict(data: Any, what: str, source_name: str, private: bool) -> JWK:
    if not isinstance(data, dict):
        raise WalletRefusal("WALLET_FILE_UNREADABLE", f"{what} ({source_name}) is not a JWK object.")
    try:
        key = JWK(**data)
        pub = key.export_public(as_dict=True)
    except Exception as e:
        raise WalletRefusal("WALLET_FILE_UNREADABLE", f"{what} ({source_name}) is not a valid JWK: {e}")
    if pub.get("kty") != "EC" or pub.get("crv") != "P-256":
        raise WalletRefusal("WALLET_FILE_UNREADABLE", f"{what} ({source_name}) must be a P-256 key.")
    if private and not key.has_private:
        raise WalletRefusal("WALLET_FILE_UNREADABLE", f"{what} ({source_name}) has no private part.")
    if not private and key.has_private:
        # A pinned key file with private material means another party's secret leaked into the wallet.
        raise WalletRefusal(
            "PINNED_KEY_HAS_PRIVATE_PART",
            f"{what} ({source_name}) contains a private key. The wallet must only hold public keys for other parties.",
        )
    return key


def _load_key(path: Path, what: str, private: bool) -> JWK:
    data = _read_json(path, what)
    return _validate_jwk_dict(data, what, path.name, private=private)


def pin_merchant_key(
    merchant_id: str,
    public_jwk: Dict[str, Any],
    directory: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Pins a merchant's public P-256 JWK in merchant_keys.json under `merchant_id`.
    Never accepts private key material and never overwrites an existing merchant_id with a different key.
    """
    if not isinstance(merchant_id, str) or not merchant_id.strip():
        raise WalletRefusal("WALLET_FILE_UNREADABLE", "merchant_id must be a non-empty string.")
    clean_id = merchant_id.strip()
    key = _validate_jwk_dict(
        public_jwk,
        f"pinned merchant public key for '{clean_id}'",
        MERCHANT_KEYS_FILE,
        private=False,
    )
    pub_dict = key.export_public(as_dict=True)

    d = Path(directory) if directory else wallet_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / MERCHANT_KEYS_FILE
    existing_map: Dict[str, Any] = {}
    if path.exists():
        raw = _read_json(path, "pinned merchant keyring")
        if not isinstance(raw, dict):
            raise WalletRefusal("WALLET_FILE_UNREADABLE", f"pinned merchant keyring ({MERCHANT_KEYS_FILE}) is not a JSON object.")
        for mid, jwk_data in raw.items():
            existing_key = _validate_jwk_dict(
                jwk_data,
                f"pinned merchant public key for '{mid}'",
                MERCHANT_KEYS_FILE,
                private=False,
            )
            if mid == clean_id and existing_key.thumbprint() != key.thumbprint():
                raise WalletRefusal(
                    "MERCHANT_KEY_CONFLICT",
                    f"Merchant '{clean_id}' is already pinned to a different public key; refusing to overwrite.",
                )
            existing_map[mid] = existing_key.export_public(as_dict=True)

    existing_map[clean_id] = pub_dict
    tmp = d / (MERCHANT_KEYS_FILE + ".tmp")
    tmp.write_text(json.dumps(existing_map, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return pub_dict


def _peek_unverified_jwt_selector(jwt_token: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extracts only the unverified merchant_id (or iss) and kid selector from a JWT so the wallet
    can look up the corresponding pinned public key on disk. Never reads key material from the JWT.
    """
    parts = jwt_token.split(".")
    if len(parts) != 3:
        return None, None
    try:
        pad_h = parts[0] + "=" * (-len(parts[0]) % 4)
        pad_p = parts[1] + "=" * (-len(parts[1]) % 4)
        header = json.loads(base64.urlsafe_b64decode(pad_h).decode("utf-8"))
        payload = json.loads(base64.urlsafe_b64decode(pad_p).decode("utf-8"))
    except Exception:
        return None, None
    if not isinstance(header, dict) or not isinstance(payload, dict):
        return None, None
    kid = header.get("kid") if isinstance(header.get("kid"), str) else None
    merchant_id: Optional[str] = None
    merchant_claim = payload.get("merchant")
    if isinstance(merchant_claim, dict) and isinstance(merchant_claim.get("id"), str):
        merchant_id = merchant_claim["id"].strip() or None
    elif isinstance(payload.get("iss"), str):
        merchant_id = payload["iss"].strip() or None
    return merchant_id, kid


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_mandate_hash(token: str) -> str:
    """Canonical SHA-256 hash matching the seller's compute_open_payment_mandate_hash."""
    clean = token.strip()
    if "~~" in clean:
        clean = clean.split("~~")[0].strip()
    return _sha256_hex(clean.rstrip("~"))


def _thumbprint(jwk_dict: Any) -> str:
    if not isinstance(jwk_dict, dict):
        raise ValueError("cnf.jwk is not an object")
    return JWK(**jwk_dict).thumbprint()


def _constraint(constraints: Any, kind: type) -> Any:
    """Returns the single constraint of `kind`. Missing or duplicated constraints are refused."""
    matches = [c for c in (constraints or []) if isinstance(c, kind)]
    if len(matches) != 1:
        raise WalletRefusal(
            "MISSING_REQUIRED_CONSTRAINT",
            f"Owner limits must contain exactly one {kind.__name__} constraint (found {len(matches)}).",
        )
    return matches[0]


class _OwnerLimits:
    """Owner-signed open mandates after full verification."""

    def __init__(self, buyer_email: str, checkout_token: str, payment_token: str,
                 checkout: OpenCheckoutMandate, payment: OpenPaymentMandate):
        self.buyer_email = buyer_email
        self.checkout_token = checkout_token
        self.payment_token = payment_token
        self.checkout = checkout
        self.payment = payment
        self.payment_key = _sha256_hex(payment_token)
        self.canonical_payment_hash = _canonical_mandate_hash(payment_token)


class BuyerWallet:
    def __init__(self, directory: Optional[Path] = None):
        self.dir = Path(directory) if directory else wallet_dir()
        self._client = MandateClient()

    # ── Loading & verification ────────────────────────────────────────────

    def _agent_key(self) -> JWK:
        return _load_key(self.dir / AGENT_KEY_FILE, "buyer agent key", private=True)

    def get_keystore(self):
        """Returns the hardware enclave keystore wrapping the buyer agent's signing key."""
        from .keystore import SoftwareEnclaveKeystore, PasskeyAttestationKeystore
        key = self._agent_key()
        keystore_type = os.environ.get("AP2_KEYSTORE_TYPE", "software").lower()
        if keystore_type == "passkey":
            return PasskeyAttestationKeystore(key=key)
        return SoftwareEnclaveKeystore(key)

    def _resolve_merchant_key(self, jwt_token: str) -> Tuple[JWK, Optional[str]]:
        """
        Resolves a pinned merchant public key from merchant_keys.json or merchant_public.jwk.
        Fails closed if no pinned key file exists or if any pinned file contains private key material.
        """
        keyring_path = self.dir / MERCHANT_KEYS_FILE
        single_path = self.dir / MERCHANT_PUBLIC_KEY_FILE
        has_keyring = keyring_path.exists()
        has_single = single_path.exists()

        if not has_keyring and not has_single:
            raise WalletRefusal(
                "WALLET_NOT_CONFIGURED",
                f"Missing pinned merchant public key ({MERCHANT_PUBLIC_KEY_FILE}). Run: python scripts/setup_claude_desktop_demo.py",
            )

        keyring: Dict[str, JWK] = {}
        if has_keyring:
            raw = _read_json(keyring_path, "pinned merchant keyring")
            if not isinstance(raw, dict) or not raw:
                raise WalletRefusal(
                    "WALLET_FILE_UNREADABLE",
                    f"pinned merchant keyring ({MERCHANT_KEYS_FILE}) must be a non-empty JSON object.",
                )
            for mid, jwk_data in raw.items():
                if not isinstance(mid, str) or not mid.strip():
                    raise WalletRefusal(
                        "WALLET_FILE_UNREADABLE",
                        f"pinned merchant keyring ({MERCHANT_KEYS_FILE}) has an empty merchant id.",
                    )
                keyring[mid.strip()] = _validate_jwk_dict(
                    jwk_data,
                    f"pinned merchant public key for '{mid}'",
                    MERCHANT_KEYS_FILE,
                    private=False,
                )

        single_key: Optional[JWK] = None
        if has_single:
            single_key = _load_key(single_path, "pinned merchant public key", private=False)

        merchant_id, kid = _peek_unverified_jwt_selector(jwt_token)
        if merchant_id and merchant_id in keyring:
            return keyring[merchant_id], merchant_id

        if kid and keyring:
            for mid, k in keyring.items():
                if k.kid == kid and (merchant_id is None or merchant_id == mid):
                    return k, mid

        if single_key is not None and not keyring:
            return single_key, None

        raise WalletRefusal(
            "CHECKOUT_SIGNATURE_INVALID",
            f"No pinned merchant public key matches merchant '{merchant_id or 'unknown'}'.",
        )

    def _load_limits(self, require_unexpired_checkout: bool = True) -> _OwnerLimits:
        """Loads owner limits and verifies signature, expiry, agent binding and required constraints."""
        raw = _read_json(self.dir / OWNER_LIMITS_FILE, "owner spending limits")
        if not isinstance(raw, dict):
            raise WalletRefusal("MALFORMED_OWNER_LIMITS", "owner_limits.json must be a JSON object.")
        buyer_email = raw.get("buyer_email")
        chk_token = raw.get("open_checkout_mandate_token")
        pay_token = raw.get("open_payment_mandate_token")
        for name, value in (("buyer_email", buyer_email),
                            ("open_checkout_mandate_token", chk_token),
                            ("open_payment_mandate_token", pay_token)):
            if not isinstance(value, str) or not value.strip():
                raise WalletRefusal("MALFORMED_OWNER_LIMITS", f"owner_limits.json is missing '{name}'.")

        owner_pub = _load_key(self.dir / OWNER_PUBLIC_KEY_FILE, "pinned owner public key", private=False)
        try:
            open_chk = SdJwtMandate.from_sd_jwt(chk_token, owner_pub, OpenCheckoutMandate).mandate_payload
            open_pay = SdJwtMandate.from_sd_jwt(pay_token, owner_pub, OpenPaymentMandate).mandate_payload
        except Exception as e:
            raise WalletRefusal(
                "OWNER_SIGNATURE_INVALID",
                f"Owner limits are not validly signed by the pinned owner key: {e}",
            )

        now = int(time.time())
        agent_thumb = self._agent_key().thumbprint()
        norm_email = buyer_email.strip().lower()
        for label, payload in (("checkout", open_chk), ("payment", open_pay)):
            if not isinstance(payload.exp, int):
                raise WalletRefusal("OWNER_LIMITS_EXPIRED", f"Open {label} mandate has no expiry.")
            if (label == "payment" or require_unexpired_checkout) and payload.exp <= now:
                raise WalletRefusal(
                    "OWNER_LIMITS_EXPIRED",
                    f"Open {label} mandate expired; ask the owner to sign new limits.",
                    escalation={
                        "requires_human_approval": True,
                        "action": "REAUTHORIZE_EXPIRED_LIMITS",
                        "buyer_email": norm_email,
                        "mandate_type": label,
                        "expired_at": datetime.datetime.fromtimestamp(payload.exp, tz=datetime.timezone.utc).isoformat(),
                    },
                )
            try:
                bound_thumb = _thumbprint((payload.cnf or {}).get("jwk"))
            except Exception as e:
                raise WalletRefusal("AGENT_KEY_MISMATCH", f"Open {label} mandate has no usable cnf.jwk: {e}")
            if bound_thumb != agent_thumb:
                raise WalletRefusal(
                    "AGENT_KEY_MISMATCH",
                    f"Open {label} mandate is bound to a different agent key than this wallet's.",
                )

        # Fail closed: the constraints this wallet relies on must be present
        _constraint(open_chk.constraints, AllowedMerchants)
        _constraint(open_chk.constraints, LineItems)
        _constraint(open_pay.constraints, AmountRange)
        _constraint(open_pay.constraints, AllowedPayees)
        _constraint(open_pay.constraints, Budget)

        return _OwnerLimits(norm_email, chk_token, pay_token, open_chk, open_pay)

    # ── Ledger (what this wallet has already signed or synced) ────────────

    def _read_ledger(self) -> Dict[str, Any]:
        path = self.dir / LEDGER_FILE
        if not path.exists():
            return {"open_payment_mandates": {}}
        data = _read_json(path, "wallet ledger")
        if not isinstance(data, dict) or not isinstance(data.get("open_payment_mandates"), dict):
            raise WalletRefusal("WALLET_FILE_UNREADABLE", "ledger.json is malformed.")
        return data

    def _usage(self, payment_key: str, exclude_checkout_hash: Optional[str] = None) -> Tuple[int, int]:
        """Returns (total_cents, uses) already signed or renewed against an open payment mandate."""
        mandate_entry = self._read_ledger()["open_payment_mandates"].get(payment_key, {})
        if not isinstance(mandate_entry, dict):
            raise WalletRefusal("WALLET_FILE_UNREADABLE", "ledger.json mandate entry is malformed.")
        signed = mandate_entry.get("signed", {})
        renewals = mandate_entry.get("renewals", {})
        if not isinstance(signed, dict) or not isinstance(renewals, dict):
            raise WalletRefusal("WALLET_FILE_UNREADABLE", "ledger.json signed/renewals entries are malformed.")
        total, uses = 0, 0
        for chk_hash, entry in signed.items():
            if chk_hash == exclude_checkout_hash:
                continue
            amount = entry.get("amount_cents") if isinstance(entry, dict) else None
            if not isinstance(amount, int) or isinstance(amount, bool):
                raise WalletRefusal("WALLET_FILE_UNREADABLE", "ledger.json has a non-integer amount.")
            total += amount
            uses += 1
        for _sale_id, entry in renewals.items():
            amount = entry.get("amount_cents") if isinstance(entry, dict) else None
            if not isinstance(amount, int) or isinstance(amount, bool):
                raise WalletRefusal("WALLET_FILE_UNREADABLE", "ledger.json has a non-integer renewal amount.")
            total += amount
            uses += 1
        return total, uses

    def _renewal_usage(self, payment_key: str) -> Tuple[int, int]:
        """Returns (renewal_cents, renewal_count) recorded from verified merchant renewal receipts."""
        mandate_entry = self._read_ledger()["open_payment_mandates"].get(payment_key, {})
        renewals = mandate_entry.get("renewals", {}) if isinstance(mandate_entry, dict) else {}
        if not isinstance(renewals, dict):
            raise WalletRefusal("WALLET_FILE_UNREADABLE", "ledger.json renewals entry is malformed.")
        total, count = 0, 0
        for _sale_id, entry in renewals.items():
            amount = entry.get("amount_cents") if isinstance(entry, dict) else None
            if not isinstance(amount, int) or isinstance(amount, bool):
                raise WalletRefusal("WALLET_FILE_UNREADABLE", "ledger.json has a non-integer renewal amount.")
            total += amount
            count += 1
        return total, count

    def _write_ledger(self, ledger: Dict[str, Any]) -> None:
        tmp = self.dir / (LEDGER_FILE + ".tmp")
        tmp.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
        os.replace(tmp, self.dir / LEDGER_FILE)

    def _record(self, payment_key: str, checkout_hash: str, amount_cents: int) -> None:
        ledger = self._read_ledger()
        entry = ledger["open_payment_mandates"].setdefault(payment_key, {"signed": {}})
        entry.setdefault("signed", {})[checkout_hash] = {
            "amount_cents": amount_cents,
            "signed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        self._write_ledger(ledger)

    # ── Tools ──────────────────────────────────────────────────────────────

    def describe_limits(self) -> Dict[str, Any]:
        """Returns the verified owner limits and how much of them this wallet has already used."""
        lim = self._load_limits()
        amount = _constraint(lim.payment.constraints, AmountRange)
        budget = _constraint(lim.payment.constraints, Budget)
        payees = _constraint(lim.payment.constraints, AllowedPayees)
        line_items = _constraint(lim.checkout.constraints, LineItems)
        recurrence = [c for c in lim.payment.constraints if isinstance(c, AgentRecurrence)]

        budget_cents = int(budget.max * 100)  # same conversion the SDK's BudgetEvaluator uses
        used_cents, used_count = self._usage(lim.payment_key)
        renewal_cents, renewal_count = self._renewal_usage(lim.payment_key)
        tiers = sorted({
            item.id
            for req in line_items.items
            for item in (req.acceptable_items or [])
            if getattr(item, "id", None)
        })
        return {
            "status": "AUTHORIZED",
            "buyer_email": lim.buyer_email,
            "currency": amount.currency,
            "max_price_per_purchase_cents": amount.max,
            "monthly_budget_cap": round(amount.max / 100, 2),
            "total_budget_cents": budget_cents,
            "signed_so_far_cents": used_cents,
            "remaining_budget_cents": max(budget_cents - used_cents, 0),
            "purchases_signed": used_count,
            "renewals_recorded": renewal_count,
            "renewal_spend_cents": renewal_cents,
            "max_purchases": recurrence[0].max_occurrences if recurrence else None,
            "recurrence": getattr(recurrence[0].frequency, "value", recurrence[0].frequency) if recurrence else None,
            "allowed_merchants": [p.id for p in payees.allowed],
            "allowed_tiers": tiers,
            # New purchases need the short-lived checkout mandate; renewals run on the payment mandate's term
            "purchase_window_expires_at": datetime.datetime.fromtimestamp(lim.checkout.exp, tz=datetime.timezone.utc).isoformat(),
            "billing_term_expires_at": datetime.datetime.fromtimestamp(lim.payment.exp, tz=datetime.timezone.utc).isoformat(),
            "how_to_buy": (
                "1) Call the seller's negotiate_tier_terms with buyer_email and monthly_budget_cap from these limits. "
                "2) Optionally pass the returned checkout_jwt to preview_checkout to dry-run constraint checks without reserving budget. "
                "3) Pass the returned checkout_jwt to this wallet's sign_checkout. "
                "4) Call the seller's purchase_subscription with offer_id, buyer_email, "
                "checkout_mandate_chain and payment_mandate_chain."
            ),
        }

    @staticmethod
    def _format_cents(cents: int) -> str:
        return f"${cents / 100:.2f}"

    @classmethod
    def _format_checkout_violation(
        cls, violations: List[str], checkout: Checkout, lim: _OwnerLimits
    ) -> str:
        formatted = []
        for v in violations:
            if "Merchant" in v and "not allowed" in v:
                m_name = (checkout.merchant.name if checkout.merchant else None) or (checkout.merchant.id if checkout.merchant else "unknown")
                formatted.append(f"Merchant '{m_name}' is not in the owner's allowed merchant list.")
            elif "line_items" in v or "line item" in v:
                tier_id = checkout.line_items[0].item.id if (checkout.line_items and checkout.line_items[0].item) else "unknown"
                formatted.append(f"Plan '{tier_id}' is not in the owner's allowed plans list.")
            else:
                formatted.append(v)
        return "; ".join(formatted)

    @classmethod
    def _format_payment_violation(
        cls,
        violations: List[str],
        total_cents: int,
        lim: _OwnerLimits,
        used_cents: int,
        used_count: int,
    ) -> str:
        formatted = []
        for v in violations:
            # 1. AmountRange: Amount <amt> exceeds maximum <max>
            m_max = re.search(r"Amount (\d+) exceeds maximum (\d+)", v)
            if m_max:
                amt = int(m_max.group(1))
                max_cents = int(m_max.group(2))
                formatted.append(f"{cls._format_cents(amt)} exceeds the owner's {cls._format_cents(max_cents)} per-purchase limit")
                continue

            # 2. AmountRange below min: Amount <amt> below minimum <min>
            m_min = re.search(r"Amount (\d+) below minimum (\d+)", v)
            if m_min:
                amt = int(m_min.group(1))
                min_cents = int(m_min.group(2))
                formatted.append(f"{cls._format_cents(amt)} is below the owner's {cls._format_cents(min_cents)} minimum amount")
                continue

            # 3. Budget cumulative spend: Cumulative spend <cum> exceeds budget limit <limit> (past spend: <past>)
            m_cum = re.search(r"Cumulative spend (\d+) exceeds budget limit (\d+) \(past spend: (\d+)\)", v)
            if m_cum:
                budget_limit = int(m_cum.group(2))
                past_spend = int(m_cum.group(3))
                remaining = max(0, budget_limit - past_spend)
                formatted.append(
                    f"{cls._format_cents(total_cents)} exceeds the remaining budget of "
                    f"{cls._format_cents(remaining)} ({cls._format_cents(budget_limit)} limit, "
                    f"{cls._format_cents(past_spend)} already spent)"
                )
                continue

            # 4. Payee not allowed
            if "Payee" in v or "payee" in v:
                formatted.append(f"Payee is not in the owner's allowed payee list: {v}")
                continue

            formatted.append(v)
        return "; ".join(formatted)

    def _evaluate_checkout(
        self, checkout_jwt: Any
    ) -> Tuple[_OwnerLimits, Checkout, str, int, str, str, str, PaymentMandate, int, int]:
        """
        Runs the full verification and constraint evaluation pipeline without signing or mutating ledger.json:
          1. Owner limits: signature, expiry, agent binding, required constraints
          2. Merchant checkout: signature with the pinned merchant key, then structure
          3. Owner constraints, evaluated by the vendored AP2 SDK
        """
        if not isinstance(checkout_jwt, str) or not checkout_jwt.strip():
            raise WalletRefusal("MISSING_CHECKOUT_JWT", "checkout_jwt (from negotiate_tier_terms) is required.")
        checkout_jwt = checkout_jwt.strip()

        # 1. Owner limits: signature, expiry, agent binding, required constraints
        lim = self._load_limits()

        # 2. Merchant checkout: signature with the pinned merchant key, then structure
        merchant_pub, pinned_merchant_id = self._resolve_merchant_key(checkout_jwt)
        try:
            chk_payload = verify_jwt(checkout_jwt, merchant_pub)
        except Exception as e:
            raise WalletRefusal(
                "CHECKOUT_SIGNATURE_INVALID",
                f"Checkout JWT is not signed by the pinned merchant key: {e}",
            )
        if not isinstance(chk_payload, dict):
            raise WalletRefusal("CHECKOUT_MALFORMED", "Checkout JWT payload is not an object.")
        try:
            checkout = Checkout.model_validate(chk_payload)
        except Exception as e:
            raise WalletRefusal("CHECKOUT_MALFORMED", f"Checkout JWT payload is not a valid Checkout: {e}")

        nonce = chk_payload.get("nonce")
        if not isinstance(nonce, str) or not nonce:
            raise WalletRefusal("CHECKOUT_MALFORMED", "Checkout has no merchant nonce.")
        if checkout.merchant is None or not checkout.merchant.id:
            raise WalletRefusal("CHECKOUT_MALFORMED", "Checkout has no merchant id.")
        if pinned_merchant_id is not None and checkout.merchant.id != pinned_merchant_id:
            raise WalletRefusal(
                "CHECKOUT_SIGNATURE_INVALID",
                f"Checkout merchant '{checkout.merchant.id}' does not match pinned merchant '{pinned_merchant_id}'.",
            )
        if not checkout.currency:
            raise WalletRefusal("CHECKOUT_MALFORMED", "Checkout has no currency.")
        if len(checkout.line_items or []) != 1:
            raise WalletRefusal("CHECKOUT_MALFORMED", "Checkout must contain exactly one line item.")
        totals = [t for t in (checkout.totals or []) if t.type == "total"]
        if len(totals) != 1 or not isinstance(totals[0].amount, int) or totals[0].amount <= 0:
            raise WalletRefusal("CHECKOUT_MALFORMED", "Checkout must carry exactly one positive integer 'total'.")
        total_cents = totals[0].amount
        tier_id = checkout.line_items[0].item.id
        merchant_id = checkout.merchant.id
        checkout_hash = _sha256_hex(checkout_jwt)

        # 3. Owner constraints, evaluated by the vendored AP2 SDK
        try:
            chk_violations = check_checkout_constraints(lim.checkout, checkout)
        except Exception as e:
            raise WalletRefusal("CONSTRAINT_EVALUATION_FAILED", f"Could not evaluate checkout constraints: {e}")
        if chk_violations:
            raw_reason = "; ".join(chk_violations)
            msg = self._format_checkout_violation(chk_violations, checkout, lim)
            allowed_merchants = [m.id for m in _constraint(lim.checkout.constraints, AllowedMerchants).allowed]
            allowed_tiers = sorted({
                item.id
                for req in _constraint(lim.checkout.constraints, LineItems).items
                for item in (req.acceptable_items or [])
                if getattr(item, "id", None)
            })
            raise WalletRefusal(
                "CHECKOUT_CONSTRAINT_VIOLATION",
                raw_reason,
                message=msg,
                escalation={
                    "requires_human_approval": True,
                    "action": "APPROVE_CHECKOUT_EXCEPTION",
                    "buyer_email": lim.buyer_email,
                    "requested_merchant_id": merchant_id,
                    "requested_tier_id": tier_id,
                    "requested_amount_cents": total_cents,
                    "allowed_merchants": allowed_merchants,
                    "allowed_tiers": allowed_tiers,
                },
            )

        closed_pay = PaymentMandate(
            vct="mandate.payment.1",
            transaction_id=checkout_hash,
            payment_amount=Amount(amount=total_cents, currency=checkout.currency),
            payee=Merchant(id=merchant_id, name=checkout.merchant.name),
            payment_instrument=PAYMENT_INSTRUMENT,
        )
        # Re-signing the same checkout (a retry) must not count twice against the budget
        used_cents, used_count = self._usage(lim.payment_key, exclude_checkout_hash=checkout_hash)
        try:
            pay_violations = check_payment_constraints(
                lim.payment,
                closed_pay,
                open_checkout_hash=checkout_hash,
                mandate_context=MandateContext(total_amount=used_cents, total_uses=used_count),
            )
        except Exception as e:
            raise WalletRefusal("CONSTRAINT_EVALUATION_FAILED", f"Could not evaluate payment constraints: {e}")
        if pay_violations:
            raw_reason = "; ".join(pay_violations)
            msg = self._format_payment_violation(pay_violations, total_cents, lim, used_cents, used_count)
            amount_range = _constraint(lim.payment.constraints, AmountRange)
            budget_constraint = _constraint(lim.payment.constraints, Budget)
            payees_constraint = _constraint(lim.payment.constraints, AllowedPayees)
            recurrence = [c for c in lim.payment.constraints if isinstance(c, AgentRecurrence)]
            max_occurrences = recurrence[0].max_occurrences if recurrence else None
            budget_limit_cents = int(budget_constraint.max * 100)
            remaining_budget_cents = max(budget_limit_cents - used_cents, 0)
            per_purchase_shortfall_cents = max(total_cents - amount_range.max, 0)
            budget_shortfall_cents = max((used_cents + total_cents) - budget_limit_cents, 0)
            occurrences_shortfall = (
                max((used_count + 1) - max_occurrences, 0) if max_occurrences is not None else 0
            )
            raise WalletRefusal(
                "PAYMENT_CONSTRAINT_VIOLATION",
                raw_reason,
                message=msg,
                escalation={
                    "requires_human_approval": True,
                    "action": "INCREASE_SPENDING_LIMITS",
                    "buyer_email": lim.buyer_email,
                    "requested_merchant_id": merchant_id,
                    "requested_tier_id": tier_id,
                    "requested_amount_cents": total_cents,
                    "current_max_per_purchase_cents": amount_range.max,
                    "required_max_per_purchase_cents": max(amount_range.max, total_cents),
                    "per_purchase_shortfall_cents": per_purchase_shortfall_cents,
                    "current_total_budget_cents": budget_limit_cents,
                    "required_total_budget_cents": max(budget_limit_cents, used_cents + total_cents),
                    "budget_shortfall_cents": budget_shortfall_cents,
                    "remaining_budget_cents": remaining_budget_cents,
                    "purchases_used": used_count,
                    "max_purchases": max_occurrences,
                    "occurrences_shortfall": occurrences_shortfall,
                    "allowed_payees": [p.id for p in payees_constraint.allowed],
                },
            )

        return (
            lim,
            checkout,
            nonce,
            total_cents,
            tier_id,
            merchant_id,
            checkout_hash,
            closed_pay,
            used_cents,
            used_count,
        )

    def preview_checkout(self, checkout_jwt: Any) -> Dict[str, Any]:
        """
        Read-only pre-flight ("paper-trading") check: verifies a merchant-signed Checkout JWT
        against the owner's limits and AP2 constraints without signing or reserving budget in ledger.json.
        """
        (
            lim,
            checkout,
            _nonce,
            total_cents,
            tier_id,
            merchant_id,
            checkout_hash,
            _closed_pay,
            used_cents,
            used_count,
        ) = self._evaluate_checkout(checkout_jwt)

        budget = _constraint(lim.payment.constraints, Budget)
        budget_cents = int(budget.max * 100)
        recurrence = [c for c in lim.payment.constraints if isinstance(c, AgentRecurrence)]
        max_purchases = recurrence[0].max_occurrences if recurrence else None
        signed_map = self._read_ledger()["open_payment_mandates"].get(lim.payment_key, {}).get("signed", {})
        already_signed = isinstance(signed_map, dict) and checkout_hash in signed_map
        actual_before_cents, actual_before_count = self._usage(lim.payment_key)
        projected_used_cents = used_cents + total_cents
        projected_used_count = used_count + 1

        return {
            "status": "WOULD_SIGN",
            "dry_run": True,
            "buyer_email": lim.buyer_email,
            "merchant_id": merchant_id,
            "tier_id": tier_id,
            "amount_cents": total_cents,
            "currency": checkout.currency,
            "checkout_hash": checkout_hash,
            "already_signed": already_signed,
            "budget_impact": {
                "total_budget_cents": budget_cents,
                "signed_before_cents": actual_before_cents,
                "signed_after_cents": projected_used_cents,
                "remaining_after_cents": max(budget_cents - projected_used_cents, 0),
                "purchases_before": actual_before_count,
                "purchases_after": projected_used_count,
                "max_purchases": max_purchases,
            },
            "next_step": (
                "Call sign_checkout with the same checkout_jwt to cryptographically sign "
                "the AP2 v0.2 checkout_mandate_chain and payment_mandate_chain."
            ),
        }

    def sign_checkout(self, checkout_jwt: Any, dry_run: bool = False) -> Dict[str, Any]:
        """
        Verifies a merchant-signed Checkout JWT against the owner's limits and, only if every
        check passes, signs the closed Checkout and Payment mandates with the agent key.
        If dry_run=True, performs the exact same verification without signing or reserving budget.
        """
        if not isinstance(dry_run, bool):
            raise WalletRefusal("INVALID_ARGUMENT", "dry_run must be a boolean.")
        if dry_run:
            return self.preview_checkout(checkout_jwt)

        (
            lim,
            checkout,
            nonce,
            total_cents,
            tier_id,
            merchant_id,
            checkout_hash,
            closed_pay,
            _used_cents,
            _used_count,
        ) = self._evaluate_checkout(checkout_jwt)

        # 4. Every check passed: sign with the agent key only
        agent_key = self._agent_key()
        closed_chk = CheckoutMandate(
            vct="mandate.checkout.1",
            checkout_jwt=checkout_jwt.strip(),
            checkout_hash=checkout_hash,
        )
        try:
            checkout_chain = self._client.present(
                holder_key=agent_key,
                mandate_token=lim.checkout_token,
                payloads=[closed_chk],
                aud=merchant_id,
                nonce=nonce,
            )
            payment_chain = self._client.present(
                holder_key=agent_key,
                mandate_token=lim.payment_token,
                payloads=[closed_pay],
                aud=merchant_id,
                nonce=nonce,
            )
        except Exception as e:
            raise WalletRefusal("SIGNING_FAILED", f"Could not sign closed mandates: {e}")

        self._record(lim.payment_key, checkout_hash, total_cents)

        return {
            "status": "SIGNED",
            "buyer_email": lim.buyer_email,
            "merchant_id": merchant_id,
            "tier_id": tier_id,
            "amount_cents": total_cents,
            "currency": checkout.currency,
            "checkout_hash": checkout_hash,
            "checkout_mandate_chain": checkout_chain,
            "payment_mandate_chain": payment_chain,
            "next_step": (
                "Call the seller's purchase_subscription with offer_id (from negotiate_tier_terms), "
                "buyer_email, checkout_mandate_chain and payment_mandate_chain."
            ),
        }

    def record_renewal_receipt(self, renewal_receipt_jwt: Any) -> Dict[str, Any]:
        """
        Verifies a merchant-signed AP2 renewal receipt JWT (ap2.renewal_receipt.1) against the
        pinned merchant key and the owner's payment mandate constraints, then records the renewal
        idempotently in ledger.json so get_spending_limits and sign_checkout reflect recurring charges.
        """
        if not isinstance(renewal_receipt_jwt, str) or not renewal_receipt_jwt.strip():
            raise WalletRefusal("MISSING_RENEWAL_RECEIPT", "renewal_receipt_jwt is required.")
        renewal_receipt_jwt = renewal_receipt_jwt.strip()

        # 1. Owner limits: signature, payment-term expiry, agent binding, required constraints
        lim = self._load_limits(require_unexpired_checkout=False)

        # 2. Merchant signature verification against pinned merchant key
        merchant_pub, pinned_merchant_id = self._resolve_merchant_key(renewal_receipt_jwt)
        try:
            payload = verify_jwt(renewal_receipt_jwt, merchant_pub)
        except Exception as e:
            raise WalletRefusal(
                "RECEIPT_SIGNATURE_INVALID",
                f"Renewal receipt JWT is not signed by the pinned merchant key: {e}",
            )
        if not isinstance(payload, dict):
            raise WalletRefusal("RECEIPT_MALFORMED", "Renewal receipt JWT payload is not an object.")

        if payload.get("vct") != "ap2.renewal_receipt.1":
            raise WalletRefusal("RECEIPT_MALFORMED", "Renewal receipt must carry vct 'ap2.renewal_receipt.1'.")

        iss = payload.get("iss")
        if not isinstance(iss, str) or not iss.strip():
            raise WalletRefusal("RECEIPT_MALFORMED", "Renewal receipt has no merchant 'iss'.")
        iss = iss.strip()
        if pinned_merchant_id is not None and iss != pinned_merchant_id:
            raise WalletRefusal(
                "RECEIPT_SIGNATURE_INVALID",
                f"Renewal receipt issuer '{iss}' does not match pinned merchant '{pinned_merchant_id}'.",
            )

        sub = payload.get("sub")
        expected_email_hash = _sha256_hex(lim.buyer_email)
        if not isinstance(sub, str) or sub.strip().lower() not in (lim.buyer_email, expected_email_hash):
            raise WalletRefusal(
                "RECEIPT_MANDATE_MISMATCH",
                f"Renewal receipt buyer subject '{sub}' does not match wallet owner '{lim.buyer_email}'.",
            )

        mandate_hash = payload.get("mandate_hash")
        if not isinstance(mandate_hash, str) or mandate_hash.strip() not in (lim.payment_key, lim.canonical_payment_hash):
            raise WalletRefusal(
                "RECEIPT_MANDATE_MISMATCH",
                "Renewal receipt mandate_hash does not match this wallet's open payment mandate.",
            )

        sale_id = payload.get("sale_id")
        if not isinstance(sale_id, str) or not sale_id.strip():
            raise WalletRefusal("RECEIPT_MALFORMED", "Renewal receipt has no sale_id.")
        sale_id = sale_id.strip()

        subscription_id = payload.get("subscription_id")
        if not isinstance(subscription_id, str) or not subscription_id.strip():
            raise WalletRefusal("RECEIPT_MALFORMED", "Renewal receipt has no subscription_id.")
        subscription_id = subscription_id.strip()

        outcome = payload.get("outcome")
        if outcome not in ("INITIAL", "VERIFIED"):
            raise WalletRefusal("RECEIPT_MALFORMED", "Renewal receipt outcome must be 'INITIAL' or 'VERIFIED'.")

        amount_cents = payload.get("amount_cents")
        if not isinstance(amount_cents, int) or isinstance(amount_cents, bool) or amount_cents <= 0:
            raise WalletRefusal("RECEIPT_MALFORMED", "Renewal receipt must carry a positive integer 'amount_cents'.")

        amount_range = _constraint(lim.payment.constraints, AmountRange)
        currency = payload.get("currency")
        if not isinstance(currency, str) or currency != amount_range.currency:
            raise WalletRefusal(
                "RECEIPT_MALFORMED",
                f"Renewal receipt currency '{currency}' does not match mandate currency '{amount_range.currency}'.",
            )

        payees_constraint = _constraint(lim.payment.constraints, AllowedPayees)
        allowed_payees = [p.id for p in payees_constraint.allowed]
        if iss not in allowed_payees:
            raise WalletRefusal(
                "PAYMENT_CONSTRAINT_VIOLATION",
                f"Payee {iss} not in allowed list",
                message=f"Payee is not in the owner's allowed payee list: Payee {iss} not in allowed list",
            )

        charged_at_raw = payload.get("charged_at")
        if not isinstance(charged_at_raw, str) or not charged_at_raw.strip():
            raise WalletRefusal("RECEIPT_MALFORMED", "Renewal receipt has no charged_at timestamp.")
        try:
            charged_at_dt = datetime.datetime.fromisoformat(charged_at_raw.strip().replace("Z", "+00:00"))
        except ValueError as e:
            raise WalletRefusal(
                "RECEIPT_MALFORMED",
                f"Renewal receipt charged_at is not a valid ISO-8601 timestamp: {e}",
            )
        if charged_at_dt.tzinfo is None:
            charged_at_dt = charged_at_dt.replace(tzinfo=datetime.timezone.utc)
        charged_at = charged_at_dt.isoformat()
        if lim.payment.exp <= charged_at_dt.timestamp():
            raise WalletRefusal(
                "OWNER_LIMITS_EXPIRED",
                "Open payment mandate had expired when the renewal was charged; ask the owner to sign new limits.",
                escalation={
                    "requires_human_approval": True,
                    "action": "REAUTHORIZE_EXPIRED_LIMITS",
                    "buyer_email": lim.buyer_email,
                    "mandate_type": "payment",
                    "expired_at": datetime.datetime.fromtimestamp(
                        lim.payment.exp, tz=datetime.timezone.utc
                    ).isoformat(),
                },
            )

        ledger = self._read_ledger()
        entry = ledger["open_payment_mandates"].setdefault(lim.payment_key, {"signed": {}})
        signed_map = entry.setdefault("signed", {})
        renewals = entry.setdefault("renewals", {})
        initial_sales = entry.setdefault("initial_sales", {})

        if not isinstance(signed_map, dict) or not signed_map:
            raise WalletRefusal(
                "NO_SIGNED_CHECKOUT",
                "Cannot record a renewal receipt before this wallet has signed an initial checkout.",
            )

        if outcome == "INITIAL":
            if sale_id in renewals:
                raise WalletRefusal(
                    "RECEIPT_CONFLICT",
                    f"Sale '{sale_id}' is already recorded as a renewal; cannot reclassify as INITIAL.",
                )
            signed_amounts = {
                s_entry.get("amount_cents")
                for s_entry in signed_map.values()
                if isinstance(s_entry, dict)
            }
            if amount_cents not in signed_amounts:
                raise WalletRefusal(
                    "RECEIPT_AMOUNT_MISMATCH",
                    f"Initial sale amount ({amount_cents} cents) does not match any checkout signed by this wallet.",
                )
            existing_init = initial_sales.get(sale_id)
            if isinstance(existing_init, dict):
                if (
                    existing_init.get("amount_cents") != amount_cents
                    or existing_init.get("subscription_id") != subscription_id
                ):
                    raise WalletRefusal(
                        "RECEIPT_CONFLICT",
                        f"Sale '{sale_id}' is already recorded with different amount or subscription_id.",
                    )
            else:
                # Initial charge is already reserved in `signed` at checkout signing time; bind without double-counting
                initial_sales[sale_id] = {
                    "subscription_id": subscription_id,
                    "amount_cents": amount_cents,
                    "currency": currency,
                    "charged_at": charged_at,
                }
                self._write_ledger(ledger)
        else:
            if sale_id in initial_sales:
                raise WalletRefusal(
                    "RECEIPT_CONFLICT",
                    f"Sale '{sale_id}' is already recorded as an INITIAL sale; cannot record again as a renewal.",
                )
            existing_ren = renewals.get(sale_id)
            if isinstance(existing_ren, dict):
                if (
                    existing_ren.get("amount_cents") != amount_cents
                    or existing_ren.get("subscription_id") != subscription_id
                ):
                    raise WalletRefusal(
                        "RECEIPT_CONFLICT",
                        f"Renewal sale '{sale_id}' is already recorded with different amount or subscription_id.",
                    )
            else:
                used_cents, used_count = self._usage(lim.payment_key)
                candidate = PaymentMandate(
                    vct="mandate.payment.1",
                    transaction_id=sale_id,
                    payment_amount=Amount(amount=amount_cents, currency=currency),
                    payee=Merchant(id=iss, name=iss),
                    payment_instrument=PAYMENT_INSTRUMENT,
                )
                try:
                    pay_violations = check_payment_constraints(
                        lim.payment,
                        candidate,
                        mandate_context=MandateContext(total_amount=used_cents, total_uses=used_count),
                    )
                except Exception as e:
                    raise WalletRefusal("CONSTRAINT_EVALUATION_FAILED", f"Could not evaluate payment constraints: {e}")
                if pay_violations:
                    raw_reason = "; ".join(pay_violations)
                    msg = self._format_payment_violation(pay_violations, amount_cents, lim, used_cents, used_count)
                    budget_constraint = _constraint(lim.payment.constraints, Budget)
                    recurrence = [c for c in lim.payment.constraints if isinstance(c, AgentRecurrence)]
                    max_occurrences = recurrence[0].max_occurrences if recurrence else None
                    budget_limit_cents = int(budget_constraint.max * 100)
                    remaining_budget_cents = max(budget_limit_cents - used_cents, 0)
                    per_purchase_shortfall_cents = max(amount_cents - amount_range.max, 0)
                    budget_shortfall_cents = max((used_cents + amount_cents) - budget_limit_cents, 0)
                    occurrences_shortfall = (
                        max((used_count + 1) - max_occurrences, 0) if max_occurrences is not None else 0
                    )
                    raise WalletRefusal(
                        "PAYMENT_CONSTRAINT_VIOLATION",
                        raw_reason,
                        message=msg,
                        escalation={
                            "requires_human_approval": True,
                            "action": "INCREASE_SPENDING_LIMITS",
                            "buyer_email": lim.buyer_email,
                            "requested_merchant_id": iss,
                            "requested_amount_cents": amount_cents,
                            "current_max_per_purchase_cents": amount_range.max,
                            "required_max_per_purchase_cents": max(amount_range.max, amount_cents),
                            "per_purchase_shortfall_cents": per_purchase_shortfall_cents,
                            "current_total_budget_cents": budget_limit_cents,
                            "required_total_budget_cents": max(budget_limit_cents, used_cents + amount_cents),
                            "budget_shortfall_cents": budget_shortfall_cents,
                            "remaining_budget_cents": remaining_budget_cents,
                            "purchases_used": used_count,
                            "max_purchases": max_occurrences,
                            "occurrences_shortfall": occurrences_shortfall,
                            "allowed_payees": allowed_payees,
                        },
                    )

                renewals[sale_id] = {
                    "subscription_id": subscription_id,
                    "amount_cents": amount_cents,
                    "currency": currency,
                    "charged_at": charged_at,
                }
                self._write_ledger(ledger)

        budget = _constraint(lim.payment.constraints, Budget)
        budget_cents = int(budget.max * 100)
        used_cents, used_count = self._usage(lim.payment_key)
        renewal_cents, renewal_count = self._renewal_usage(lim.payment_key)

        return {
            "status": "RECORDED",
            "outcome": outcome,
            "sale_id": sale_id,
            "subscription_id": subscription_id,
            "amount_cents": amount_cents,
            "currency": currency,
            "signed_so_far_cents": used_cents,
            "remaining_budget_cents": max(budget_cents - used_cents, 0),
            "purchases_signed": used_count,
            "renewals_recorded": renewal_count,
            "renewal_spend_cents": renewal_cents,
        }
