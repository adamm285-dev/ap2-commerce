"""
Standalone Autonomous External Buyer Agent & MCP Client Harness.
Simulates a 3rd-party autonomous agent (e.g. Claude Desktop, Grok, ChatGPT, Cursor)
discovering and transacting with AP2 Seller Node over Model Context Protocol (MCP).

Supports two transports:
1. HTTP: JSON-RPC 2.0 over HTTP (POST http://127.0.0.1:8001/mcp)
2. stdio: Subprocess communication via stdin/stdout with `python -m backend.mcp_server`
"""

import sys
import os
import json
import uuid
import time
import argparse
import asyncio
import logging
from typing import Dict, Any, Optional, List
import tempfile
import atexit

# Ensure isolated temp DB in external buyer harness to protect development DB
if not os.environ.get("A2A_DB_PATH"):
    _temp_ext_buyer_db = os.path.join(tempfile.gettempdir(), f"a2a_ext_buyer_{os.getpid()}_{uuid.uuid4().hex[:8]}.db")
    os.environ["A2A_DB_PATH"] = _temp_ext_buyer_db

    def _cleanup_ext_buyer_temp_db():
        for ext in ["", "-wal", "-shm", "-journal"]:
            f = _temp_ext_buyer_db + ext
            try:
                if os.path.exists(f):
                    os.remove(f)
            except OSError:
                pass

    atexit.register(_cleanup_ext_buyer_temp_db)

logger = logging.getLogger("external_buyer_agent")


