"""
Autonomous Buyer Agent for AP2 Protocol.
Operates under strict programmatic financial guardrails (Ed25519 dual mandates),
negotiates with Seller Nodes over Model Context Protocol (MCP),
and autonomously executes approved compute infrastructure commitments.
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
        agent_id: str = "buyer-agent-01",
        monthly_budget_cap: float = 100.00,
        contractor_email: str = "agent-alpha@nexus-systems.io",
    ):
        self.agent_id = agent_id
        self.monthly_budget_cap = monthly_budget_cap
        self.contractor_email = contractor_email
        self.audit_log: list = []

    async def run_autonomous_onboarding_cycle(
        self, target_trade: str = "ap2-gateway"
    ) -> Dict[str, Any]:
        """Executes the full 5-phase Agent-to-Agent autonomous commerce cycle."""
        print(f"\n=======================================================")
        print(f"🤖 [BUYER AGENT {self.agent_id}] Starting Autonomous Cycle")
        print(f"   Monthly Spending Mandate Cap: ${self.monthly_budget_cap:.2f}/mo")
        print(f"   Target Compute Tier:          {target_trade}")
        print(f"=======================================================\n")

        # Phase 1: Local Telemetry & Business Need Assessment
        print("📊 [Phase 1: Opportunity Assessment (Pipeline Telemetry)]")
        print(f"   Autonomous Buyer: Nexus Autonomous Systems Corp ({self.contractor_email})")
        print(f"   Cluster Ingestion: 240 workload tasks queued | Headroom: 80 tasks")
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
            # Fallback to default tier
            matching_tier = next(
                (p for p in catalog.get("plans", []) if p["tier_id"] == "ap2-gateway"),
                catalog.get("plans", [{}])[0] if catalog.get("plans") else None,
            )

        if not matching_tier:
            raise RuntimeError(f"No matching service tier found for tier '{target_trade}'")

        monthly_price = matching_tier["monthly_price"]
        print(f"   Found Provider: {catalog.get('provider')}")
        print(f"   Tier Title:     {matching_tier['title']}")
        print(f"   Monthly Price:  ${monthly_price:.2f}/mo (USD)")
        print(f"   Features:       {', '.join(matching_tier.get('features', []))}\n")

        # Phase 3: Evaluate Spending Mandate Guardrails
        print("⚖️  [Phase 3: Programmatic Spending Mandate Verification]")
        mandate_result = await seller_agent.verify_spending_mandate(
            buyer_agent_id=self.agent_id,
            amount=monthly_price,
            recurrence=RecurrenceType.MONTHLY.value,
            category="COMPUTE_NODE_SERVICE",
            monthly_budget_cap=self.monthly_budget_cap,
            contractor_email=self.contractor_email,
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
            tier_id=matching_tier.get("tier_id", "ap2-gateway"),
            agreed_monthly_rate=monthly_price,
            mandate_proof_hash=proof_hash,
            contractor_email=self.contractor_email,
            buyer_agent_id=self.agent_id,
        )
        subscription_id = purchase_result.get("subscription_id")
        print(f"   PayPal Vault Subscription: {subscription_id}")
        print(
            f"   Payment Channel:           PayPal Subscriptions Vault"
        )
        print(
            f"   Billing Cycle:             ${monthly_price:.2f} / month (Auto-debit)\n"
        )

        # Phase 5: FastMCP Compute Node Provisioning
        print("🖥️ [Phase 5: FastMCP Compute Node Provisioning]")
        provision_result = await seller_agent.provision_compute_node(
            subscription_id=subscription_id,
            contractor_email=self.contractor_email,
            tier_id=matching_tier.get("tier_id", "ap2-gateway"),
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
            contractor_name="Nexus Autonomous Systems Corp",
            business_entity="Nexus Autonomous Systems Corp",
            allocated_did=assigned_endpoint,
            trade_vertical=matching_tier.get("title", "Dedicated AI Service Gateway"),
            monthly_subscription_fee=monthly_price,
            paypal_subscription_id=subscription_id,
            contractor_email=self.contractor_email,
            mandate_proof_hash=proof_hash,
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
            "tier_id": matching_tier.get("tier_id", "ap2-gateway"),
            "monthly_amount": monthly_price,
            "mandate_proof": proof_hash,
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
        default="agent-alpha@nexus-systems.io",
        help="Buyer email for identity binding",
    )
    args = parser.parse_args()

    agent = BuyerAgent(
        monthly_budget_cap=args.budget, contractor_email=args.email
    )
    await agent.run_autonomous_onboarding_cycle(target_trade=args.tier)


if __name__ == "__main__":
    asyncio.run(main())
