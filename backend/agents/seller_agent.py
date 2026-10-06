"""
Seller Agent (FieldSmith Pro MCP Server).
Exposes the merchant capability catalog and executes autonomous trade commitments.
Can be queried programmatically by any Model Context Protocol (MCP) compliant client or Buyer Agent.
Conforms to FIDO / AP2 Intent Mandate specifications.
"""

import os
import re
import json
import uuid
import hashlib
import datetime
import logging
from typing import Dict, Any, List, Optional
from ..models import (
    QuoteRequest,
    SpendingMandateRequest,
    ProvisionRequest,
    DispatchLockRequest,
    ZapierSyncRequest,
    RecurrenceType,
)
from ..services.mandate_evaluator import (
    evaluate_spending_mandate,
    verify_authorized_mandate,
    register_authorized_mandate,
    get_authorized_mandate,
    bind_mandate_email,
    build_ap2_intent_mandate,
    build_ap2_cart_mandate,
    validate_buyer_intent_mandate,
    sign_mandate_token,
    ledger,
)
from ..services.paypal_service import paypal_service
from ..services.plan_catalog import (
    PLANS,
    TIER_ALIASES,
    QUOTA_UNIT,
    QUOTA_UNIT_DEFINITION,
    INCLUDED_ON_ALL_PLANS,
    SUPPORTED_TRADES,
    ACTIVATION,
    TRUST_SIGNALS,
    resolve_plan,
    get_plan,
    plan_summary,
    public_plan,
)
from ..services.telnyx_provisioner import telnyx_provisioner
from ..services.zapier_mcp_dispatcher import zapier_mcp_dispatcher
from ..services.crypto_mandate import verify_mandate_proof, verify_ap2_intent_mandate
from ..config import settings

logger = logging.getLogger("seller_agent")

# Model Context Protocol (MCP) Tool Declarations
SELLER_MCP_TOOLS = [
    {
        "name": "get_service_catalog",
        "description": "Returns the FieldSmith plan catalog with buyer context: plans and quotas, capabilities included on every plan, supported trades with their intake focus, activation requirements, and guarantee and policy links.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "inspect_subscription_tiers",
        "description": "Inspects FieldSmith Pro commercial SaaS subscription tiers ($49.99 Solo Starter, $79.99 FieldSmith Pro, $179.99 Fleet Dispatch), screened-call quotas, and features.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "negotiate_tier_terms",
        "description": "Evaluates buyer budget cap against desired FieldSmith SaaS tier. If asking price exceeds budget, returns pre-approved counter-offer down-tiering to a plan within budget (e.g. Solo Starter at $49.99/mo) with a signed AP2 Intent Mandate.",
        "input_schema": {
            "type": "object",
            "required": ["buyer_agent_id", "contractor_email", "tier_id", "monthly_budget_cap"],
            "properties": {
                "buyer_agent_id": {
                    "type": "string",
                    "description": "Unique identifier of the Buyer Agent",
                },
                "contractor_email": {
                    "type": "string",
                    "description": "Contractor PayPal billing email. The issued mandate is bound to this email and can only be redeemed by it.",
                },
                "tier_id": {
                    "type": "string",
                    "description": "Desired FieldSmith SaaS subscription tier ('solo-starter' at $49.99, 'fieldsmith-pro' at $79.99, 'pro-dispatch' at $179.99)",
                },
                "monthly_budget_cap": {
                    "type": "number",
                    "description": "Strict maximum monthly budget cap authorized by the contractor's mandate",
                },
                "proposed_price": {
                    "type": "number",
                    "description": "Optional buyer-proposed target monthly price for counter-negotiation",
                },
                "recurrence": {
                    "type": "string",
                    "enum": ["monthly", "annual", "one_time"],
                    "default": "monthly",
                    "description": "Billing cadence",
                },
                "category": {
                    "type": "string",
                    "default": "TELEPHONY_AI_SCREENER",
                    "description": "Authorized spending category",
                },
                "buyer_intent_mandate": {
                    "type": "object",
                    "description": "Optional buyer-signed AP2 Intent Mandate (vct: ap2.mandate.intent.1). If omitted, seller creates a seller-attested intent mandate on buyer's behalf.",
                },
            },
        },
    },
    {
        "name": "evaluate_spending_mandate",
        "description": "Validates buyer agent programmatic budget caps and generates signed mandate proof tokens.",
        "input_schema": {
            "type": "object",
            "required": ["buyer_agent_id", "amount", "recurrence", "category", "monthly_budget_cap"],
            "properties": {
                "buyer_agent_id": {"type": "string", "description": "Unique ID of the Buyer Agent"},
                "amount": {"type": "number", "description": "Proposed asking price per billing cycle"},
                "recurrence": {
                    "type": "string",
                    "enum": ["one_time", "monthly", "annual"],
                    "description": "Billing recurrence cadence",
                },
                "category": {"type": "string", "description": "Spending category"},
                "monthly_budget_cap": {
                    "type": "number",
                    "description": "Strict maximum monthly budget authorized by the buyer mandate",
                },
            },
        },
    },
    {
        "name": "purchase_subscription",
        "description": "Binds a verified AP2 Intent Mandate or signed AP2 Cart Mandate offer to PayPal Recurring Vault for automated monthly billing. Provide offer_id (recommended from next_action) or tier_id + agreed_monthly_rate + mandate_proof_hash.",
        "input_schema": {
            "type": "object",
            "required": ["contractor_email"],
            "properties": {
                "offer_id": {
                    "type": "string",
                    "description": "Merchant offer_id returned in Cart Mandate and next_action (e.g. 'off_solo_starter_49_...'). Automatically resolves and binds all pre-verified terms without rate tampering risk.",
                },
                "contractor_email": {
                    "type": "string",
                    "description": "Contractor PayPal billing email; must match the email the mandate was negotiated for.",
                },
                "tier_id": {
                    "type": "string",
                    "description": "Optional if offer_id is provided. Subscription tier ID (e.g. 'solo-starter', 'fieldsmith-pro', 'pro-dispatch').",
                },
                "agreed_monthly_rate": {
                    "type": "number",
                    "description": "Optional if offer_id is provided. Agreed monthly subscription rate.",
                },
                "mandate_proof_hash": {
                    "type": "string",
                    "description": "Optional if offer_id is provided. mandate_proof_hash returned by negotiate_tier_terms.",
                },
            },
        },
    },
    {
        "name": "provision_telecom_line",
        "description": "Allocates a dedicated local 10DLC telephone DID upon verified PayPal subscription. Restricted strictly to licensed US contractors (NANP +1 3-digit area code).",
        "input_schema": {
            "type": "object",
            "required": ["subscription_id", "contractor_email"],
            "properties": {
                "subscription_id": {"type": "string", "description": "Verified PayPal subscription ID"},
                "contractor_email": {"type": "string", "description": "Contractor notification email"},
                "area_code": {"type": "string", "default": "863", "description": "Target NPA area code (3-digit NANP e.g. 863, 813, 214)"},
                "simulate_exhaustion": {"type": "boolean", "default": False, "description": "Test LATA failover"},
            },
        },
    },
    {
        "name": "dispatch_zapier_mcp",
        "description": "Executes downline multi-app back-office action chain into QuickBooks Online, Jobber, and Google Workspace.",
        "input_schema": {
            "type": "object",
            "properties": {
                "workflow_type": {"type": "string", "default": "a2a_onboarding"},
                "contractor_name": {"type": "string"},
                "business_entity": {"type": "string"},
                "allocated_did": {"type": "string"},
                "trade_vertical": {"type": "string"},
                "monthly_subscription_fee": {"type": "number"},
                "paypal_subscription_id": {"type": "string"},
                "contractor_email": {"type": "string"},
                "mandate_proof_hash": {"type": "string"},
                "webhook_url": {"type": "string"},
            },
        },
    },
]


