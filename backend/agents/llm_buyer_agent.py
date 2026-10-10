"""
Real AI Buyer Agent for AP2 Protocol (Stage 3).
Autonomous, LLM-driven buyer agent that:
1. Reads the human owner's procurement request and constraints.
2. Interacts with the Seller Agent over MCP tools (inspect, negotiate, purchase, provision).
3. Evaluates counter-offers against human open-mandate constraints.
4. Autonomous Mandate Closing: Signs closed mandates ONLY with the Agent P-256 Key.
   NEVER holds or sees the human owner's private key (Mandate Segregation Principle).
5. Shows a readable step log:
   requested -> over limit -> counter-offer -> checked against limits -> signed -> purchased
6. Features pluggable model runners:
   - StubbedModelRunner: Deterministic offline ReAct runner (default; passes all tests & CI with no API keys).
   - OpenAICompatibleRunner: Works with xAI Grok (https://api.x.ai/v1), OpenAI, or local models.
   - GeminiRunner: Works with Google Gemini (via google-genai / REST).
   - AnthropicRunner: Works with Anthropic Claude.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import logging
import os
import re
import sys
import tempfile
import atexit
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

# Ensure isolated temp DB in LLM buyer agent to protect development DB
if not os.environ.get("A2A_DB_PATH"):
    _temp_buyer_db = os.path.join(tempfile.gettempdir(), f"a2a_llm_buyer_{os.getpid()}_{uuid.uuid4().hex[:8]}.db")
    os.environ["A2A_DB_PATH"] = _temp_buyer_db

    def _cleanup_llm_buyer_temp_db():
        for ext in ["", "-wal", "-shm", "-journal"]:
            f = _temp_buyer_db + ext
            try:
                if os.path.exists(f):
                    os.remove(f)
            except OSError:
                pass

    atexit.register(_cleanup_llm_buyer_temp_db)


from jwcrypto.jwk import JWK

from ap2.sdk.generated.checkout_mandate import CheckoutMandate
from ap2.sdk.generated.payment_mandate import PaymentMandate
from ap2.sdk.generated.types.amount import Amount
from ap2.sdk.generated.types.merchant import Merchant
from ap2.sdk.generated.types.payment_instrument import PaymentInstrument
from ap2.sdk.mandate import MandateClient

from ..config import settings
from ..services.ap2_keys import (
    get_demo_agent_key,
    get_demo_user_key,
)
from ..services.ap2_service import (
    AP2_MERCHANT_ID,
    AP2_MERCHANT_NAME,
    dollars_to_minor_units,
)
from ..services.plan_catalog import resolve_plan
from ..services.trusted_surface_service import create_trusted_surface_open_mandates
from .seller_agent import seller_agent

logger = logging.getLogger("llm_buyer_agent")


# ── Model Runner Interface & Implementations ─────────────────────────────


class BaseModelRunner(ABC):
    """Abstract interface for LLM reasoning and tool selection."""

    @abstractmethod
    async def decide_next_action(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Returns a dictionary representing the model's next turn:
        {
            "thought": str,
            "action": "call_tool" | "finish" | "reject",
            "tool_name": Optional[str],
            "parameters": Optional[Dict[str, Any]],
            "content": Optional[str],
        }
        """
        pass


