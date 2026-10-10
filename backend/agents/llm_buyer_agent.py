"""
Real AI Buyer Agent for AP2 Protocol (Stage 3).
Autonomous, LLM-driven buyer agent that:
1. Reads the human owner's procurement request and constraints.
2. Interacts with the Seller Agent over MCP tools (inspect, negotiate, purchase, provision).
3. Evaluates counter-offers against human open-mandate constraints.
4. Autonomous Mandate Closing: Signs closed presentation mandates ONLY with the Agent P-256 Key.
   NEVER holds or sees the human owner's private key (Mandate Segregation Principle).
5. Deterministic Pre-Signature Guard: Decodes open mandates and validates LineItems, AmountRange,
   payee, currency, and Checkout JWT match before every signature on every path.
6. Shows a readable step log:
   requested -> over limit -> counter-offer -> checked against limits -> signed -> purchased
7. Model Runners:
   - StubbedModelRunner: Deterministic offline ReAct runner (default; passes all tests & CI with no API keys).
   - OpenAICompatibleRunner: Connects to any OpenAI-compatible HTTP endpoint. Requires explicit --model and --base-url.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import logging
import os
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
from ap2.sdk.sdjwt import common
from ap2.sdk.utils import b64url_decode

from ..config import settings
from ..services.ap2_keys import get_demo_agent_key
from ..services.ap2_service import (
    AP2_MERCHANT_ID,
    AP2_MERCHANT_NAME,
    dollars_to_minor_units,
    minor_units_to_dollars,
)
from ..services.plan_catalog import resolve_plan
from .seller_agent import seller_agent


def decode_jwt_unverified(token: str) -> Dict[str, Any]:
    """Decodes a JWT payload without verification for inspection."""
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        return common.decode_jwt_segment(parts[1], "payload")
    except Exception:
        return {}


logger = logging.getLogger("llm_buyer_agent")

ALLOWED_BUYER_TOOLS = {
    "get_service_catalog",
    "inspect_subscription_tiers",
    "negotiate_tier_terms",
    "evaluate_spending_mandate",
    "purchase_subscription",
    "provision_compute_node",
    "dispatch_zapier_mcp",
    "get_subscription_details",
    "sign_and_purchase",
}

SIGN_AND_PURCHASE_TOOL = {
    "name": "sign_and_purchase",
    "description": "Cryptographically signs closed Checkout and Payment mandates using the Agent P-256 key within human limits, and executes subscription purchase.",
    "input_schema": {
        "type": "object",
        "properties": {
            "tier_id": {"type": "string", "description": "The approved or counter-offered compute tier ID (e.g. ap2-gateway, ap2-batch)"},
            "monthly_price": {"type": "number", "description": "Agreed monthly subscription price in USD"},
            "checkout_jwt": {"type": "string", "description": "Merchant-signed checkout JWT"},
            "checkout_hash": {"type": "string", "description": "SHA-256 checkout hash"},
            "nonce": {"type": "string", "description": "Cryptographic order nonce from merchant"},
            "offer_id": {"type": "string", "description": "Negotiated offer identifier"},
        },
        "required": ["tier_id", "monthly_price", "checkout_jwt", "checkout_hash", "nonce"],
    },
}


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
            "tool_call_id": Optional[str],
            "parameters": Optional[Dict[str, Any]],
            "content": Optional[str],
        }
        """
        pass


