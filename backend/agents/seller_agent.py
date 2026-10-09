"""
Seller Agent (AP2 Autonomous Seller MCP Server).
Exposes the merchant capability catalog and executes autonomous compute commitments.
Can be queried programmatically by any Model Context Protocol (MCP) compliant client or Buyer Agent.
Conforms to FIDO / AP2 Intent Mandate specifications.
"""

import os
import re
import json
import math
import uuid
import hashlib
import datetime
import logging
from typing import Dict, Any, List, Optional
from ..models import (
    SpendingMandateRequest,
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
    PUBLIC_AP2_TIER_ALIASES,
    QUOTA_UNIT,
    QUOTA_UNIT_DEFINITION,
    INCLUDED_ON_ALL_PLANS,
    ACTIVATION,
    TRUST_SIGNALS,
    resolve_plan,
    get_plan,
    get_plans,
    get_tier_aliases,
    get_public_tier_aliases,
    get_quota_unit,
    get_quota_unit_definition,
    get_included_on_all_plans,
    get_activation,
    get_trust_signals,
    get_seller_profile,
    resolve_paypal_plan_id,
    plan_summary,
    public_plan,
)
from ..services.zapier_mcp_dispatcher import zapier_mcp_dispatcher
from ..services.crypto_mandate import (
    verify_mandate_proof,
    verify_ap2_intent_mandate,
    is_trusted_buyer_key,
)
from ..database import get_buyer_key_email
from ..config import settings
from ..services.ap2_service import (
    AP2_MERCHANT_ID,
    create_merchant_checkout,
    create_merchant_counter_offer,
    verify_ap2_chains,
    create_checkout_receipt_jwt,
    create_payment_receipt_jwt,
    compute_checkout_hash,
    get_issued_checkout,
    ERR_INVALID_CREDENTIAL,
    ERR_INVALID_MANDATE,
    ERR_UNRESOLVED_CONSTRAINT,
)

logger = logging.getLogger("seller_agent")

