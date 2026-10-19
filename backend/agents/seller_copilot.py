"""
AP2 Node Operations Copilot (Buyer-Side Agent Reasoner).
Represents the autonomous enterprise buyer's operations copilot.
Ingests compute workload telemetry, diagnoses pipeline capacity, queries AP2 Seller MCP server,
and orchestrates autonomous A2A execution upon human approval.
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from ..mcp_server import process_mcp_request

logger = logging.getLogger("seller_copilot")


class SellerCopilot:
    """Autonomous Operations Copilot managing compute node procurement and fleet telemetry."""

    def __init__(
        self,
        contractor_name: str = "Demo Autonomous Buyer",
        business_entity: str = "Demo Buyer Corp",
        trade_vertical: str = "Dedicated AI Service Gateway",
        budget_cap: float = 100.00,
        contractor_email: str = "agent-alpha@example.com",
        simulate_exhaustion: bool = False,
    ):
        self.contractor_name = contractor_name
        self.business_entity = business_entity
        self.trade_vertical = trade_vertical
        self.budget_cap = budget_cap
        self.contractor_email = contractor_email
        self.simulate_exhaustion = simulate_exhaustion
        self.session_id = f"copilot-{uuid.uuid4().hex[:8]}"

    def get_call_leakage_telemetry(self) -> Dict[str, Any]:
        """Calculates workload demand telemetry and pipeline capacity constraints."""
        return {
            "contractor_name": self.contractor_name,
            "business_entity": self.business_entity,
            "cluster_provider": "AP2 Autonomous Node Network",
            "total_tasks": 240,
            "queued_tasks": 80,
            "pending_tasks": 8,
            "queue_rate": "33.3%",
            "estimated_lost_revenue": 6200.00,
            "recent_queued_tasks": [
                {
                    "requester_name": "Demo High-Throughput Worker",
                    "client_endpoint": "mcp+https://batch-01.example.com/mcp",
                    "estimated_job_value": 3250.00,
                    "task_description": "Queued 125 batch synthesis jobs awaiting gateway execution.",
                },
                {
                    "requester_name": "Enterprise Cluster Node",
                    "client_endpoint": "mcp+https://cluster-01.example.com/mcp",
                    "estimated_job_value": 1800.00,
                    "task_description": "Dedicated AI service gateway needed to route reasoning queries.",
                },
            ],
        }

    get_workload_telemetry = get_call_leakage_telemetry

    # MOCK(M-016): keyword-matched canned replies with hardcoded fleet stats, not an AI model
    async def handle_message(self, user_message: str) -> Dict[str, Any]:
        """
        Processes a message from the operator, evaluates intent,
        and returns the conversational reply, suggested quick replies, and telemetry.
        """
        msg = user_message.lower().strip()
        telemetry = self.get_call_leakage_telemetry()
        missed = telemetry.get("pending_tasks", 8)
        loss = telemetry.get("estimated_lost_revenue", 6200.00)
        leads = telemetry.get("recent_queued_tasks", [])

        # Priority 1: Approval / Execution
        if any(w in msg for w in ["approve", "setup", "activate", "execute", "go ahead", "do it"]) or msg in ["yes", "yep", "yeah", "ok", "okay"]:
            exec_result = await self.execute_autonomous_a2a_cycle()
            exec_status = exec_result.get("status")
            if exec_status == "REJECTED":
                reason = exec_result.get("reason") or "Spending mandate check rejected the request."
                reply = (
                    f"❌ **Spending Mandate Rejected**\n\n"
                    f"The autonomous purchase could not proceed because the mandate evaluation rejected it:\n"
                    f"• **Reason**: {reason}\n\n"
                    f"No subscription was recorded, no compute node was provisioned, and no back-office sync was dispatched."
                )
                return {
                    "reply": reply,
                    "phase": "REJECTED",
                    "telemetry": telemetry,
                    "suggested_actions": [
                        "Review spending mandate",
                        "What's my monthly budget cap?",
                        "Check pending workload queue",
                    ],
                    "execution_result": exec_result,
                }

            if exec_status != "SUCCESS":
                reason = exec_result.get("reason") or "Purchases go through the buyer wallet flow."
                reply = (
                    f"🔒 **Buyer Wallet Required**\n\n"
                    f"Mandate policy evaluation succeeded, but the server cannot sign owner limits or execute purchases outside mock mode.\n"
                    f"• **Detail**: {reason}\n\n"
                    f"Please complete the purchase through the buyer wallet flow."
                )
                return {
                    "reply": reply,
                    "phase": "WALLET_REQUIRED",
                    "telemetry": telemetry,
                    "suggested_actions": [
                        "Review spending mandate",
                        "Check pending workload queue",
                    ],
                    "execution_result": exec_result,
                }

            did = exec_result.get("assigned_did") or "not available (missing)"
            qbo = (exec_result.get("zapier_sync") or {}).get("qbo_draft_invoice_id") or "not available (missing)"
            sub_id = exec_result.get("subscription_id") or "not available (missing)"
            sub_price = exec_result.get("monthly_amount")
            price_str = f"${sub_price:.2f}/mo" if isinstance(sub_price, (int, float)) else "missing amount"

            reply = (
                f"🎉 **Autonomous A2A Setup Complete!**\n\n"
                f"I negotiated the agreement with the AP2 Seller Node and executed your recurring **{price_str} PayPal subscription** (`{sub_id}`).\n\n"
                f"• **Dedicated Compute Endpoint**: `{did}` (Bound to {self.business_entity})\n"
                f"• **AP2 v0.2 Security**: Verified ES256 Checkout & Payment Mandate Chains\n"
                f"• **ERP Automation**: Provisioned and active on cluster schedule\n"
                f"• **QuickBooks Online**: Monthly software subscription expense recorded (`{qbo}`)\n\n"
                f"You're completely live! Workload tasks will now be automatically routed and executed under your spending mandate."
            )
            return {
                "reply": reply,
                "phase": "COMPLETED",
                "telemetry": telemetry,
                "suggested_actions": [
                    "View in AP2 Fleet Ledger",
                    "Check Bryntum Dispatch Timeline",
                    "Inspect A2A Protocol Audit Trail",
                ],
                "execution_result": exec_result,
            }

        # Priority 2: Discovery & Proposal
        if any(w in msg for w in ["find", "solution", "service", "answering", "fix", "options", "what can we do", "recommend"]):
            catalog_resp = await process_mcp_request({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "get_service_catalog", "arguments": {}},
            })
            catalog = {}
            if catalog_resp and "result" in catalog_resp:
                raw_text = catalog_resp["result"]["content"][0]["text"]
                catalog = json.loads(raw_text)

            tier = next(
                (p for p in catalog.get("plans", []) if p["tier_id"] == "ap2-gateway"),
                {"title": "Dedicated AI Service Gateway", "monthly_price": 79.99},
            )
            price = tier["monthly_price"]

            reply = (
                f"I queried the autonomous registry and found **AP2 Autonomous Node Network** (Seller Node MCP).\n\n"
                f"• **Plan**: {tier['title']}\n"
                f"• **Cost**: **${price:.2f}/month** (Auto-debit via PayPal Subscriptions)\n"
                f"• **Budget Mandate**: Your pre-approved company spending limit is **${self.budget_cap:.2f}/mo** (Leaves **${(self.budget_cap - price):.2f}/mo** remaining)\n"
                f"• **What it does**: Provisions a dedicated mcp+https endpoint, provides 450 workload tasks/month, and syncs directly into QuickBooks Online.\n\n"
                f"**Ready for your single approval:** Shall I negotiate the A2A agreement and provision your node for **{self.business_entity}**?"
            )
            return {
                "reply": reply,
                "phase": "PROPOSAL",
                "telemetry": telemetry,
                "suggested_actions": [
                    f"Approve Setup (${price:.2f}/mo via PayPal)",
                    "Review spending mandate",
                ],
                "proposal": {
                    "provider": "AP2 Autonomous Node Network",
                    "plan": tier["title"],
                    "monthly_price": price,
                    "budget_cap": self.budget_cap,
                    "business_entity": self.business_entity,
                    "payment_channel": "PayPal Subscriptions",
                },
            }

        # Priority 3: Audit Trail & M2M Protocol Inspection
        if any(w in msg for w in ["audit", "inspect", "protocol", "trail", "trace", "proof", "hmac", "m2m", "evidence"]):
            from ..api.m2m_audit import get_latest_artifacts
            latest = get_latest_artifacts() or {}
            latest_sub = latest.get("paypal_subscription_id") or "not available (no run recorded)"
            latest_qbo = (latest.get("quickbooks") or {}).get("purchase_id") or "not available (no run recorded)"
            reply = (
                f"🛡️ **A2A Protocol Cryptographic Audit Trail:**\n\n"
                f"• **Step 1: Mandate Evaluation (RFC 8032 / ES256)**: Pre-approved spending cap (${self.budget_cap:.2f}/mo) mathematically evaluated against seller catalog.\n"
                f"• **Step 2: PayPal Subscriptions Rails**: Recurring billing agreement (`{latest_sub}`).\n"
                f"• **Step 3: MCP Endpoint Binding**: Dedicated mcp+https compute endpoint provisioned with MCP over HTTPS (JSON-RPC 2.0).\n"
                f"• **Step 4: Zapier MCP Settlement**: Downline webhooks dispatched to QuickBooks Online API v3 expense in Account 6300 (`{latest_qbo}`).\n\n"
                f"You can review the live JSON-RPC 2.0 frames in the right panel or click **Back-Office Payloads** in the top bar for raw artifacts."
            )
            return {
                "reply": reply,
                "phase": "AUDIT",
                "telemetry": telemetry,
                "suggested_actions": [
                    "View in AP2 Fleet Ledger",
                    "Check Bryntum Dispatch Timeline",
                    "Test Cryptographic Anti-Tamper (+1¢)",
                    "View Back-Office Payloads",
                ],
                "proposal": None,
                "action_type": "INSPECT_AUDIT_TRAIL",
            }

        # Priority 4: Fleet Ledger / Mission Control Navigation
        if any(w in msg for w in ["fleet", "ledger"]):
            reply = (
                f"📊 **AP2 Enterprise Fleet Ledger Command Center:**\n\n"
                f"The **Fleet Ledger** provides real-time enterprise telemetry across all active node subscribers:\n"
                f"• **Active Nodes**: 13 Active of 14 Provisioned Nodes across North America\n"
                f"• **MRR**: $1,219.87/mo tracked via PayPal Subscriptions\n"
                f"• **Mandate Verification Rate**: 100% ES256 cryptographic integrity\n"
                f"• **Annualized GMV**: $14,638.44 across 3 compute tiers\n\n"
                f"Select the **AG Studio Fleet Ledger** tab in the top navigation to view the live command center dashboard and interactive analytics."
            )
            return {
                "reply": reply,
                "phase": "NAVIGATION",
                "telemetry": telemetry,
                "suggested_actions": [
                    "Inspect A2A Protocol Audit Trail",
                    "Check Bryntum Dispatch Timeline",
                    "Check pending workload queue",
                ],
                "proposal": None,
                "action_type": "NAVIGATE_FLEET_LEDGER",
            }

        # Priority 5: Bryntum Timeline Navigation
        if any(w in msg for w in ["bryntum", "timeline", "dispatch", "calendar", "schedule"]):
            reply = (
                f"📅 **Bryntum Node Dispatch Timeline:**\n\n"
                f"The Bryntum timeline maps live workload scheduling, resource allocations, and incoming task requests in real time. "
                f"The dedicated gateway node is scheduled for active streaming.\n\n"
                f"Select the **Bryntum Fleet Timeline** tab in the top navigation to view the dispatch calendar."
            )
            return {
                "reply": reply,
                "phase": "NAVIGATION",
                "telemetry": telemetry,
                "suggested_actions": [
                    "Inspect A2A Protocol Audit Trail",
                    "View in AP2 Fleet Ledger",
                    "Check pending workload queue",
                ],
                "proposal": None,
                "action_type": "NAVIGATE_BRYNTUM",
            }

        # Priority 6: Budget Mandate & Spending Cap Inquiry
        if any(w in msg for w in ["budget", "cap", "mandate", "limit"]):
            reply = (
                f"💼 **Contractor Spending Mandate Policy:**\n\n"
                f"• **Authorized Entity**: {self.business_entity}\n"
                f"• **Pre-Approved Monthly Cap**: **${self.budget_cap:.2f}/mo**\n"
                f"• **Dedicated AI Service Gateway**: **$79.99/mo** (Leaves **${(self.budget_cap - 79.99):.2f}/mo** headroom)\n"
                f"• **Enforcement**: Cryptographic Ed25519 signature verification. "
                f"Any charge exceeding ${self.budget_cap:.2f} is blocked at the gateway."
            )
            return {
                "reply": reply,
                "phase": "PROPOSAL",
                "telemetry": telemetry,
                "suggested_actions": [
                    "Find an autonomous compute node",
                    "Check pending workload queue",
                    "Inspect A2A Protocol Audit Trail",
                ],
                "proposal": None,
            }

        # Priority 7: Back-Office Payloads Inquiry
        if any(w in msg for w in ["payload", "back-office", "erp", "qbo", "quickbooks"]):
            from ..api.m2m_audit import get_latest_artifacts
            latest = get_latest_artifacts() or {}
            latest_qbo = (latest.get("quickbooks") or {}).get("purchase_id") or "not available (no run recorded)"
            reply = (
                f"📄 **Back-Office Artifact Inspector:**\n\n"
                f"Every autonomous transaction generates authentic downline settlement payloads:\n"
                f"• **QuickBooks Online API v3**: Purchase expense memo (`{latest_qbo}`) categorized to Account 6300 (Software & SaaS)\n"
                f"• **Cryptographic Proof**: Dual mandate authorization validating exact parameters\n\n"
                f"Click **Back-Office Payloads** in the top bar to inspect the raw JSON structures."
            )
            return {
                "reply": reply,
                "phase": "AUDIT",
                "telemetry": telemetry,
                "suggested_actions": [
                    "Inspect A2A Protocol Audit Trail",
                    "View in AP2 Fleet Ledger",
                    "Test Cryptographic Anti-Tamper (+1¢)",
                ],
                "proposal": None,
                "action_type": "OPEN_INSPECTOR",
            }

        # Priority 8: Workload queue / diagnosis
        if any(w in msg for w in ["queue", "pending", "backlog", "check", "today", "capacity", "task", "workload"]):
            reply = (
                f"Hey {self.contractor_name.split()[0]}, I analyzed your workload pipeline telemetry. "
                f"You have **{missed} pending tasks** ({telemetry.get('queue_rate', '33.3%')}) "
                f"awaiting compute capacity, representing an estimated **${loss:,.2f} in deferred output**.\n\n"
                f"Would you like me to find an autonomous compute node to execute your workloads 24/7?"
            )
            return {
                "reply": reply,
                "phase": "DIAGNOSIS",
                "telemetry": telemetry,
                "suggested_actions": [
                    "Find an autonomous compute node",
                    "What's my monthly budget cap?",
                    "How much did I lose this week?",
                ],
                "proposal": None,
            }

        # Default fallback
        return {
            "reply": (
                f"Hi {self.contractor_name.split()[0]}, I'm your AI Business Copilot. "
                f"I monitor your compute workloads and enforce your company spending limits. "
                f"You can ask me: *\"What is my workload queue?\"* or *\"What's my monthly budget cap?\"*"
            ),
            "phase": "IDLE",
            "telemetry": telemetry,
            "suggested_actions": [
                "Check pending workload queue",
                "What's my monthly budget cap?",
                "Find an autonomous compute node",
            ],
            "proposal": None,
        }

    # MOCK(M-026): executes a mock-mode AP2 purchase server-side when the copilot approves
    async def execute_autonomous_a2a_cycle(self) -> Dict[str, Any]:
        """
        Executes the machine-to-machine exchange through the MCP Server:
        1. Mandate evaluation (and counter-offer check if applicable)
        2. In mock mode only: AP2 v0.2 purchase via execute_mock_deck_purchase
        3. Dedicated compute node endpoint provisioning
        4. Downline Zapier sync into QBO
        """
        from ..config import settings

        protocol_trace: List[Dict[str, Any]] = []

        # Step 1: Programmatic Spending Mandate Verification
        t1 = datetime.now(timezone.utc).isoformat()
        mandate_req = {
            "jsonrpc": "2.0",
            "id": 101,
            "method": "tools/call",
            "params": {
                "name": "evaluate_spending_mandate",
                "arguments": {
                    "buyer_agent_id": f"buyer-{self.contractor_name.split()[0].lower()}",
                    "amount": 79.99,
                    "recurrence": "monthly",
                    "category": "autonomous-node-service",
                    "monthly_budget_cap": self.budget_cap,
                },
            },
        }
        mandate_resp = await process_mcp_request(mandate_req)
        mandate_data = json.loads(mandate_resp["result"]["content"][0]["text"])
        approved = bool(mandate_data.get("approved", False))
        monthly_price = 79.99
        tier_title = "Dedicated AI Service Gateway"

        # Check for autonomous counter-offer if $79.99 exceeds budget cap
        if not approved:
            has_counter = mandate_data.get("counterOfferAvailable") or mandate_data.get("counter_offer_available", False)
            counter_amount = float(mandate_data.get("counterOfferAmount") or mandate_data.get("counter_offer_amount", 0.0))
            counter_tier = mandate_data.get("counterOfferTier") or mandate_data.get("counter_offer_tier", "Alternative Tier")
            if has_counter and counter_amount > 0 and counter_amount <= self.budget_cap:
                counter_req = {
                    "jsonrpc": "2.0",
                    "id": 1011,
                    "method": "tools/call",
                    "params": {
                        "name": "evaluate_spending_mandate",
                        "arguments": {
                            "buyer_agent_id": f"buyer-{self.contractor_name.split()[0].lower()}",
                            "amount": counter_amount,
                            "recurrence": "monthly",
                            "category": "autonomous-node-service",
                            "monthly_budget_cap": self.budget_cap,
                        },
                    },
                }
                c_resp = await process_mcp_request(counter_req)
                mandate_data = json.loads(c_resp["result"]["content"][0]["text"])
                approved = bool(mandate_data.get("approved", False))
                if approved:
                    monthly_price = counter_amount
                    tier_title = f"{counter_tier} (Negotiated)"

        raw_proof = mandate_data.get("mandateProofHash") or mandate_data.get("mandate_proof_hash")
        proof_hash = raw_proof if raw_proof else None
        reason = mandate_data.get("reason")
        authorized_amt = float(mandate_data.get("authorizedAmount") or mandate_data.get("authorized_amount") or (monthly_price if approved else 0.0))
        remaining_budget = mandate_data.get("monthlyCapRemaining")
        if remaining_budget is None:
            remaining_budget = mandate_data.get("monthly_cap_remaining")
        if remaining_budget is None:
            remaining_budget = round(self.budget_cap - authorized_amt, 2) if approved else self.budget_cap

        protocol_trace.append({
            "step": 1,
            "timestamp": t1,
            "protocol": "MCP JSON-RPC 2.0",
            "method": "tools/call:evaluate_spending_mandate",
            "decision": "APPROVED" if approved else "REJECTED",
            "proof_hash": proof_hash,
            "budget_cap": self.budget_cap,
            "authorized_amount": authorized_amt,
            "remaining_budget": remaining_budget,
            "tier_title": tier_title,
            "reason": reason,
        })

        if not approved:
            return {
                "status": "REJECTED",
                "reason": reason or "Spending mandate check rejected the request.",
                "protocol_trace": protocol_trace,
            }

        if not getattr(settings, "mock_external_apis", False):
            return {
                "status": "WALLET_REQUIRED",
                "reason": "Outside mock mode, the copilot does not execute purchases; purchases go through the buyer wallet flow.",
                "protocol_trace": protocol_trace,
            }

        tier_target = "ap2-gateway" if monthly_price == 79.99 else ("ap2-batch" if monthly_price == 49.99 else "ap2-cluster")

        # Step 2 & 3: Execute AP2 v0.2 purchase and node provisioning via shared mock deck purchase flow
        t2 = datetime.now(timezone.utc).isoformat()
        from ..server import execute_mock_deck_purchase
        deck_res = await execute_mock_deck_purchase(
            tier_id=tier_target,
            agreed_monthly_rate=monthly_price,
            buyer_email=self.contractor_email,
            contractor_name=self.contractor_name,
            business_entity=self.business_entity,
            monthly_budget_cap=self.budget_cap,
        )
        if deck_res.get("status") != "ACTIVE":
            detail = deck_res.get("detail") or {}
            rej_reason = detail.get("reason") or detail.get("message") or "AP2 purchase rejected."
            return {
                "status": "REJECTED",
                "reason": rej_reason,
                "protocol_trace": protocol_trace,
            }

        purchase_res = deck_res.get("purchaseResult") or {}
        prov_res = deck_res.get("provisionResult") or {}
        sub_id = purchase_res.get("subscription_id") or deck_res.get("subscriptionId")
        plan_id = purchase_res.get("plan_id")
        verified_proof = purchase_res.get("mandate_proof_hash") or proof_hash
        protocol_trace[0]["proof_hash"] = verified_proof

        protocol_trace.append({
            "step": 2,
            "timestamp": t2,
            "protocol": "PayPal Subscriptions v1",
            "action": "AUTHORIZE_BILLING_AGREEMENT",
            "subscription_id": sub_id,
            "plan_id": plan_id,
            "monthly_amount": purchase_res.get("agreed_monthly_rate", monthly_price),
            "payer_entity": self.business_entity,
            "checkout_receipt": purchase_res.get("checkout_receipt"),
            "payment_receipt": purchase_res.get("payment_receipt"),
        })

        t3 = datetime.now(timezone.utc).isoformat()
        assigned_did = prov_res.get("assigned_did") or prov_res.get("endpoint") or deck_res.get("assignedDid")
        protocol_trace.append({
            "step": 3,
            "timestamp": t3,
            "protocol": "MCP JSON-RPC 2.0",
            "method": "tools/call:provision_compute_node",
            "assigned_did": assigned_did,
            "carrier": prov_res.get("carrier"),
            "routing_state": prov_res.get("routing_state"),
            "node_id": prov_res.get("node_id"),
        })

        # Step 4: Downline Zapier MCP Dispatch (QBO)
        t4 = datetime.now(timezone.utc).isoformat()
        zap_req = {
            "jsonrpc": "2.0",
            "id": 103,
            "method": "tools/call",
            "params": {
                "name": "dispatch_zapier_mcp",
                "arguments": {
                    "workflow_type": "a2a_onboarding",
                    "contractor_name": self.contractor_name,
                    "business_entity": self.business_entity,
                    "allocated_did": assigned_did,
                    "trade_vertical": tier_title,
                    "monthly_subscription_fee": monthly_price,
                    "paypal_subscription_id": sub_id,
                    "contractor_email": self.contractor_email,
                    "mandate_proof_hash": verified_proof,
                },
            },
        }
        zap_resp = await process_mcp_request(zap_req)
        zap_data = json.loads(zap_resp["result"]["content"][0]["text"])
        protocol_trace.append({
            "step": 4,
            "timestamp": t4,
            "protocol": "MCP JSON-RPC 2.0",
            "method": "tools/call:dispatch_zapier_mcp",
            "qbo_expense_id": zap_data.get("qbo_draft_invoice_id") or zap_data.get("qboDraftInvoiceId"),
            "gcal_event_id": zap_data.get("google_calendar_event_id") or zap_data.get("googleCalendarEventId"),
            "qbo_export": zap_data.get("qbo_payload") or zap_data.get("qboPayload"),
            "status": zap_data.get("status"),
        })

        return {
            "status": "SUCCESS",
            "subscription_id": sub_id,
            "assigned_did": assigned_did,
            "mandate_proof": verified_proof,
            "monthly_amount": purchase_res.get("agreed_monthly_rate", monthly_price),
            "checkout_receipt": purchase_res.get("checkout_receipt"),
            "payment_receipt": purchase_res.get("payment_receipt"),
            "protocol_trace": protocol_trace,
            "zapier_sync": zap_data,
        }


# Backwards compatibility alias
ContractorCopilot = SellerCopilot