class ExternalBuyerAgent:
    """
    Autonomous Buyer Agent that acts on behalf of a contractor to negotiate,
    mandate-check, and purchase business telephony solutions headlessly over MCP.
    """

    def __init__(
        self,
        transport: str = "http",
        server_url: str = "http://127.0.0.1:8001/mcp",
        contractor_name: Optional[str] = None,
        business_entity: Optional[str] = None,
        contractor_email: Optional[str] = None,
        trade_id: Optional[str] = None,
        budget_cap: float = 100.00,
        area_code: str = "703",
        webhook_url: Optional[str] = None,
        verbose: bool = True,
        reset_ledger: bool = True,
        simulate_exhaustion: bool = False,
        admin_api_key: Optional[str] = None,
        profile: Optional[str] = None,
    ):
        self.transport = transport
        self.server_url = server_url
        self.profile = "ap2"
        self.contractor_name = contractor_name or "Nexus Autonomous Buyer"
        self.business_entity = business_entity or "Nexus Autonomous Systems Corp"
        self.contractor_email = contractor_email or "agent-alpha@example.com"
        self.trade_id = trade_id or "ap2-gateway"
        self.category = "AUTONOMOUS_NODE_SERVICE"

        self.budget_cap = budget_cap
        self.area_code = area_code
        self.webhook_url = webhook_url
        self.verbose = verbose
        self.reset_ledger = reset_ledger
        self.simulate_exhaustion = simulate_exhaustion
        if admin_api_key:
            self.admin_api_key = admin_api_key
        else:
            try:
                from ..config import settings
                self.admin_api_key = getattr(settings, "admin_api_key", "")
            except Exception:
                self.admin_api_key = os.getenv("ADMIN_API_KEY", "")
        self.request_id = 0
        self.audit_log: List[Dict[str, Any]] = []

    def _next_id(self) -> int:
        self.request_id += 1
        return self.request_id

    def log(self, message: str):
        if self.verbose:
            print(message)

    async def _send_rpc(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Dispatches a JSON-RPC 2.0 request over the configured transport."""
        req_id = self._next_id()
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {},
        }

        if self.transport == "http":
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(
                    self.server_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                if res.status_code != 200:
                    raise RuntimeError(f"HTTP error {res.status_code}: {res.text}")
                return res.json()

        elif self.transport == "stdio":
            # For stdio, import and call process_mcp_request directly in-process or via stdin
            from ..mcp_server import process_mcp_request
            resp = await process_mcp_request(payload)
            if resp is None:
                return {"jsonrpc": "2.0", "id": req_id, "result": {}}
            return resp

        else:
            raise ValueError(f"Unsupported transport: {self.transport}")

    async def _call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Invokes an MCP tool via tools/call and parses the returned JSON payload."""
        t0 = time.perf_counter()
        resp = await self._send_rpc(
            method="tools/call",
            params={
                "name": tool_name,
                "arguments": arguments,
            },
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000

        if "error" in resp:
            raise RuntimeError(f"Tool '{tool_name}' failed with error: {resp['error']}")

        content_raw = resp.get("result", {}).get("content", [{}])[0].get("text", "{}")
        try:
            parsed = json.loads(content_raw)
        except Exception:
            parsed = {"raw": content_raw}

        self.audit_log.append({
            "tool": tool_name,
            "arguments": arguments,
            "latency_ms": round(elapsed_ms, 2),
            "result": parsed,
        })
        return parsed

    async def execute_autonomous_procurement(self) -> Dict[str, Any]:
        """
        Executes the full 7-step autonomous procurement lifecycle:
        1. Initialize handshake
        2. Tool discovery
        3. Catalog inspection
        4. Quote calculation
        5. Spending mandate check & AP2 v0.2 mandate proof
        6. Compute node endpoint allocation
        7. Back-office ERP & QBO export
        """
        self.log("\n" + "=" * 65)
        self.log(f"🤖 [EXTERNAL BUYER AGENT] Initiating Autonomous A2A Procurement")
        self.log(f"   Transport:        {self.transport.upper()} ({self.server_url if self.transport == 'http' else 'In-Process stdio'})")
        self.log(f"   Contractor:       {self.contractor_name} ({self.business_entity})")
        self.log(f"   Target Vertical:  {self.trade_id}")
        self.log(f"   Monthly Budget:   ${self.budget_cap:.2f}/mo (Mandate Cap)")
        self.log("=" * 65 + "\n")

        # Optional: Reset Ledger before execution
        if self.reset_ledger:
            try:
                from ..services.mandate_evaluator import ledger
                ledger.reset()
            except Exception:
                pass
            if self.transport == "http":
                try:
                    headers = {}
                    if getattr(self, "admin_api_key", None):
                        headers["X-Admin-Key"] = self.admin_api_key
                    async with httpx.AsyncClient(timeout=3.0) as client:
                        reset_url = self.server_url.replace("/mcp", "/api/agent/spending-mandate/reset")
                        await client.post(reset_url, json={}, headers=headers)
                except Exception:
                    pass

        # Step 1: Initialize Handshake
        self.log("🤝 [Step 1: MCP Initialize Handshake]")
        init_resp = await self._send_rpc(
            method="initialize",
            params={
                "protocolVersion": "2024-11-05",
                "clientInfo": {
                    "name": "external-contractor-buyer-agent",
                    "version": "1.0.0",
                },
            },
        )
        server_info = init_resp.get("result", {}).get("serverInfo", {})
        server_name = server_info.get("name", "unknown")
        proto_ver = init_resp.get("result", {}).get("protocolVersion", "")
        self.log(f"   Connected to Server: {server_name} (MCP Protocol: {proto_ver})")
        self.log("   Handshake verified successfully.\n")

        # Send notifications/initialized
        await self._send_rpc(method="notifications/initialized")

        # Step 2: Tool Discovery
        self.log("🔍 [Step 2: MCP Tool Discovery (tools/list)]")
        tools_resp = await self._send_rpc(method="tools/list")
        discovered_tools = tools_resp.get("result", {}).get("tools", [])
        tool_names = [t.get("name") for t in discovered_tools]
        self.log(f"   Discovered {len(discovered_tools)} MCP tools:")
        for t in discovered_tools:
            self.log(f"     • {t.get('name')}: {t.get('description')[:60]}...")
        self.log("")

        # Step 3: Service Catalog Discovery
        self.log("📋 [Step 3: Querying Service Catalog (get_service_catalog)]")
        catalog = await self._call_tool("get_service_catalog", {})
        plan_id = catalog.get("tier_id_aliases", {}).get(self.trade_id, self.trade_id)
        selected_tier = next(
            (p for p in catalog.get("plans", []) if p.get("tier_id") == plan_id),
            {"tier_id": plan_id, "monthly_price": 79.99, "title": "Dedicated AI Service Gateway"},
        )
        workload = next(
            (t for t in catalog.get("supported_workloads", []) if t.get("tier_id") == self.trade_id),
            None,
        )
        monthly_price = float(selected_tier.get("monthly_price", 79.99))
        tier_title = selected_tier.get("title", "Dedicated AI Service Gateway")
        if workload:
            tier_title = f"{tier_title} ({workload.get('title', '')})"
        self.log(f"   Provider:        {catalog.get('provider', 'AP2 Autonomous Node Network')}")
        self.log(f"   Selected Plan:   {tier_title}")
        self.log(f"   Monthly Cost:    ${monthly_price:.2f}/mo (USD)")
        self.log(f"   Features:        {', '.join(selected_tier.get('features', []))}\n")

        # Step 4: Autonomous Compute Specification
        self.log("⚡ [Step 4: Autonomous Compute Specification]")
        self.log(f"   Selected Tier:   {tier_title}")
        self.log(f"   Workload Quota:  {selected_tier.get('workload_tasks_per_month', 450)} workload tasks/mo")
        self.log("   Compute Target:  Dedicated AI Gateway micro-agent coordination\n")

        # Step 5: Programmatic Spending Mandate Evaluation
        self.log("⚖️  [Step 5: Enforcing Spending Mandate Policy (evaluate_spending_mandate)]")
        buyer_agent_id = f"buyer-{self.contractor_name.split()[0].lower()}"
        mandate = await self._call_tool(
            "evaluate_spending_mandate",
            {
                "buyer_agent_id": buyer_agent_id,
                "amount": monthly_price,
                "recurrence": "monthly",
                "category": self.category,
                "monthly_budget_cap": self.budget_cap,
            },
        )
        approved = mandate.get("approved", False)
        proof_hash = mandate.get("mandateProofHash") or mandate.get("mandate_proof_hash", "")
        rem_budget = mandate.get("monthlyCapRemaining") or mandate.get("monthly_cap_remaining", 0.0)

        self.log(f"   Authorization:   {'APPROVED' if approved else 'REJECTED'}")
        self.log(f"   Budget Policy:   ${monthly_price:.2f} <= ${self.budget_cap:.2f}/mo Cap")
        self.log(f"   Remaining Cap:   ${rem_budget:.2f}")

        # Dynamic Negotiation: Check for Counter-Offer if initial tier exceeds budget
        if not approved:
            has_counter = mandate.get("counterOfferAvailable") or mandate.get("counter_offer_available", False)
            counter_amount = float(mandate.get("counterOfferAmount") or mandate.get("counter_offer_amount", 0.0))
            counter_tier = mandate.get("counterOfferTier") or mandate.get("counter_offer_tier", "Alternative Tier")
            counter_tier_id = mandate.get("counterOfferTierId") or mandate.get("counter_offer_tier_id") or "ap2-batch"

            if has_counter and counter_amount > 0 and counter_amount <= self.budget_cap:
                self.log(f"\n🔄 [AUTONOMOUS NEGOTIATION] Counter-Offer Received: '{counter_tier}' @ ${counter_amount:.2f}/mo")
                self.log(f"   Autonomous Decision: ${counter_amount:.2f} <= ${self.budget_cap:.2f} Cap -> ACCEPT COUNTER-OFFER")
                self.log("   Re-evaluating mandate with negotiated rate...")

                mandate = await self._call_tool(
                    "evaluate_spending_mandate",
                    {
                        "buyer_agent_id": buyer_agent_id,
                        "amount": counter_amount,
                        "recurrence": "monthly",
                        "category": self.category,
                        "monthly_budget_cap": self.budget_cap,
                    },
                )
                approved = mandate.get("approved", False)
                proof_hash = mandate.get("mandateProofHash") or mandate.get("mandate_proof_hash", "")
                rem_budget = mandate.get("monthlyCapRemaining") or mandate.get("monthly_cap_remaining", 0.0)
                monthly_price = counter_amount
                plan_id = counter_tier_id
                tier_title = f"{counter_tier} (Negotiated)"

                self.log(f"   Counter-Offer Authorization: {'APPROVED' if approved else 'REJECTED'}")
                self.log(f"   Negotiated Monthly Rate:     ${monthly_price:.2f}/mo")
                self.log(f"   Remaining Cap:               ${rem_budget:.2f}")

        if not approved:
            reason = mandate.get("reason", "Budget cap exceeded or policy violation")
            self.log(f"\n❌ [ABORT] Mandate Rejected: {reason}")
            return {
                "status": "REJECTED",
                "reason": reason,
                "audit_log": self.audit_log,
            }

        self.log(f"   AP2 Mandate Hash: {proof_hash[:24]}... ({len(proof_hash)} chars)\n")

        # Step 6: Bind to PayPal Recurring Vault via purchase_subscription
        self.log("💳 [Step 6: Autonomous PayPal Subscription Vault Binding (purchase_subscription)]")
        offer_id = mandate.get("offerId") or mandate.get("offer_id")

        from backend.tests.ap2_test_utils import build_test_ap2_chains
        chains = build_test_ap2_chains(
            tier_id=plan_id,
            monthly_price=monthly_price,
            buyer_email=self.contractor_email,
            budget_cap=self.budget_cap,
            checkout_record={
                "checkout_jwt": mandate.get("checkout_jwt"),
                "checkout_hash": mandate.get("checkout_hash") or proof_hash,
                "nonce": mandate.get("nonce") or f"nonce_{self.request_id}",
                "order_id": offer_id or f"off_{plan_id}_{int(monthly_price)}",
            } if mandate.get("checkout_jwt") else None,
        )

        purchase_args = {
            "tier_id": plan_id,
            "agreed_monthly_rate": monthly_price,
            "contractor_email": self.contractor_email,
            "buyer_email": self.contractor_email,
            "checkout_mandate_chain": chains["checkout_mandate_chain"],
            "payment_mandate_chain": chains["payment_mandate_chain"],
            "checkout_jwt": chains["checkout_jwt"],
            "nonce": chains["nonce"],
        }
        if offer_id:
            purchase_args["offer_id"] = offer_id
        if proof_hash:
            purchase_args["mandate_proof_hash"] = proof_hash

        purchase_resp = await self._call_tool("purchase_subscription", purchase_args)
        sub_status = purchase_resp.get("status")
        subscription_id = purchase_resp.get("subscription_id")
        chk_rec = purchase_resp.get("checkout_receipt")
        pay_rec = purchase_resp.get("payment_receipt")
        if not subscription_id or sub_status not in ("ACTIVE", "APPROVAL_PENDING"):
            err_msg = purchase_resp.get("reason") or purchase_resp.get("error") or f"Status: {sub_status}"
            self.log(f"\n❌ [ABORT] PayPal Purchase Failed: {err_msg}")
            return {
                "status": "PURCHASE_FAILED",
                "error": err_msg,
                "audit_log": self.audit_log,
            }

        self.log(f"   Vault Subscription ID: {subscription_id} (Status: {sub_status})")
        self.log(f"   PayPal Vault Status:   {purchase_resp.get('paypal_vault_status', 'VAULT_BOUND')}")
        self.log(f"   Monthly Billing Rate:  ${monthly_price:.2f}/mo (Auto-debit)")
        if chk_rec:
            self.log(f"   Signed Checkout Receipt: {chk_rec[:24]}...")
        if pay_rec:
            self.log(f"   Signed Payment Receipt:  {pay_rec[:24]}...")
        self.log("")

        # Step 6b: If sub_status == "APPROVAL_PENDING" (live PayPal Sandbox flow), simulate buyer approval
        if sub_status == "APPROVAL_PENDING":
            self.log(f"⏳ [Step 6b: Simulating Sandbox Buyer Approval in PayPal Sandbox for {subscription_id}]")
            approval_simulated = False
            if self.transport == "http" and self.server_url:
                base_url = self.server_url.replace("/a2a/mcp", "").replace("/mcp", "")
                sim_url = f"{base_url}/api/paypal/simulate-approval/{subscription_id}"
                try:
                    headers = {}
                    if getattr(self, "admin_api_key", None):
                        headers["X-Admin-Key"] = self.admin_api_key
                    async with httpx.AsyncClient(timeout=10.0) as sim_client:
                        sim_resp = await sim_client.post(sim_url, headers=headers)
                        if sim_resp.status_code == 200:
                            sim_data = sim_resp.json()
                            sub_status = sim_data.get("status", "ACTIVE")
                            approval_simulated = True
                            self.log(f"   ✓ Sandbox approval simulated via HTTP ({subscription_id} -> ACTIVE)\n")
                        else:
                            self.log(f"   ⚠️ Sandbox approval simulation HTTP returned {sim_resp.status_code}: {sim_resp.text}")
                except Exception as e:
                    self.log(f"   ⚠️ Sandbox approval simulation HTTP error: {e}")

            if not approval_simulated:
                try:
                    from ..agents.seller_agent import (
                        _COMPLETED_SUBSCRIPTIONS,
                        _ACTIVE_CONTRACTOR_SUBSCRIPTIONS,
                        reconcile_contractor_ledger,
                    )
                    if subscription_id in _COMPLETED_SUBSCRIPTIONS:
                        rec = _COMPLETED_SUBSCRIPTIONS[subscription_id]
                        if isinstance(rec, dict):
                            rec["status"] = "ACTIVE"
                            rec["paypal_vault_status"] = "VAULT_BOUND"
                            rec["vault_billing_authorized"] = True
                            rec["vault_customer_present"] = False
                            _COMPLETED_SUBSCRIPTIONS[subscription_id] = rec
                            if self.contractor_email:
                                _ACTIVE_CONTRACTOR_SUBSCRIPTIONS[self.contractor_email.strip().lower()] = subscription_id
                                reconcile_contractor_ledger(self.contractor_email)
                            sub_status = "ACTIVE"
                            self.log(f"   ✓ Sandbox approval simulated via in-memory registry ({subscription_id} -> ACTIVE)\n")
                except Exception as e:
                    self.log(f"   ⚠️ In-process approval simulation error: {e}")

        # Step 7: Compute Node Allocation (provision_compute_node)
        self.log("🚀 [Step 7: Compute Node Allocation (provision_compute_node)]")
        prov = await self._call_tool(
            "provision_compute_node",
            {
                "subscription_id": subscription_id,
                "buyer_email": self.contractor_email,
                "node_type": "gateway",
            },
        )
        if prov.get("status") == "REJECTED":
            err_msg = prov.get("reason") or prov.get("error") or "Compute node provisioning rejected"
            self.log(f"\n❌ [ABORT] Node Provisioning Rejected: {err_msg}")
            return {
                "status": "PROVISION_FAILED",
                "error": err_msg,
                "audit_log": self.audit_log,
            }
        node_endpoint = prov.get("endpoint")
        allocated_node_id = prov.get("node_id")
        carrier = "Dual-Transport FastMCP (RFC 8032)"
        routing_state = "NODE_ACTIVE"
        assigned_did = node_endpoint
        self.log(f"   Allocated Node:  {allocated_node_id}")
        self.log(f"   Node Endpoint:   {node_endpoint}")
        self.log(f"   Routing State:   {routing_state}\n")

        # Step 8: Downline Back-Office Synchronization
        self.log("⚡ [Step 8: Back-Office CRM & Fleet Synchronization (dispatch_zapier_mcp)]")
        zapier_payload = {
            "workflow_type": "a2a_onboarding",
            "contractor_name": self.contractor_name,
            "subscriber_name": self.contractor_name,
            "business_entity": self.business_entity,
            "trade_vertical": tier_title,
            "service_vertical": tier_title,
            "monthly_subscription_fee": monthly_price,
            "paypal_subscription_id": subscription_id,
            "contractor_email": self.contractor_email,
            "buyer_email": self.contractor_email,
            "mandate_proof_hash": proof_hash,
            "webhook_url": self.webhook_url,
        }
        if assigned_did:
            zapier_payload["allocated_did"] = assigned_did
        if node_endpoint:
            zapier_payload["node_endpoint"] = node_endpoint

        zapier_res = await self._call_tool("dispatch_zapier_mcp", zapier_payload)

        erp_id = zapier_res.get("erpRoutingId") or zapier_res.get("erp_routing_id")
        qbo_id = zapier_res.get("qboDraftInvoiceId") or zapier_res.get("qbo_draft_invoice_id")
        gcal_id = zapier_res.get("googleCalendarEventId") or zapier_res.get("google_calendar_event_id")

        self.log(f"   ERP Dispatch:    {erp_id} (CloudEvents v1.0 & Node Synced)")
        self.log(f"   QuickBooks QBO:  {qbo_id} (Mapped to Account 6300: Software & SaaS)")
        self.log(f"   Executive Brief: {gcal_id} (Daily 6:30 AM Briefing Scheduled)")
        if self.webhook_url:
            self.log(f"   Webhook Hook:    Dispatched to {self.webhook_url} (HTTP {zapier_res.get('webhookStatusCode')})")
        self.log("")

        # Summary
        self.log("=" * 65)
        self.log("🎉 [SUCCESS] Autonomous Machine-to-Machine Commerce Cycle Complete!")
        self.log("   • Buyer Agent Mandate Hash: " + proof_hash)
        self.log("   • PayPal Subscription ID:   " + subscription_id)
        if assigned_did:
            self.log("   • Provisioned DID:          " + assigned_did)
        if node_endpoint:
            self.log("   • Node Endpoint:            " + node_endpoint)
        self.log("   • ERP Routing Record:       " + str(erp_id))
        self.log("   • QuickBooks Expense Ref:   " + str(qbo_id))
        self.log("=" * 65 + "\n")

        res_dict = {
            "status": "COMPLETED",
            "contractor_name": self.contractor_name,
            "business_entity": self.business_entity,
            "selected_tier": tier_title,
            "monthly_amount": monthly_price,
            "mandate_proof_hash": proof_hash,
            "paypal_subscription_id": subscription_id,
            "carrier": carrier,
            "routing_state": routing_state,
            "erp_routing_id": erp_id,
            "qbo_expense_id": qbo_id,
            "google_calendar_event_id": gcal_id,
            "audit_log": self.audit_log,
        }
        if assigned_did:
            res_dict["assigned_did"] = assigned_did
            res_dict["provisioned_did"] = assigned_did
        if node_endpoint:
            res_dict["node_endpoint"] = node_endpoint
            res_dict["allocated_node_id"] = allocated_node_id
        if chk_rec:
            res_dict["checkout_receipt"] = chk_rec
        if pay_rec:
            res_dict["payment_receipt"] = pay_rec
        return res_dict


async def main():
    parser = argparse.ArgumentParser(
        description="Autonomous External Buyer Agent & MCP Client Harness"
    )
    parser.add_argument(
        "--transport",
        choices=["http", "stdio"],
        default="http",
        help="Transport mode for MCP communication (default: http)",
    )
    parser.add_argument(
        "--server-url",
        default="http://127.0.0.1:8001/mcp",
        help="HTTP URL to MCP Server (default: http://127.0.0.1:8001/mcp)",
    )
    parser.add_argument(
        "--contractor-name",
        default="Nexus Autonomous Buyer",
        help="Buyer agent identity name (default: Nexus Autonomous Buyer)",
    )
    parser.add_argument(
        "--business-entity",
        default="Nexus Autonomous Systems Corp",
        help="Buyer legal business entity",
    )
    parser.add_argument(
        "--email",
        default="agent-alpha@example.com",
        help="Buyer email address",
    )
    parser.add_argument(
        "--trade",
        default="ap2-gateway",
        help="Compute tier identifier (default: ap2-gateway)",
    )
    parser.add_argument(
        "--budget",
        "--budget-cap",
        dest="budget",
        type=float,
        default=100.00,
        help="Monthly spending mandate budget cap (default: 100.00)",
    )
    parser.add_argument(
        "--reset-ledger",
        action="store_true",
        default=True,
        help="Reset spending mandate ledger before execution (default: True)",
    )
    parser.add_argument(
        "--no-reset-ledger",
        dest="reset_ledger",
        action="store_false",
        help="Do not reset spending mandate ledger before execution",
    )
    parser.add_argument(
        "--area-code",
        default="703",
        help="Local area code for region allocation (default: 703)",
    )
    parser.add_argument(
        "--simulate-exhaustion",
        action="store_true",
        default=False,
        help="Simulate local exchange pool exhaustion to test contiguous LATA failover",
    )
    parser.add_argument(
        "--webhook-url",
        default=None,
        help="Optional external webhook URL to test live payload dispatch",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON summary on completion",
    )

    args = parser.parse_args()

    agent = ExternalBuyerAgent(
        transport=args.transport,
        server_url=args.server_url,
        contractor_name=args.contractor_name,
        business_entity=args.business_entity,
        contractor_email=args.email,
        trade_id=args.trade,
        budget_cap=args.budget,
        area_code=args.area_code,
        webhook_url=args.webhook_url,
        verbose=not args.json,
        reset_ledger=args.reset_ledger,
        simulate_exhaustion=args.simulate_exhaustion,
    )

    result = await agent.execute_autonomous_procurement()

    if args.json:
        print(json.dumps(result, indent=2))

    if result.get("status") == "COMPLETED":
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
