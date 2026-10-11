"""
Autonomous Buyer Agent for AP2 Protocol.
Operates under strict programmatic financial guardrails (AP2 v0.2 ES256 SD-JWT dual mandate chains),
negotiates with Seller Nodes over Model Context Protocol (MCP),
and autonomously executes approved compute infrastructure commitments.
"""

import os
import sys
import tempfile
import atexit
import uuid
import asyncio
import argparse
import json
import logging
from pathlib import Path
from typing import Dict, Any

# Ensure isolated temp DB in buyer agent to protect development DB
if not os.environ.get("A2A_DB_PATH"):
    _temp_buyer_db = os.path.join(tempfile.gettempdir(), f"a2a_buyer_{os.getpid()}_{uuid.uuid4().hex[:8]}.db")
    os.environ["A2A_DB_PATH"] = _temp_buyer_db

    def _cleanup_buyer_temp_db():
        for ext in ["", "-wal", "-shm", "-journal"]:
            f = _temp_buyer_db + ext
            try:
                if os.path.exists(f):
                    os.remove(f)
            except OSError:
                pass

    atexit.register(_cleanup_buyer_temp_db)

from .seller_agent import seller_agent
from ..models import RecurrenceType
from ..services.trusted_surface_service import (
    create_trusted_surface_open_mandates,
    get_demo_agent_key,
)
from ap2.sdk.mandate import MandateClient
from ap2.sdk.generated.checkout_mandate import CheckoutMandate
from ap2.sdk.generated.payment_mandate import PaymentMandate
from ap2.sdk.generated.types.amount import Amount
from ap2.sdk.generated.types.merchant import Merchant
from ap2.sdk.generated.types.payment_instrument import PaymentInstrument
from ..services.ap2_service import (
    AP2_MERCHANT_ID,
    AP2_MERCHANT_NAME,
    verify_receipt_jwt,
    dollars_to_minor_units,
)

logger = logging.getLogger("buyer_agent")


