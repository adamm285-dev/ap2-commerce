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
    register_authorized_mandate,
    get_authorized_mandate,
    bind_mandate_email,
    build_ap2_intent_mandate,
    build_ap2_cart_mandate,
    validate_buyer_intent_mandate,
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
from ..database import (
    get_buyer_key_email,
    get_recurring_mandate,
    list_subscription_recurring_charges,
)
from ..config import settings
from ..services.ap2_service import (
    AP2_MERCHANT_ID,
    create_merchant_checkout,
    create_merchant_counter_offer,
    verify_ap2_chains,
    create_checkout_receipt_jwt,
    create_payment_receipt_jwt,
    create_renewal_receipt_jwt,
    build_ap2_payment_challenge,
    compute_checkout_hash,
    get_issued_checkout,
    dollars_to_minor_units,
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
        "description": "Evaluates buyer budget cap against desired AP2 compute tier. If asking price exceeds budget, returns pre-approved counter-offer down-tiering to a plan within budget (e.g. Batch Worker at $49.99/mo). If buyer holds an existing active plan, replaces_subscription_id indicates the plan will be upgraded/replaced. Issues merchant-signed Checkout JWT (ES256) binding line items and price in integer minor units. Response fields: offer_id/order_id (merchant offer identifier), tier_id (offered plan), requested_tier_id (requested plan), agreed_monthly_rate/price (monthly price in USD), checkout_jwt (merchant-signed checkout JWT), checkout_hash/mandate_proof_hash (SHA-256 hash of checkout_jwt), next_action (instructions for buyer wallet to sign checkout_jwt before purchase).",
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
                    "description": "Strict maximum monthly budget cap authorized by the buyer mandate (in USD, or supply monthly_budget_cap_cents in integer cents)",
                },
                "monthly_budget_cap_cents": {
                    "type": "integer",
                    "description": "Strict maximum monthly budget cap in integer cents (e.g. 6000 for $60.00)",
                },
                "proposed_price": {
                    "type": "number",
                    "description": "Optional buyer-proposed target monthly price for counter-negotiation",
                },
                "proposed_price_cents": {
                    "type": "integer",
                    "description": "Optional buyer-proposed target monthly price in integer cents",
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
                "amount": {"type": "number", "description": "Proposed asking price per billing cycle (in USD, or supply amount_cents)"},
                "amount_cents": {"type": "integer", "description": "Proposed asking price in integer cents"},
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
                "monthly_budget_cap_cents": {
                    "type": "integer",
                    "description": "Strict maximum monthly budget in integer cents",
                },
            },
        },
    },
    {
        "name": "purchase_subscription",
        "description": "Verifies AP2 v0.2 Mandate Chains (Checkout + Payment SD-JWTs) signed by the buyer wallet and creates the subscription. Returns merchant-signed Checkout Receipt and Payment Receipt.",
        "input_schema": {
            "type": "object",
            "required": ["buyer_email", "checkout_mandate_chain", "payment_mandate_chain"],
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
                    "description": "Optional if offer_id is provided. Agreed monthly subscription rate in USD.",
                },
                "agreed_monthly_rate_cents": {
                    "type": "integer",
                    "description": "Optional if offer_id is provided. Agreed monthly subscription rate in integer cents.",
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
            "required": ["subscription_id"],
            "properties": {
                "subscription_id": {"type": "string", "description": "PayPal subscription ID to onboard (looks up subscription details if fee/endpoint omitted)"},
                "workflow_type": {"type": "string", "default": "a2a_onboarding"},
                "subscriber_name": {"type": "string"},
                "business_entity": {"type": "string"},
                "node_endpoint": {"type": "string"},
                "service_vertical": {"type": "string"},
                "monthly_subscription_fee": {"type": "number"},
                "monthly_subscription_fee_cents": {"type": "integer"},
                "paypal_subscription_id": {"type": "string"},
                "buyer_email": {"type": "string"},
                "mandate_proof_hash": {"type": "string"},
            },
        },
    },
    {
        "name": "get_subscription_details",
        "description": "Retrieves the live status, plan information, next billing date, subscriber details, and merchant-signed renewal_receipts (ap2.renewal_receipt.1 JWTs for wallet synchronization via record_renewal_receipt) of a PayPal subscription. Aligns with official PayPal AI-Toolkit subscription schema.",
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
    """Masks an email for responses that any client agent can request."""
    if not email or "@" not in email:
        return email
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


def resolve_tier_from_paypal_plan(plan_id: Optional[str]) -> tuple[str, float]:
    """Maps a PayPal billing plan_id to its canonical tier_id and agreed monthly rate."""
    if not plan_id:
        return ("ap2-gateway", 79.99)
    p = plan_id.lower()
    if plan_id == getattr(settings, "paypal_plan_id_batch", "P-AP2-BATCH-WORKER") or "batch" in p:
        return ("ap2-batch", 49.99)
    elif plan_id == getattr(settings, "paypal_plan_id_cluster", "P-AP2-CLUSTER-NODE") or "cluster" in p:
        return ("ap2-cluster", 179.99)
    elif plan_id == getattr(settings, "paypal_plan_id_gateway", "P-AP2-SERVICE-GATEWAY") or "gateway" in p:
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
        chk_record = create_merchant_checkout(
            tier_id=tier_id,
            monthly_price=amount,
            contractor_email=email,
            order_id=offer_id,
        )
        proof_hash = chk_record["checkout_hash"]
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
        auth_entry = {
            "status": "PENDING_CHECKOUT",
            "is_offer": True,
            "tier_id": tier_id,
            "amount": amount,
            "buyer_agent_id": buyer_agent_id,
            "contractor_email": email,
            "claimed_budget_cap": monthly_budget_cap,
            "monthly_budget_cap": amount,
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

        if not tier_id or not str(tier_id).strip():
            return {
                "status": "REJECTED",
                "error": "TIER_ID_REQUIRED",
                "approved": False,
                "original_request_approved": False,
                "tier_id": tier_id,
                "reason": "tier_id is required.",
            }

        if monthly_budget_cap is None or not isinstance(monthly_budget_cap, (int, float)) or not math.isfinite(monthly_budget_cap) or monthly_budget_cap < 0:
            return {
                "status": "REJECTED",
                "error": "BUDGET_CAP_REQUIRED",
                "approved": False,
                "original_request_approved": False,
                "tier_id": tier_id,
                "reason": "monthly_budget_cap is required and must be a finite number >= 0.",
            }

        if not buyer_agent_id or not str(buyer_agent_id).strip():
            return {
                "status": "REJECTED",
                "error": "BUYER_AGENT_ID_REQUIRED",
                "approved": False,
                "original_request_approved": False,
                "tier_id": tier_id,
                "reason": "buyer_agent_id is required.",
            }

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
                "monthly_budget_cap_cents": dollars_to_minor_units(monthly_budget_cap),
                "agreed_monthly_rate": active_sub.get("agreed_monthly_rate"),
                "agreed_monthly_rate_cents": (
                    dollars_to_minor_units(active_sub["agreed_monthly_rate"])
                    if active_sub.get("agreed_monthly_rate") is not None
                    else None
                ),
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
                ref = f"neg_rej_{uuid.uuid4().hex[:12]}"
                err_desc = mandate_res.get("reason") or "Budget exhausted."
                chk_receipt = create_checkout_receipt_jwt(
                    order_id=f"ord_{uuid.uuid4().hex[:8]}",
                    closed_mandate_reference=ref,
                    status="Error",
                    error=ERR_INVALID_MANDATE,
                    error_description=err_desc,
                )
                pay_receipt = create_payment_receipt_jwt(
                    payment_id=f"pay_{uuid.uuid4().hex[:8]}",
                    closed_mandate_reference=ref,
                    status="Error",
                    error=ERR_INVALID_MANDATE,
                    error_description=err_desc,
                )
                req_cents = dollars_to_minor_units(standard_price)
                cap_cents = dollars_to_minor_units(monthly_budget_cap)
                rem_dollars = ledger.get_remaining_budget(
                    agent_id=buyer_agent_id, cap=monthly_budget_cap, contractor_email=email
                )
                rem_cents = dollars_to_minor_units(max(0.0, rem_dollars))
                shortfall_cents = max(0, req_cents - rem_cents)
                rejection = {
                    "status": "REJECTED",
                    "approved": False,
                    "original_request_approved": False,
                    "tier_id": tier_id,
                    "error": "BUDGET_EXHAUSTED",
                    "monthly_budget_cap": round(monthly_budget_cap, 2),
                    "monthly_budget_cap_cents": cap_cents,
                    "monthly_cap_remaining_cents": rem_cents,
                    "reason": err_desc,
                    "escalation": {
                        "type": "human_step_up_required",
                        "action": "increase_spending_limits",
                        "requested_tier_id": tier_id,
                        "requested_amount_cents": req_cents,
                        "monthly_budget_cap_cents": cap_cents,
                        "monthly_cap_remaining_cents": rem_cents,
                        "shortfall_cents": shortfall_cents,
                        "violations": [err_desc],
                        "message": err_desc,
                    },
                    "checkout_receipt": chk_receipt,
                    "payment_receipt": pay_receipt,
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
                "tool": "sign_checkout",
                "server": "buyer wallet",
                "parameters": {
                    "checkout_jwt": issued["checkout_jwt"],
                },
                "then_call": {
                    "tool": "purchase_subscription",
                    "server": "seller",
                    "parameters": {
                        "offer_id": issued["offer_id"],
                        "tier_id": tier_id,
                        "agreed_monthly_rate": standard_price,
                        "agreed_monthly_rate_cents": dollars_to_minor_units(standard_price),
                        "buyer_email": email,
                        "checkout_mandate_chain": "<from sign_checkout>",
                        "payment_mandate_chain": "<from sign_checkout>",
                    },
                },
            }
            res_approved: Dict[str, Any] = {
                "status": "APPROVED",
                "approved": True,
                "original_request_approved": True,
                "negotiation_id": issued["negotiation_id"],
                "offer_id": issued["offer_id"],
                "tier_id": tier_id,
                "requested_tier_id": tier_id,
                "agreed_monthly_rate": standard_price,
                "agreed_monthly_rate_cents": dollars_to_minor_units(standard_price),
                "price": standard_price,
                "price_cents": dollars_to_minor_units(standard_price),
                "monthly_budget_cap": round(monthly_budget_cap, 2),
                "monthly_budget_cap_cents": dollars_to_minor_units(monthly_budget_cap),
                "monthly_cap_remaining": round(monthly_budget_cap - standard_price, 2),
                "monthly_cap_remaining_cents": dollars_to_minor_units(max(0.0, monthly_budget_cap - standard_price)),
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
                ref = f"neg_rej_{uuid.uuid4().hex[:12]}"
                err_desc = (
                    f"Requested tier '{tier_id}' lists at ${standard_price:.2f}/mo, which exceeds monthly budget cap of ${monthly_budget_cap:.2f}. "
                    f"Buyer is already subscribed to the highest viable plan within budget ('{active_sub.get('tier_id')}' at ${active_sub.get('agreed_monthly_rate', 49.99):.2f}/mo, Subscription: {active_sub_id}). "
                    f"No better offer available under current budget cap."
                )
                chk_receipt = create_checkout_receipt_jwt(
                    order_id=f"ord_{uuid.uuid4().hex[:8]}",
                    closed_mandate_reference=ref,
                    status="Error",
                    error=ERR_INVALID_MANDATE,
                    error_description=err_desc,
                )
                pay_receipt = create_payment_receipt_jwt(
                    payment_id=f"pay_{uuid.uuid4().hex[:8]}",
                    closed_mandate_reference=ref,
                    status="Error",
                    error=ERR_INVALID_MANDATE,
                    error_description=err_desc,
                )
                req_cents = dollars_to_minor_units(standard_price)
                cap_cents = dollars_to_minor_units(monthly_budget_cap)
                shortfall_cents = max(0, req_cents - cap_cents)
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
                    "monthly_budget_cap_cents": cap_cents,
                    "reason": err_desc,
                    "escalation": {
                        "type": "human_step_up_required",
                        "action": "increase_spending_limits",
                        "requested_tier_id": tier_id,
                        "requested_amount_cents": req_cents,
                        "monthly_budget_cap_cents": cap_cents,
                        "shortfall_cents": shortfall_cents,
                        "violations": [err_desc],
                        "message": err_desc,
                    },
                    "checkout_receipt": chk_receipt,
                    "payment_receipt": pay_receipt,
                }
            issued = self._issue_mandate(
                buyer_agent_id, email, down_tier_id, 49.99,
                recurrence, category, monthly_budget_cap,
                buyer_intent_mandate=buyer_intent_mandate,
            )
            remaining_after_down = round(monthly_budget_cap - 49.99, 2)
            counter_checkout = create_merchant_counter_offer(
                requested_tier_id=tier_id,
                counter_tier_id=down_tier_id,
                counter_price=49.99,
                budget_cap=monthly_budget_cap,
                contractor_email=email,
                order_id=issued["offer_id"],
            )
            down_hash = counter_checkout["checkout_hash"]
            next_action = {
                "type": "tool_call",
                "tool": "sign_checkout",
                "server": "buyer wallet",
                "parameters": {
                    "checkout_jwt": counter_checkout["checkout_jwt"],
                },
                "then_call": {
                    "tool": "purchase_subscription",
                    "server": "seller",
                    "parameters": {
                        "offer_id": issued["offer_id"],
                        "tier_id": down_tier_id,
                        "agreed_monthly_rate": 49.99,
                        "agreed_monthly_rate_cents": 4999,
                        "buyer_email": email,
                        "checkout_mandate_chain": "<from sign_checkout>",
                        "payment_mandate_chain": "<from sign_checkout>",
                    },
                },
            }

            # Update registered mandate with counter-offer checkout details & nonce
            auth_entry = get_authorized_mandate(issued["offer_id"])
            if auth_entry:
                auth_entry["checkout_jwt"] = counter_checkout["checkout_jwt"]
                auth_entry["checkout_hash"] = down_hash
                auth_entry["proof_hash"] = down_hash
                auth_entry["mandate_proof_hash"] = down_hash
                auth_entry["order_id"] = counter_checkout["order_id"]
                auth_entry["nonce"] = counter_checkout.get("nonce")
                auth_entry["counter_checkout_jwt"] = counter_checkout["checkout_jwt"]
                auth_entry["counter_checkout_hash"] = down_hash
                auth_entry["counter_order_id"] = counter_checkout["order_id"]
                auth_entry["counter_nonce"] = counter_checkout.get("nonce")
                register_authorized_mandate(issued["offer_id"], auth_entry)
                register_authorized_mandate(down_hash, auth_entry)

            counter_reason = (
                f"Requested plan '{tier_id}' lists at ${standard_price:.2f}/mo, which exceeds monthly budget cap of ${monthly_budget_cap:.2f}. "
                f"Counter-offer available: Down-tier to '{get_plan('ap2-batch')['title']}' at {plan_summary('ap2-batch')}, "
                f"leaving ${remaining_after_down:.2f} in your monthly budget. "
                f"Sign checkout_jwt with buyer wallet, then call purchase_subscription with offer_id='{issued['offer_id']}' and the signed mandate chains."
            )

            res_counter = {
                "status": "COUNTER_OFFER",
                "approved": False,
                "original_request_approved": False,
                "negotiation_id": issued["negotiation_id"],
                "offer_id": issued["offer_id"],
                "tier_id": down_tier_id,
                "requested_tier_id": tier_id,
                "agreed_monthly_rate": 49.99,
                "agreed_monthly_rate_cents": 4999,
                "price": 49.99,
                "price_cents": 4999,
                "counter_offer_available": True,
                "counter_offer_tier": down_tier_title,
                "counter_offer_tier_id": down_tier_id,
                "counter_offer_amount": 49.99,
                "counter_offer_amount_cents": 4999,
                "counter_offer_mandate_hash": down_hash,
                "mandate_proof_hash": down_hash,
                "ap2_intent_mandate": issued["ap2_mandate"],
                "ap2_cart_mandate": issued["ap2_cart_mandate"],
                "checkout_jwt": counter_checkout["checkout_jwt"],
                "checkout_hash": down_hash,
                "order_id": counter_checkout["order_id"],
                "nonce": counter_checkout.get("nonce"),
                "counter_offer_checkout_jwt": counter_checkout["checkout_jwt"],
                "counter_offer_checkout_hash": down_hash,
                "offer_expires_at": issued["offer_expires_at"],
                "monthly_budget_cap": round(monthly_budget_cap, 2),
                "monthly_budget_cap_cents": dollars_to_minor_units(monthly_budget_cap),
                "monthly_cap_remaining": remaining_after_down,
                "monthly_cap_remaining_cents": dollars_to_minor_units(max(0.0, remaining_after_down)),
                "next_action": next_action,
                "reason": counter_reason,
            }
            if active_sub_id:
                res_counter["replaces_subscription_id"] = active_sub_id
            return res_counter

        # 3. Budget below minimum viable tier ($49.99)
        min_tier_name = "High-Throughput Batch Worker at $49.99/mo"
        err_desc = f"Monthly budget cap of ${monthly_budget_cap:.2f} is below minimum viable tier ({min_tier_name})."
        ref = f"neg_rej_{uuid.uuid4().hex[:12]}"
        chk_receipt = create_checkout_receipt_jwt(
            order_id=f"ord_{uuid.uuid4().hex[:8]}",
            closed_mandate_reference=ref,
            status="Error",
            error=ERR_INVALID_MANDATE,
            error_description=err_desc,
        )
        pay_receipt = create_payment_receipt_jwt(
            payment_id=f"pay_{uuid.uuid4().hex[:8]}",
            closed_mandate_reference=ref,
            status="Error",
            error=ERR_INVALID_MANDATE,
            error_description=err_desc,
        )
        req_cents = dollars_to_minor_units(standard_price)
        min_viable_cents = 4999
        cap_cents = dollars_to_minor_units(monthly_budget_cap)
        rem_dollars = ledger.get_remaining_budget(agent_id=buyer_agent_id, cap=monthly_budget_cap, contractor_email=email)
        rem_cents = dollars_to_minor_units(max(0.0, rem_dollars))
        rejection = {
            "status": "REJECTED",
            "approved": False,
            "original_request_approved": False,
            "tier_id": tier_id,
            "error": "BUDGET_EXHAUSTED",
            "counter_offer_available": False,
            "monthly_budget_cap": round(monthly_budget_cap, 2),
            "monthly_budget_cap_cents": cap_cents,
            "monthly_cap_remaining": round(rem_dollars, 2),
            "monthly_cap_remaining_cents": rem_cents,
            "reason": err_desc,
            "escalation": {
                "type": "human_step_up_required",
                "action": "increase_spending_limits",
                "requested_tier_id": tier_id,
                "requested_amount_cents": req_cents,
                "minimum_viable_tier_id": "ap2-batch",
                "minimum_viable_amount_cents": min_viable_cents,
                "monthly_budget_cap_cents": cap_cents,
                "monthly_cap_remaining_cents": rem_cents,
                "shortfall_cents": max(0, req_cents - cap_cents),
                "minimum_viable_shortfall_cents": max(0, min_viable_cents - cap_cents),
                "violations": [err_desc],
                "message": err_desc,
            },
            "checkout_receipt": chk_receipt,
            "payment_receipt": pay_receipt,
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
        Tool implementation: Verifies AP2 Intent Mandate, AP2 Cart Mandate, or AP2 v0.2 Mandate Chain
        and creates the subscription.
        Cryptographically verifies the mandate proof against tier, rate, and buyer identity.
        Replayed requests return the identical, immutable subscription record (idempotency).
        """
        verified_chk_receipt = None
        verified_pay_receipt = None

        # 0. AP2 v0.2 Mandate Chain Verification (Strictly Required)
        if not (checkout_mandate_chain and payment_mandate_chain):
            ref = mandate_proof_hash or offer_id or "missing_chains"
            err_receipt = create_checkout_receipt_jwt(
                order_id=offer_id or "unknown_order",
                closed_mandate_reference=ref,
                status="Error",
                error=ERR_INVALID_MANDATE,
                error_description="MISSING_MANDATE_CHAINS: AP2 v0.2 checkout and payment mandate chains are strictly required on every purchase.",
            )
            err_pay_receipt = create_payment_receipt_jwt(
                payment_id=f"err_{uuid.uuid4().hex[:8]}",
                closed_mandate_reference=ref,
                status="Error",
                error=ERR_INVALID_MANDATE,
                error_description="MISSING_MANDATE_CHAINS: AP2 v0.2 checkout and payment mandate chains are strictly required on every purchase.",
            )
            return {
                "status": "REJECTED",
                "error": ERR_INVALID_MANDATE,
                "reason": "MISSING_MANDATE_CHAINS: AP2 v0.2 checkout and payment mandate chains are strictly required on every purchase.",
                "message": "Purchase rejected: AP2 v0.2 checkout and payment mandate chains are strictly required on every purchase.",
                "checkout_receipt": err_receipt,
                "payment_receipt": err_pay_receipt,
            }

        if not contractor_email and buyer_email:
            contractor_email = buyer_email

        chk_jwt = checkout_jwt
        expected_nonce = kwargs.get("nonce")
        auth_lookup: Optional[Dict[str, Any]] = None
        if offer_id:
            auth_lookup = get_authorized_mandate(offer_id)
        if not auth_lookup and mandate_proof_hash:
            auth_lookup = get_authorized_mandate(mandate_proof_hash)
        if not auth_lookup and chk_jwt:
            from ..services.ap2_service import compute_checkout_hash
            c_hash = compute_checkout_hash(chk_jwt)
            if c_hash:
                auth_lookup = get_authorized_mandate(c_hash)

        if auth_lookup:
            if not chk_jwt:
                chk_jwt = auth_lookup.get("counter_checkout_jwt") or auth_lookup.get("checkout_jwt")
            if not expected_nonce:
                expected_nonce = auth_lookup.get("counter_nonce") or auth_lookup.get("nonce")
            auth_email = (auth_lookup.get("contractor_email") or auth_lookup.get("buyer_email") or "").strip().lower()
            if auth_email:
                if contractor_email and contractor_email.strip().lower() != auth_email:
                    desc = (
                        f"IDENTITY_MISMATCH_DETECTED: Offer is bound to '{auth_email}', "
                        f"cannot be redeemed by '{contractor_email.strip().lower()}'."
                    )
                    logger.warning(f"[SECURITY] {desc}")
                    ref = mandate_proof_hash or offer_id or "offer_mismatch"
                    err_receipt = create_checkout_receipt_jwt(
                        order_id=offer_id or "unknown_order",
                        closed_mandate_reference=ref,
                        status="Error",
                        error="MANDATE_SECURITY_BREACH",
                        error_description=desc,
                    )
                    err_pay_receipt = create_payment_receipt_jwt(
                        payment_id=f"err_{uuid.uuid4().hex[:8]}",
                        closed_mandate_reference=ref,
                        status="Error",
                        error="MANDATE_SECURITY_BREACH",
                        error_description=desc,
                    )
                    return {
                        "status": "REJECTED",
                        "error": "MANDATE_SECURITY_BREACH",
                        "reason": desc,
                        "message": f"Purchase rejected: {desc}",
                        "checkout_receipt": err_receipt,
                        "payment_receipt": err_pay_receipt,
                    }
                if not contractor_email:
                    contractor_email = auth_email

        from ..services.ap2_service import (
            compute_open_payment_mandate_hash,
            compute_checkout_hash,
            get_stored_receipt,
            clear_stored_receipt,
        )
        from ..database import (
            get_open_mandate_total_usage,
            is_mandate_revoked,
            acquire_purchase_lease,
            release_purchase_lease,
            PURCHASE_LEASE_TTL_SECONDS,
        )
        from ap2.sdk.constraints import MandateContext

        # Identify if this is a candidate replay of an already completed subscription
        computed_chk_hash = (
            compute_checkout_hash(chk_jwt)
            if isinstance(chk_jwt, str) and chk_jwt.strip()
            else None
        )

        candidate_replay_sub = None
        for k in (offer_id, mandate_proof_hash, computed_chk_hash):
            if k and k in _COMPLETED_SUBSCRIPTIONS:
                candidate_replay_sub = _COMPLETED_SUBSCRIPTIONS[k]
                break

        open_pay_hash = compute_open_payment_mandate_hash(payment_mandate_chain)
        exclude_sub_id = (
            candidate_replay_sub.get("subscription_id")
            if isinstance(candidate_replay_sub, dict)
            else None
        )
        tot_amt, tot_uses = get_open_mandate_total_usage(
            open_pay_hash, exclude_subscription_id=exclude_sub_id
        )
        settlement_ctx = MandateContext(total_amount=tot_amt, total_uses=tot_uses)

        ap2_verify_res = verify_ap2_chains(
            checkout_mandate_token=checkout_mandate_chain,
            payment_mandate_token=payment_mandate_chain,
            checkout_jwt=chk_jwt,
            expected_aud=AP2_MERCHANT_ID,
            expected_nonce=expected_nonce,
            enforce_replay_defense=(candidate_replay_sub is None),
            buyer_email=contractor_email,
            mandate_context=settlement_ctx,
        )
        if not ap2_verify_res.get("valid"):
            err_code = ap2_verify_res.get("error", ERR_INVALID_MANDATE)
            err_desc = ap2_verify_res.get("error_description", "Mandate chain verification failed")
            logger.warning(f"[AP2_VERIFIER] Purchase rejected: {err_code} - {err_desc}")
            rej_out: Dict[str, Any] = {
                "status": "REJECTED",
                "error": err_code,
                "reason": err_desc,
                "message": f"Purchase rejected: {err_desc}",
                "checkout_receipt": ap2_verify_res.get("checkout_receipt"),
                "payment_receipt": ap2_verify_res.get("payment_receipt"),
            }
            if ap2_verify_res.get("escalation"):
                rej_out["escalation"] = ap2_verify_res["escalation"]
            return rej_out

        verified_tier = ap2_verify_res.get("tier_id")
        verified_price = ap2_verify_res.get("monthly_price")
        checkout_hash = ap2_verify_res.get("checkout_hash")
        verified_buyer_email = ap2_verify_res.get("verified_buyer_email")
        if not contractor_email and verified_buyer_email:
            contractor_email = verified_buyer_email
        closed_pay_obj = ap2_verify_res.get("closed_payment_mandate")
        closed_pay_tx_id = getattr(closed_pay_obj, "transaction_id", None) if closed_pay_obj else None

        if not candidate_replay_sub:
            for k in (offer_id, mandate_proof_hash, checkout_hash):
                if k and k in _COMPLETED_SUBSCRIPTIONS:
                    candidate_replay_sub = _COMPLETED_SUBSCRIPTIONS[k]
                    break

        # If this is a replay of an already-settled subscription and verification succeeded:
        if candidate_replay_sub and isinstance(candidate_replay_sub, dict):
            c_status = str(candidate_replay_sub.get("status", "")).upper()
            if c_status in ("CANCELLED", "CANCELED", "EXPIRED", "DENIED", "REPLACED"):
                return {
                    "status": "REJECTED",
                    "error": "MANDATE_ALREADY_REDEEMED",
                    "reason": "Mandate already redeemed; negotiate again.",
                    "message": "Purchase rejected: mandate already redeemed; negotiate again.",
                }
            cached_email = candidate_replay_sub.get("contractor_email") or candidate_replay_sub.get("buyer_email")
            if contractor_email and cached_email and contractor_email.strip().lower() != cached_email.strip().lower():
                reason = f"IDENTITY_MISMATCH_DETECTED: Mandate is bound to '{cached_email}', cannot be redeemed by '{contractor_email}'."
                logger.warning(f"[SECURITY] Mandate verification failed: {reason}")
                return {
                    "status": "REJECTED",
                    "error": "MANDATE_SECURITY_BREACH",
                    "reason": reason,
                    "message": f"Purchase rejected: {reason}",
                }
            return {**candidate_replay_sub, "idempotent_replay": True}

        if not mandate_proof_hash and offer_id:
            auth_entry_lookup = auth_lookup or get_authorized_mandate(offer_id)
            if auth_entry_lookup:
                mandate_proof_hash = auth_entry_lookup.get("mandate_proof_hash") or auth_entry_lookup.get("hash")
        mandate_proof_hash = mandate_proof_hash or checkout_hash

        def _reject_purchase(desc: str, err_code: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
            ref = checkout_hash or mandate_proof_hash or offer_id or "unknown_ref"
            pay_ref = closed_pay_tx_id or ref
            if checkout_hash:
                clear_stored_receipt(checkout_hash)
            if closed_pay_tx_id:
                clear_stored_receipt(closed_pay_tx_id)
            err_receipt = create_checkout_receipt_jwt(
                order_id=offer_id or "unknown_order",
                closed_mandate_reference=ref,
                status="Error",
                error=ERR_INVALID_MANDATE,
                error_description=desc,
            )
            err_pay_receipt = create_payment_receipt_jwt(
                payment_id=f"err_{uuid.uuid4().hex[:8]}",
                closed_mandate_reference=pay_ref,
                status="Error",
                error=ERR_INVALID_MANDATE,
                error_description=desc,
            )
            ret = {
                "status": "REJECTED",
                "error": err_code,
                "reason": desc,
                "message": f"Purchase rejected: {desc}",
                "checkout_receipt": err_receipt,
                "payment_receipt": err_pay_receipt,
            }
            if extra:
                ret.update(extra)
            return ret

        # Verify offer_id binding against verified checkout_hash and email
        if offer_id and auth_lookup:
            expected_hashes = {
                str(h).strip()
                for h in (
                    auth_lookup.get("checkout_hash"),
                    auth_lookup.get("counter_checkout_hash"),
                    auth_lookup.get("mandate_proof_hash"),
                    auth_lookup.get("proof_hash"),
                    auth_lookup.get("hash"),
                )
                if h
            }
            if expected_hashes and checkout_hash and str(checkout_hash).strip() not in expected_hashes:
                desc = (
                    f"OFFER_MISMATCH_DETECTED: offer_id '{offer_id}' does not match "
                    f"the checkout mandate hash '{checkout_hash}'."
                )
                logger.warning(f"[SECURITY] {desc}")
                return _reject_purchase(desc, "OFFER_MISMATCH_DETECTED")
            auth_email = (auth_lookup.get("contractor_email") or auth_lookup.get("buyer_email") or "").strip().lower()
            if auth_email and contractor_email and auth_email != contractor_email.strip().lower():
                desc = (
                    f"IDENTITY_MISMATCH_DETECTED: Offer '{offer_id}' is bound to '{auth_email}', "
                    f"cannot be redeemed by '{contractor_email.strip().lower()}'."
                )
                logger.warning(f"[SECURITY] {desc}")
                return _reject_purchase(desc, "MANDATE_SECURITY_BREACH")
            if auth_email and not contractor_email:
                contractor_email = auth_email

        norm_email = contractor_email.strip().lower() if contractor_email else None
        open_pay_hash = ap2_verify_res.get("open_payment_mandate_hash") or open_pay_hash
        lease_holder = acquire_purchase_lease(
            open_mandate_hash=open_pay_hash,
            buyer_email=norm_email,
            ttl_seconds=PURCHASE_LEASE_TTL_SECONDS,
        )
        if not lease_holder:
            desc = "PURCHASE_IN_PROGRESS: Another purchase for this mandate or buyer is currently in flight; retry after it settles."
            logger.warning(f"[CONCURRENCY] {desc}")
            return _reject_purchase(desc, "PURCHASE_IN_PROGRESS")

        try:
            # Re-read the open-mandate settlement totals under the lease and compare with the pre-verification snapshot
            post_lease_amt, post_lease_uses = get_open_mandate_total_usage(
                open_pay_hash, exclude_subscription_id=exclude_sub_id
            )
            if (post_lease_amt, post_lease_uses) != (tot_amt, tot_uses):
                desc = "PURCHASE_IN_PROGRESS: Open mandate settlement totals changed while verifying; retry against updated totals."
                logger.warning(f"[CONCURRENCY] {desc}")
                return _reject_purchase(desc, "PURCHASE_IN_PROGRESS")

            if is_mandate_revoked(mandate_proof_hash) or (offer_id and is_mandate_revoked(offer_id)):
                desc = "MANDATE_REVOKED: Mandate has been cryptographically revoked by owner."
                logger.warning(f"[SECURITY] {desc}")
                return _reject_purchase(desc, "MANDATE_REVOKED")

            # Parameter integrity: if buyer provided tier_id or rate, they must match verified chain
            if tier_id and verified_tier and tier_id != verified_tier:
                desc = f"TIER_MISMATCH_DETECTED: Requested tier '{tier_id}' does not match mandate chain tier '{verified_tier}'."
                logger.warning(f"[SECURITY] {desc}")
                return _reject_purchase(desc, "TIER_MISMATCH_DETECTED")

            if agreed_monthly_rate is not None and verified_price is not None and round(agreed_monthly_rate, 2) != round(verified_price, 2):
                desc = f"RATE_TAMPERING_DETECTED: Agreed monthly rate ${agreed_monthly_rate:.2f} does not match mandate chain price ${verified_price:.2f}."
                logger.warning(f"[SECURITY] {desc}")
                return _reject_purchase(desc, "RATE_TAMPERING_DETECTED")

            tier_id = verified_tier or tier_id
            if not tier_id:
                desc = "MISSING_TIER: No subscription tier specified or determined from verified checkout mandate."
                logger.warning(f"[SECURITY] {desc}")
                return _reject_purchase(desc, "MISSING_TIER")

            agreed_monthly_rate = verified_price if verified_price is not None else agreed_monthly_rate
            verified_chk_receipt = ap2_verify_res.get("checkout_receipt")
            verified_pay_receipt = ap2_verify_res.get("payment_receipt")

            auth = get_authorized_mandate(offer_id or mandate_proof_hash) or {}
            auth_bound_email = (auth.get("contractor_email") or auth.get("buyer_email") or "").strip().lower()
            if auth_bound_email and norm_email and auth_bound_email != norm_email:
                desc = (
                    f"IDENTITY_MISMATCH_DETECTED: Mandate is bound to '{auth_bound_email}', "
                    f"cannot be redeemed by '{norm_email}'."
                )
                logger.warning(f"[SECURITY] {desc}")
                return _reject_purchase(desc, "MANDATE_SECURITY_BREACH")
            if auth_bound_email and not norm_email:
                contractor_email = auth_bound_email
                norm_email = auth_bound_email

            buyer_id = auth.get("buyer_agent_id", "unknown")

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

            # Resolve authoritative monthly budget cap strictly from owner-signed chain
            cap = ap2_verify_res.get("authoritative_budget_cap") if ap2_verify_res else None
            if cap is None:
                desc = "BUDGET_CAP_NOT_FOUND: Verified payment mandate chain carries no owner-signed price limit or AmountRange constraint."
                logger.warning(f"[SECURITY] {desc}")
                return _reject_purchase(desc, "BUDGET_CAP_NOT_FOUND")

            # Purchase-time budget enforcement
            remaining_before = ledger.get_remaining_budget(agent_id=buyer_id, cap=cap, contractor_email=contractor_email)
            effective_available = round(remaining_before + old_rate, 2)

            if agreed_monthly_rate > effective_available or agreed_monthly_rate > cap:
                logger.warning(
                    f"[SECURITY] Purchase budget breach: rate ${agreed_monthly_rate:.2f}/mo exceeds "
                    f"available ${effective_available:.2f}/mo (cap: ${cap:.2f})"
                )
                desc = (
                    f"Purchase rate ${agreed_monthly_rate:.2f}/mo exceeds available monthly budget of "
                    f"${effective_available:.2f} (budget cap: ${cap:.2f})."
                )
                req_cents = dollars_to_minor_units(agreed_monthly_rate)
                cap_cents = dollars_to_minor_units(cap)
                rem_cents = dollars_to_minor_units(max(0.0, remaining_before))
                avail_cents = dollars_to_minor_units(max(0.0, effective_available))
                return _reject_purchase(
                    desc,
                    "BUDGET_EXHAUSTED",
                    extra={
                        "monthly_budget_cap": round(cap, 2),
                        "monthly_budget_cap_cents": cap_cents,
                        "monthly_cap_remaining": round(remaining_before, 2),
                        "monthly_cap_remaining_cents": rem_cents,
                        "active_subscription_id": old_sub_id,
                        "escalation": {
                            "type": "human_step_up_required",
                            "action": "increase_spending_limits",
                            "requested_tier_id": tier_id,
                            "requested_amount_cents": req_cents,
                            "monthly_budget_cap_cents": cap_cents,
                            "monthly_cap_remaining_cents": rem_cents,
                            "shortfall_cents": max(0, req_cents - avail_cents),
                            "violations": [desc],
                            "message": desc,
                        },
                    },
                )

            # Mandates issued without an email are locked to their first redeemer only after all budget checks pass
            if contractor_email:
                if mandate_proof_hash:
                    bind_mandate_email(mandate_proof_hash, contractor_email)
                if offer_id:
                    bind_mandate_email(offer_id, contractor_email)
                if checkout_hash:
                    bind_mandate_email(checkout_hash, contractor_email)

            # 3. Invoke PayPal Gateway
            subscriber_name = (
                kwargs.get("subscriber_name")
                or kwargs.get("contractor_name")
                or auth.get("subscriber_name")
                or (f"Buyer Agent ({buyer_id})" if buyer_id and buyer_id != "unknown" else "Buyer Agent")
            )
            if not checkout_hash or not str(checkout_hash).strip():
                desc = "MISSING_CHECKOUT_HASH: Verified checkout chain is missing checkout_hash required for PayPal idempotency."
                logger.error(f"[SECURITY] {desc}")
                return _reject_purchase(desc, ERR_INVALID_MANDATE)
            paypal_request_id = f"ap2-sub-{str(checkout_hash).strip()[:32]}"
            try:
                paypal_result = await paypal_service.create_subscription(
                    tier_id=tier_id,
                    agreed_monthly_rate=agreed_monthly_rate,
                    contractor_email=contractor_email,
                    contractor_name=subscriber_name,
                    offer_id=offer_id,
                    mandate_proof_hash=mandate_proof_hash,
                    paypal_request_id=paypal_request_id,
                )
            except Exception as e:
                desc = f"PAYPAL_SUBSCRIPTION_ERROR: Failed to create PayPal subscription: {e}"
                logger.error(f"[PAYPAL] {desc}", exc_info=True)
                return _reject_purchase(desc, "PAYPAL_SUBSCRIPTION_ERROR")
            sub_id = paypal_result.get("subscription_id") if isinstance(paypal_result, dict) else None
            raw_status = paypal_result.get("status") if isinstance(paypal_result, dict) else None
            sub_status = str(raw_status).strip().upper() if isinstance(raw_status, str) and raw_status.strip() else ""
            if not sub_id or not sub_status:
                desc = (
                    f"PAYPAL_SUBSCRIPTION_ERROR: PayPal subscription reply missing required "
                    f"{'subscription_id' if not sub_id else 'status'}."
                )
                logger.error(f"[PAYPAL] {desc}")
                return _reject_purchase(desc, "PAYPAL_SUBSCRIPTION_ERROR")

            is_mock = bool(paypal_result.get("mock_mode")) if "mock_mode" in paypal_result else getattr(paypal_service, "mock_mode", False)
            approval_url = paypal_result.get("approval_url")
            created_time = paypal_result.get("created_time") or (
                datetime.datetime.now(datetime.timezone.utc).isoformat() if is_mock else None
            )
            next_billing = paypal_result.get("next_billing_time") or (
                (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30)).isoformat() if is_mock else None
            )
            negotiation_id = auth.get("negotiation_id") or f"neg_{hashlib.sha256((mandate_proof_hash or offer_id).encode()).hexdigest()[:12]}"
            payer_id = paypal_result.get("payer_id")
            vault_id = paypal_result.get("vault_id")
            payment_token = paypal_result.get("payment_token")
            paypal_req_id = paypal_result.get("paypal_request_id")
            hateoas_links = list(paypal_result.get("hateoas_links") or [])
            if is_mock and hateoas_links:
                for link in hateoas_links:
                    link["simulated"] = True
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

            # Record open payment mandate settlement upon successful purchase
            if ap2_verify_res and sub_status in ("ACTIVE", "APPROVAL_PENDING"):
                from ..database import record_open_mandate_settlement
                amount_cents = dollars_to_minor_units(agreed_monthly_rate)
                record_open_mandate_settlement(
                    mandate_hash=open_pay_hash,
                    subscription_id=sub_id,
                    amount_cents=amount_cents,
                )

                # Keep the owner-signed mandate so every PayPal renewal can be checked against it
                from ..services.recurring_mandate_service import register_recurring_mandate
                closed_pay = ap2_verify_res["closed_payment_mandate"]
                if norm_email:
                    register_recurring_mandate(
                        subscription_id=sub_id,
                        payment_mandate_chain=payment_mandate_chain,
                        mandate_hash=open_pay_hash,
                        buyer_email=norm_email,
                        amount_cents=closed_pay.payment_amount.amount,
                        currency=closed_pay.payment_amount.currency,
                    )
                else:
                    logger.warning(f"[RECURRING] Subscription {sub_id} has no buyer email; its renewals will be suspended.")

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
                    tier_id=tier_id,
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
                "agreed_monthly_rate_cents": dollars_to_minor_units(agreed_monthly_rate),
                "monthly_budget_cap": round(cap, 2),
                "monthly_budget_cap_cents": dollars_to_minor_units(cap),
                "monthly_cap_remaining": round(remaining_budget, 2),
                "monthly_cap_remaining_cents": dollars_to_minor_units(max(0.0, remaining_budget)),
                "billing_cycle": "monthly",
                "billing_cycles": billing_cycles,
                "currency": "USD",
                "mandate_proof_hash": mandate_proof_hash,
                "traceable_proof": traceable_proof,
                "subscriber_country_code": paypal_result.get("subscriber_country_code", "US"),
                "paypal_vault_status": vault_status,
                "vault_billing_authorized": vault_authorized,
                "vault_customer_present": customer_present,
                "paypal_environment": "mock" if getattr(paypal_service, "mock_mode", False) else "sandbox",
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
                "subscriber_name": subscriber_name,
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
            if auth and isinstance(auth, dict):
                auth["status"] = "COMPLETED"
                auth["subscription_id"] = sub_id
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
        finally:
            release_purchase_lease(lease_holder)

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
            raw_email = (sub.get("buyer_email") or sub.get("contractor_email") or "").strip().lower()
            rec_mandate = get_recurring_mandate(subscription_id)
            if rec_mandate and not raw_email:
                raw_email = (rec_mandate.get("buyer_email") or "").strip().lower()
            renewal_receipts: List[Dict[str, Any]] = []
            for chg in list_subscription_recurring_charges(subscription_id):
                chg_status = chg.get("status")
                if chg_status in ("INITIAL", "VERIFIED"):
                    receipt_jwt = create_renewal_receipt_jwt(
                        sale_id=chg["sale_id"],
                        subscription_id=subscription_id,
                        mandate_hash=chg["mandate_hash"],
                        buyer_email=raw_email,
                        amount_cents=int(chg["amount_cents"]),
                        currency=chg.get("currency") or "USD",
                        outcome=chg_status,
                        charged_at=chg.get("charged_at") or "",
                    )
                    renewal_receipts.append({
                        "sale_id": chg["sale_id"],
                        "outcome": chg_status,
                        "amount_cents": int(chg["amount_cents"]),
                        "currency": chg.get("currency") or "USD",
                        "charged_at": chg.get("charged_at") or "",
                        "renewal_receipt_jwt": receipt_jwt,
                    })
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
                "renewal_receipts": renewal_receipts,
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
        if not subscription_id or not str(subscription_id).strip():
            return {
                "status": "REJECTED",
                "error": "SUBSCRIPTION_ID_REQUIRED",
                "reason": "subscription_id is required for node provisioning.",
            }

        if not buyer_email and contractor_email:
            buyer_email = contractor_email
        if not buyer_email or not str(buyer_email).strip() or "@" not in str(buyer_email):
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
                "ap2_payment_challenge": build_ap2_payment_challenge(),
            }

        sub_status = (sub.get("status") or "").upper()
        if sub_status == "APPROVAL_PENDING":
            return {
                "status": "REJECTED",
                "error": "SUBSCRIPTION_NOT_CAPTURED",
                "reason": f"Subscription '{subscription_id}' is APPROVAL_PENDING. Buyer must authorize payment in PayPal before node provisioning.",
                "approval_url": sub.get("approval_url"),
                "ap2_payment_challenge": build_ap2_payment_challenge(),
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
                "ap2_payment_challenge": build_ap2_payment_challenge(),
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
        # MOCK(M-010): placeholder node endpoint, nothing is provisioned
        endpoint = f"mcp+https://{host_prefix}.example.com/agents/{node_id}"

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
        proof = sub.get("mandate_proof_hash") or sub.get("traceable_proof") or f"mandate:{subscription_id}"

        return {
            "status": "PROVISIONED",
            "subscription_id": subscription_id,
            "buyer_email": buyer_email,
            "node_id": node_id,
            "node_type": clean_node_type,
            "endpoint": endpoint,
            "assigned_did": endpoint,
            "carrier": "MCP over HTTPS (JSON-RPC 2.0)",
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
        monthly_subscription_fee: Optional[float] = None,
        paypal_subscription_id: Optional[str] = None,
        buyer_email: Optional[str] = None,
        mandate_proof_hash: Optional[str] = None,
        webhook_url: Optional[str] = None,
        contractor_name: Optional[str] = None,
        contractor_email: Optional[str] = None,
        allocated_did: Optional[str] = None,
        trade_vertical: Optional[str] = None,
        subscription_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Tool implementation: Dispatches downline business automation through Zapier MCP."""
        raw_sub_id = subscription_id or paypal_subscription_id or kwargs.get("sub_id")
        target_sub_id = raw_sub_id.strip() if isinstance(raw_sub_id, str) else ""
        if not target_sub_id:
            return {
                "status": "REJECTED",
                "error": "SUBSCRIPTION_ID_REQUIRED",
                "reason": "Cannot dispatch back-office automation: subscription_id is required.",
            }

        sub = _COMPLETED_SUBSCRIPTIONS.get(target_sub_id)
        if not sub:
            from ..database import get_subscription
            sub = get_subscription(target_sub_id)
        if not sub:
            return {
                "status": "REJECTED",
                "error": "SUBSCRIPTION_NOT_FOUND",
                "reason": f"Cannot dispatch back-office automation: Subscription '{target_sub_id}' was not found.",
            }

        sub_name = (
            subscriber_name
            or contractor_name
            or (sub.get("subscriber_name") or sub.get("contractor_name") if sub else None)
            or "Autonomous Buyer Agent"
        )
        biz_entity = business_entity or "Autonomous Node Network"
        endpoint = (
            node_endpoint
            or allocated_did
            or (sub.get("node_endpoint") or sub.get("allocated_endpoint") or sub.get("endpoint") or sub.get("assigned_did") if sub else None)
            or "mcp+https://gateway-01.example.com/agents/gateway"
        )
        vertical = service_vertical or trade_vertical or "Autonomous Compute"
        email = (
            buyer_email
            or contractor_email
            or (sub.get("buyer_email") or sub.get("contractor_email") if sub else None)
        )
        if not email or not str(email).strip() or "@" not in str(email):
            return {
                "status": "REJECTED",
                "error": "BUYER_EMAIL_REQUIRED",
                "reason": "buyer_email is required for dispatch.",
            }

        fee = monthly_subscription_fee
        if fee is None:
            fee = sub.get("agreed_monthly_rate", 79.99)

        proof = (
            mandate_proof_hash
            or sub.get("mandate_proof_hash")
            or sub.get("traceable_proof")
        )

        req = ZapierSyncRequest(
            workflowType=workflow_type,
            contractorName=sub_name,
            businessEntity=biz_entity,
            allocatedDid=endpoint,
            tradeVertical=vertical,
            monthlySubscriptionFee=fee,
            paypalSubscriptionId=target_sub_id,
            contractorEmail=email,
            mandateProofHash=proof,
            webhookUrl=webhook_url,
        )
        res = await zapier_mcp_dispatcher.execute_downline_sync(req)
        return res.model_dump(by_alias=True)


seller_agent = SellerAgent()
