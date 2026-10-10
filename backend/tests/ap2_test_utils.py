"""
Helper utilities for creating valid AP2 v0.2 mandate chains in unit and regression tests.
"""
import os
import tempfile
import atexit
import uuid
from typing import Dict, Any, Optional, List

# Ensure isolated temp DB in test utils when run outside pytest to protect development DB
if not os.environ.get("A2A_DB_PATH"):
    _temp_test_utils_db = os.path.join(tempfile.gettempdir(), f"a2a_test_utils_{os.getpid()}_{uuid.uuid4().hex[:8]}.db")
    os.environ["A2A_DB_PATH"] = _temp_test_utils_db

    def _cleanup_test_utils_temp_db():
        for ext in ["", "-wal", "-shm", "-journal"]:
            f = _temp_test_utils_db + ext
            try:
                if os.path.exists(f):
                    os.remove(f)
            except OSError:
                pass

    atexit.register(_cleanup_test_utils_temp_db)
    from backend.database import init_db
    init_db()

from jwcrypto.jwk import JWK
from ap2.sdk.mandate import MandateClient
from ap2.sdk.generated.checkout_mandate import CheckoutMandate
from ap2.sdk.generated.payment_mandate import PaymentMandate
from ap2.sdk.generated.types.amount import Amount
from ap2.sdk.generated.types.merchant import Merchant
from ap2.sdk.generated.types.payment_instrument import PaymentInstrument

from backend.database import register_buyer_key
from backend.services.trusted_surface_service import create_trusted_surface_open_mandates
from backend.services.ap2_service import (
    create_merchant_checkout,
    AP2_MERCHANT_ID,
    AP2_MERCHANT_NAME,
)


def build_test_ap2_chains(
    tier_id: str = "ap2-batch",
    monthly_price: float = 49.99,
    buyer_email: Optional[str] = None,
    budget_cap: float = 100.0,
    yearly_budget_ceiling: Optional[float] = None,
    allowed_tiers: Optional[List[str]] = None,
    owner_key: Optional[JWK] = None,
    agent_key: Optional[JWK] = None,
    vault_id: str = "vault-test-chain",
    checkout_record: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    u = uuid.uuid4().hex[:8]
    email = buyer_email or f"test-buyer-{u}@example.com"
    if not owner_key:
        owner_key = JWK.generate(kty="EC", crv="P-256", kid=f"owner-{u}")
        register_buyer_key(
            kid=owner_key.kid,
            public_key_hex=owner_key.export_public(),
            contractor_email=email,
            business_name="Test Enterprise LLC",
        )
    if not agent_key:
        agent_key = JWK.generate(kty="EC", crv="P-256", kid=f"agent-{u}")

    tiers = allowed_tiers or ["ap2-batch", "ap2-gateway", "ap2-cluster"]
    if tier_id not in tiers:
        tiers.append(tier_id)

    yearly_cap = yearly_budget_ceiling if yearly_budget_ceiling is not None else budget_cap * 12

    limits = create_trusted_surface_open_mandates(
        buyer_email=email,
        monthly_budget_cap=budget_cap,
        yearly_budget_ceiling=yearly_cap,
        allowed_tiers=tiers,
        agent_key=agent_key,
        user_key=owner_key,
    )

    if checkout_record is None:
        chk_rec = create_merchant_checkout(
            tier_id=tier_id,
            monthly_price=monthly_price,
            contractor_email=email,
        )
    else:
        chk_rec = checkout_record

    mc = MandateClient()
    chk_chain = mc.present(
        holder_key=agent_key,
        mandate_token=limits["open_checkout_mandate_token"],
        payloads=[
            CheckoutMandate(
                vct="mandate.checkout.1",
                checkout_jwt=chk_rec["checkout_jwt"],
                checkout_hash=chk_rec["checkout_hash"],
            )
        ],
        aud=AP2_MERCHANT_ID,
        nonce=chk_rec["nonce"],
    )

    cents = int(round(monthly_price * 100))
    pay_chain = mc.present(
        holder_key=agent_key,
        mandate_token=limits["open_payment_mandate_token"],
        payloads=[
            PaymentMandate(
                vct="mandate.payment.1",
                transaction_id=chk_rec["checkout_hash"],
                payment_amount=Amount(amount=cents, currency="USD"),
                payee=Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME),
                payment_instrument=PaymentInstrument(type="paypal_vault", id=vault_id),
            )
        ],
        aud=AP2_MERCHANT_ID,
        nonce=chk_rec["nonce"],
    )

    return {
        "checkout_mandate_chain": chk_chain,
        "payment_mandate_chain": pay_chain,
        "checkout_jwt": chk_rec["checkout_jwt"],
        "checkout_hash": chk_rec["checkout_hash"],
        "nonce": chk_rec["nonce"],
        "order_id": chk_rec.get("order_id"),
        "buyer_email": email,
        "tier_id": tier_id,
        "monthly_price": monthly_price,
        "owner_key": owner_key,
        "agent_key": agent_key,
        "limits": limits,
        "chk_record": chk_rec,
    }