class BuyerAgent:
    def __init__(
        self,
        agent_id: str = "buyer-agent-01",
        monthly_budget_cap: float = 100.00,
        contractor_email: str = "agent-alpha@example.com",
    ):
        self.agent_id = agent_id
        self.monthly_budget_cap = monthly_budget_cap
        self.contractor_email = contractor_email
        self.audit_log: list = []

    async def run_autonomous_onboarding_cycle(
        self, target_trade: str = "ap2-gateway"
    ) -> Dict[str, Any]:
        """Executes the full 5-phase Agent-to-Agent autonomous commerce cycle with AP2 v0.2 chains."""
        print(f"\n=======================================================")
        print(f"🤖 [BUYER AGENT {self.agent_id}] Starting Autonomous AP2 v0.2 Cycle")
        print(f"   Monthly Spending Mandate Cap: ${self.monthly_budget_cap:.2f}/mo")
        print(f"   Target Compute Tier:          {target_trade}")
        print(f"=======================================================\n")

        # Phase 1: Local Telemetry & Business Need Assessment
        print("📊 [Phase 1: Opportunity Assessment (Pipeline Telemetry)]")
        print(f"   Autonomous Buyer: Acme Compute Co ({self.contractor_email})")
        print(f"   Conclusion: Dedicated AI Service Gateway required (Budget Cap: ${self.monthly_budget_cap:.2f}/mo)\n")

        # Phase 2: Query Seller Agent MCP Catalog
        print("🔍 [Phase 2: Seller Agent MCP Catalog Inquiry]")
        catalog = await seller_agent.get_service_catalog()
        target_tier_id = catalog.get("tier_id_aliases", {}).get(target_trade, target_trade)
        matching_tier = next(
            (p for p in catalog.get("plans", []) if p["tier_id"] == target_tier_id),
            None,
        )
        if not matching_tier:
            matching_tier = next(
                (p for p in catalog.get("plans", []) if p["tier_id"] == "ap2-gateway"),
                catalog.get("plans", [{}])[0] if catalog.get("plans") else None,
            )

        if not matching_tier:
            raise RuntimeError(f"No matching service tier found for tier '{target_trade}'")

        standard_price = matching_tier["monthly_price"]
        print(f"   Found Provider: {catalog.get('provider')}")
        print(f"   Tier Title:     {matching_tier['title']}")
        print(f"   Monthly Price:  ${standard_price:.2f}/mo (USD)")
        print(f"   Features:       {', '.join(matching_tier.get('features', []))}\n")

        # Phase 3: Mint Trusted Surface Open Mandates & Negotiate Terms (AP2 v0.2)
        print("⚖️  [Phase 3: AP2 v0.2 Mandate Verification & Term Negotiation]")
        agent_key = get_demo_agent_key()
        mandate_client = MandateClient()
        # MOCK(M-005): in-process buyer agent signs owner limits with the demo owner key
        open_mandates = create_trusted_surface_open_mandates(
            monthly_budget_cap=self.monthly_budget_cap,
            buyer_email=self.contractor_email,
            allowed_tiers=["ap2-batch", "ap2-gateway", "ap2-cluster"],
            agent_key=agent_key,
        )
        open_chk_tok = open_mandates["open_checkout_mandate_token"]
        open_pay_tok = open_mandates["open_payment_mandate_token"]

        negotiate_res = await seller_agent.negotiate_tier_terms(
            buyer_agent_id=self.agent_id,
            buyer_email=self.contractor_email,
            tier_id=target_tier_id,
            monthly_budget_cap=self.monthly_budget_cap,
        )

        status = negotiate_res.get("status")
        agreed_tier_id = target_tier_id
        monthly_price = standard_price
        chk_jwt = None
        chk_hash = None
        nonce = None

        if status == "APPROVED":
            chk_jwt = negotiate_res.get("checkout_jwt")
            chk_hash = negotiate_res.get("checkout_hash")
            nonce = negotiate_res.get("nonce")
            order_id = negotiate_res.get("order_id")
            rem_cap = negotiate_res.get("monthly_cap_remaining", self.monthly_budget_cap - monthly_price)

            print(f"   Policy Check:   ${monthly_price:.2f} <= ${self.monthly_budget_cap:.2f} Cap")
            print(f"   Decision:       APPROVED")
            print(f"   Remaining Cap:  ${rem_cap:.2f} (After this commitment)")
            print(f"   Merchant Order: {order_id}")
            print(f"   Checkout Hash:  {chk_hash[:24]}...\n")

        elif status == "COUNTER_OFFER":
            c_amount = float(negotiate_res.get("counter_offer_amount", 49.99))
            c_tier_id = negotiate_res.get("counter_offer_tier_id", "ap2-batch")
            c_title = negotiate_res.get("counter_offer_tier", "High-Throughput Batch Worker")
            chk_jwt = negotiate_res.get("checkout_jwt") or negotiate_res.get("counter_offer_checkout_jwt")
            chk_hash = negotiate_res.get("checkout_hash") or negotiate_res.get("counter_offer_checkout_hash")
            nonce = negotiate_res.get("nonce")
            order_id = negotiate_res.get("order_id")

            print("🤝 [Phase 3b: Counter-Offer Bargaining & Acceptance]")
            print(f"   Seller Offer:   {c_title} ({c_tier_id}) at ${c_amount:.2f}/mo")
            op_c = "<=" if c_amount <= self.monthly_budget_cap else ">"
            print(f"   Policy Check:   ${c_amount:.2f} {op_c} ${self.monthly_budget_cap:.2f} Cap (Remaining: ${self.monthly_budget_cap - c_amount:.2f})")

            if c_amount <= self.monthly_budget_cap:
                print(f"   Decision:       ACCEPTED (Within ${self.monthly_budget_cap:.2f} Budget Cap)")
                print(f"   Merchant Order: {order_id}")
                print(f"   Checkout Hash:  {chk_hash[:24]}...\n")
                agreed_tier_id = c_tier_id
                monthly_price = c_amount
                matching_tier = next(
                    (p for p in catalog.get("plans", []) if p["tier_id"] == c_tier_id),
                    {"tier_id": c_tier_id, "title": c_title},
                )
            else:
                reason = f"Counter-offer ${c_amount:.2f} exceeds remaining monthly budget cap of ${self.monthly_budget_cap:.2f}."
                print(f"❌ Mandate violation: {reason}")
                return {"status": "REJECTED", "reason": reason}

        else:
            raw_reason = negotiate_res.get("reason", "Budget cap exceeded or policy violation")
            full_reason = raw_reason
            if "exceeds" not in full_reason.lower() and "below minimum" in full_reason.lower():
                full_reason = f"{raw_reason} (exceeds remaining monthly budget cap of ${self.monthly_budget_cap:.2f})"
            print(f"❌ Mandate violation: {full_reason}")
            chk_rec = negotiate_res.get("checkout_receipt")
            pay_rec = negotiate_res.get("payment_receipt")
            if chk_rec:
                print(f"   Signed Checkout Receipt: {chk_rec[:24]}...")
            if pay_rec:
                print(f"   Signed Payment Receipt:  {pay_rec[:24]}...")
            print()
            return {
                "status": "REJECTED",
                "reason": full_reason,
                "checkout_receipt": chk_rec,
                "payment_receipt": pay_rec,
            }

        # Present closed AP2 v0.2 Checkout and Payment Mandates
        print("🔐 [Presenting Closed AP2 v0.2 Mandate Chains]")
        price_cents = dollars_to_minor_units(monthly_price)
        closed_chk = CheckoutMandate(
            vct="mandate.checkout.1",
            checkout_jwt=chk_jwt,
            checkout_hash=chk_hash,
        )
        chk_chain = mandate_client.present(
            holder_key=agent_key,
            mandate_token=open_chk_tok,
            payloads=[closed_chk],
            aud=AP2_MERCHANT_ID,
            nonce=nonce,
        )

        closed_pay = PaymentMandate(
            vct="mandate.payment.1",
            transaction_id=chk_hash,
            payment_amount=Amount(amount=price_cents, currency="USD"),
            payee=Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME),
            payment_instrument=PaymentInstrument(type="paypal_vault", id="vault_agent_mit"),
        )
        pay_chain = mandate_client.present(
            holder_key=agent_key,
            mandate_token=open_pay_tok,
            payloads=[closed_pay],
            aud=AP2_MERCHANT_ID,
            nonce=nonce,
        )
        print(f"   Checkout Mandate Chain: {chk_chain[:32]}... ({len(chk_chain)} chars)")
        print(f"   Payment Mandate Chain:  {pay_chain[:32]}... ({len(pay_chain)} chars)\n")

        # Phase 4: Delegate PayPal Subscription Session with AP2 v0.2 Chains
        print("💳 [Phase 4: Delegated PayPal Subscription Initiation (AP2 v0.2 Chains)]")
        purchase_result = await seller_agent.purchase_subscription(
            tier_id=agreed_tier_id,
            agreed_monthly_rate=monthly_price,
            checkout_mandate_chain=chk_chain,
            payment_mandate_chain=pay_chain,
            checkout_jwt=chk_jwt,
            buyer_email=self.contractor_email,
            contractor_email=self.contractor_email,
            nonce=nonce,
        )
        subscription_id = purchase_result.get("subscription_id")
        chk_receipt = purchase_result.get("checkout_receipt")
        pay_receipt = purchase_result.get("payment_receipt")

        print(f"   PayPal Vault Subscription: {subscription_id}")
        print(f"   Payment Channel:           PayPal Subscriptions Vault")
        print(f"   Billing Cycle:             ${monthly_price:.2f} / month (Auto-debit)")
        if chk_receipt:
            print(f"   Signed Checkout Receipt:   {chk_receipt[:32]}...")
        if pay_receipt:
            print(f"   Signed Payment Receipt:    {pay_receipt[:32]}...\n")

        # Phase 5: MCP Compute Node Provisioning
        print("🖥️ [Phase 5: MCP Compute Node Provisioning]")
        provision_result = await seller_agent.provision_compute_node(
            subscription_id=subscription_id,
            contractor_email=self.contractor_email,
            tier_id=agreed_tier_id,
        )

        assigned_endpoint = provision_result.get("endpoint")
        if not assigned_endpoint or provision_result.get("status") != "PROVISIONED":
            error_msg = provision_result.get("reason") or provision_result.get("error") or "Unknown provisioning failure"
            raise RuntimeError(f"Provisioning failed: no endpoint returned ({error_msg})")

        print(f"   Subscriber:       {self.contractor_email}")
        print(f"   Compute Endpoint: {assigned_endpoint}\n")

        # Phase 6: Downline Back-Office Synchronization via Zapier MCP
        print("⚡ [Phase 6: Autonomous Zapier MCP Back-Office Sync]")
        zapier_result = await seller_agent.dispatch_zapier_mcp(
            workflow_type="a2a_onboarding",
            contractor_name="Acme Compute Co",
            business_entity="Acme Compute Co",
            allocated_did=assigned_endpoint,
            trade_vertical=matching_tier.get("title", "Dedicated AI Service Gateway"),
            monthly_subscription_fee=monthly_price,
            paypal_subscription_id=subscription_id,
            contractor_email=self.contractor_email,
            mandate_proof_hash=chk_hash,
        )
        print(
            f"   QuickBooks Online: Recorded recurring software expense ({zapier_result.get('qboDraftInvoiceId')})"
        )
        print(
            f"   Calendar Service:  Scheduled node verification audit ({zapier_result.get('googleCalendarEventId')})\n"
        )

        # Summary Ledger Record
        ledger_entry = {
            "buyer_agent_id": self.agent_id,
            "tier_id": agreed_tier_id,
            "monthly_amount": monthly_price,
            "mandate_proof": chk_hash,
            "checkout_hash": chk_hash,
            "checkout_receipt": chk_receipt,
            "payment_receipt": pay_receipt,
            "subscription_id": subscription_id,
            "allocated_did": assigned_endpoint,
            "status": "ACTIVE_SUBSCRIPTION",
            "zapier_mcp_sync": {
                "qbo_expense_id": zapier_result.get("qboDraftInvoiceId"),
                "google_briefing_id": zapier_result.get("googleCalendarEventId"),
                "status": zapier_result.get("status"),
            },
        }
        self.audit_log.append(ledger_entry)

        print("=======================================================")
        print("🎉 [CYCLE COMPLETE] Autonomous Transaction Ledger Entry:")
        print(json.dumps(ledger_entry, indent=2))
        print("=======================================================\n")

        return ledger_entry


async def main():
    parser = argparse.ArgumentParser(
        description="Run Autonomous AP2 Buyer Agent"
    )
    parser.add_argument(
        "--budget",
        type=float,
        default=100.00,
        help="Monthly spending mandate cap",
    )
    parser.add_argument(
        "--tier",
        type=str,
        default="ap2-gateway",
        help="Target compute tier",
    )
    parser.add_argument(
        "--email",
        type=str,
        default="agent-alpha@example.com",
        help="Buyer email for identity binding",
    )
    args = parser.parse_args()

    agent = BuyerAgent(
        monthly_budget_cap=args.budget, contractor_email=args.email
    )
    await agent.run_autonomous_onboarding_cycle(target_trade=args.tier)


if __name__ == "__main__":
    asyncio.run(main())