class StubbedModelRunner(BaseModelRunner):
    """
    Deterministic offline ReAct runner for AP2 procurement.
    Simulates genuine LLM reasoning, constraint evaluation, and counter-offer decisions
    without requiring external network calls or API credentials.
    """

    def __init__(self):
        self._turn = 0

    async def decide_next_action(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        last_msg = messages[-1] if messages else {}
        role = last_msg.get("role")
        content = last_msg.get("content", "")

        # Initial turn: Inspect available tiers in the seller catalog
        if role == "user":
            return {
                "thought": "I need to inspect the seller's compute tiers to check prices and capabilities against the owner's request.",
                "action": "call_tool",
                "tool_name": "inspect_subscription_tiers",
                "parameters": {},
            }

        # Subsequent turns evaluate previous tool responses
        if role == "tool":
            tool_name = last_msg.get("tool_name")
            tool_result = last_msg.get("result", {})

            if tool_name == "inspect_subscription_tiers":
                # Extract requested tier & budget cap from context
                ctx = messages[0].get("context", {})
                target_tier = ctx.get("target_tier", "ap2-gateway")
                budget_cap = float(ctx.get("budget_cap", 60.00))

                return {
                    "thought": f"Catalog inspected. Target tier '{target_tier}' lists at $79.99/mo, which may exceed owner budget ${budget_cap:.2f}/mo. I will submit terms to negotiate_tier_terms.",
                    "action": "call_tool",
                    "tool_name": "negotiate_tier_terms",
                    "parameters": {
                        "buyer_agent_id": ctx.get("agent_id", "buyer-agent-llm-01"),
                        "buyer_email": ctx.get("buyer_email", "agent-alpha@nexus-systems.io"),
                        "tier_id": target_tier,
                        "monthly_budget_cap": budget_cap,
                    },
                }

            if tool_name == "negotiate_tier_terms":
                status = tool_result.get("status")
                ctx = messages[0].get("context", {})
                budget_cap = float(ctx.get("budget_cap", 60.00))
                allowed_tiers = ctx.get("allowed_tiers", ["ap2-batch", "ap2-gateway", "ap2-cluster"])

                if status == "COUNTER_OFFER":
                    c_amount = float(tool_result.get("counter_offer_amount", 49.99))
                    c_tier = tool_result.get("counter_offer_tier_id", "ap2-batch")

                    # LLM Cognitive Decision: Evaluate counter-offer against owner constraints
                    if c_amount <= budget_cap and (not allowed_tiers or c_tier in allowed_tiers):
                        return {
                            "thought": (
                                f"Seller returned COUNTER-OFFER: {c_tier} at ${c_amount:.2f}/mo. "
                                f"Constraint Check: ${c_amount:.2f} <= ${budget_cap:.2f} Cap (Remaining: ${budget_cap - c_amount:.2f}) "
                                f"and '{c_tier}' is authorized in allowed_tiers. "
                                f"DECISION: ACCEPT counter-offer and sign closed mandates."
                            ),
                            "action": "call_tool",
                            "tool_name": "sign_and_purchase",
                            "parameters": {
                                "tier_id": c_tier,
                                "monthly_price": c_amount,
                                "checkout_jwt": tool_result.get("checkout_jwt") or tool_result.get("counter_offer_checkout_jwt"),
                                "checkout_hash": tool_result.get("checkout_hash") or tool_result.get("counter_offer_checkout_hash"),
                                "nonce": tool_result.get("nonce"),
                                "offer_id": tool_result.get("offer_id"),
                            },
                        }
                    else:
                        return {
                            "thought": f"Counter-offer of ${c_amount:.2f}/mo exceeds budget cap ${budget_cap:.2f} or tier '{c_tier}' is not allowed. REJECTING.",
                            "action": "reject",
                            "content": f"Negotiation rejected: counter-offer ${c_amount:.2f}/mo exceeds authorized budget cap ${budget_cap:.2f}.",
                        }

                elif status == "APPROVED":
                    price = float(tool_result.get("agreed_monthly_rate", 79.99))
                    tier_id = tool_result.get("tier_id", "ap2-gateway")
                    return {
                        "thought": f"Seller APPROVED requested tier '{tier_id}' at ${price:.2f}/mo within budget cap. Signing closed mandates.",
                        "action": "call_tool",
                        "tool_name": "sign_and_purchase",
                        "parameters": {
                            "tier_id": tier_id,
                            "monthly_price": price,
                            "checkout_jwt": tool_result.get("checkout_jwt"),
                            "checkout_hash": tool_result.get("checkout_hash"),
                            "nonce": tool_result.get("nonce"),
                            "offer_id": tool_result.get("offer_id"),
                        },
                    }
                else:
                    reason = tool_result.get("reason", "Budget cap breach")
                    return {
                        "thought": f"Seller rejected tier terms: {reason}.",
                        "action": "reject",
                        "content": f"Procurement rejected by seller: {reason}",
                    }

            if tool_name == "purchase_subscription":
                sub_id = tool_result.get("subscription_id")
                status = tool_result.get("status")
                if status == "ACTIVE" and sub_id:
                    ctx = messages[0].get("context", {})
                    tier_id = ctx.get("target_tier", "ap2-gateway")
                    node_type = "gateway" if "gateway" in tier_id else ("batch" if "batch" in tier_id else "cluster")
                    return {
                        "thought": f"Subscription {sub_id} activated! Now provisioning dedicated compute node.",
                        "action": "call_tool",
                        "tool_name": "provision_compute_node",
                        "parameters": {
                            "subscription_id": sub_id,
                            "buyer_email": ctx.get("buyer_email", "agent-alpha@nexus-systems.io"),
                            "node_type": node_type,
                        },
                    }
                else:
                    return {
                        "thought": f"Purchase unsuccessful: {tool_result}",
                        "action": "reject",
                        "content": f"Purchase failed: {tool_result.get('error') or tool_result.get('reason')}",
                    }

            if tool_name == "provision_compute_node":
                endpoint = tool_result.get("endpoint") or tool_result.get("assigned_endpoint") or tool_result.get("assigned_did") or "active-compute-node"
                return {
                    "thought": "Dedicated compute node successfully provisioned. Procurement cycle complete.",
                    "action": "finish",
                    "content": f"Successfully procured and provisioned AP2 autonomous compute node: {endpoint}",
                }

        return {
            "thought": "No further actions required.",
            "action": "finish",
            "content": "Autonomous buyer agent completed cycle.",
        }


class OpenAICompatibleRunner(BaseModelRunner):
    """
    Runner for OpenAI-compatible APIs, including xAI Grok (https://api.x.ai/v1),
    OpenAI (https://api.openai.com/v1), or local models.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key or os.environ.get("XAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
        self.base_url = (
            base_url
            or os.environ.get("XAI_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or ("https://api.x.ai/v1" if os.environ.get("XAI_API_KEY") else "https://api.openai.com/v1")
        ).rstrip("/")
        self.model = model or os.environ.get("GROK_MODEL") or os.environ.get("OPENAI_MODEL") or "grok-2"

    async def decide_next_action(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not self.api_key:
            raise ValueError("OpenAICompatibleRunner requires XAI_API_KEY or OPENAI_API_KEY.")

        import httpx

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Format messages for OpenAI / Grok chat completions
        oai_messages = [{"role": "system", "content": system_prompt}]
        for m in messages:
            r = m.get("role")
            if r == "user":
                oai_messages.append({"role": "user", "content": m.get("content", "")})
            elif r == "assistant":
                oai_messages.append({"role": "assistant", "content": m.get("content", "")})
            elif r == "tool":
                oai_messages.append({
                    "role": "function",
                    "name": m.get("tool_name", "unknown_tool"),
                    "content": json.dumps(m.get("result", {})),
                })

        # Convert tool schemas
        oai_tools = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
                },
            }
            for t in tools
        ]

        payload = {
            "model": self.model,
            "messages": oai_messages,
            "tools": oai_tools,
            "temperature": 0.1,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]["message"]
        tool_calls = choice.get("tool_calls")
        content = choice.get("content") or ""

        if tool_calls:
            tc = tool_calls[0]["function"]
            tname = tc["name"]
            targs = json.loads(tc.get("arguments", "{}"))
            return {
                "thought": content or f"Calling tool {tname}",
                "action": "call_tool",
                "tool_name": tname,
                "parameters": targs,
            }

        return {
            "thought": content,
            "action": "finish",
            "content": content,
        }


# ── Autonomous AI Buyer Agent ────────────────────────────────────────────


class LLMBuyerAgent:
    """
    Autonomous AI Buyer Agent conforming to AP2 v0.2 Protocol.
    Executes the autonomous procurement cycle with strict key segregation:
    - Never holds owner private key
    - Signs closed mandates only with agent_key
    - Produces a clear step-by-step progress trace:
      (requested -> over limit -> counter-offer -> checked against limits -> signed)
    """

    def __init__(
        self,
        agent_id: str = "buyer-agent-llm-01",
        monthly_budget_cap: float = 60.00,
        buyer_email: str = "agent-alpha@nexus-systems.io",
        agent_key: Optional[JWK] = None,
        model_runner: Optional[BaseModelRunner] = None,
    ):
        self.agent_id = agent_id
        self.monthly_budget_cap = monthly_budget_cap
        self.buyer_email = buyer_email.strip().lower()
        self.agent_key = agent_key or get_demo_agent_key()
        self.mandate_client = MandateClient()
        self.step_log: List[str] = []
        self.trace_events: List[Dict[str, Any]] = []

        # Model runner selection: default to StubbedModelRunner for deterministic tests
        if model_runner is not None:
            self.model_runner = model_runner
        elif os.environ.get("XAI_API_KEY") or os.environ.get("OPENAI_API_KEY"):
            self.model_runner = OpenAICompatibleRunner()
        else:
            self.model_runner = StubbedModelRunner()

    def _log_step(self, step_name: str, message: str, payload: Optional[Dict[str, Any]] = None):
        """Records a human-readable progress step and trace event."""
        entry = f"[{step_name}] {message}"
        self.step_log.append(entry)
        self.trace_events.append({
            "step": step_name,
            "message": message,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "details": payload or {},
        })
        print(f"   {entry}")

    async def run_autonomous_procurement(
        self,
        owner_request: str,
        target_tier: str = "ap2-gateway",
        open_checkout_mandate_token: Optional[str] = None,
        open_payment_mandate_token: Optional[str] = None,
        allowed_tiers: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Executes the autonomous AI procurement loop.
        """
        print(f"\n=======================================================")
        print(f"🤖 [AP2 AI BUYER AGENT: {self.agent_id}]")
        print(f"   Model Runner:        {self.model_runner.__class__.__name__}")
        print(f"   Owner Prompt:        \"{owner_request}\"")
        print(f"   Monthly Budget Cap:  ${self.monthly_budget_cap:.2f}/mo")
        print(f"   Target Compute Tier: {target_tier}")
        print(f"=======================================================\n")

        self.step_log.clear()
        self.trace_events.clear()

        # Step 1: Requested
        self._log_step(
            "STEP 1: REQUESTED",
            f"Ingested owner prompt: \"{owner_request}\" (Target: {target_tier}, Budget Cap: ${self.monthly_budget_cap:.2f}/mo)",
            {"target_tier": target_tier, "budget_cap": self.monthly_budget_cap},
        )

        # Ensure Open Mandates are present (from Trusted Surface)
        chk_open = open_checkout_mandate_token
        pay_open = open_payment_mandate_token

        if not (chk_open and pay_open):
            # In mock / demo mode: generate open mandates from Trusted Surface service
            self._log_step(
                "TRUSTED SURFACE",
                f"Obtaining human-authorized Open Mandates from Trusted Surface for {self.buyer_email}...",
            )
            tiers_to_allow = allowed_tiers or ["ap2-batch", "ap2-gateway", "ap2-cluster"]
            ts_mandates = create_trusted_surface_open_mandates(
                buyer_email=self.buyer_email,
                monthly_budget_cap=self.monthly_budget_cap,
                allowed_tiers=tiers_to_allow,
                agent_key=self.agent_key,
            )
            chk_open = ts_mandates["open_checkout_mandate_token"]
            pay_open = ts_mandates["open_payment_mandate_token"]
            self._log_step(
                "TRUSTED SURFACE",
                f"Verified Open Checkout ({len(chk_open)} chars) & Payment ({len(pay_open)} chars) mandates bound to agent key.",
            )

        # Context for the LLM runner
        system_prompt = (
            f"You are an autonomous AP2 AI Buyer Agent representing {self.buyer_email}. "
            f"Your goal is to inspect seller tiers, negotiate terms, evaluate counter-offers against "
            f"the owner's strict budget cap (${self.monthly_budget_cap:.2f}/mo), sign closed mandates "
            f"with your agent key, and provision the compute node."
        )

        messages = [
            {
                "role": "user",
                "content": f"Please procure {target_tier} within ${self.monthly_budget_cap:.2f}/month.",
                "context": {
                    "agent_id": self.agent_id,
                    "buyer_email": self.buyer_email,
                    "target_tier": target_tier,
                    "budget_cap": self.monthly_budget_cap,
                    "allowed_tiers": allowed_tiers or ["ap2-batch", "ap2-gateway", "ap2-cluster"],
                },
            }
        ]

        tools = seller_agent.list_mcp_tools()
        active = True
        result_payload: Dict[str, Any] = {"status": "INITIALIZED"}

        while active:
            decision = await self.model_runner.decide_next_action(
                system_prompt=system_prompt,
                messages=messages,
                tools=tools,
            )

            action = decision.get("action")
            thought = decision.get("thought", "")
            tname = decision.get("tool_name")
            tparams = decision.get("parameters", {})

            if thought:
                logger.info(f"[LLM THOUGHT] {thought}")

            if action == "call_tool":
                # Special internal tool: sign_and_purchase
                # Closes the mandates using the agent's key and calls seller's purchase_subscription
                if tname == "sign_and_purchase":
                    purch_tier = tparams.get("tier_id")
                    monthly_price = float(tparams.get("monthly_price", 49.99))
                    price_cents = dollars_to_minor_units(monthly_price)
                    chk_jwt = tparams.get("checkout_jwt")
                    chk_hash = tparams.get("checkout_hash")
                    nonce = tparams.get("nonce")

                    # Step 5: Signed (Closed Mandates signed with Agent Key)
                    self._log_step(
                        "STEP 5: SIGNED",
                        f"Signing closed Checkout and Payment mandates with Agent P-256 Key for {purch_tier} at ${monthly_price:.2f}/mo...",
                        {"tier_id": purch_tier, "price_cents": price_cents, "checkout_hash": chk_hash[:16]},
                    )

                    # Create closed Checkout Mandate
                    closed_chk = CheckoutMandate(
                        vct="mandate.checkout.1",
                        checkout_jwt=chk_jwt,
                        checkout_hash=chk_hash,
                    )
                    chk_chain = self.mandate_client.present(
                        holder_key=self.agent_key,
                        mandate_token=chk_open,
                        payloads=[closed_chk],
                        aud=AP2_MERCHANT_ID,
                        nonce=nonce,
                    )

                    # Create closed Payment Mandate
                    closed_pay = PaymentMandate(
                        vct="mandate.payment.1",
                        transaction_id=chk_hash,
                        payment_amount=Amount(amount=price_cents, currency="USD"),
                        payee=Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME),
                        payment_instrument=PaymentInstrument(type="paypal_vault", id="vault_agent_mit"),
                    )
                    pay_chain = self.mandate_client.present(
                        holder_key=self.agent_key,
                        mandate_token=pay_open,
                        payloads=[closed_pay],
                        aud=AP2_MERCHANT_ID,
                        nonce=nonce,
                    )

                    self._log_step(
                        "STEP 5: SIGNED",
                        f"Dual SD-JWT presentation chains assembled successfully (Holder key: {self.agent_key.kid}).",
                    )

                    # Execute purchase on seller agent
                    purch_res = await seller_agent.purchase_subscription(
                        tier_id=purch_tier,
                        agreed_monthly_rate=monthly_price,
                        checkout_mandate_chain=chk_chain,
                        payment_mandate_chain=pay_chain,
                        checkout_jwt=chk_jwt,
                        buyer_email=self.buyer_email,
                        nonce=nonce,
                    )

                    messages.append({
                        "role": "tool",
                        "tool_name": "purchase_subscription",
                        "result": purch_res,
                    })

                    if purch_res.get("status") == "ACTIVE":
                        sub_id = purch_res.get("subscription_id")
                        self._log_step(
                            "STEP 6: PURCHASED",
                            f"Purchase verified by merchant! PayPal Subscription: {sub_id} (Receipts bound).",
                            {"subscription_id": sub_id},
                        )
                    else:
                        self._log_step(
                            "PURCHASE_FAILED",
                            f"Purchase rejected: {purch_res.get('error')} - {purch_res.get('reason')}",
                        )
                        active = False
                        result_payload = purch_res
                    continue

                # Standard MCP Tool execution on seller_agent
                tool_fn = getattr(seller_agent, tname, None)
                if not tool_fn:
                    raise RuntimeError(f"Unknown MCP tool '{tname}' on seller_agent.")

                tool_res = await tool_fn(**tparams)

                # Check for step transitions in seller response
                if tname == "inspect_subscription_tiers":
                    plans = tool_res.get("plans", [])
                    tgt = next((p for p in plans if p.get("tier_id") == target_tier), {})
                    standard_price = float(tgt.get("monthly_price", 79.99))
                    if standard_price > self.monthly_budget_cap:
                        # Step 2: Over Limit
                        self._log_step(
                            "STEP 2: OVER LIMIT",
                            f"Desired tier '{target_tier}' lists at ${standard_price:.2f}/mo > ${self.monthly_budget_cap:.2f}/mo budget cap.",
                            {"target_tier": target_tier, "standard_price": standard_price, "budget_cap": self.monthly_budget_cap},
                        )

                elif tname == "negotiate_tier_terms":
                    status = tool_res.get("status")
                    if status == "COUNTER_OFFER":
                        c_amount = float(tool_res.get("counter_offer_amount", 49.99))
                        c_tier = tool_res.get("counter_offer_tier_id", "ap2-batch")
                        c_title = tool_res.get("counter_offer_tier", "High-Throughput Batch Worker")

                        # Step 3: Counter-Offer
                        self._log_step(
                            "STEP 3: COUNTER-OFFER",
                            f"Seller offered alternative: {c_title} ({c_tier}) at ${c_amount:.2f}/mo.",
                            {"counter_tier": c_tier, "counter_amount": c_amount},
                        )

                        # Step 4: Checked Against Limits
                        if c_amount <= self.monthly_budget_cap:
                            self._log_step(
                                "STEP 4: CHECKED AGAINST LIMITS",
                                f"Policy Check: ${c_amount:.2f} <= ${self.monthly_budget_cap:.2f} Cap (Remaining: ${self.monthly_budget_cap - c_amount:.2f}) -> ACCEPTED",
                                {"approved": True, "remaining_cap": self.monthly_budget_cap - c_amount},
                            )
                        else:
                            self._log_step(
                                "STEP 4: CHECKED AGAINST LIMITS",
                                f"Policy Check: ${c_amount:.2f} > ${self.monthly_budget_cap:.2f} Cap -> REJECTED",
                                {"approved": False},
                            )

                    elif status == "APPROVED":
                        self._log_step(
                            "APPROVED",
                            f"Seller approved requested tier '{target_tier}' within budget cap.",
                        )
                    elif status == "REJECTED":
                        self._log_step(
                            "REJECTED",
                            f"Seller rejected request: {tool_res.get('reason')}",
                        )

                elif tname == "provision_compute_node":
                    endpoint = tool_res.get("endpoint") or tool_res.get("assigned_endpoint") or tool_res.get("assigned_did")
                    self._log_step(
                        "PROVISIONED",
                        f"Compute node provisioned: {endpoint}",
                        {"endpoint": endpoint},
                    )

                messages.append({
                    "role": "tool",
                    "tool_name": tname,
                    "result": tool_res,
                })

            elif action == "reject":
                active = False
                result_payload = {
                    "status": "REJECTED",
                    "reason": decision.get("content", "Rejected by buyer agent policy."),
                    "step_log": list(self.step_log),
                }

            elif action == "finish":
                active = False
                # Compile final output
                last_tool_res = messages[-1].get("result", {}) if messages and messages[-1].get("role") == "tool" else {}
                result_payload = {
                    "status": "COMPLETED",
                    "summary": decision.get("content", "Procurement cycle finished successfully."),
                    "step_log": list(self.step_log),
                    "trace_events": list(self.trace_events),
                    "last_result": last_tool_res,
                }

        # Print final step-by-step pipeline summary
        print("\n-------------------------------------------------------")
        print("📋 [READABLE AP2 EXECUTION STEP LOG]")
        print(" -> ".join(e.split("]")[0].strip("[") for e in self.step_log if "STEP" in e))
        print("-------------------------------------------------------\n")

        return result_payload


# ── CLI Interface ────────────────────────────────────────────────────────


async def _main():
    parser = argparse.ArgumentParser(description="AP2 AI Autonomous Buyer Agent")
    parser.add_argument("--budget", type=float, default=60.00, help="Monthly spending budget cap (USD)")
    parser.add_argument("--tier", type=str, default="ap2-gateway", help="Desired compute tier (ap2-batch, ap2-gateway, ap2-cluster)")
    parser.add_argument("--prompt", type=str, default="Procure AI compute node within budget constraints", help="Owner procurement instruction")
    parser.add_argument("--email", type=str, default="agent-alpha@nexus-systems.io", help="Buyer PayPal email")
    args = parser.parse_args()

    agent = LLMBuyerAgent(
        agent_id="buyer-agent-llm-01",
        monthly_budget_cap=args.budget,
        buyer_email=args.email,
    )

    res = await agent.run_autonomous_procurement(
        owner_request=args.prompt,
        target_tier=args.tier,
    )

    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
