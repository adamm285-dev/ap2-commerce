"""
AP2 v0.2 Buyer Wallet.

The wallet is the buyer agent's signing boundary. It runs as its own process (for example
as a second MCP server next to the seller in Claude Desktop) and holds exactly one private
key: the buyer agent's own P-256 key. It never holds the owner's key or the merchant's key.

Inputs it trusts, all local files written at setup time:
  - owner_limits.json:    owner-signed AP2 v0.2 Open Checkout and Open Payment mandates
  - owner_public.jwk:     the owner's pinned public key (verifies owner_limits.json)
  - merchant_public.jwk:  the merchant's pinned public key (verifies Checkout JWTs)

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
against the existing reservation without double-counting.

This module deliberately imports nothing from the seller side (agents, services, database).
"""

from __future__ import annotations

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
LEDGER_FILE = "ledger.json"

PAYMENT_INSTRUMENT = PaymentInstrument(type="paypal_vault", id="vault_agent_mit")


class WalletRefusal(Exception):
    """The wallet refused to act. `code` is stable and machine-readable."""

    def __init__(self, code: str, reason: str, message: Optional[str] = None):
        msg = message or reason
        super().__init__(f"{code}: {msg}")
        self.code = code
        self.reason = reason
        self.message = msg

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": "REFUSED",
            "error": self.code,
            "reason": self.reason,
            "message": self.message,
        }


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


def _load_key(path: Path, what: str, private: bool) -> JWK:
    data = _read_json(path, what)
    if not isinstance(data, dict):
        raise WalletRefusal("WALLET_FILE_UNREADABLE", f"{what} ({path.name}) is not a JWK object.")
    try:
        key = JWK(**data)
        pub = key.export_public(as_dict=True)
    except Exception as e:
        raise WalletRefusal("WALLET_FILE_UNREADABLE", f"{what} ({path.name}) is not a valid JWK: {e}")
    if pub.get("kty") != "EC" or pub.get("crv") != "P-256":
        raise WalletRefusal("WALLET_FILE_UNREADABLE", f"{what} ({path.name}) must be a P-256 key.")
    if private and not key.has_private:
        raise WalletRefusal("WALLET_FILE_UNREADABLE", f"{what} ({path.name}) has no private part.")
    if not private and key.has_private:
        # A pinned key file with private material means another party's secret leaked into the wallet.
        raise WalletRefusal(
            "PINNED_KEY_HAS_PRIVATE_PART",
            f"{what} ({path.name}) contains a private key. The wallet must only hold public keys for other parties.",
        )
    return key


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


class BuyerWallet:
    def __init__(self, directory: Optional[Path] = None):
        self.dir = Path(directory) if directory else wallet_dir()
        self._client = MandateClient()

    # ── Loading & verification ────────────────────────────────────────────

    def _agent_key(self) -> JWK:
        return _load_key(self.dir / AGENT_KEY_FILE, "buyer agent key", private=True)

    def _load_limits(self) -> _OwnerLimits:
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
        for label, payload in (("checkout", open_chk), ("payment", open_pay)):
            if not isinstance(payload.exp, int):
                raise WalletRefusal("OWNER_LIMITS_EXPIRED", f"Open {label} mandate has no expiry.")
            if payload.exp <= now:
                raise WalletRefusal("OWNER_LIMITS_EXPIRED", f"Open {label} mandate expired; ask the owner to sign new limits.")
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

        return _OwnerLimits(buyer_email.strip().lower(), chk_token, pay_token, open_chk, open_pay)

    # ── Ledger (what this wallet has already signed) ──────────────────────

    def _read_ledger(self) -> Dict[str, Any]:
        path = self.dir / LEDGER_FILE
        if not path.exists():
            return {"open_payment_mandates": {}}
        data = _read_json(path, "wallet ledger")
        if not isinstance(data, dict) or not isinstance(data.get("open_payment_mandates"), dict):
            raise WalletRefusal("WALLET_FILE_UNREADABLE", "ledger.json is malformed.")
        return data

    def _usage(self, payment_key: str, exclude_checkout_hash: Optional[str] = None) -> Tuple[int, int]:
        """Returns (total_cents, uses) already signed against an open payment mandate."""
        signed = self._read_ledger()["open_payment_mandates"].get(payment_key, {}).get("signed", {})
        total, uses = 0, 0
        for chk_hash, entry in signed.items():
            if chk_hash == exclude_checkout_hash:
                continue
            amount = entry.get("amount_cents") if isinstance(entry, dict) else None
            if not isinstance(amount, int) or isinstance(amount, bool):
                raise WalletRefusal("WALLET_FILE_UNREADABLE", "ledger.json has a non-integer amount.")
            total += amount
            uses += 1
        return total, uses

    def _record(self, payment_key: str, checkout_hash: str, amount_cents: int) -> None:
        ledger = self._read_ledger()
        entry = ledger["open_payment_mandates"].setdefault(payment_key, {"signed": {}})
        entry["signed"][checkout_hash] = {
            "amount_cents": amount_cents,
            "signed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        tmp = self.dir / (LEDGER_FILE + ".tmp")
        tmp.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
        os.replace(tmp, self.dir / LEDGER_FILE)

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
            "max_purchases": recurrence[0].max_occurrences if recurrence else None,
            "recurrence": getattr(recurrence[0].frequency, "value", recurrence[0].frequency) if recurrence else None,
            "allowed_merchants": [p.id for p in payees.allowed],
            "allowed_tiers": tiers,
            # New purchases need the short-lived checkout mandate; renewals run on the payment mandate's term
            "purchase_window_expires_at": datetime.datetime.fromtimestamp(lim.checkout.exp, tz=datetime.timezone.utc).isoformat(),
            "billing_term_expires_at": datetime.datetime.fromtimestamp(lim.payment.exp, tz=datetime.timezone.utc).isoformat(),
            "how_to_buy": (
                "1) Call the seller's negotiate_tier_terms with buyer_email and monthly_budget_cap from these limits. "
                "2) Pass the returned checkout_jwt to this wallet's sign_checkout. "
                "3) Call the seller's purchase_subscription with offer_id, buyer_email, "
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

    def sign_checkout(self, checkout_jwt: Any) -> Dict[str, Any]:
        """
        Verifies a merchant-signed Checkout JWT against the owner's limits and, only if every
        check passes, signs the closed Checkout and Payment mandates with the agent key.
        """
        if not isinstance(checkout_jwt, str) or not checkout_jwt.strip():
            raise WalletRefusal("MISSING_CHECKOUT_JWT", "checkout_jwt (from negotiate_tier_terms) is required.")
        checkout_jwt = checkout_jwt.strip()

        # 1. Owner limits: signature, expiry, agent binding, required constraints
        lim = self._load_limits()

        # 2. Merchant checkout: signature with the pinned merchant key, then structure
        merchant_pub = _load_key(self.dir / MERCHANT_PUBLIC_KEY_FILE, "pinned merchant public key", private=False)
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
            raise WalletRefusal("CHECKOUT_CONSTRAINT_VIOLATION", raw_reason, message=msg)

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
            raise WalletRefusal("PAYMENT_CONSTRAINT_VIOLATION", raw_reason, message=msg)

        # 4. Every check passed: sign with the agent key only
        agent_key = self._agent_key()
        closed_chk = CheckoutMandate(
            vct="mandate.checkout.1",
            checkout_jwt=checkout_jwt,
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