_COMPLETED_SUBSCRIPTIONS: Dict[str, Dict[str, Any]] = {}
_ACTIVE_CONTRACTOR_SUBSCRIPTIONS: Dict[str, str] = {}


def reconcile_contractor_ledger(contractor_email: str) -> float:
    """
    Reconciles the contractor's ledger commitment strictly from subscription state:
    commitment = the rate of the contractor's one ACTIVE subscription.
    Pending, replaced, cancelled, and suspended plans contribute 0.0 to commitment.
    Returns the active monthly commitment.
    """
    if not contractor_email:
        return 0.0
    norm_email = contractor_email.strip().lower()

    # Find the contractor's active subscription
    active_sub = None
    active_sub_id = _ACTIVE_CONTRACTOR_SUBSCRIPTIONS.get(norm_email)
    if active_sub_id and active_sub_id in _COMPLETED_SUBSCRIPTIONS:
        candidate = _COMPLETED_SUBSCRIPTIONS[active_sub_id]
        if isinstance(candidate, dict) and candidate.get("status") == "ACTIVE":
            active_sub = candidate

    # Fallback search if pointer was missing or pointing to inactive record
    if not active_sub:
        for v in _COMPLETED_SUBSCRIPTIONS.values():
            if isinstance(v, dict) and v.get("status") == "ACTIVE":
                cand_email = (v.get("contractor_email") or "").strip().lower()
                if cand_email == norm_email:
                    active_sub = v
                    _ACTIVE_CONTRACTOR_SUBSCRIPTIONS[norm_email] = v.get("subscription_id")
                    break

    if active_sub:
        active_rate = float(active_sub.get("agreed_monthly_rate") or 0.0)
        buyer_id = active_sub.get("buyer_agent_id")
    else:
        active_rate = 0.0
        buyer_id = None
        _ACTIVE_CONTRACTOR_SUBSCRIPTIONS.pop(norm_email, None)

    ledger.sync_contractor_commitment(
        contractor_email=norm_email,
        active_monthly_rate=active_rate,
        agent_id=buyer_id,
    )
    return active_rate


def resolve_tier_from_paypal_plan(plan_id: Optional[str]) -> tuple[str, float]:
    """Maps a PayPal billing plan_id to its canonical tier_id and agreed monthly rate."""
    if not plan_id:
        return ("fieldsmith-pro", 79.99)
    p = plan_id.lower()
    if plan_id == getattr(settings, "paypal_plan_id_solo", "P-FLSMITH-SOLO-STARTER"):
        return ("solo-starter", 49.99)
    elif plan_id == getattr(settings, "paypal_plan_id_dispatch", "P-FLSMITH-DISPATCH"):
        return ("pro-dispatch", 179.99)
    elif plan_id == getattr(settings, "paypal_plan_id_pro", "P-FLSMITH-PRO"):
        return ("fieldsmith-pro", 79.99)
    if "solo" in p or "starter" in p:
        return ("solo-starter", 49.99)
    elif "dispatch" in p:
        return ("pro-dispatch", 179.99)
    elif "pro" in p:
        return ("fieldsmith-pro", 79.99)
    return ("fieldsmith-pro", 79.99)