class StubbedModelRunner(BaseModelRunner):
    """
    Deterministic offline ReAct runner for AP2 procurement.
    Simulates LLM reasoning, constraint evaluation, and counter-offer decisions
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

        # Initial turn: Inspect available tiers in the seller catalog
        if role == "user":
            return {
                "thought": "I need to inspect the seller's compute tiers to check prices and capabilities against the owner's request.",
                "action": "call_tool",
                "tool_name": "inspect_subscription_tiers",
                "tool_call_id": f"call_inspect_{uuid.uuid4().hex[:8]}",
                "parameters": {},
            }

        # Subsequent turns evaluate previous tool responses
        if role == "tool":
            tool_name = last_msg.get("tool_name")
            tool_result = last_msg.get("result", {})

            if tool_name == "inspect_subscription_tiers":
                ctx = messages[0].get("context", {})
                target_tier = ctx.get("target_tier", "ap2-gateway")
                budget_cap = float(ctx.get("budget_cap", 60.00))

                return {
                    "thought": f"Catalog inspected. Target tier '{target_tier}' lists at $79.99/mo, which may exceed owner budget ${budget_cap:.2f}/mo. I will submit terms to negotiate_tier_terms.",
                    "action": "call_tool",
                    "tool_name": "negotiate_tier_terms",
                    "tool_call_id": f"call_negotiate_{uuid.uuid4().hex[:8]}",
                    "parameters": {
                        "buyer_agent_id": ctx.get("agent_id", "buyer-agent-llm-01"),
                        "buyer_email": ctx.get("buyer_email", "agent-alpha@example.com"),
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
                            "tool_call_id": f"call_sign_{uuid.uuid4().hex[:8]}",
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
                        "tool_call_id": f"call_sign_{uuid.uuid4().hex[:8]}",
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

            if tool_name == "sign_and_purchase" or tool_name == "purchase_subscription":
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
                        "tool_call_id": f"call_provision_{uuid.uuid4().hex[:8]}",
                        "parameters": {
                            "subscription_id": sub_id,
                            "buyer_email": ctx.get("buyer_email", "agent-alpha@example.com"),
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
    Runner for OpenAI-compatible endpoints.
    Requires explicit --model and --base-url. No default provider or model is assumed.
    """

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: Optional[str] = None,
    ):
        if not model or not base_url:
            raise ValueError("OpenAICompatibleRunner requires explicit 'model' and 'base_url'.")
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("XAI_API_KEY") or "mock-key"

    async def decide_next_action(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        import httpx

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Format messages conforming to standard OpenAI Chat Completions API
        oai_messages = [{"role": "system", "content": system_prompt}]
        for m in messages:
            r = m.get("role")
            if r == "user":
                oai_messages.append({"role": "user", "content": m.get("content", "")})
            elif r == "assistant":
                msg_dict = {"role": "assistant", "content": m.get("content")}
                if m.get("tool_calls"):
                    msg_dict["tool_calls"] = m["tool_calls"]
                oai_messages.append(msg_dict)
            elif r == "tool":
                oai_messages.append({
                    "role": "tool",
                    "tool_call_id": m.get("tool_call_id", f"call_{uuid.uuid4().hex[:8]}"),
                    "content": json.dumps(m.get("result", {})),
                })

        # Convert tool schemas (including sign_and_purchase)
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
            "temperature": 0.0,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]["message"]
        tool_calls = choice.get("tool_calls")
        content = choice.get("content") or ""

        if tool_calls:
            tc = tool_calls[0]
            call_id = tc.get("id") or f"call_{uuid.uuid4().hex[:8]}"
            fn = tc["function"]
            tname = fn["name"]
            targs = json.loads(fn.get("arguments", "{}"))
            return {
                "thought": content or f"Calling tool {tname}",
                "action": "call_tool",
                "tool_name": tname,
                "tool_call_id": call_id,
                "parameters": targs,
                "raw_tool_calls": tool_calls,
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
    - Never holds or imports the human owner's private key.
    - Requires human-authorized open spending mandates as input.
    - Deterministically validates all constraints before creating any signature.
    - Signs closed presentation mandates only with agent_key.
    - Produces a clear step-by-step progress trace.
    """

    def __init__(
        self,
        agent_id: str = "buyer-agent-llm-01",
        monthly_budget_cap: float = 60.00,
        buyer_email: str = "agent-alpha@example.com",
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
        self.signatures_produced: int = 0
        self.model_runner = model_runner or StubbedModelRunner()

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

    def _verify_pre_signature_constraints(
        self,
        purch_tier: str,
        monthly_price: float,
        chk_jwt: Optional[str],
        open_chk_tok: str,
        open_pay_tok: str,
    ) -> Tuple[bool, str]:
        """
        Deterministic check before every signature on every path.
        Decodes the open mandates and confirms:
        - the tier is in LineItems;
        - the price is at most AmountRange.max;
        - the payee is allowed;
        - the currency is USD;
        - the tier and price match the merchant-signed Checkout JWT.
        If any check fails, returns (False, reason).
        """
        try:
            price_cents = dollars_to_minor_units(monthly_price)

            def extract_claims(tok: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
                parsed = common.parse_token(tok)
                claims = dict(parsed.payload)
                objs = []
                for d in parsed.disclosures:
                    try:
                        raw = b64url_decode(d)
                        arr = json.loads(raw)
                        if isinstance(arr, list):
                            if len(arr) == 3 and isinstance(arr[1], str):
                                claims[arr[1]] = arr[2]
                            elif len(arr) == 2 and isinstance(arr[1], dict):
                                if "vct" in arr[1] or "constraints" in arr[1]:
                                    claims.update(arr[1])
                                objs.append(arr[1])
                    except Exception:
                        pass
                return claims, objs

            # 1. Decode Open Checkout Mandate claims
            chk_claims, chk_objs = extract_claims(open_chk_tok)
            allowed_line_items = []
            allowed_merchants = []

            for obj in chk_objs:
                oid = obj.get("id")
                if oid:
                    if "batch" in oid or "gateway" in oid or "cluster" in oid:
                        allowed_line_items.append(oid.strip().lower())
                    elif "merchant" in oid:
                        allowed_merchants.append(oid)

            for c in chk_claims.get("constraints", []):
                ctype = c.get("type", "") if isinstance(c, dict) else getattr(c, "type", "")
                if ctype == "checkout.line_items":
                    items = c.get("items", []) if isinstance(c, dict) else getattr(c, "items", [])
                    for req in items:
                        acc = req.get("acceptable_items", []) if isinstance(req, dict) else getattr(req, "acceptable_items", [])
                        for it in acc:
                            iid = it.get("id") if isinstance(it, dict) else getattr(it, "id", None)
                            if iid:
                                allowed_line_items.append(iid.strip().lower())
                elif ctype == "checkout.allowed_merchants":
                    merchants = c.get("allowed", []) or c.get("merchants", []) if isinstance(c, dict) else getattr(c, "allowed", [])
                    for m in merchants:
                        mid = m.get("id") if isinstance(m, dict) else getattr(m, "id", None)
                        if mid:
                            allowed_merchants.append(mid)

            if allowed_line_items and purch_tier.lower() not in allowed_line_items:
                return False, f"TIER_NOT_IN_LINE_ITEMS: Tier '{purch_tier}' is not in permitted LineItems ({allowed_line_items})."

            if allowed_merchants and AP2_MERCHANT_ID not in allowed_merchants:
                return False, f"MERCHANT_NOT_ALLOWED: Merchant '{AP2_MERCHANT_ID}' not in allowed_merchants."

            # 2. Decode Open Payment Mandate claims
            pay_claims, pay_objs = extract_claims(open_pay_tok)
            amount_range_max_cents = None
            amount_currency = None
            allowed_payees = []

            for obj in pay_objs:
                oid = obj.get("id")
                if oid and "merchant" in oid:
                    allowed_payees.append(oid)

            for c in pay_claims.get("constraints", []):
                ctype = c.get("type", "") if isinstance(c, dict) else getattr(c, "type", "")
                if ctype == "payment.amount_range":
                    amount_range_max_cents = c.get("max") if isinstance(c, dict) else getattr(c, "max", None)
                    amount_currency = c.get("currency") if isinstance(c, dict) else getattr(c, "currency", None)
                elif ctype == "payment.allowed_payees":
                    payees = c.get("allowed", []) if isinstance(c, dict) else getattr(c, "allowed", [])
                    for p in payees:
                        pid = p.get("id") if isinstance(p, dict) else getattr(p, "id", None)
                        if pid:
                            allowed_payees.append(pid)

            if amount_currency and amount_currency.upper() != "USD":
                return False, f"CURRENCY_MISMATCH: Mandate currency is '{amount_currency}', expected 'USD'."

            if amount_range_max_cents is not None and price_cents > amount_range_max_cents:
                return False, f"AMOUNT_RANGE_EXCEEDED: Price {price_cents} cents (${monthly_price:.2f}) exceeds AmountRange.max {amount_range_max_cents} cents."

            if allowed_payees and AP2_MERCHANT_ID not in allowed_payees:
                return False, f"PAYEE_NOT_ALLOWED: Payee '{AP2_MERCHANT_ID}' not in allowed_payees ({allowed_payees})."

            # 3. Decode and verify merchant-signed Checkout JWT match
            if not chk_jwt:
                return False, "MISSING_CHECKOUT_JWT: Merchant checkout JWT is required to verify tier and price integrity."

            chk_payload = decode_jwt_unverified(chk_jwt)
            chk_line_items = chk_payload.get("line_items", [])
            chk_tier = None
            if chk_line_items:
                first_item = chk_line_items[0]
                chk_tier = first_item.get("item", {}).get("id") or first_item.get("id")
            if chk_tier and chk_tier.strip().lower() != purch_tier.strip().lower():
                return False, f"CHECKOUT_TIER_MISMATCH: Checkout JWT tier '{chk_tier}' does not match purchase tier '{purch_tier}'."

            chk_totals = chk_payload.get("totals", [])
            chk_total_cents = None
            for tot in chk_totals:
                if tot.get("type") == "total":
                    chk_total_cents = tot.get("amount")
                    break
            if chk_total_cents is not None and chk_total_cents != price_cents:
                return False, f"CHECKOUT_PRICE_MISMATCH: Checkout JWT total ({chk_total_cents} cents) does not match purchase price ({price_cents} cents)."

            chk_currency = chk_payload.get("currency", "USD")
            if chk_currency.upper() != "USD":
                return False, f"CHECKOUT_CURRENCY_MISMATCH: Checkout JWT currency '{chk_currency}' is not 'USD'."

            return True, "Pre-signature constraints verified successfully."
        except Exception as e:
            return False, f"CONSTRAINT_VERIFICATION_ERROR: {e}"

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
        Requires open mandates as input. The agent cannot mint its own open mandates.
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
        self.signatures_produced = 0

        # Step 1: Requested
        self._log_step(
            "STEP 1: REQUESTED",
            f"Ingested owner prompt: \"{owner_request}\" (Target: {target_tier}, Budget Cap: ${self.monthly_budget_cap:.2f}/mo)",
            {"target_tier": target_tier, "budget_cap": self.monthly_budget_cap},
        )

        # Invariant 4a: Open mandates MUST be provided as input
        chk_open = open_checkout_mandate_token
        pay_open = open_payment_mandate_token

        if not (chk_open and pay_open):
            raise ValueError(
                "OPEN_MANDATES_REQUIRED: Both open_checkout_mandate_token and open_payment_mandate_token "
                "must be supplied. The AI Buyer Agent cannot mint its own open spending mandates."
            )

        self._log_step(
            "TRUSTED SURFACE",
            f"Loaded human-authorized Open Mandates from Trusted Surface for {self.buyer_email}.",
        )

        system_prompt = (
            f"You are an autonomous AP2 AI Buyer Agent representing {self.buyer_email}. "
            f"Your goal is to inspect seller tiers, negotiate terms, evaluate counter-offers against "
            f"the owner's strict budget cap (${self.monthly_budget_cap:.2f}/mo), sign closed presentation "
            f"mandates with your agent key via sign_and_purchase, and provision the compute node."
        )

        messages: List[Dict[str, Any]] = [
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

        # Prepare tools list: seller MCP tools plus sign_and_purchase tool schema
        mcp_tools = list(seller_agent.list_mcp_tools())
        all_tools = mcp_tools + [SIGN_AND_PURCHASE_TOOL]

        active = True
        result_payload: Dict[str, Any] = {"status": "INITIALIZED"}

        while active:
            decision = await self.model_runner.decide_next_action(
                system_prompt=system_prompt,
                messages=messages,
                tools=all_tools,
            )

            action = decision.get("action")
            thought = decision.get("thought", "")
            tname = decision.get("tool_name")
            tool_call_id = decision.get("tool_call_id") or f"call_{uuid.uuid4().hex[:8]}"
            tparams = decision.get("parameters", {})

            if thought:
                logger.info(f"[LLM THOUGHT] {thought}")

            if action == "call_tool":
                # Security Guard: Allowlist callable tools
                if tname not in ALLOWED_BUYER_TOOLS:
                    reason = f"Tool '{tname}' is not in the allowlist of permitted buyer tools."
                    self._log_step("TOOL_REJECTED", f"Security Guard: {reason}")
                    active = False
                    result_payload = {
                        "status": "REJECTED",
                        "error": "UNAUTHORIZED_TOOL",
                        "reason": reason,
                        "step_log": list(self.step_log),
                    }
                    continue

                # Add assistant message with tool_calls conforming to OpenAI spec
                messages.append({
                    "role": "assistant",
                    "content": thought or None,
                    "tool_calls": [
                        {
                            "id": tool_call_id,
                            "type": "function",
                            "function": {
                                "name": tname,
                                "arguments": json.dumps(tparams),
                            },
                        }
                    ],
                })

                if tname == "sign_and_purchase":
                    purch_tier = tparams.get("tier_id")
                    monthly_price = float(tparams.get("monthly_price", 49.99))
                    price_cents = dollars_to_minor_units(monthly_price)
                    chk_jwt = tparams.get("checkout_jwt")
                    chk_hash = tparams.get("checkout_hash")
                    nonce = tparams.get("nonce")

                    # Deterministic Pre-Signature Guard
                    valid, reason = self._verify_pre_signature_constraints(
                        purch_tier=purch_tier,
                        monthly_price=monthly_price,
                        chk_jwt=chk_jwt,
                        open_chk_tok=chk_open,
                        open_pay_tok=pay_open,
                    )
                    if not valid:
                        self._log_step("POLICY_VIOLATION", f"Pre-signature constraint verification failed: {reason}")
                        active = False
                        result_payload = {
                            "status": "REJECTED",
                            "error": "PRE_SIGNATURE_CONSTRAINT_VIOLATION",
                            "reason": reason,
                            "signatures_produced": self.signatures_produced,
                            "step_log": list(self.step_log),
                        }
                        messages.append({
                            "role": "tool",
                            "tool_name": "sign_and_purchase",
                            "tool_call_id": tool_call_id,
                            "result": {"status": "REJECTED", "error": reason},
                        })
                        continue

                    # Step 5: Signed (Closed Mandates signed with Agent P-256 Key - Single Log Entry)
                    self.signatures_produced += 1
                    self._log_step(
                        "STEP 5: SIGNED",
                        f"Signing closed Checkout and Payment mandates with Agent P-256 Key ({self.agent_key.kid}) for {purch_tier} at ${monthly_price:.2f}/mo...",
                        {"tier_id": purch_tier, "price_cents": price_cents, "checkout_hash": (chk_hash or "")[:16]},
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
                        "tool_name": "sign_and_purchase",
                        "tool_call_id": tool_call_id,
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

                # Track step transitions from seller responses
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
                    "tool_call_id": tool_call_id,
                    "result": tool_res,
                })

            elif action == "reject":
                active = False
                result_payload = {
                    "status": "REJECTED",
                    "reason": decision.get("content", "Rejected by buyer agent policy."),
                    "signatures_produced": self.signatures_produced,
                    "step_log": list(self.step_log),
                }

            elif action == "finish":
                active = False
                last_tool_res = messages[-1].get("result", {}) if messages and messages[-1].get("role") == "tool" else {}
                result_payload = {
                    "status": "COMPLETED",
                    "summary": decision.get("content", "Procurement cycle finished successfully."),
                    "signatures_produced": self.signatures_produced,
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


# ── Demo Owner Helper (Mock Mode Only) ───────────────────────────────────


def mint_demo_owner_limits_to_file(
    filepath: str,
    budget: float,
    email: str = "agent-alpha@example.com",
    allowed_tiers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Demo owner command: Human owner mints open spending mandates using the demo
    Trusted Surface key and writes them to a file for the buyer agent to consume.
    Mock mode only.
    """
    from ..services.trusted_surface_service import create_trusted_surface_open_mandates

    res = create_trusted_surface_open_mandates(
        buyer_email=email,
        monthly_budget_cap=budget,
        allowed_tiers=allowed_tiers or ["ap2-batch", "ap2-gateway", "ap2-cluster"],
    )
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2)
    return res