# AP2 Profile MCP Tool Declarations (Autonomous Compute & Worker Node Network)
AP2_SELLER_MCP_TOOLS = [
    {
        "name": "get_service_catalog",
        "description": "Returns the AP2 compute service catalog: plans, workload task quotas, capabilities included on every plan, activation requirements, and policy links.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "inspect_subscription_tiers",
        "description": "Inspects AP2 autonomous compute subscription tiers ($49.99 High-Throughput Batch Worker, $79.99 Dedicated AI Service Gateway, $179.99 Enterprise Cluster Node), workload task quotas, and features.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "negotiate_tier_terms",
        "description": "Evaluates buyer budget cap against desired AP2 compute tier. If asking price exceeds budget, returns pre-approved counter-offer down-tiering to a plan within budget (e.g. Batch Worker at $49.99/mo). Issues merchant-signed Checkout JWT (ES256) binding line items and price in integer minor units.",
        "input_schema": {
            "type": "object",
            "required": ["buyer_agent_id", "buyer_email", "tier_id", "monthly_budget_cap"],
            "properties": {
                "buyer_agent_id": {
                    "type": "string",
                    "description": "Unique identifier of the Buyer Agent",
                },
                "buyer_email": {
                    "type": "string",
                    "description": "Buyer PayPal billing email. The issued mandate is bound to this email and can only be redeemed by it.",
                },
                "tier_id": {
                    "type": "string",
                    "description": "Desired AP2 subscription tier ('ap2-batch' at $49.99, 'ap2-gateway' at $79.99, 'ap2-cluster' at $179.99)",
                },
                "monthly_budget_cap": {
                    "type": "number",
                    "description": "Strict maximum monthly budget cap authorized by the buyer mandate",
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
                    "default": "autonomous-node-service",
                    "description": "Authorized spending category",
                },
                "buyer_intent_mandate": {
                    "type": "object",
                    "description": "Optional buyer-signed AP2 Intent Mandate (vct: ap2.mandate.intent.1). If omitted, seller creates a seller-attested intent mandate on buyer's behalf.",
                },
                "checkout_jwt": {
                    "type": "string",
                    "description": "Optional merchant Checkout JWT to renegotiate or inspect.",
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
        "description": "Binds a verified AP2 v0.2 Mandate Chain (Checkout + Payment SD-JWTs) or signed AP2 Cart Mandate offer to PayPal Recurring Vault for automated monthly billing. Returns merchant-signed Checkout Receipt and Payment Receipt.",
        "input_schema": {
            "type": "object",
            "required": ["buyer_email"],
            "properties": {
                "checkout_mandate_chain": {
                    "type": "string",
                    "description": "AP2 v0.2 Checkout Mandate presentation chain (open mandate + closed mandate ~~ delimited SD-JWT tokens).",
                },
                "payment_mandate_chain": {
                    "type": "string",
                    "description": "AP2 v0.2 Payment Mandate presentation chain (open mandate + closed mandate ~~ delimited SD-JWT tokens).",
                },
                "checkout_jwt": {
                    "type": "string",
                    "description": "Merchant-signed Checkout JWT returned during negotiation.",
                },
                "offer_id": {
                    "type": "string",
                    "description": "Merchant offer_id returned in Cart Mandate and next_action (e.g. 'off_ap2_batch_49_...'). Automatically resolves and binds all pre-verified terms without rate tampering risk.",
                },
                "buyer_email": {
                    "type": "string",
                    "description": "Buyer PayPal billing email; must match the email the mandate was negotiated for.",
                },
                "tier_id": {
                    "type": "string",
                    "description": "Optional if offer_id is provided. Subscription tier ID (e.g. 'ap2-batch', 'ap2-gateway', 'ap2-cluster').",
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
        "name": "provision_compute_node",
        "description": "Provisions a dedicated autonomous compute node endpoint (mcp+https) upon verified PayPal subscription.",
        "input_schema": {
            "type": "object",
            "required": ["subscription_id", "buyer_email"],
            "properties": {
                "subscription_id": {"type": "string", "description": "Verified PayPal subscription ID"},
                "buyer_email": {"type": "string", "description": "Buyer notification email"},
                "node_type": {"type": "string", "default": "gateway", "description": "Target compute node architecture (batch, gateway, cluster)"},
            },
        },
    },
    {
        "name": "dispatch_zapier_mcp",
        "description": "Executes downline multi-app back-office action chain into accounting and task management systems.",
        "input_schema": {
            "type": "object",
            "properties": {
                "workflow_type": {"type": "string", "default": "a2a_onboarding"},
                "subscriber_name": {"type": "string"},
                "business_entity": {"type": "string"},
                "node_endpoint": {"type": "string"},
                "service_vertical": {"type": "string"},
                "monthly_subscription_fee": {"type": "number"},
                "paypal_subscription_id": {"type": "string"},
                "buyer_email": {"type": "string"},
                "mandate_proof_hash": {"type": "string"},
                "webhook_url": {"type": "string"},
            },
        },
    },
    {
        "name": "get_subscription_details",
        "description": "Retrieves the live status, plan information, next billing date, and subscriber details of a PayPal subscription. Aligns with official PayPal AI-Toolkit subscription schema.",
        "input_schema": {
            "type": "object",
            "required": ["subscription_id"],
            "properties": {
                "subscription_id": {
                    "type": "string",
                    "description": "PayPal Subscription ID (e.g. 'I-...' or 'I-A2A-VAULT-...')",
                },
            },
        },
    },
]

SELLER_MCP_TOOLS = AP2_SELLER_MCP_TOOLS

from ..database import SubscriptionsDictProxy, ActiveContractorSubscriptionsProxy

_COMPLETED_SUBSCRIPTIONS = SubscriptionsDictProxy()
_ACTIVE_CONTRACTOR_SUBSCRIPTIONS = ActiveContractorSubscriptionsProxy()


def reconcile_contractor_ledger(contractor_email: str) -> float:
    """
    Reconciles the buyer's ledger commitment strictly from subscription state:
    commitment = the rate of the buyer's one ACTIVE subscription.
    Pending, replaced, cancelled, and suspended plans contribute 0.0 to commitment.
    Returns the active monthly commitment.
    """
    if not contractor_email:
        return 0.0
    norm_email = contractor_email.strip().lower()

    # Find the contractor/buyer active subscription
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
                cand_email = (v.get("buyer_email") or v.get("contractor_email") or "").strip().lower()
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


def _mask_email(email: Optional[str]) -> Optional[str]:
    """Masks an email for responses that any caller can request."""
    if not email or "@" not in email:
        return email
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


def resolve_tier_from_paypal_plan(plan_id: Optional[str]) -> tuple[str, float]:
    """Maps a PayPal billing plan_id to its canonical tier_id and agreed monthly rate."""
    if not plan_id:
        return ("ap2-gateway", 79.99)
    p = plan_id.lower()
    if plan_id == getattr(settings, "paypal_plan_id_solo", "P-AP2-BATCH-WORKER") or "batch" in p or "solo" in p or "starter" in p:
        return ("ap2-batch", 49.99)
    elif plan_id == getattr(settings, "paypal_plan_id_dispatch", "P-AP2-CLUSTER-NODE") or "cluster" in p or "dispatch" in p:
        return ("ap2-cluster", 179.99)
    elif plan_id == getattr(settings, "paypal_plan_id_pro", "P-AP2-SERVICE-GATEWAY") or "gateway" in p or "pro" in p:
        return ("ap2-gateway", 79.99)
    return ("ap2-gateway", 79.99)


class SellerAgent:
    def __init__(self, agent_name: Optional[str] = None):
        self._custom_name = agent_name

    @property
    def agent_name(self) -> str:
        if self._custom_name:
            return self._custom_name
        return "AP2 Autonomous Seller MCP"

    @agent_name.setter
    def agent_name(self, value: str):
        self._custom_name = value

    def list_mcp_tools(self) -> List[Dict[str, Any]]:
        """Returns the MCP tool definitions for agent tool-use discovery."""
        return SELLER_MCP_TOOLS

    async def get_service_catalog(self) -> Dict[str, Any]:
        """Tool implementation: Returns the plan catalog with buyer context for intent matching."""
        return {
            "provider": self.agent_name,
            "currency": "USD",
            "quota_unit": get_quota_unit(),
            "quota_unit_definition": get_quota_unit_definition(),
            "plans": [public_plan(plan) for plan in get_plans()],
            "included_on_all_plans": get_included_on_all_plans(),
            "supported_workloads": [
                {
                    "workload_id": "batch-processing",
                    "title": "High-throughput asynchronous batch processing",
                    "intake_focus": ["Queue depth", "Data transformation", "Payload verification", "Batch scheduling"],
                },
                {
                    "workload_id": "gateway-routing",
                    "title": "Real-time AI service gateway routing",
                    "intake_focus": ["Request routing", "Model mediation", "Low-latency streaming", "Protocol translation"],
                },
                {
                    "workload_id": "cluster-orchestration",
                    "title": "Distributed multi-agent cluster execution",
                    "intake_focus": ["Resource allocation", "State replication", "Cluster scaling", "Fault tolerance"],
                },
            ],
            "workloads_note": "All compute workloads are supported across all tiers. Pick a tier by throughput and task volume.",
            "tier_id_aliases": get_public_tier_aliases("ap2"),
            "activation": get_activation(),
            "trust_signals": get_trust_signals(),
        }

    async def inspect_subscription_tiers(self) -> Dict[str, Any]:
        """Tool implementation: Returns subscription tiers, quotas, and pricing parameters."""
        subscription_plans = []
        for plan in get_plans():
            entry = public_plan(plan)
            entry["is_negotiable"] = False
            entry["tier_id_aliases"] = [alias for alias, target in get_public_tier_aliases("ap2").items() if target == plan["tier_id"]]
            subscription_plans.append(entry)
        return {
            "provider": self.agent_name,
            "currency": "USD",
            "protocol_support": ["AP2", "MCP"],
            "service_description": "AP2 Autonomous Compute & Worker Node Network for Agent Infrastructure",
            "quota_unit": get_quota_unit(),
            "quota_unit_definition": get_quota_unit_definition(),
            "billing_period": "monthly",
            "subscription_plans": subscription_plans,
            "included_on_all_plans": get_included_on_all_plans(),
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

        kid = buyer_intent_mandate.get("kid") if isinstance(buyer_intent_mandate, dict) else None
        pub_hex = buyer_intent_mandate.get("public_key") if isinstance(buyer_intent_mandate, dict) else None
        if (
            buyer_intent_mandate
            and is_trusted_buyer_key(kid, pub_hex)
            and verify_ap2_intent_mandate(buyer_intent_mandate)
        ):
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
        chk_record = create_merchant_checkout(
            tier_id=tier_id,
            monthly_price=amount,
            contractor_email=email,
            order_id=offer_id,
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
            "checkout_jwt": chk_record["checkout_jwt"],
            "checkout_hash": chk_record["checkout_hash"],
            "order_id": chk_record["order_id"],
            "nonce": chk_record.get("nonce"),
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
            "checkout_jwt": chk_record["checkout_jwt"],
            "checkout_hash": chk_record["checkout_hash"],
            "order_id": chk_record["order_id"],
            "nonce": chk_record.get("nonce"),
        }

    async def negotiate_tier_terms(
        self,
        buyer_agent_id: str,
        tier_id: str,
        monthly_budget_cap: float,
        contractor_email: Optional[str] = None,
        proposed_price: Optional[float] = None,
        recurrence: str = "monthly",
        category: Optional[str] = None,
        buyer_intent_mandate: Optional[Dict[str, Any]] = None,
        buyer_email: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Tool implementation: Evaluates buyer budget cap against desired tier.
        Autonomously negotiates down-tier counter-offers with verifiable AP2 cryptographic mandate proof hashes.
        Accepts optional buyer_intent_mandate signed by the buyer agent; falls back to seller-attested intent mandate.
        """
        if category is None:
            category = "autonomous-node-service"

        if not contractor_email and buyer_email:
            contractor_email = buyer_email

        plan = resolve_plan(tier_id)
        if plan is None:
            available = ", ".join(f"'{p['tier_id']}' (${p['monthly_price']:.2f}/mo)" for p in PLANS)
            reason_msg = f"Unknown tier_id '{tier_id}'. Available tiers: {available}."
            return {
                "status": "REJECTED",
                "error": "UNKNOWN_TIER",
                "approved": False,
                "original_request_approved": False,
                "tier_id": tier_id,
                "reason": reason_msg,
            }

        standard_price = plan["monthly_price"]
        workload_tasks = plan.get("workload_tasks_per_month", 125)

        if not contractor_email and buyer_intent_mandate and isinstance(buyer_intent_mandate, dict):
            payer = buyer_intent_mandate.get("payer")
            if isinstance(payer, dict):
                contractor_email = payer.get("email")

        signed_cap = None
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
                "error": "BUYER_EMAIL_REQUIRED",
                "reason": "buyer_email is required; the issued AP2 mandate is bound to it.",
            }

        email = contractor_email.strip().lower()
        # Saved caps come only from key registration or a mandate signed by the buyer's own
        # registered key; any other cap applies to this negotiation only and cannot exceed the saved cap.
        signing_kid = buyer_intent_mandate.get("kid") if isinstance(buyer_intent_mandate, dict) else None
        if signed_cap is not None and signing_kid and get_buyer_key_email(signing_kid) == email:
            ledger.set_contractor_cap(email, monthly_budget_cap, source="signed_mandate")
        else:
            monthly_budget_cap = ledger.effective_cap(email, monthly_budget_cap)

        active_sub_id = _ACTIVE_CONTRACTOR_SUBSCRIPTIONS.get(email) if email else None
        active_sub = _COMPLETED_SUBSCRIPTIONS.get(active_sub_id) if active_sub_id else None
        if active_sub and active_sub.get("status") != "ACTIVE":
            active_sub = None
            active_sub_id = None
        if not active_sub_id and email:
            for s in reversed(list(_COMPLETED_SUBSCRIPTIONS.values())):
                if isinstance(s, dict) and (s.get("buyer_email", "").strip().lower() == email or s.get("contractor_email", "").strip().lower() == email):
                    if s.get("status") == "ACTIVE":
                        active_sub_id = s.get("subscription_id")
                        active_sub = s
                        break

        def norm_plan(p: Optional[str]) -> str:
            p = (p or "").lower().replace("-", "").replace("_", "")
            if "batch" in p or "solo" in p:
                return "ap2-batch"
            if "gateway" in p or ("pro" in p and "dispatch" not in p and "cluster" not in p):
                return "ap2-gateway"
            if "cluster" in p or "dispatch" in p:
                return "ap2-cluster"
            return p

        req_norm = norm_plan(tier_id)
        current_norm = norm_plan(active_sub.get("tier_id")) if active_sub else None

        # Guard 1: Already subscribed to the requested tier
        if active_sub and req_norm == current_norm:
            logger.info(
                f"[A2A_SELLER] Subscriber {email} already subscribed to active plan {active_sub_id} ({active_sub.get('tier_id')})"
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
                    f"Buyer '{email}' is already actively subscribed to '{tier_id}' "
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
            next_action_params: Dict[str, Any] = {
                "offer_id": issued["offer_id"],
                "tier_id": tier_id,
                "agreed_monthly_rate": standard_price,
                "mandate_proof_hash": issued["hash"],
                "buyer_email": email,
                "checkout_jwt": issued["checkout_jwt"],
                "checkout_hash": issued["checkout_hash"],
                "nonce": issued.get("nonce"),
            }

            next_action = {
                "type": "tool_call",
                "tool": "purchase_subscription",
                "parameters": next_action_params,
            }
            res_approved: Dict[str, Any] = {
                "status": "APPROVED",
                "approved": True,
                "original_request_approved": True,
                "negotiation_id": issued["negotiation_id"],
                "offer_id": issued["offer_id"],
                "tier_id": tier_id,
                "agreed_monthly_rate": standard_price,
                "monthly_budget_cap": round(monthly_budget_cap, 2),
                "monthly_cap_remaining": round(monthly_budget_cap - standard_price, 2),
                "mandate_proof_hash": issued["hash"],
                "ap2_intent_mandate": issued["ap2_mandate"],
                "ap2_cart_mandate": issued["ap2_cart_mandate"],
                "checkout_jwt": issued["checkout_jwt"],
                "checkout_hash": issued["checkout_hash"],
                "order_id": issued["order_id"],
                "nonce": issued.get("nonce"),
                "offer_expires_at": issued["offer_expires_at"],
                "next_action": next_action,
                "workload_tasks_per_month": workload_tasks,
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
            down_tier_id = "ap2-batch"
            down_tier_title = "High-Throughput Batch Worker"

            # Guard 2: If buyer is already on minimum tier, they already hold the best plan within budget
            if active_sub and current_norm == down_tier_id:
                logger.info(
                    f"[A2A_SELLER] Subscriber {email} requested {tier_id} (${standard_price:.2f}), cap ${monthly_budget_cap:.2f}, "
                    f"already on best viable plan {active_sub_id} ({down_tier_id})"
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
                        f"Buyer is already subscribed to the highest viable plan within budget ('{active_sub.get('tier_id')}' at ${active_sub.get('agreed_monthly_rate', 49.99):.2f}/mo, Subscription: {active_sub_id}). "
                        f"No better offer available under current budget cap."
                    ),
                }
            issued = self._issue_mandate(
                buyer_agent_id, email, down_tier_id, 49.99,
                recurrence, category, monthly_budget_cap,
                buyer_intent_mandate=buyer_intent_mandate,
            )
            down_hash = issued["hash"]
            remaining_after_down = round(monthly_budget_cap - 49.99, 2)
            counter_checkout = create_merchant_counter_offer(
                requested_tier_id=tier_id,
                counter_tier_id=down_tier_id,
                counter_price=49.99,
                budget_cap=monthly_budget_cap,
                contractor_email=email,
            )
            next_action_params = {
                "offer_id": issued["offer_id"],
                "tier_id": down_tier_id,
                "agreed_monthly_rate": 49.99,
                "mandate_proof_hash": down_hash,
                "buyer_email": email,
                "checkout_jwt": counter_checkout["checkout_jwt"],
                "checkout_hash": counter_checkout["checkout_hash"],
                "nonce": counter_checkout.get("nonce"),
            }

            next_action = {
                "type": "tool_call",
                "tool": "purchase_subscription",
                "parameters": next_action_params,
            }

            # Update registered mandate with counter-offer checkout details & nonce
            auth_entry = get_authorized_mandate(issued["offer_id"])
            if auth_entry:
                auth_entry["counter_checkout_jwt"] = counter_checkout["checkout_jwt"]
                auth_entry["counter_checkout_hash"] = counter_checkout["checkout_hash"]
                auth_entry["counter_order_id"] = counter_checkout["order_id"]
                auth_entry["counter_nonce"] = counter_checkout.get("nonce")
                register_authorized_mandate(issued["offer_id"], auth_entry)
                register_authorized_mandate(down_hash, auth_entry)

            counter_reason = (
                f"Requested plan '{tier_id}' lists at ${standard_price:.2f}/mo, which exceeds monthly budget cap of ${monthly_budget_cap:.2f}. "
                f"Counter-offer available: Down-tier to '{get_plan('ap2-batch')['title']}' at {plan_summary('ap2-batch')}, "
                f"leaving ${remaining_after_down:.2f} in your monthly budget. "
                f"Execute next_action tool call with offer_id='{issued['offer_id']}' to bind to PayPal Vault."
            )

            res_counter = {
                "status": "COUNTER_OFFER",
                "approved": False,
                "original_request_approved": False,
                "negotiation_id": issued["negotiation_id"],
                "offer_id": issued["offer_id"],
                "tier_id": tier_id,
                "counter_offer_available": True,
                "counter_offer_tier": down_tier_title,
                "counter_offer_tier_id": down_tier_id,
                "counter_offer_amount": 49.99,
                "counter_offer_mandate_hash": down_hash,
                "mandate_proof_hash": down_hash,
                "ap2_intent_mandate": issued["ap2_mandate"],
                "ap2_cart_mandate": issued["ap2_cart_mandate"],
                "checkout_jwt": counter_checkout["checkout_jwt"],
                "checkout_hash": counter_checkout["checkout_hash"],
                "order_id": counter_checkout["order_id"],
                "nonce": counter_checkout.get("nonce"),
                "counter_offer_checkout_jwt": counter_checkout["checkout_jwt"],
                "counter_offer_checkout_hash": counter_checkout["checkout_hash"],
                "offer_expires_at": issued["offer_expires_at"],
                "monthly_budget_cap": round(monthly_budget_cap, 2),
                "monthly_cap_remaining": remaining_after_down,
                "next_action": next_action,
                "reason": counter_reason,
            }
            if active_sub_id:
                res_counter["replaces_subscription_id"] = active_sub_id
            return res_counter

        # 3. Budget below minimum viable tier ($49.99)
        min_tier_name = "High-Throughput Batch Worker at $49.99/mo"
        rejection = {
            "status": "REJECTED",
            "approved": False,
            "original_request_approved": False,
            "tier_id": tier_id,
            "error": "BUDGET_EXHAUSTED",
            "counter_offer_available": False,
            "monthly_budget_cap": round(monthly_budget_cap, 2),
            "monthly_cap_remaining": round(ledger.get_remaining_budget(agent_id=buyer_agent_id, cap=monthly_budget_cap, contractor_email=email), 2),
            "reason": f"Monthly budget cap of ${monthly_budget_cap:.2f} is below minimum viable tier ({min_tier_name}).",
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
        buyer_email: Optional[str] = None,
        checkout_mandate_chain: Optional[str] = None,
        payment_mandate_chain: Optional[str] = None,
        checkout_jwt: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Tool implementation: Binds verified AP2 Intent Mandate, AP2 Cart Mandate, or AP2 v0.2 Mandate Chain
        to PayPal Recurring Vault.
        Cryptographically verifies the mandate proof against tier, rate, and buyer identity.
        Replayed requests return the identical, immutable subscription record (idempotency).
        """
        if not contractor_email and buyer_email:
            contractor_email = buyer_email

        verified_chk_receipt = None
        verified_pay_receipt = None

        # 0. AP2 v0.2 Mandate Chain Verification
        ap2_verify_res = None
        if checkout_mandate_chain and payment_mandate_chain:
            chk_jwt = checkout_jwt
            expected_nonce = kwargs.get("nonce")
            if offer_id:
                auth_lookup = get_authorized_mandate(offer_id)
                if auth_lookup:
                    if not chk_jwt:
                        chk_jwt = auth_lookup.get("counter_checkout_jwt") or auth_lookup.get("checkout_jwt")
                    if not expected_nonce:
                        expected_nonce = auth_lookup.get("counter_nonce") or auth_lookup.get("nonce")

            ap2_verify_res = verify_ap2_chains(
                checkout_mandate_token=checkout_mandate_chain,
                payment_mandate_token=payment_mandate_chain,
                checkout_jwt=chk_jwt,
                expected_aud=AP2_MERCHANT_ID,
                expected_nonce=expected_nonce,
                buyer_email=contractor_email,
            )
            if not ap2_verify_res.get("valid"):
                err_code = ap2_verify_res.get("error", ERR_INVALID_MANDATE)
                err_desc = ap2_verify_res.get("error_description", "Mandate chain verification failed")
                logger.warning(f"[AP2_VERIFIER] Purchase rejected: {err_code} - {err_desc}")
                return {
                    "status": "REJECTED",
                    "error": err_code,
                    "reason": err_desc,
                    "message": f"Purchase rejected: {err_desc}",
                    "checkout_receipt": ap2_verify_res.get("checkout_receipt"),
                    "payment_receipt": ap2_verify_res.get("payment_receipt"),
                }
            tier_id = ap2_verify_res.get("tier_id") or tier_id
            agreed_monthly_rate = ap2_verify_res.get("monthly_price", agreed_monthly_rate)
            verified_chk_receipt = ap2_verify_res.get("checkout_receipt")
            verified_pay_receipt = ap2_verify_res.get("payment_receipt")
            mandate_proof_hash = mandate_proof_hash or ap2_verify_res.get("checkout_hash")
        else:
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
                ref = mandate_proof_hash or offer_id or "unknown_ref"
                err_code = ERR_INVALID_CREDENTIAL if "signature" in reason.lower() else ERR_INVALID_MANDATE
                err_receipt = create_checkout_receipt_jwt(
                    order_id=offer_id or "unknown_order",
                    closed_mandate_reference=ref,
                    status="Error",
                    error=err_code,
                    error_description=reason,
                )
                return {
                    "status": "REJECTED",
                    "error": "MANDATE_SECURITY_BREACH",
                    "reason": reason,
                    "message": f"Purchase rejected: {reason}",
                    "checkout_receipt": err_receipt,
                }

        # 1b. Price integrity: a subscription settles only at its tier's catalog price
        plan = resolve_plan(tier_id) if tier_id else None
        if (
            plan is None
            or agreed_monthly_rate is None
            or not math.isfinite(agreed_monthly_rate)
            or round(agreed_monthly_rate, 2) != round(plan["monthly_price"], 2)
        ):
            logger.warning(f"[SECURITY] Purchase rate does not match catalog price for tier '{tier_id}'")
            ref = mandate_proof_hash or offer_id or "unknown_ref"
            err_receipt = create_checkout_receipt_jwt(
                order_id=offer_id or "unknown_order",
                closed_mandate_reference=ref,
                status="Error",
                error=ERR_INVALID_MANDATE,
                error_description="RATE_TAMPERING_DETECTED: agreed_monthly_rate must equal the catalog price of the requested tier.",
            )
            return {
                "status": "REJECTED",
                "error": "RATE_TAMPERING_DETECTED",
                "reason": "RATE_TAMPERING_DETECTED: agreed_monthly_rate must equal the catalog price of the requested tier.",
                "message": "Purchase rejected: agreed_monthly_rate must equal the catalog price of the requested tier.",
                "checkout_receipt": err_receipt,
            }

        # 2. Idempotency Check: a verified replay returns the existing subscription
        cache_key = offer_id or mandate_proof_hash
        if cache_key and cache_key in _COMPLETED_SUBSCRIPTIONS:
            cached = _COMPLETED_SUBSCRIPTIONS[cache_key]
            if isinstance(cached, dict):
                c_status = str(cached.get("status", "")).upper()
                if c_status in ("ACTIVE", "ACTIVE_STREAMING", "APPROVAL_PENDING", "PENDING", "PENDING_DEPOSIT"):
                    return cached
                if c_status in ("CANCELLED", "CANCELED", "EXPIRED", "DENIED", "REPLACED"):
                    return {
                        "status": "REJECTED",
                        "error": "MANDATE_ALREADY_REDEEMED",
                        "reason": "Mandate already redeemed; negotiate again.",
                        "message": "Purchase rejected: mandate already redeemed; negotiate again.",
                    }
                return cached
            return cached

        # Mandates issued without an email are locked to their first redeemer
        if mandate_proof_hash and contractor_email:
            bind_mandate_email(mandate_proof_hash, contractor_email)
        auth = get_authorized_mandate(offer_id or mandate_proof_hash) or {}

        buyer_id = auth.get("buyer_agent_id", "unknown")
        norm_email = contractor_email.strip().lower() if contractor_email else None

        # Plan Change Model: Check for active existing subscription for this buyer
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
        if ap2_verify_res and ap2_verify_res.get("authoritative_budget_cap") is not None:
            cap = ap2_verify_res["authoritative_budget_cap"]
        else:
            cap = auth.get("monthly_budget_cap")
            saved_cap = ledger.get_saved_cap(norm_email)
            if saved_cap is not None:
                cap = saved_cap
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
            ref = mandate_proof_hash or offer_id or "unknown_ref"
            err_receipt = create_payment_receipt_jwt(
                payment_id=f"err_{uuid.uuid4().hex[:8]}",
                closed_mandate_reference=ref,
                status="Error",
                error=ERR_INVALID_MANDATE,
                error_description=(
                    f"Purchase rate ${agreed_monthly_rate:.2f}/mo exceeds available monthly budget of "
                    f"${effective_available:.2f} (budget cap: ${cap:.2f})."
                ),
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
                "payment_receipt": err_receipt,
            }

        # 3. Invoke PayPal Gateway
        paypal_result = await paypal_service.create_subscription(
            tier_id=tier_id,
            agreed_monthly_rate=agreed_monthly_rate,
            contractor_email=contractor_email or "buyer-agent@autonomous-procurement.org",
            contractor_name="Autonomous Buyer Agent",
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
        if old_sub_id and old_sub and old_sub_id != sub_id:
            if sub_status == "ACTIVE":
                old_sub["status"] = "REPLACED"
                old_sub["replaced_by"] = sub_id
                old_sub["replaced_at"] = created_time
                old_sub["message"] = f"Subscription {old_sub_id} was replaced by {sub_id}."
            else:
                old_sub["pending_replacement"] = sub_id
                old_sub["pending_replacement_tier"] = tier_id
                old_sub["pending_replacement_at"] = created_time

        # Reconcile buyer active pointer and ledger commitment
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

        ap2_mandate = auth.get("ap2_mandate")
        if ap2_mandate is None:
            ap2_mandate = build_ap2_intent_mandate(
                buyer_agent_id=buyer_id,
                amount=agreed_monthly_rate,
                recurrence="monthly",
                category="autonomous-node-service",
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
            clean_node_type = "batch" if "batch" in (tier_id or "") else ("cluster" if "cluster" in (tier_id or "") else "gateway")
            next_action = {
                "type": "tool_call",
                "tool": "provision_compute_node",
                "parameters": {
                    "subscription_id": sub_id,
                    "buyer_email": contractor_email,
                    "node_type": clean_node_type,
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

        plan_id = paypal_result.get("plan_id") or resolve_paypal_plan_id(tier_id, profile="ap2")
        product_id = "PROD-AP2-AUTONOMOUS-COMPUTE"
        contractor_name = "Autonomous Buyer Agent"
        business_entity = "Autonomous Compute Network"

        response = {
            "status": sub_status,
            "subscription_id": sub_id,
            "negotiation_id": negotiation_id,
            "offer_id": auth.get("offer_id"),
            "buyer_agent_id": buyer_id,
            "plan_id": plan_id,
            "product_id": product_id,
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
            "buyer_email": contractor_email,
            "contractor_email": contractor_email,
            "subscriber_name": contractor_name,
            "business_entity": business_entity,
        }
        if not verified_chk_receipt:
            ref = mandate_proof_hash or offer_id or f"ref_{uuid.uuid4().hex[:8]}"
            verified_chk_receipt = create_checkout_receipt_jwt(
                order_id=offer_id or f"ord_{uuid.uuid4().hex[:8]}",
                closed_mandate_reference=ref,
                status="Success",
            )
            verified_pay_receipt = create_payment_receipt_jwt(
                payment_id=sub_id,
                closed_mandate_reference=ref,
                status="Success",
            )
        response["checkout_receipt"] = verified_chk_receipt
        response["payment_receipt"] = verified_pay_receipt
        plan_obj = resolve_plan(tier_id, profile="ap2")
        if plan_obj and "workload_tasks_per_month" in plan_obj:
            response["workload_tasks_per_month"] = plan_obj["workload_tasks_per_month"]
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

    async def get_subscription_details(self, subscription_id: str) -> Dict[str, Any]:
        """
        Retrieves live subscription details, plan information, and status.
        Conforms to official PayPal AI-Toolkit subscription schema.
        """
        if not subscription_id:
            return {"error": "INVALID_ARGUMENT", "message": "subscription_id is required."}

        # Check local persistent store first
        sub = _COMPLETED_SUBSCRIPTIONS.get(subscription_id)
        if sub:
            return {
                "id": sub.get("subscription_id"),
                "status": sub.get("status"),
                "plan_id": sub.get("plan_id"),
                "tier_id": sub.get("tier_id"),
                "agreed_monthly_rate": sub.get("agreed_monthly_rate"),
                "buyer_email": _mask_email(sub.get("buyer_email") or sub.get("contractor_email")),
                "contractor_email": _mask_email(sub.get("contractor_email") or sub.get("buyer_email")),
                "create_time": sub.get("create_time"),
                "next_billing_time": sub.get("next_billing_time"),
                "paypal_vault_status": sub.get("paypal_vault_status"),
                "approval_url": sub.get("approval_url"),
                "hateoas_links": sub.get("hateoas_links", []),
                "mock_mode": paypal_service.mock_mode,
            }

        # Query PayPal Sandbox API directly
        try:
            live_data = await paypal_service.verify_subscription(subscription_id)
            return live_data
        except Exception as e:
            return {"error": "NOT_FOUND", "message": f"Subscription '{subscription_id}' not found: {e}"}

    async def provision_compute_node(
        self,
        subscription_id: str,
        buyer_email: Optional[str] = None,
        node_type: str = "gateway",
        contractor_email: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Tool implementation: Provisions a dedicated autonomous compute node endpoint (mcp+https) upon verified PayPal subscription."""
        if not buyer_email and contractor_email:
            buyer_email = contractor_email
        if not buyer_email or "@" not in buyer_email:
            return {
                "status": "REJECTED",
                "error": "BUYER_EMAIL_REQUIRED",
                "reason": "buyer_email is required for node provisioning.",
            }

        sub_key = subscription_id.strip()
        sub = _COMPLETED_SUBSCRIPTIONS.get(sub_key)
        if not sub:
            try:
                remote_sub = await paypal_service.verify_subscription(sub_key)
                if remote_sub and not remote_sub.get("error") and remote_sub.get("status") in ("ACTIVE", "APPROVAL_PENDING"):
                    sub = remote_sub
            except Exception:
                sub = None

        if not sub:
            return {
                "status": "REJECTED",
                "error": "SUBSCRIPTION_NOT_FOUND",
                "reason": f"Subscription '{subscription_id}' was not found or does not exist.",
            }

        sub_status = (sub.get("status") or "").upper()
        if sub_status == "APPROVAL_PENDING":
            return {
                "status": "REJECTED",
                "error": "SUBSCRIPTION_NOT_CAPTURED",
                "reason": f"Subscription '{subscription_id}' is APPROVAL_PENDING. Buyer must authorize payment in PayPal before node provisioning.",
                "approval_url": sub.get("approval_url"),
            }

        if sub.get("status") == "REPLACED":
            return {
                "status": "REJECTED",
                "error": "SUBSCRIPTION_SUPERSEDED",
                "reason": f"Subscription '{subscription_id}' was replaced by '{sub.get('replaced_by')}' and is no longer active.",
            }

        if sub_status != "ACTIVE":
            return {
                "status": "REJECTED",
                "error": "SUBSCRIPTION_NOT_ACTIVE",
                "reason": f"Subscription '{subscription_id}' is not active (current status: {sub_status or 'UNKNOWN'}).",
            }

        country = (sub.get("subscriber_country_code") or "US").upper()
        if country != "US":
            return {
                "status": "REJECTED",
                "error": "US_DOMESTIC_ONLY",
                "reason": f"Compute node provisioning is strictly restricted to US entities (found '{country}').",
            }

        owner_email = sub.get("buyer_email") or sub.get("contractor_email")
        if not owner_email and isinstance(sub.get("subscriber"), dict):
            owner_email = sub["subscriber"].get("email_address")
        if owner_email and buyer_email.strip().lower() != owner_email.strip().lower():
            return {
                "status": "REJECTED",
                "error": "IDENTITY_MISMATCH_DETECTED",
                "reason": f"Subscription '{subscription_id}' belongs to '{owner_email}', cannot be provisioned for '{buyer_email}'.",
            }

        clean_sub = sub_key.replace("-", "").lower()
        sub_hash = hashlib.sha256(clean_sub.encode()).hexdigest()[:8]
        tier_id = sub.get("tier_id", "ap2-gateway")
        clean_node_type = "batch" if "batch" in tier_id else ("cluster" if "cluster" in tier_id else "gateway")
        node_id = f"node-{clean_node_type}-{sub_hash}"
        host_prefix = "batch-01" if clean_node_type == "batch" else ("cluster-01" if clean_node_type == "cluster" else "gateway-01")
        endpoint = f"mcp+https://{host_prefix}.acme-systems.io/agents/{node_id}"

        sub["allocated_node_id"] = node_id
        sub["node_endpoint"] = endpoint

        # Resolve tier catalog quota for AP2 compute tasks
        resolved_plan = resolve_plan(tier_id, profile="ap2")
        workload_tasks = (
            resolved_plan.get("workload_tasks_per_month")
            if resolved_plan and "workload_tasks_per_month" in resolved_plan
            else sub.get("workload_tasks_per_month", 450)
        )
        sub["workload_tasks_per_month"] = workload_tasks
        _COMPLETED_SUBSCRIPTIONS[sub_key] = sub

        monthly_fee = sub.get("agreed_monthly_rate", 79.99)
        proof = sub.get("traceable_proof") or sub.get("mandate_proof_hash") or f"mandate:{subscription_id}"

        return {
            "status": "PROVISIONED",
            "subscription_id": subscription_id,
            "buyer_email": buyer_email,
            "node_id": node_id,
            "node_type": clean_node_type,
            "endpoint": endpoint,
            "assigned_did": endpoint,
            "carrier": "Dual-Transport FastMCP (RFC 8032)",
            "routing_state": "ACTIVE_COMPUTE_NODE",
            "workload_tasks_per_month": workload_tasks,
            "next_action": {
                "type": "tool_call",
                "tool": "dispatch_zapier_mcp",
                "parameters": {
                    "workflow_type": "a2a_onboarding",
                    "subscriber_name": "Autonomous Buyer Agent",
                    "business_entity": "Autonomous Node Network",
                    "node_endpoint": endpoint,
                    "service_vertical": "Autonomous Compute",
                    "monthly_subscription_fee": monthly_fee,
                    "paypal_subscription_id": subscription_id,
                    "buyer_email": buyer_email,
                    "mandate_proof_hash": proof,
                },
            },
        }

    async def dispatch_zapier_mcp(
        self,
        workflow_type: str = "a2a_onboarding",
        subscriber_name: Optional[str] = None,
        business_entity: Optional[str] = None,
        node_endpoint: Optional[str] = None,
        service_vertical: Optional[str] = None,
        monthly_subscription_fee: float = 79.99,
        paypal_subscription_id: str = "I-AUTONOMOUS-8902",
        buyer_email: Optional[str] = None,
        mandate_proof_hash: Optional[str] = None,
        webhook_url: Optional[str] = None,
        contractor_name: Optional[str] = None,
        contractor_email: Optional[str] = None,
        allocated_did: Optional[str] = None,
        trade_vertical: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Tool implementation: Dispatches downline business automation through Zapier MCP."""
        sub_name = subscriber_name or contractor_name or "Autonomous Buyer Agent"
        biz_entity = business_entity or "Autonomous Node Network"
        endpoint = node_endpoint or allocated_did or "mcp+https://gateway-01.acme-systems.io/agents/gateway"
        vertical = service_vertical or trade_vertical or "Autonomous Compute"
        email = buyer_email or contractor_email or "buyer-agent@autonomous-procurement.org"

        req = ZapierSyncRequest(
            workflowType=workflow_type,
            contractorName=sub_name,
            businessEntity=biz_entity,
            allocatedDid=endpoint,
            tradeVertical=vertical,
            monthlySubscriptionFee=monthly_subscription_fee,
            paypalSubscriptionId=paypal_subscription_id,
            contractorEmail=email,
            mandateProofHash=mandate_proof_hash,
            webhookUrl=webhook_url,
        )
        res = await zapier_mcp_dispatcher.execute_downline_sync(req)
        return res.model_dump(by_alias=True)


seller_agent = SellerAgent()