class SellerAgent:
    def __init__(self, agent_name: str = "FieldSmith Pro Seller MCP"):
        self.agent_name = agent_name

    def list_mcp_tools(self) -> List[Dict[str, Any]]:
        """Returns the MCP tool definitions for agent tool-use discovery."""
        return SELLER_MCP_TOOLS

    async def get_service_catalog(self) -> Dict[str, Any]:
        """Tool implementation: Returns the plan catalog with buyer context for intent matching."""
        return {
            "provider": self.agent_name,
            "currency": "USD",
            "quota_unit": QUOTA_UNIT,
            "quota_unit_definition": QUOTA_UNIT_DEFINITION,
            "plans": [public_plan(plan) for plan in PLANS],
            "included_on_all_plans": INCLUDED_ON_ALL_PLANS,
            "supported_trades": SUPPORTED_TRADES,
            "trades_note": "Every trade is supported on every plan. Pick a plan by call volume and crew size, not by trade.",
            "tier_id_aliases": TIER_ALIASES,
            "activation": ACTIVATION,
            "trust_signals": TRUST_SIGNALS,
        }

    async def inspect_subscription_tiers(self) -> Dict[str, Any]:
        """Tool implementation: Returns FieldSmith Pro SaaS subscription tiers, quotas, and pricing parameters."""
        subscription_plans = []
        for plan in PLANS:
            entry = public_plan(plan)
            entry["is_negotiable"] = False
            entry["tier_id_aliases"] = [alias for alias, target in TIER_ALIASES.items() if target == plan["tier_id"]]
            subscription_plans.append(entry)
        return {
            "provider": self.agent_name,
            "currency": "USD",
            "protocol_support": ["AP2", "MCP"],
            "service_description": "FieldSmith Pro AI Telephony & Voice Dispatch Receptionist SaaS for Field Service Contractors",
            "quota_unit": QUOTA_UNIT,
            "quota_unit_definition": QUOTA_UNIT_DEFINITION,
            "billing_period": "monthly",
            "subscription_plans": subscription_plans,
            "included_on_all_plans": INCLUDED_ON_ALL_PLANS,
        }

    def _issue_mandate(
        self,
        buyer_agent_id: str,
        contractor_email: str,
        tier_id: str,
        amount: float,
        recurrence: str,
        category: str,
        monthly_budget_cap: float,
        buyer_intent_mandate: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Issues one email-bound proof hash, signed AP2 Intent Mandate (or adopts verified buyer-signed mandate), and signed AP2 Cart Mandate."""
        email = contractor_email.strip().lower()
        clean_tier = tier_id.replace("-", "_").lower()
        offer_id = f"off_{clean_tier}_{int(amount)}_{uuid.uuid4().hex[:8]}"
        proof_hash = sign_mandate_token(
            agent_id=buyer_agent_id,
            amount=amount,
            recurrence=recurrence,
            secret=settings.a2a_mandate_secret,
            contractor_email=email,
            offer_id=offer_id,
        )
        negotiation_id = f"neg_{hashlib.sha256(proof_hash.encode()).hexdigest()[:12]}"

        if buyer_intent_mandate and verify_ap2_intent_mandate(buyer_intent_mandate):
            ap2_mandate = dict(buyer_intent_mandate)
        else:
            ap2_mandate = build_ap2_intent_mandate(
                buyer_agent_id=buyer_agent_id,
                amount=amount,
                recurrence=recurrence,
                category=category,
                tier_id=tier_id,
                contractor_email=email,
                negotiation_id=negotiation_id,
            )

        ap2_cart = build_ap2_cart_mandate(
            offer_id=offer_id,
            tier_id=tier_id,
            amount=amount,
            recurrence=recurrence,
            contractor_email=email,
            negotiation_id=negotiation_id,
            category=category,
        )
        auth_entry = {
            "tier_id": tier_id,
            "amount": amount,
            "buyer_agent_id": buyer_agent_id,
            "contractor_email": email,
            "monthly_budget_cap": monthly_budget_cap,
            "negotiation_id": negotiation_id,
            "offer_id": offer_id,
            "proof_hash": proof_hash,
            "mandate_proof_hash": proof_hash,
            "ap2_mandate": ap2_mandate,
            "ap2_cart_mandate": ap2_cart,
        }
        register_authorized_mandate(proof_hash, auth_entry)
        register_authorized_mandate(offer_id, auth_entry)

        return {
            "hash": proof_hash,
            "offer_id": offer_id,
            "negotiation_id": negotiation_id,
            "ap2_mandate": ap2_mandate,
            "ap2_cart_mandate": ap2_cart,
            "offer_expires_at": ap2_cart.get("offer_expires_at"),
        }

    async def negotiate_tier_terms(
        self,
        buyer_agent_id: str,
        tier_id: str,
        monthly_budget_cap: float,
        contractor_email: Optional[str] = None,
        proposed_price: Optional[float] = None,
        recurrence: str = "monthly",
        category: str = "TELEPHONY_AI_SCREENER",
        buyer_intent_mandate: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Tool implementation: Evaluates buyer budget cap against desired tier.
        Autonomously negotiates down-tier counter-offers with verifiable AP2 cryptographic mandate proof hashes.
        Accepts optional buyer_intent_mandate signed by the buyer agent; falls back to seller-attested intent mandate.
        """
        plan = resolve_plan(tier_id)
        if plan is None:
            available = ", ".join(f"'{p['tier_id']}' (${p['monthly_price']:.2f}/mo)" for p in PLANS)
            return {
                "status": "REJECTED",
                "error": "UNKNOWN_TIER",
                "approved": False,
                "original_request_approved": False,
                "tier_id": tier_id,
                "reason": f"Unknown tier_id '{tier_id}'. Available FieldSmith tiers: {available}.",
            }

        standard_price = plan["monthly_price"]
        screened_calls = plan["screened_calls_per_month"]

        if not contractor_email and buyer_intent_mandate and isinstance(buyer_intent_mandate, dict):
            payer = buyer_intent_mandate.get("payer")
            if isinstance(payer, dict):
                contractor_email = payer.get("email")

        if buyer_intent_mandate:
            valid, err_code, signed_cap = validate_buyer_intent_mandate(
                mandate=buyer_intent_mandate,
                contractor_email=contractor_email,
                service_category=category,
            )
            if not valid:
                return {
                    "status": "REJECTED",
                    "approved": False,
                    "original_request_approved": False,
                    "tier_id": tier_id,
                    "error": err_code,
                    "reason": f"Buyer-provided Intent Mandate rejected: {err_code}",
                }
            if signed_cap is not None:
                # The signed mandate's cap strictly overrides any unsigned monthly_budget_cap passed in arguments
                monthly_budget_cap = signed_cap

            payer_in_mandate = buyer_intent_mandate.get("payer", {}).get("email")
            if payer_in_mandate and not contractor_email:
                contractor_email = str(payer_in_mandate).strip().lower()

        if not contractor_email or "@" not in contractor_email:
            return {
                "status": "REJECTED",
                "approved": False,
                "original_request_approved": False,
                "tier_id": tier_id,
                "error": "CONTRACTOR_EMAIL_REQUIRED",
                "reason": "contractor_email is required; the issued AP2 mandate is bound to it.",
            }

        email = contractor_email.strip().lower()
        if email and monthly_budget_cap:
            ledger.set_contractor_cap(email, monthly_budget_cap)

        active_sub_id = _ACTIVE_CONTRACTOR_SUBSCRIPTIONS.get(email) if email else None
        active_sub = _COMPLETED_SUBSCRIPTIONS.get(active_sub_id) if active_sub_id else None
        if active_sub and active_sub.get("status") != "ACTIVE":
            active_sub = None
            active_sub_id = None
        if not active_sub_id and email:
            for s in reversed(list(_COMPLETED_SUBSCRIPTIONS.values())):
                if isinstance(s, dict) and s.get("contractor_email", "").strip().lower() == email:
                    if s.get("status") == "ACTIVE":
                        active_sub_id = s.get("subscription_id")
                        active_sub = s
                        break

        def norm_plan(p: Optional[str]) -> str:
            p = (p or "").lower().replace("-", "").replace("_", "")
            if "solo" in p:
                return "solo-starter"
            if "pro" in p and "dispatch" not in p and "fleet" not in p:
                return "fieldsmith-pro"
            if "dispatch" in p or "fleet" in p:
                return "pro-dispatch"
            return p

        req_norm = norm_plan(tier_id)
        current_norm = norm_plan(active_sub.get("tier_id")) if active_sub else None

        # Guard 1: Already subscribed to the requested tier
        if active_sub and req_norm == current_norm:
            logger.info(
                f"[A2A_SELLER] Contractor {email} already subscribed to active plan {active_sub_id} ({active_sub.get('tier_id')})"
            )
            return {
                "status": "ALREADY_SUBSCRIBED",
                "approved": False,
                "original_request_approved": False,
                "tier_id": tier_id,
                "error": "ALREADY_SUBSCRIBED",
                "subscription_id": active_sub_id,
                "active_subscription_id": active_sub_id,
                "monthly_budget_cap": round(monthly_budget_cap, 2),
                "agreed_monthly_rate": active_sub.get("agreed_monthly_rate"),
                "reason": (
                    f"Contractor '{email}' is already actively subscribed to '{tier_id}' "
                    f"(Subscription: {active_sub_id}). No new offer or subscription required."
                ),
            }

        # 1. Direct Approval: Desired tier is within budget cap
        if monthly_budget_cap >= standard_price:
            mandate_res = await self.verify_spending_mandate(
                buyer_agent_id=buyer_agent_id,
                amount=standard_price,
                recurrence=recurrence,
                category=category,
                monthly_budget_cap=monthly_budget_cap,
                contractor_email=email,
            )
            if not mandate_res.get("approved"):
                rejection = {
                    "status": "REJECTED",
                    "approved": False,
                    "original_request_approved": False,
                    "tier_id": tier_id,
                    "error": "BUDGET_EXHAUSTED",
                    "monthly_budget_cap": round(monthly_budget_cap, 2),
                    "reason": mandate_res.get("reason"),
                }
                if active_sub_id:
                    rejection["active_subscription_id"] = active_sub_id
                return rejection
            issued = self._issue_mandate(
                buyer_agent_id, email, tier_id, standard_price,
                recurrence, category, monthly_budget_cap,
                buyer_intent_mandate=buyer_intent_mandate,
            )
            next_action = {
                "type": "tool_call",
                "tool": "purchase_subscription",
                "parameters": {
                    "offer_id": issued["offer_id"],
                    "contractor_email": email,
                    "tier_id": tier_id,
                    "agreed_monthly_rate": standard_price,
                    "mandate_proof_hash": issued["hash"],
                },
            }
            res_approved = {
                "status": "APPROVED",
                "approved": True,
                "original_request_approved": True,
                "negotiation_id": issued["negotiation_id"],
                "offer_id": issued["offer_id"],
                "tier_id": tier_id,
                "agreed_monthly_rate": standard_price,
                "monthly_budget_cap": round(monthly_budget_cap, 2),
                "monthly_cap_remaining": round(monthly_budget_cap - standard_price, 2),
                "screened_calls_per_month": screened_calls,
                "mandate_proof_hash": issued["hash"],
                "ap2_intent_mandate": issued["ap2_mandate"],
                "ap2_cart_mandate": issued["ap2_cart_mandate"],
                "offer_expires_at": issued["offer_expires_at"],
                "next_action": next_action,
                "reason": f"Plan '{tier_id}' at ${standard_price:.2f}/mo approved within ${monthly_budget_cap:.2f}/mo cap.",
            }
            if active_sub_id:
                res_approved["replaces_subscription_id"] = active_sub_id
            return res_approved

        remaining_now = ledger.get_remaining_budget(agent_id=buyer_agent_id, cap=monthly_budget_cap, contractor_email=email)
        norm_email_lookup = email.strip().lower() if email else ""
        existing_sub = ledger._contractor_subscriptions.get(norm_email_lookup, 0.0)
        effective_available = round(remaining_now + existing_sub, 2)

        if monthly_budget_cap >= 49.99 and effective_available >= 49.99:
            # Guard 2: If contractor is already on Solo Starter, they already hold the best plan within budget
            if active_sub and current_norm == "solo-starter":
                logger.info(
                    f"[A2A_SELLER] Contractor {email} requested {tier_id} (${standard_price:.2f}), cap ${monthly_budget_cap:.2f}, "
                    f"already on best viable plan {active_sub_id} (solo-starter)"
                )
                return {
                    "status": "NO_BETTER_OFFER",
                    "approved": False,
                    "original_request_approved": False,
                    "tier_id": tier_id,
                    "error": "NO_BETTER_OFFER",
                    "current_subscription_id": active_sub_id,
                    "active_subscription_id": active_sub_id,
                    "current_tier_id": active_sub.get("tier_id"),
                    "monthly_budget_cap": round(monthly_budget_cap, 2),
                    "reason": (
                        f"Requested tier '{tier_id}' lists at ${standard_price:.2f}/mo, which exceeds monthly budget cap of ${monthly_budget_cap:.2f}. "
                        f"Contractor is already subscribed to the highest viable plan within budget ('{active_sub.get('tier_id')}' at ${active_sub.get('agreed_monthly_rate', 49.99):.2f}/mo, Subscription: {active_sub_id}). "
                        f"No better offer available under current budget cap."
                    ),
                }
            issued = self._issue_mandate(
                buyer_agent_id, email, "solo-starter", 49.99,
                recurrence, category, monthly_budget_cap,
                buyer_intent_mandate=buyer_intent_mandate,
            )
            solo_hash = issued["hash"]
            remaining_after_solo = round(monthly_budget_cap - 49.99, 2)
            next_action = {
                "type": "tool_call",
                "tool": "purchase_subscription",
                "parameters": {
                    "offer_id": issued["offer_id"],
                    "contractor_email": email,
                    "tier_id": "solo-starter",
                    "agreed_monthly_rate": 49.99,
                    "mandate_proof_hash": solo_hash,
                },
            }
            res_counter = {
                "status": "COUNTER_OFFER",
                "approved": False,
                "original_request_approved": False,
                "negotiation_id": issued["negotiation_id"],
                "offer_id": issued["offer_id"],
                "tier_id": tier_id,
                "counter_offer_available": True,
                "counter_offer_tier": "FieldSmith Solo Starter",
                "counter_offer_tier_id": "solo-starter",
                "counter_offer_amount": 49.99,
                "counter_offer_mandate_hash": solo_hash,
                "mandate_proof_hash": solo_hash,
                "ap2_intent_mandate": issued["ap2_mandate"],
                "ap2_cart_mandate": issued["ap2_cart_mandate"],
                "offer_expires_at": issued["offer_expires_at"],
                "monthly_budget_cap": round(monthly_budget_cap, 2),
                "monthly_cap_remaining": remaining_after_solo,
                "next_action": next_action,
                "reason": (
                    f"Requested FieldSmith plan '{tier_id}' lists at ${standard_price:.2f}/mo, which exceeds monthly budget cap of ${monthly_budget_cap:.2f}. "
                    f"Counter-offer available: Down-tier to '{get_plan('solo-starter')['title']}' at {plan_summary('solo-starter')}, "
                    f"leaving ${remaining_after_solo:.2f} in your monthly software budget. "
                    f"Execute next_action tool call with offer_id='{issued['offer_id']}' to bind to PayPal Vault."
                ),
            }
            if active_sub_id:
                res_counter["replaces_subscription_id"] = active_sub_id
            return res_counter

        # 3. Budget below minimum viable tier ($49.99)
        rejection = {
            "status": "REJECTED",
            "approved": False,
            "original_request_approved": False,
            "tier_id": tier_id,
            "error": "BUDGET_EXHAUSTED",
            "counter_offer_available": False,
            "monthly_budget_cap": round(monthly_budget_cap, 2),
            "monthly_cap_remaining": round(ledger.get_remaining_budget(agent_id=buyer_agent_id, cap=monthly_budget_cap, contractor_email=email), 2),
            "reason": f"Monthly budget cap of ${monthly_budget_cap:.2f} is below minimum viable tier (FieldSmith Solo Starter at $49.99/mo).",
        }
        if active_sub_id:
            rejection["active_subscription_id"] = active_sub_id
        return rejection

    async def verify_spending_mandate(
        self,
        buyer_agent_id: str,
        amount: float,
        recurrence: str,
        category: str,
        monthly_budget_cap: float,
        contractor_email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Tool implementation: Enforces buyer spending limits."""
        req = SpendingMandateRequest(
            buyerAgentId=buyer_agent_id,
            amount=amount,
            recurrence=RecurrenceType(recurrence),
            category=category,
            monthlyBudgetCap=monthly_budget_cap,
            contractorEmail=contractor_email,
        )
        res = evaluate_spending_mandate(req)
        return res.model_dump(by_alias=True)

    async def purchase_subscription(
        self,
        tier_id: Optional[str] = None,
        agreed_monthly_rate: Optional[float] = None,
        mandate_proof_hash: Optional[str] = None,
        contractor_email: Optional[str] = None,
        offer_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Tool implementation: Binds verified AP2 Intent Mandate or AP2 Cart Mandate to PayPal Recurring Vault.
        Cryptographically verifies the mandate proof against tier, rate, and contractor identity.
        Replayed requests return the identical, immutable subscription record (idempotency).
        """
        # Resolve parameters from offer_id if caller omitted them
        if offer_id and not (tier_id and agreed_monthly_rate and mandate_proof_hash):
            auth_lookup = get_authorized_mandate(offer_id)
            if auth_lookup:
                tier_id = tier_id or auth_lookup.get("tier_id")
                agreed_monthly_rate = agreed_monthly_rate if agreed_monthly_rate is not None else auth_lookup.get("amount")
                mandate_proof_hash = mandate_proof_hash or auth_lookup.get("mandate_proof_hash") or auth_lookup.get("proof_hash") or offer_id
                contractor_email = contractor_email or auth_lookup.get("contractor_email")

        # 1. Anti-Tamper & Identity Verification (always runs, even for replays)
        valid, reason = verify_authorized_mandate(
            proof_hash=mandate_proof_hash,
            tier_id=tier_id,
            agreed_rate=agreed_monthly_rate,
            contractor_email=contractor_email,
            offer_id=offer_id,
        )
        if not valid:
            logger.warning(f"[SECURITY] Mandate verification failed for {tier_id}: {reason}")
            return {
                "status": "REJECTED",
                "error": "MANDATE_SECURITY_BREACH",
                "reason": reason,
                "message": f"Purchase rejected: {reason}",
            }

        # 2. Idempotency Check: a verified replay returns the existing subscription
        cache_key = offer_id or mandate_proof_hash
        if cache_key and cache_key in _COMPLETED_SUBSCRIPTIONS:
            return _COMPLETED_SUBSCRIPTIONS[cache_key]

        # Mandates issued without an email are locked to their first redeemer
        if mandate_proof_hash and contractor_email:
            bind_mandate_email(mandate_proof_hash, contractor_email)
        auth = get_authorized_mandate(offer_id or mandate_proof_hash) or {}

        buyer_id = auth.get("buyer_agent_id", "unknown")
        norm_email = contractor_email.strip().lower() if contractor_email else None

        # Plan Change Model: Check for active existing subscription for this contractor
        old_sub_id = _ACTIVE_CONTRACTOR_SUBSCRIPTIONS.get(norm_email) if norm_email else None
        old_sub = _COMPLETED_SUBSCRIPTIONS.get(old_sub_id) if old_sub_id else None
        old_rate = 0.0
        if old_sub and isinstance(old_sub, dict) and old_sub.get("status") == "ACTIVE":
            old_rate = old_sub.get("agreed_monthly_rate", 0.0)
            old_sub_id = old_sub.get("subscription_id", old_sub_id)
        else:
            old_sub_id = None
            old_sub = None

        # Resolve effective monthly budget cap
        cap = auth.get("monthly_budget_cap")
        if norm_email and norm_email in getattr(ledger, "_contractor_caps", {}):
            cap = ledger._contractor_caps[norm_email]
        if cap is None:
            cap = 100.0

        # Purchase-time budget enforcement
        remaining_before = ledger.get_remaining_budget(agent_id=buyer_id, cap=cap, contractor_email=contractor_email)
        effective_available = round(remaining_before + old_rate, 2)

        if agreed_monthly_rate > effective_available or agreed_monthly_rate > cap:
            logger.warning(
                f"[SECURITY] Purchase budget breach: rate ${agreed_monthly_rate:.2f}/mo exceeds "
                f"available ${effective_available:.2f}/mo (cap: ${cap:.2f})"
            )
            return {
                "status": "REJECTED",
                "error": "BUDGET_EXHAUSTED",
                "reason": (
                    f"Purchase rate ${agreed_monthly_rate:.2f}/mo exceeds available monthly budget of "
                    f"${effective_available:.2f} (budget cap: ${cap:.2f})."
                ),
                "monthly_budget_cap": round(cap, 2),
                "monthly_cap_remaining": round(remaining_before, 2),
                "active_subscription_id": old_sub_id,
            }

        # 3. Invoke PayPal Gateway (calls real PayPal Sandbox in live mode; deterministic in mock mode)
        paypal_result = await paypal_service.create_subscription(
            tier_id=tier_id,
            agreed_monthly_rate=agreed_monthly_rate,
            contractor_email=contractor_email or "marcus@millercustomfloors.com",
            contractor_name="Marcus Miller",
            offer_id=offer_id,
            mandate_proof_hash=mandate_proof_hash,
        )
        sub_id = paypal_result["subscription_id"]
        sub_status = paypal_result.get("status", "ACTIVE")
        approval_url = paypal_result.get("approval_url")
        created_time = paypal_result.get("created_time") or datetime.datetime.now(datetime.timezone.utc).isoformat()
        next_billing = paypal_result.get("next_billing_time") or (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30)).isoformat()
        negotiation_id = auth.get("negotiation_id") or f"neg_{hashlib.sha256((mandate_proof_hash or offer_id).encode()).hexdigest()[:12]}"
        payer_id = paypal_result.get("payer_id") or (f"PAYER-{hashlib.sha256(contractor_email.strip().lower().encode()).hexdigest()[:12].upper()}" if contractor_email else "PAYER-A2A-BUYER")
        vault_id = paypal_result.get("vault_id") or f"vault_tok_{sub_id.lower().replace('-', '_')}"
        payment_token = paypal_result.get("payment_token") or f"tok_{hashlib.sha256(f'{sub_id}:payment'.encode()).hexdigest()[:16]}"
        paypal_req_id = paypal_result.get("paypal_request_id") or f"req_{hashlib.sha256(sub_id.encode()).hexdigest()[:16]}"
        hateoas_links = paypal_result.get("hateoas_links") or [
            {
                "href": f"https://api.sandbox.paypal.com/v1/billing/subscriptions/{sub_id}",
                "rel": "self",
                "method": "GET",
            },
            {
                "href": f"https://api.sandbox.paypal.com/v1/billing/subscriptions/{sub_id}/cancel",
                "rel": "cancel",
                "method": "POST",
            },
        ]
        if not approval_url and hateoas_links:
            for link in hateoas_links:
                if link.get("rel") == "approve":
                    approval_url = link.get("href")
                    break

        # Mark old subscription as REPLACED (Plan Change Model)
        if old_sub_id and old_sub:
            if sub_status == "ACTIVE":
                old_sub["status"] = "REPLACED"
                old_sub["replaced_by"] = sub_id
                old_sub["replaced_at"] = created_time
                old_sub["message"] = f"Subscription {old_sub_id} was replaced by {sub_id}."
            else:
                # Keep old subscription ACTIVE while new plan awaits buyer authorization in PayPal
                old_sub["pending_replacement"] = sub_id
                old_sub["pending_replacement_tier"] = tier_id
                old_sub["pending_replacement_at"] = created_time

        # Reconcile contractor active pointer and ledger commitment strictly from active subscription state
        if norm_email:
            if sub_status == "ACTIVE":
                _ACTIVE_CONTRACTOR_SUBSCRIPTIONS[norm_email] = sub_id
                ledger.sync_contractor_commitment(
                    contractor_email=norm_email,
                    active_monthly_rate=agreed_monthly_rate,
                    agent_id=buyer_id,
                )
            elif old_sub_id and old_sub and old_sub.get("status") == "ACTIVE":
                _ACTIVE_CONTRACTOR_SUBSCRIPTIONS[norm_email] = old_sub_id
                ledger.sync_contractor_commitment(
                    contractor_email=norm_email,
                    active_monthly_rate=old_rate,
                    agent_id=buyer_id,
                )
            elif _ACTIVE_CONTRACTOR_SUBSCRIPTIONS.get(norm_email) == sub_id:
                _ACTIVE_CONTRACTOR_SUBSCRIPTIONS.pop(norm_email, None)
                reconcile_contractor_ledger(norm_email)
        else:
            if sub_status == "ACTIVE":
                ledger.record_spend(
                    agreed_monthly_rate,
                    {
                        "agent_id": buyer_id,
                        "tier_id": tier_id,
                        "mandate_proof_hash": mandate_proof_hash,
                    },
                )

        remaining_budget = ledger.get_remaining_budget(
            agent_id=buyer_id, cap=cap, contractor_email=contractor_email
        )

        # Return the exact signed mandate issued at negotiation, unchanged
        ap2_mandate = auth.get("ap2_mandate")
        if ap2_mandate is None:
            ap2_mandate = build_ap2_intent_mandate(
                buyer_agent_id=buyer_id,
                amount=agreed_monthly_rate,
                recurrence="monthly",
                category="TELEPHONY_AI_SCREENER",
                tier_id=tier_id or "*",
                contractor_email=contractor_email,
                negotiation_id=negotiation_id,
            )

        billing_cycles = [
            {
                "sequence": 1,
                "tenure_type": "REGULAR",
                "frequency": {"interval_unit": "MONTH", "interval_count": 1},
                "total_cycles": 0,
                "pricing_scheme": {
                    "fixed_price": {"value": f"{agreed_monthly_rate:.2f}", "currency_code": "USD"}
                },
            }
        ]

        if sub_status == "APPROVAL_PENDING":
            next_action = {
                "type": "human_approval_required",
                "action": "approve_paypal_subscription",
                "approval_url": approval_url,
                "subscription_id": sub_id,
                "message": "Human approval required: please authorize the recurring subscription in PayPal Sandbox at approval_url before provisioning.",
            }
            msg = f"PayPal subscription {sub_id} created with status APPROVAL_PENDING. Awaiting buyer authorization via PayPal checkout."
            vault_status = "PENDING_APPROVAL"
            vault_authorized = False
            customer_present = True
        else:
            next_action = {
                "type": "tool_call",
                "tool": "provision_telecom_line",
                "parameters": {
                    "subscription_id": sub_id,
                    "contractor_email": contractor_email,
                    "area_code": "863",
                },
            }
            msg = f"Successfully bound PayPal subscription {sub_id} at ${agreed_monthly_rate:.2f}/mo under verified AP2 Intent Mandate."
            vault_status = "VAULT_BOUND"
            vault_authorized = True
            customer_present = False

        # Generate traceable proof linking negotiation -> subscription -> ERP
        mandate_id = ap2_mandate.get("mandate_id") if isinstance(ap2_mandate, dict) else None
        cart_id = auth.get("ap2_cart_mandate", {}).get("cart_id") if isinstance(auth.get("ap2_cart_mandate"), dict) else None
        traceable_proof = f"mandate:{mandate_id or 'none'}|cart:{cart_id or 'none'}|hash:{mandate_proof_hash or offer_id}"

        response = {
            "status": sub_status,
            "subscription_id": sub_id,
            "negotiation_id": negotiation_id,
            "offer_id": auth.get("offer_id"),
            "buyer_agent_id": buyer_id,
            "plan_id": f"P-FLSMITH-{tier_id.upper().replace('-', '_')}",
            "product_id": "PROD-FIELDSMITH-A2A-TELEPHONY",
            "payer_id": payer_id,
            "vault_id": vault_id,
            "payment_token": payment_token,
            "payment_method": "paypal_vault_mit",
            "tier_id": tier_id,
            "agreed_monthly_rate": round(agreed_monthly_rate, 2),
            "monthly_budget_cap": round(cap, 2),
            "monthly_cap_remaining": round(remaining_budget, 2),
            "billing_cycle": "monthly",
            "billing_cycles": billing_cycles,
            "currency": "USD",
            "mandate_proof_hash": mandate_proof_hash,
            "traceable_proof": traceable_proof,
            "contractor_email": contractor_email,
            "contractor_name": "Marcus Miller",
            "business_entity": "Miller Custom Flooring LLC",
            "subscriber_country_code": paypal_result.get("subscriber_country_code", "US"),
            "paypal_vault_status": vault_status,
            "vault_billing_authorized": vault_authorized,
            "vault_customer_present": customer_present,
            "paypal_environment": "sandbox",
            "paypal_request_id": paypal_req_id,
            "create_time": created_time,
            "next_billing_time": next_billing,
            "hateoas_links": hateoas_links,
            "ap2_intent_mandate": ap2_mandate,
            "ap2_cart_mandate": auth.get("ap2_cart_mandate"),
            "next_action": next_action,
            "message": msg,
        }
        if approval_url:
            response["approval_url"] = approval_url
        if old_sub_id:
            response["replaces_subscription_id"] = old_sub_id

        # Cache for strict idempotency
        if mandate_proof_hash:
            _COMPLETED_SUBSCRIPTIONS[mandate_proof_hash] = response
        if auth.get("offer_id"):
            _COMPLETED_SUBSCRIPTIONS[auth["offer_id"]] = response
        if offer_id:
            _COMPLETED_SUBSCRIPTIONS[offer_id] = response
        _COMPLETED_SUBSCRIPTIONS[sub_id] = response
        if norm_email:
            if sub_status == "ACTIVE":
                _ACTIVE_CONTRACTOR_SUBSCRIPTIONS[norm_email] = sub_id
            reconcile_contractor_ledger(norm_email)
        return response



    async def calculate_quote(
        self,
        trade_id: str,
        square_footage: float,
        material_type: str,
        postal_code: str,
    ) -> Dict[str, Any]:
        """Deprecated legacy method retained for backwards compatibility."""
        waste = round(square_footage * 1.10, 1)
        deposit = 250.00 if square_footage >= 500 else 150.00
        return {
            "trade_id": trade_id,
            "waste_allowance_sq_ft": waste,
            "required_deposit": deposit,
            "labor_estimate": f"${square_footage * 4.00:.2f} - ${square_footage * 5.50:.2f}",
            "postal_code": postal_code,
            "deprecated": True,
        }

    async def provision_telecom_line(
        self,
        subscription_id: str,
        contractor_email: str,
        area_code: str = "863",
        simulate_exhaustion: bool = False,
    ) -> Dict[str, Any]:
        """Tool implementation: Executes KYC-verified DID allocation with automated LATA failover."""
        # 0. US-Domestic Only (NANP) Validation
        area_code_str = str(area_code).strip()
        if not re.match(r"^[2-9]\d{2}$", area_code_str) or area_code_str.endswith("11"):
            return {
                "status": "REJECTED",
                "error": "US_DOMESTIC_ONLY",
                "reason": f"FieldSmith Pro services are strictly restricted to licensed US contractors (NANP +1). Invalid US area code: '{area_code}'.",
            }

        # 1. Validate that the PayPal subscription exists and has been captured
        sub = _COMPLETED_SUBSCRIPTIONS.get(subscription_id.strip())
        if not sub:
            try:
                remote_sub = await paypal_service.verify_subscription(subscription_id.strip())
                if remote_sub and not remote_sub.get("mock_mode"):
                    remote_status = remote_sub.get("status", "ACTIVE")
                    tier_id, rate = resolve_tier_from_paypal_plan(remote_sub.get("plan_id"))
                    subscriber_data = remote_sub.get("subscriber") or {}
                    shipping_addr = subscriber_data.get("shipping_address") or {}
                    addr = shipping_addr.get("address") or subscriber_data.get("address") or {}
                    country = (
                        addr.get("country_code")
                        or subscriber_data.get("country_code")
                        or remote_sub.get("country_code")
                        or "US"
                    )
                    sub = {
                        "subscription_id": subscription_id.strip(),
                        "status": remote_status,
                        "contractor_email": subscriber_data.get("email_address", contractor_email),
                        "tier_id": tier_id,
                        "agreed_monthly_rate": rate,
                        "plan_id": remote_sub.get("plan_id"),
                        "subscriber_country_code": country,
                        "subscriber": subscriber_data,
                    }
                    _COMPLETED_SUBSCRIPTIONS[subscription_id.strip()] = sub
            except Exception as e:
                logger.warning(f"Could not verify remote PayPal subscription {subscription_id}: {e}")

        if not sub:
            return {
                "status": "REJECTED",
                "error": "SUBSCRIPTION_NOT_FOUND",
                "reason": f"Subscription '{subscription_id}' does not exist or has not been activated in PayPal Vault. Call purchase_subscription first.",
            }

        # 1.5 Validate payment approval and active status
        sub_status = sub.get("status")
        if sub_status == "APPROVAL_PENDING":
            return {
                "status": "REJECTED",
                "error": "PAYMENT_APPROVAL_PENDING",
                "reason": f"Subscription '{subscription_id}' is pending buyer approval in PayPal. It must be approved before telecom provisioning can proceed.",
                "approval_url": sub.get("approval_url"),
            }
        elif sub_status in ["CANCELLED", "SUSPENDED", "PAYMENT_FAILED"]:
            return {
                "status": "REJECTED",
                "error": f"SUBSCRIPTION_{sub_status}",
                "reason": f"Subscription '{subscription_id}' is {sub_status}. Telecom provisioning is blocked for inactive subscriptions.",
            }
        elif sub_status == "REPLACED":
            return {
                "status": "REJECTED",
                "error": "SUBSCRIPTION_SUPERSEDED",
                "reason": f"Subscription '{subscription_id}' was replaced by '{sub.get('replaced_by')}' and is no longer active.",
            }

        # 2. Validate US-Domestic subscriber entity
        subscriber_country = (
            sub.get("subscriber_country_code")
            or sub.get("country_code")
            or (sub.get("subscriber", {}).get("shipping_address", {}).get("address", {}).get("country_code") if isinstance(sub.get("subscriber"), dict) else None)
            or (sub.get("subscriber", {}).get("address", {}).get("country_code") if isinstance(sub.get("subscriber"), dict) else None)
            or (sub.get("subscriber", {}).get("country_code") if isinstance(sub.get("subscriber"), dict) else None)
        )
        if subscriber_country and str(subscriber_country).strip().upper() != "US":
            return {
                "status": "REJECTED",
                "error": "US_DOMESTIC_ONLY",
                "reason": f"FieldSmith Pro services are strictly restricted to US entities. Payer country '{subscriber_country}' is not supported.",
            }

        # 3. Identity anti-theft: Ensure contractor_email matches the subscription owner
        owner_email = sub.get("contractor_email", "")
        if owner_email and contractor_email.strip().lower() != owner_email.strip().lower():
            return {
                "status": "REJECTED",
                "error": "IDENTITY_MISMATCH_DETECTED",
                "reason": f"Subscription '{subscription_id}' belongs to '{owner_email}', cannot be provisioned for '{contractor_email}'.",
            }

        req = ProvisionRequest(
            subscriptionId=subscription_id,
            contractorEmail=contractor_email,
            areaCode=area_code,
            simulateExhaustion=simulate_exhaustion,
        )

        # Check if this contractor has an existing DID to retain (from replaced sub or contractor history)
        replaces_sub_id = sub.get("replaces_subscription_id")
        retained_did = None
        if replaces_sub_id:
            old_sub = _COMPLETED_SUBSCRIPTIONS.get(replaces_sub_id)
            if old_sub:
                retained_did = old_sub.get("allocated_did") or old_sub.get("assigned_did")
        if not retained_did and contractor_email:
            retained_did = telnyx_provisioner.get_contractor_did(contractor_email)

        if retained_did:
            res = telnyx_provisioner.retain_did(req, retained_did, replaces_subscription_id=replaces_sub_id)
        else:
            res = await telnyx_provisioner.provision_did(req, simulate_exhaustion=simulate_exhaustion)
        res_dict = res.model_dump(by_alias=True)

        # Accurately resolve assigned DID from Telnyx response
        allocated_did = res.assigned_did or res_dict.get("assignedDid") or res_dict.get("assigned_did")
        sub["allocated_did"] = allocated_did
        sub["assigned_did"] = allocated_did
        _COMPLETED_SUBSCRIPTIONS[subscription_id]["allocated_did"] = allocated_did
        _COMPLETED_SUBSCRIPTIONS[subscription_id]["assigned_did"] = allocated_did
        res_dict["status"] = res.status
        res_dict["assignedDid"] = allocated_did
        res_dict["assigned_did"] = allocated_did
        res_dict["allocatedDid"] = allocated_did
        res_dict["allocated_did"] = allocated_did
        if replaces_sub_id:
            res_dict["retained_from_subscription"] = replaces_sub_id
            res_dict["retainedFromSubscription"] = replaces_sub_id

        # Dynamically populate downline parameters from the verified subscription
        tier_id = sub.get("tier_id", "solo-starter")
        monthly_fee = sub.get("agreed_monthly_rate", 49.99)
        contractor_name = sub.get("contractor_name", "Marcus Miller")
        business_entity = sub.get("business_entity", "Miller Custom Flooring LLC")
        proof = sub.get("traceable_proof") or sub.get("mandate_proof_hash") or f"mandate:{subscription_id}"
        trade_vertical = "Tile & Custom Flooring" if "floor" in tier_id or "solo" in tier_id else "Commercial Field Services"

        res_dict["next_action"] = {
            "type": "tool_call",
            "tool": "dispatch_zapier_mcp",
            "parameters": {
                "workflow_type": "a2a_onboarding",
                "contractor_name": contractor_name,
                "business_entity": business_entity,
                "allocated_did": allocated_did,
                "trade_vertical": trade_vertical,
                "monthly_subscription_fee": monthly_fee,
                "paypal_subscription_id": subscription_id,
                "contractor_email": contractor_email,
                "mandate_proof_hash": proof,
            },
        }
        return res_dict

    async def dispatch_zapier_mcp(
        self,
        workflow_type: str = "a2a_onboarding",
        contractor_name: str = "Marcus Miller",
        business_entity: str = "Miller Custom Flooring LLC",
        allocated_did: str = "+1 (863) 267-8902",
        trade_vertical: str = "Tile & Custom Flooring",
        monthly_subscription_fee: float = 79.99,
        paypal_subscription_id: str = "I-AUTONOMOUS-8902",
        contractor_email: str = "marcus@millercustomfloors.com",
        mandate_proof_hash: Optional[str] = None,
        webhook_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Tool implementation: Dispatches downline business automation through Zapier MCP."""
        req = ZapierSyncRequest(
            workflowType=workflow_type,
            contractorName=contractor_name,
            businessEntity=business_entity,
            allocatedDid=allocated_did,
            tradeVertical=trade_vertical,
            monthlySubscriptionFee=monthly_subscription_fee,
            paypalSubscriptionId=paypal_subscription_id,
            contractorEmail=contractor_email,
            mandateProofHash=mandate_proof_hash,
            webhookUrl=webhook_url,
        )
        res = await zapier_mcp_dispatcher.execute_downline_sync(req)
        return res.model_dump(by_alias=True)


seller_agent = SellerAgent()
