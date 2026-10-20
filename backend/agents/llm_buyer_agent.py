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
from dotenv import load_dotenv

load_dotenv()

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
from ap2.sdk.generated.types.checkout import Checkout
from ap2.sdk.generated.open_checkout_mandate import (
    OpenCheckoutMandate,
    AllowedMerchants as ChkAllowedMerchants,
    LineItems as ChkLineItems,
)
from ap2.sdk.generated.open_payment_mandate import (
    OpenPaymentMandate,
    AmountRange as PayAmountRange,
    AllowedPayees as PayAllowedPayees,
    Budget as PayBudget,
)
from ap2.sdk.mandate import MandateClient, SdJwtMandate
from ap2.sdk.sdjwt import common
from ap2.sdk.jwt_helper import verify_jwt
from ap2.sdk.constraints import (
    check_checkout_constraints,
    check_payment_constraints,
    MandateContext,
)
from ap2.sdk.utils import b64url_decode

from ..config import settings
from ..database import get_open_mandate_total_usage
from ..services.ap2_keys import get_demo_agent_key
from ..services.ap2_service import (
    AP2_MERCHANT_ID,
    AP2_MERCHANT_NAME,
    dollars_to_minor_units,
    minor_units_to_dollars,
    get_merchant_public_key,
    resolve_root_public_key,
    compute_checkout_hash,
    compute_open_payment_mandate_hash,
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
    "description": "Cryptographically signs closed Checkout and Payment mandates using the Agent P-256 key within human limits, and executes subscription purchase using the offer_id issued by the seller.",
    "input_schema": {
        "type": "object",
        "properties": {
            "offer_id": {
                "type": "string",
                "description": "Negotiated offer identifier previously issued by the seller during negotiation",
            },
            "tier_id": {
                "type": "string",
                "description": "Optional compute tier ID for pre-signing verification (e.g. ap2-gateway, ap2-batch)",
            },
            "monthly_price": {
                "type": "number",
                "description": "Optional agreed monthly subscription price in USD for pre-signing verification",
            },
        },
        "required": ["offer_id"],
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


# MOCK(M-015): scripted stand-in for an LLM
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
                                "offer_id": tool_result.get("offer_id"),
                                "tier_id": c_tier,
                                "monthly_price": c_amount,
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
                            "offer_id": tool_result.get("offer_id"),
                            "tier_id": tier_id,
                            "monthly_price": price,
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
    Runner for OpenAI-compatible endpoints (including xAI Grok).
    Requires explicit --model. Sets provider presets when --provider is used.
    """

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        api_key_env: Optional[str] = None,
        provider: Optional[str] = None,
    ):
        if provider == "xai":
            base_url = base_url or "https://api.x.ai/v1"
            api_key_env = api_key_env or "XAI_API_KEY"
        elif provider == "openai":
            base_url = base_url or "https://api.openai.com/v1"
            api_key_env = api_key_env or "OPENAI_API_KEY"
        elif provider == "gemini":
            base_url = base_url or "https://generativelanguage.googleapis.com/v1beta/openai"
            api_key_env = api_key_env or "GEMINI_API_KEY"

        if not model:
            raise ValueError("OpenAICompatibleRunner requires explicit 'model'.")
        if not base_url:
            raise ValueError("OpenAICompatibleRunner requires explicit 'base_url' or recognized 'provider'.")
        self.model = model
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        if api_key:
            self.api_key = api_key
        elif api_key_env and os.environ.get(api_key_env):
            self.api_key = os.environ.get(api_key_env)
        elif settings.mock_external_apis:
            self.api_key = "mock-key"
        elif api_key_env:
            raise ValueError(f"Environment variable '{api_key_env}' is not set or empty.")
        else:
            raise ValueError("Explicit 'api_key' or 'api_key_env' is required when mock_external_apis is False.")

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
            if resp.status_code != 200:
                print(f"\n[HTTP {resp.status_code} ERROR] {resp.text}\n")
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
        # MOCK(M-015): scripted runner used when no model provider is given
        self.model_runner = model_runner or StubbedModelRunner()
        self.held_offers: Dict[str, Dict[str, Any]] = {}

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
        Deterministic pre-signature guard conforming to AP2 v0.2 Protocol.
        1. Verifies merchant ES256 signature on Checkout JWT with get_merchant_public_key().
        2. Parses Checkout object using Checkout.model_validate(chk_payload).
        3. Decodes open checkout and payment mandates with SdJwtMandate.from_sd_jwt and resolve_root_public_key.
        4. Fails closed: ensures AllowedMerchants and LineItems exist on checkout;
           ensures AmountRange, AllowedPayees, and Budget exist on payment.
        5. Evaluates candidate closed mandates using check_checkout_constraints and check_payment_constraints with MandateContext.
        If any check or decoding fails, returns (False, reason) and halts before producing any signatures.
        """
        if not chk_jwt:
            return False, "MISSING_CHECKOUT_JWT: Merchant checkout JWT is required to verify tier and price integrity."
        if not open_chk_tok or not open_pay_tok:
            return False, "MISSING_OPEN_MANDATES: Both open checkout and open payment mandate tokens are required."

        # 1. Verify merchant ES256 signature on Checkout JWT and parse Checkout object
        try:
            merchant_pub_key = get_merchant_public_key()
            chk_payload = verify_jwt(chk_jwt, merchant_pub_key)
            checkout_obj = Checkout.model_validate(chk_payload)
            checkout_hash = compute_checkout_hash(chk_jwt)
        except Exception as e:
            return False, f"CHECKOUT_JWT_VERIFICATION_FAILED: Merchant Checkout JWT signature or structure invalid: {e}"

        # 2. Decode open checkout and payment mandates with SdJwtMandate.from_sd_jwt
        try:
            parsed_chk = common.parse_token(open_chk_tok)
            chk_root_key = resolve_root_public_key(parsed_chk, buyer_email=self.buyer_email)
            open_chk_mandate = SdJwtMandate.from_sd_jwt(open_chk_tok, chk_root_key, OpenCheckoutMandate)

            parsed_pay = common.parse_token(open_pay_tok)
            pay_root_key = resolve_root_public_key(parsed_pay, buyer_email=self.buyer_email)
            open_pay_mandate = SdJwtMandate.from_sd_jwt(open_pay_tok, pay_root_key, OpenPaymentMandate)
        except Exception as e:
            return False, f"OPEN_MANDATE_DECODE_FAILED: Could not read or verify open mandate tokens: {e}"

        # 3. Fail closed: ensure required constraints exist on open mandates
        chk_constraints = open_chk_mandate.mandate_payload.constraints or []
        has_allowed_merchants = any(isinstance(c, ChkAllowedMerchants) for c in chk_constraints)
        has_line_items = any(isinstance(c, ChkLineItems) for c in chk_constraints)
        if not (has_allowed_merchants and has_line_items):
            return False, "MISSING_REQUIRED_CHECKOUT_CONSTRAINTS: Open checkout mandate must contain AllowedMerchants and LineItems constraints."

        pay_constraints = open_pay_mandate.mandate_payload.constraints or []
        has_amount_range = any(isinstance(c, PayAmountRange) for c in pay_constraints)
        has_allowed_payees = any(isinstance(c, PayAllowedPayees) for c in pay_constraints)
        has_budget = any(isinstance(c, PayBudget) for c in pay_constraints)
        if not (has_amount_range and has_allowed_payees and has_budget):
            return False, "MISSING_REQUIRED_PAYMENT_CONSTRAINTS: Open payment mandate must contain AmountRange, AllowedPayees, and Budget constraints."

        # 4. Check tier and price match against merchant Checkout object
        price_cents = dollars_to_minor_units(monthly_price)
        chk_line_items = checkout_obj.line_items or []
        first_item = chk_line_items[0].item if chk_line_items else None
        jwt_tier = first_item.id if first_item else None
        if jwt_tier and purch_tier and jwt_tier.strip().lower() != purch_tier.strip().lower():
            return False, f"CHECKOUT_TIER_MISMATCH: Checkout JWT tier '{jwt_tier}' does not match purchase tier '{purch_tier}'."

        jwt_total_cents = None
        for tot in (checkout_obj.totals or []):
            if tot.type == "total":
                jwt_total_cents = tot.amount
                break
        if jwt_total_cents is None and first_item:
            jwt_total_cents = first_item.price
        if jwt_total_cents is not None and jwt_total_cents != price_cents:
            return False, f"CHECKOUT_PRICE_MISMATCH: Checkout JWT total ({jwt_total_cents} cents) does not match purchase price ({price_cents} cents)."

        # 5. Evaluate candidate closed mandates against open constraints using AP2 SDK evaluators
        try:
            chk_violations = check_checkout_constraints(open_chk_mandate.mandate_payload, checkout_obj)
            if chk_violations:
                return False, f"CHECKOUT_CONSTRAINT_VIOLATION: {'; '.join(chk_violations)}"

            candidate_pay = PaymentMandate(
                vct="mandate.payment.1",
                transaction_id=checkout_hash,
                payment_amount=Amount(amount=price_cents, currency="USD"),
                payee=Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME),
                payment_instrument=PaymentInstrument(type="paypal_vault", id=f"vault_{self.agent_id}"),
            )

            open_pay_hash = compute_open_payment_mandate_hash(open_pay_tok)
            tot_amt, tot_uses = get_open_mandate_total_usage(open_pay_hash)
            mandate_ctx = MandateContext(total_amount=tot_amt, total_uses=tot_uses)

            pay_violations = check_payment_constraints(
                open_pay_mandate.mandate_payload,
                candidate_pay,
                open_checkout_hash=checkout_hash,
                mandate_context=mandate_ctx,
            )
            if pay_violations:
                return False, f"PAYMENT_CONSTRAINT_VIOLATION: {'; '.join(pay_violations)}"

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
        model_name = getattr(self.model_runner, "model", None)
        model_label = model_name if model_name else "Scripted demo runner (no AI model)"

        print(f"\n=======================================================")
        print(f"🤖 [AP2 AI BUYER AGENT: {self.agent_id}]")
        print(f"   Model:               {model_label}")
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
            f"Ingested owner prompt: \"{owner_request}\" [Model: {model_label}] (Target: {target_tier}, Budget Cap: ${self.monthly_budget_cap:.2f}/mo)",
            {"target_tier": target_tier, "budget_cap": self.monthly_budget_cap, "model": model_label},
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
                tool_calls_to_append = decision.get("raw_tool_calls") or [
                    {
                        "id": tool_call_id,
                        "type": "function",
                        "function": {
                            "name": tname,
                            "arguments": json.dumps(tparams),
                        },
                    }
                ]
                messages.append({
                    "role": "assistant",
                    "content": thought or None,
                    "tool_calls": tool_calls_to_append,
                })

                if tname == "sign_and_purchase":
                    offer_id = tparams.get("offer_id")
                    held_offer = self.held_offers.get(offer_id) if offer_id else None

                    if not held_offer:
                        reason = f"UNAUTHORIZED_OFFER_ID: offer_id '{offer_id}' was not issued by the seller."
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

                    # Pre-signing validation: if model explicitly passed tier or price, verify match with seller offer
                    req_tier = tparams.get("tier_id")
                    if req_tier and req_tier.strip().lower() != (held_offer["tier_id"] or "").strip().lower():
                        reason = f"TIER_MISMATCH: Model requested tier '{req_tier}' does not match seller offer tier '{held_offer['tier_id']}'."
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

                    req_price = tparams.get("monthly_price")
                    if req_price is not None and abs(float(req_price) - held_offer["monthly_price"]) > 0.001:
                        reason = f"PRICE_MISMATCH: Model requested price ${float(req_price):.2f} does not match seller offer price ${held_offer['monthly_price']:.2f}."
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

                    # The agent fills in tokens and terms from the held seller response
                    purch_tier = held_offer["tier_id"]
                    monthly_price = float(held_offer["monthly_price"])
                    price_cents = dollars_to_minor_units(monthly_price)
                    chk_jwt = held_offer["checkout_jwt"]
                    chk_hash = held_offer["checkout_hash"]
                    nonce = held_offer["nonce"]

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
                        chk_rec = purch_res.get("checkout_receipt")
                        pay_rec = purch_res.get("payment_receipt")
                        step_meta: Dict[str, Any] = {}
                        msg = f"Purchase rejected: {purch_res.get('error')} - {purch_res.get('reason')}"
                        if chk_rec or pay_rec:
                            msg += " (signed checkout + payment error receipts attached)"
                            if chk_rec:
                                step_meta["checkout_receipt"] = "attached"
                            if pay_rec:
                                step_meta["payment_receipt"] = "attached"
                        self._log_step(
                            "PURCHASE_FAILED",
                            msg,
                            step_meta or None,
                        )
                        active = False
                        result_payload = dict(purch_res)
                        result_payload["step_log"] = list(self.step_log)
                        result_payload["signatures_produced"] = self.signatures_produced
                        if chk_rec:
                            result_payload["checkout_receipt"] = chk_rec
                        if pay_rec:
                            result_payload["payment_receipt"] = pay_rec
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
                    offer_id = tool_res.get("offer_id")
                    if offer_id:
                        if status == "COUNTER_OFFER":
                            c_tier_offer = tool_res.get("counter_offer_tier_id", "ap2-batch")
                            c_amount_offer = float(tool_res.get("counter_offer_amount", 49.99))
                            c_jwt_offer = tool_res.get("counter_offer_checkout_jwt") or tool_res.get("checkout_jwt")
                            c_hash_offer = tool_res.get("counter_offer_checkout_hash") or tool_res.get("checkout_hash")
                        else:
                            c_tier_offer = tool_res.get("tier_id")
                            c_amount_offer = float(tool_res.get("agreed_monthly_rate", 0.0))
                            c_jwt_offer = tool_res.get("checkout_jwt")
                            c_hash_offer = tool_res.get("checkout_hash")

                        self.held_offers[offer_id] = {
                            "offer_id": offer_id,
                            "tier_id": c_tier_offer,
                            "monthly_price": c_amount_offer,
                            "checkout_jwt": c_jwt_offer,
                            "checkout_hash": c_hash_offer,
                            "nonce": tool_res.get("nonce"),
                            "status": status,
                        }

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
                        chk_rec = tool_res.get("checkout_receipt")
                        pay_rec = tool_res.get("payment_receipt")
                        step_meta: Dict[str, Any] = {}
                        msg = f"Seller rejected request: {tool_res.get('reason')}"
                        if chk_rec or pay_rec:
                            msg += " (signed checkout + payment error receipts attached)"
                            if chk_rec:
                                step_meta["checkout_receipt"] = "attached"
                            if pay_rec:
                                step_meta["payment_receipt"] = "attached"
                        self._log_step(
                            "REJECTED",
                            msg,
                            step_meta or None,
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
                last_tool_res = messages[-1].get("result", {}) if messages and messages[-1].get("role") == "tool" else {}
                chk_rec = last_tool_res.get("checkout_receipt")
                pay_rec = last_tool_res.get("payment_receipt")
                result_payload = {
                    "status": "REJECTED",
                    "reason": decision.get("content", "Rejected by buyer agent policy."),
                    "signatures_produced": self.signatures_produced,
                    "step_log": list(self.step_log),
                }
                if chk_rec:
                    result_payload["checkout_receipt"] = chk_rec
                if pay_rec:
                    result_payload["payment_receipt"] = pay_rec

            elif action == "finish":
                active = False
                last_tool_res = messages[-1].get("result", {}) if messages and messages[-1].get("role") == "tool" else {}
                has_purchase = any("STEP 6: PURCHASED" in s for s in self.step_log)
                if has_purchase:
                    result_payload = {
                        "status": "COMPLETED",
                        "summary": decision.get("content", "Procurement cycle finished successfully."),
                        "signatures_produced": self.signatures_produced,
                        "step_log": list(self.step_log),
                        "trace_events": list(self.trace_events),
                        "last_result": last_tool_res,
                    }
                else:
                    reason = decision.get("content") or decision.get("thought") or "Model concluded procurement cycle without making a purchase."
                    result_payload = {
                        "status": "NO_PURCHASE",
                        "reason": reason,
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

        result_payload["model"] = model_label
        return result_payload


# ── Demo Owner Helper (Mock Mode Only) ───────────────────────────────────


# MOCK(M-005): CLI plays the owner using the demo owner key
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
    if not settings.mock_external_apis:
        raise PermissionError("mint_demo_owner_limits_to_file is permitted only when mock_external_apis is True.")

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
    parser.add_argument("--provider", type=str, choices=["openai", "xai", "gemini"], default=None, help="LLM provider preset ('openai', 'xai', or 'gemini')")
    parser.add_argument("--model", type=str, default=None, help="Explicit model identifier for OpenAICompatibleRunner (required when --provider is set)")
    parser.add_argument("--base-url", type=str, default=None, help="Explicit base URL for OpenAICompatibleRunner")
    parser.add_argument("--api-key-env", type=str, default=None, help="Name of environment variable containing API key for OpenAICompatibleRunner")
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

    if args.provider and not args.model:
        parser.error("--model must be explicitly specified when --provider is used.")

    base_url = args.base_url
    api_key_env = args.api_key_env

    if args.provider == "xai":
        base_url = base_url or "https://api.x.ai/v1"
        api_key_env = api_key_env or "XAI_API_KEY"
    elif args.provider == "openai":
        base_url = base_url or "https://api.openai.com/v1"
        api_key_env = api_key_env or "OPENAI_API_KEY"
    elif args.provider == "gemini":
        base_url = base_url or "https://generativelanguage.googleapis.com/v1beta/openai"
        api_key_env = api_key_env or "GEMINI_API_KEY"

    runner = None
    if args.model:
        if not base_url:
            parser.error("Explicit --base-url or --provider is required when --model is specified.")
        runner = OpenAICompatibleRunner(
            model=args.model,
            base_url=base_url,
            api_key_env=api_key_env,
            provider=args.provider,
        )

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