# ── CLI Interface ────────────────────────────────────────────────────────


async def _main():
    parser = argparse.ArgumentParser(description="AP2 AI Autonomous Buyer Agent")
    parser.add_argument("--budget", type=float, default=60.00, help="Monthly spending budget cap (USD)")
    parser.add_argument("--tier", type=str, default="ap2-gateway", help="Desired compute tier (ap2-batch, ap2-gateway, ap2-cluster)")
    parser.add_argument("--prompt", type=str, default="Procure AI compute node within budget constraints", help="Owner procurement instruction")
    parser.add_argument("--email", type=str, default="agent-alpha@example.com", help="Buyer PayPal email")
    parser.add_argument("--mandates-file", type=str, default="owner_limits.json", help="Path to file containing human-authorized open mandates")
    parser.add_argument("--mint-owner-limits", action="store_true", help="Demo owner command: write open mandates to file (mock mode only)")
    parser.add_argument("--model", type=str, default=None, help="Explicit model identifier for OpenAICompatibleRunner")
    parser.add_argument("--base-url", type=str, default=None, help="Explicit base URL for OpenAICompatibleRunner")
    args = parser.parse_args()

    limits_path = args.mandates_file

    # If --mint-owner-limits or mandates file doesn't exist or default demo file, execute demo owner command in mock mode
    should_mint = args.mint_owner_limits or not os.path.exists(limits_path)
    if not should_mint and args.mandates_file == "owner_limits.json":
        from ..config import settings
        if settings.mock_external_apis:
            should_mint = True

    if should_mint:
        print(f"\n[DEMO OWNER COMMAND] Minting human-authorized open mandates with demo owner key (mock mode only)...")
        mint_demo_owner_limits_to_file(limits_path, budget=args.budget, email=args.email)
        print(f"[DEMO OWNER COMMAND] Saved open spending limits to '{limits_path}'.\n")

    # The AI Buyer Agent strictly reads the human owner's open mandates from the file
    with open(limits_path, "r", encoding="utf-8") as f:
        mandates_data = json.load(f)

    chk_open = mandates_data.get("open_checkout_mandate_token")
    pay_open = mandates_data.get("open_payment_mandate_token")

    runner = None
    if args.model and args.base_url:
        runner = OpenAICompatibleRunner(model=args.model, base_url=args.base_url)

    agent = LLMBuyerAgent(
        agent_id="buyer-agent-llm-01",
        monthly_budget_cap=args.budget,
        buyer_email=args.email,
        model_runner=runner,
    )

    res = await agent.run_autonomous_procurement(
        owner_request=args.prompt,
        target_tier=args.tier,
        open_checkout_mandate_token=chk_open,
        open_payment_mandate_token=pay_open,
    )

    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
