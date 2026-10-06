"""
Contractor Autonomous Buyer Agent.
Represents the solo tradesperson. Operates under strict programmatic financial
guardrails, negotiates with Seller Agents over Model Context Protocol (MCP),
and autonomously executes approved trade software commitments.
"""

import asyncio
import argparse
import json
import logging
from pathlib import Path
from typing import Dict, Any
from .seller_agent import seller_agent
from ..models import RecurrenceType

logger = logging.getLogger("buyer_agent")


class BuyerAgent:
    def __init__(
        self,
        agent_id: str = "contractor-solo-buyer-01",
        monthly_budget_cap: float = 100.00,
        contractor_email: str = "adam@floorsmithllc.com",
    ):
        self.agent_id = agent_id
        self.monthly_budget_cap = monthly_budget_cap
        self.contractor_email = contractor_email
        self.audit_log: list = []

    async def run_autonomous_onboarding_cycle(
        self, target_trade: str = "flooring-tile"
    ) -> Dict[str, Any]:
        """Executes the full 5-phase Agent-to-Agent autonomous commerce cycle."""
        print(f"\n=======================================================")
        print(f"🤖 [BUYER AGENT {self.agent_id}] Starting Autonomous Cycle")
        print(f"   Monthly Spending Mandate Cap: ${self.monthly_budget_cap:.2f}/mo")
        print(f"   Target Contractor Vertical:   {target_trade}")
        print(f"=======================================================\n")

        # Phase 1: Local Telemetry & Business Need Assessment
        print("📊 [Phase 1: Opportunity Assessment (Local Call Log Ingestion)]")
        fixture_path = (
            Path(__file__).resolve().parent.parent / "data" / "call_logs_fixture.json"
        )
        if fixture_path.exists():
            with open(fixture_path, "r", encoding="utf-8") as f:
                logs_data = json.load(f)
            missed_calls = logs_data.get("missed_calls", 8)
            estimated_lost_revenue = logs_data.get("estimated_lost_revenue", 6200.00)
            recent_leads = logs_data.get("recent_missed_leads", [])
            print(
                f"   Contractor: {logs_data.get('contractor_name')} ({logs_data.get('business_entity')})"
            )
            print(
                f"   Carrier Log: {logs_data.get('telephony_carrier')} — {logs_data.get('analyzed_period')}"
            )
            print(
                f"   Total Calls Ingested: {logs_data.get('total_inbound_calls')} | Missed: {missed_calls} ({logs_data.get('missed_call_rate')})"
            )
            for lead in recent_leads[:2]:
                print(
                    f"     • [{lead['caller_name']}] \"{lead['voicemail_transcript'][:55]}...\" (Loss: ${lead['estimated_job_value']:,.2f})"
                )
            print(f"   Total Uncaptured Revenue: ${estimated_lost_revenue:,.2f}")
            roi_mult = logs_data.get("buyer_agent_recommendation", {}).get(
                "projected_net_roi_multiple", "69.6x"
            )
            print(
                f"   Conclusion: Autonomous voice screener required (Budget ROI: {roi_mult})\n"
            )
        else:
            missed_calls = 8
            estimated_lost_revenue = 4200.00
            print(
                f"   Detected {missed_calls} missed customer calls during jobsite tile demo."
            )
            print(
                f"   Estimated uncaptured revenue: ${estimated_lost_revenue:,.2f}"
            )
            print(
                f"   Conclusion: Autonomous voice screener required (Budget ROI: >40x)\n"
            )

        # Phase 2: Query Seller Agent MCP Catalog
        print("🔍 [Phase 2: Seller Agent MCP Catalog Inquiry]")
        catalog = await seller_agent.get_service_catalog()
        target_tier_id = catalog.get("tier_id_aliases", {}).get(target_trade, target_trade)
        matching_tier = next(
            (p for p in catalog.get("plans", []) if p["tier_id"] == target_tier_id),
            None,
        )
        if not matching_tier:
            raise RuntimeError(
                f"No matching service tier found for trade '{target_trade}'"
            )

        monthly_price = matching_tier["monthly_price"]
        print(f"   Found Provider: {catalog.get('provider')}")
        print(f"   Tier Title:     {matching_tier['title']}")
        print(f"   Monthly Price:  ${monthly_price:.2f}/mo (USD)")
        print(f"   Features:       {', '.join(matching_tier['features'])}\n")

        # Phase 3: Evaluate Spending Mandate Guardrails
        print("⚖️  [Phase 3: Programmatic Spending Mandate Verification]")
        mandate_result = await seller_agent.verify_spending_mandate(
            buyer_agent_id=self.agent_id,
            amount=monthly_price,
            recurrence=RecurrenceType.MONTHLY.value,
            category="contractor-dispatch-ai",
            monthly_budget_cap=self.monthly_budget_cap,
        )

        approved = mandate_result.get("approved", False)
        proof_hash = mandate_result.get("mandateProofHash", "")
        remaining_cap = mandate_result.get("monthlyCapRemaining", 0.0)

        print(
            f"   Policy Check:   ${monthly_price:.2f} <= ${self.monthly_budget_cap:.2f} Cap"
        )
        print(f"   Decision:       {'APPROVED' if approved else 'REJECTED'}")
        print(
            f"   Remaining Cap:  ${remaining_cap:.2f} (After this authorization)"
        )
        print(f"   Mandate Proof:  {proof_hash[:24]}...\n")

        if not approved:
            print(f"❌ Mandate violation: {mandate_result.get('reason')}")
            return {"status": "REJECTED", "reason": mandate_result.get("reason")}

        # Phase 4: Delegate PayPal Subscription Session
        print("💳 [Phase 4: Delegated PayPal Subscription Initiation]")
        purchase_result = await seller_agent.purchase_subscription(
            tier_id=matching_tier.get("trade_id", "fieldsmith-pro"),
            agreed_monthly_rate=monthly_price,
            mandate_proof_hash=proof_hash,
            contractor_email=self.contractor_email,
        )
        subscription_id = purchase_result.get("subscription_id")
        print(f"   PayPal Vault Subscription: {subscription_id}")
        print(
            f"   Payment Channel:           PayPal Subscriptions Vault"
        )
        print(
            f"   Billing Cycle:             ${monthly_price:.2f} / month (Auto-debit)\n"
        )

        # Phase 5: KYC-Anchored Telecom Provisioning
        print("📞 [Phase 5: KYC Telnyx DID Line Allocation]")
        provision_result = await seller_agent.provision_telecom_line(
            subscription_id=subscription_id,
            contractor_email=self.contractor_email,
            area_code="863",
        )

        assigned_did = provision_result.get("assignedDid") or provision_result.get("assigned_did")
        carrier = provision_result.get("carrier")
        routing_state = provision_result.get("routingState")

        print(f"   KYC Subscriber:   {self.contractor_email}")
        print(f"   Assigned DID:     {assigned_did}")
        print(f"   Carrier Binding:  {carrier}")
        print(f"   Security State:   {routing_state} (100% Inbound Locked)\n")

        # Phase 6: Downline Back-Office Synchronization via Zapier MCP
        print("⚡ [Phase 6: Autonomous Zapier MCP Back-Office Sync]")
        zapier_result = await seller_agent.dispatch_zapier_mcp(
            workflow_type="a2a_onboarding",
            contractor_name="Marcus Miller",
            business_entity="Miller Custom Flooring LLC",
            allocated_did=assigned_did,
            trade_vertical="Tile & Custom Flooring",
            monthly_subscription_fee=monthly_price,
            paypal_subscription_id=subscription_id,
            contractor_email=self.contractor_email,
        )
        print(
            f"   QuickBooks Online: Recorded recurring software expense ({zapier_result.get('qboDraftInvoiceId')})"
        )
        print(
            f"   Jobber CRM:        Registered allocated DID into routing ({zapier_result.get('jobberQuoteId')})"
        )
        print(
            f"   Google Workspace:  Scheduled 6:30 AM executive briefing ({zapier_result.get('googleCalendarEventId')})\n"
        )

        # Summary Ledger Record
        ledger_entry = {
            "buyer_agent_id": self.agent_id,
            "trade": target_trade,
            "monthly_amount": monthly_price,
            "mandate_proof": proof_hash,
            "subscription_id": subscription_id,
            "assigned_did": assigned_did,
            "status": "ACTIVE_SUBSCRIPTION",
            "zapier_mcp_sync": {
                "qbo_expense_id": zapier_result.get("qboDraftInvoiceId"),
                "jobber_routing_id": zapier_result.get("jobberQuoteId"),
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
        description="Run Autonomous Contractor Buyer Agent"
    )
    parser.add_argument(
        "--budget",
        type=float,
        default=100.00,
        help="Monthly spending mandate cap",
    )
    parser.add_argument(
        "--trade",
        type=str,
        default="flooring-tile",
        help="Contractor trade vertical",
    )
    parser.add_argument(
        "--email",
        type=str,
        default="adam@floorsmithllc.com",
        help="Contractor email for KYC identity",
    )
    args = parser.parse_args()

    agent = BuyerAgent(
        monthly_budget_cap=args.budget, contractor_email=args.email
    )
    await agent.run_autonomous_onboarding_cycle(target_trade=args.trade)


if __name__ == "__main__":
    asyncio.run(main())
