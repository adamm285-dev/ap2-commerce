"""
Seller Agent (FieldSmith Pro MCP Server).
Exposes the merchant capability catalog and executes autonomous trade commitments.
Can be queried programmatically by any Model Context Protocol (MCP) compliant client or Buyer Agent.
Conforms to FIDO / AP2 Intent Mandate specifications.
"""

import os
import json
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
    sign_mandate_token,
    ledger,
)
from ..services.paypal_service import paypal_service
from ..services.telnyx_provisioner import telnyx_provisioner
from ..services.zapier_mcp_dispatcher import zapier_mcp_dispatcher
from ..services.crypto_mandate import verify_mandate_proof
from ..config import settings

logger = logging.getLogger("seller_agent")

# Model Context Protocol (MCP) Tool Declarations
SELLER_MCP_TOOLS = [
    {
        "name": "get_service_catalog",
        "description": "Returns platform technical specifications, 10DLC telephony infrastructure, and backoffice integration capabilities.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "inspect_subscription_tiers",
        "description": "Inspects FieldSmith Pro commercial subscription tiers, monthly & annual pricing, screening minutes, overage rates, and negotiable trade options.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "negotiate_tier_terms",
        "description": "Evaluates buyer budget cap against desired subscription tier. If standard rate exceeds budget, autonomously negotiates tailored trade plan or pre-approved counter-offer with signed cryptographic mandate.",
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
                    "description": "Desired subscription tier (e.g. 'flooring-tile', 'solo-starter')",
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
        "description": "Binds a verified AP2 Intent Mandate to PayPal Recurring Vault for automated monthly billing.",
        "input_schema": {
            "type": "object",
            "required": ["tier_id", "agreed_monthly_rate", "mandate_proof_hash", "contractor_email"],
            "properties": {
                "tier_id": {"type": "string", "description": "Subscription tier ID (e.g. 'solo-starter', 'flooring-tile')"},
                "agreed_monthly_rate": {"type": "number", "description": "Agreed monthly subscription rate"},
                "mandate_proof_hash": {"type": "string", "description": "mandate_proof_hash returned by negotiate_tier_terms"},
                "contractor_email": {"type": "string", "description": "Contractor PayPal billing email; must match the email the mandate was negotiated for"},
            },
        },
    },
    {
        "name": "provision_telecom_line",
        "description": "Allocates a dedicated local 10DLC telephone DID upon verified PayPal subscription.",
        "input_schema": {
            "type": "object",
            "required": ["subscription_id", "contractor_email"],
            "properties": {
                "subscription_id": {"type": "string", "description": "Verified PayPal subscription ID"},
                "contractor_email": {"type": "string", "description": "Contractor notification email"},
                "area_code": {"type": "string", "default": "863", "description": "Target NPA area code"},
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


# Cache of completed subscriptions for strict idempotency (stable create_time)
_COMPLETED_SUBSCRIPTIONS: Dict[str, Dict[str, Any]] = {}


class SellerAgent:
    def __init__(self, agent_name: str = "FieldSmith Pro Seller MCP"):
        self.agent_name = agent_name

    def list_mcp_tools(self) -> List[Dict[str, Any]]:
        """Returns the MCP tool definitions for agent tool-use discovery."""
        return SELLER_MCP_TOOLS

    async def get_service_catalog(self) -> Dict[str, Any]:
        """Tool implementation: Returns available trade solutions."""
        return {
            "provider": self.agent_name,
            "currency": "USD",
            "tiers": [
                {
                    "trade_id": "solo-starter",
                    "title": "Solo Starter Intake",
                    "monthly_price": 49.99,
                    "features": [
                        "100 Screening Minutes",
                        "Automated Voice Screener",
                        "Dedicated 10DLC Number",
                        "Dynamic Negotiation Tier",
                    ],
                },
                {
                    "trade_id": "flooring-tile",
                    "title": "Tile & Custom Flooring",
                    "monthly_price": 79.99,
                    "features": [
                        "Sub-500ms Voice Screener",
                        "Substrate Scoping",
                        "Deposit Locking",
                    ],
                },
                {
                    "trade_id": "roofing-storm",
                    "title": "Roofing & Storm Restoration",
                    "monthly_price": 79.99,
                    "features": [
                        "Hail Damage Triage",
                        "Photo Intake Link",
                        "Insurance Intake",
                    ],
                },
                {
                    "trade_id": "plumbing-emergency",
                    "title": "Emergency Plumbing & Rooter",
                    "monthly_price": 79.99,
                    "features": [
                        "Burst Pipe Triage",
                        "Instant GPS Mobilization",
                        "24/7 Screening",
                    ],
                },
                {
                    "trade_id": "pro-dispatch",
                    "title": "Pro Multi-Trade / High-Volume Dispatch",
                    "monthly_price": 179.99,
                    "features": [
                        "Fleet Multi-Trade Routing",
                        "Unlimited Telephony Intake",
                        "Bryntum Dispatch Synchronization",
                        "Full ERP Automation",
                    ],
                },
            ],
        }

    async def inspect_subscription_tiers(self) -> Dict[str, Any]:
        """Tool implementation: Returns rich commercial subscription tiers, quotas, and pricing parameters."""
        return {
            "provider": self.agent_name,
            "currency": "USD",
            "protocol_support": ["AP2", "KYA", "FIDO"],
            "subscription_plans": [
                {
                    "tier_id": "solo-starter",
                    "trade_id": "solo-starter",
                    "title": "Solo Starter Intake",
                    "monthly_price": 49.99,
                    "annual_price": "479.90",
                    "screening_minutes": 100,
                    "overage_rate_per_min": 0.25,
                    "is_negotiable": False,
                    "features": [
                        "100 Screening Minutes",
                        "Automated Voice Screener",
                        "Dedicated 10DLC Number",
                        "Dynamic Negotiation Tier",
                    ],
                },
                {
                    "tier_id": "flooring-tile",
                    "trade_id": "flooring-tile",
                    "title": "Tile & Custom Flooring Specialized Screener",
                    "monthly_price": 79.99,
                    "annual_price": "767.90",
                    "screening_minutes": 300,
                    "overage_rate_per_min": 0.20,
                    "is_negotiable": False,
                    "features": [
                        "300 Screening Minutes",
                        "Sub-500ms Voice Screener",
                        "Substrate & Tile Scoping",
                        "Deposit Locking",
                    ],
                },
                {
                    "tier_id": "roofing-storm",
                    "trade_id": "roofing-storm",
                    "title": "Roofing & Storm Restoration",
                    "monthly_price": 79.99,
                    "annual_price": "767.90",
                    "screening_minutes": 300,
                    "overage_rate_per_min": 0.20,
                    "is_negotiable": False,
                    "features": [
                        "300 Screening Minutes",
                        "Hail Damage Triage",
                        "Photo Intake Link",
                        "Insurance Intake",
                    ],
                },
                {
                    "tier_id": "plumbing-emergency",
                    "trade_id": "plumbing-emergency",
                    "title": "Emergency Plumbing & Rooter",
                    "monthly_price": 79.99,
                    "annual_price": "767.90",
                    "screening_minutes": 300,
                    "overage_rate_per_min": 0.20,
                    "is_negotiable": False,
                    "features": [
                        "300 Screening Minutes",
                        "Burst Pipe Triage",
                        "Instant GPS Mobilization",
                        "24/7 Screening",
                    ],
                },
                {
                    "tier_id": "pro-dispatch",
                    "trade_id": "pro-dispatch",
                    "title": "Pro Multi-Trade / High-Volume Dispatch",
                    "monthly_price": 179.99,
                    "annual_price": "1727.90",
                    "screening_minutes": 1000,
                    "overage_rate_per_min": 0.15,
                    "is_negotiable": False,
                    "features": [
                        "1000 Screening Minutes",
                        "Fleet Multi-Trade Routing",
                        "Unlimited Telephony Intake",
                        "Bryntum Dispatch Synchronization",
                        "Full ERP Automation",
                    ],
                },
            ],
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
    ) -> Dict[str, Any]:
        """Issues one email-bound proof hash and its signed AP2 Intent Mandate, and registers both."""
        email = contractor_email.strip().lower()
        proof_hash = sign_mandate_token(
            agent_id=buyer_agent_id,
            amount=amount,
            recurrence=recurrence,
            secret=settings.a2a_mandate_secret,
            contractor_email=email,
        )
        negotiation_id = f"neg_{hashlib.sha256(proof_hash.encode()).hexdigest()[:12]}"
        ap2_mandate = build_ap2_intent_mandate(
            buyer_agent_id=buyer_agent_id,
            amount=amount,
            recurrence=recurrence,
            category=category,
            tier_id=tier_id,
            contractor_email=email,
            negotiation_id=negotiation_id,
        )
        register_authorized_mandate(
            proof_hash,
            {
                "tier_id": tier_id,
                "amount": amount,
                "buyer_agent_id": buyer_agent_id,
                "contractor_email": email,
                "monthly_budget_cap": monthly_budget_cap,
                "negotiation_id": negotiation_id,
                "ap2_mandate": ap2_mandate,
            },
        )
        return {"hash": proof_hash, "negotiation_id": negotiation_id, "ap2_mandate": ap2_mandate}

    async def negotiate_tier_terms(
        self,
        buyer_agent_id: str,
        tier_id: str,
        monthly_budget_cap: float,
        contractor_email: Optional[str] = None,
        proposed_price: Optional[float] = None,
        recurrence: str = "monthly",
        category: str = "TELEPHONY_AI_SCREENER",
    ) -> Dict[str, Any]:
        """
        Tool implementation: Evaluates buyer budget cap against desired tier.
        Autonomously negotiates down-tier counter-offers with verifiable AP2 cryptographic mandate proof hashes.
        """
        tier_prices = {
            "solo-starter": 49.99,
            "flooring-tile": 79.99,
            "roofing-storm": 79.99,
            "plumbing-emergency": 79.99,
            "pro-dispatch": 179.99,
        }
        tier_minutes = {
            "solo-starter": 100,
            "flooring-tile": 300,
            "roofing-storm": 300,
            "plumbing-emergency": 300,
            "pro-dispatch": 1000,
        }
        standard_price = tier_prices.get(tier_id, 79.99)
        minutes = tier_minutes.get(tier_id, 300)

        if not contractor_email or "@" not in contractor_email:
            return {
                "status": "REJECTED",
                "approved": False,
                "original_request_approved": False,
                "tier_id": tier_id,
                "error": "CONTRACTOR_EMAIL_REQUIRED",
                "reason": "contractor_email is required; the issued AP2 mandate is bound to it.",
            }

        # 1. Direct Approval: Desired tier is within budget cap
        if monthly_budget_cap >= standard_price:
            mandate_res = await self.verify_spending_mandate(
                buyer_agent_id=buyer_agent_id,
                amount=standard_price,
                recurrence=recurrence,
                category=category,
                monthly_budget_cap=monthly_budget_cap,
            )
            if not mandate_res.get("approved"):
                return {
                    "status": "REJECTED",
                    "approved": False,
                    "original_request_approved": False,
                    "tier_id": tier_id,
                    "monthly_budget_cap": round(monthly_budget_cap, 2),
                    "reason": mandate_res.get("reason"),
                }
            issued = self._issue_mandate(
                buyer_agent_id, contractor_email, tier_id, standard_price,
                recurrence, category, monthly_budget_cap,
            )
            return {
                "status": "APPROVED",
                "approved": True,
                "original_request_approved": True,
                "negotiation_id": issued["negotiation_id"],
                "tier_id": tier_id,
                "agreed_monthly_rate": standard_price,
                "monthly_budget_cap": round(monthly_budget_cap, 2),
                "monthly_cap_remaining": round(monthly_budget_cap - standard_price, 2),
                "screening_minutes": minutes,
                "mandate_proof_hash": issued["hash"],
                "ap2_intent_mandate": issued["ap2_mandate"],
                "reason": f"Plan '{tier_id}' at ${standard_price:.2f}/mo approved within ${monthly_budget_cap:.2f}/mo cap.",
            }

        # 2. Desired tier exceeds budget: Down-tier counter-offer to Solo Starter ($49.99)
        if monthly_budget_cap >= 49.99:
            issued = self._issue_mandate(
                buyer_agent_id, contractor_email, "solo-starter", 49.99,
                recurrence, category, monthly_budget_cap,
            )
            solo_hash = issued["hash"]

            remaining_after_solo = round(monthly_budget_cap - 49.99, 2)
            return {
                "status": "COUNTER_OFFER",
                "approved": False,
                "original_request_approved": False,
                "negotiation_id": issued["negotiation_id"],
                "tier_id": tier_id,
                "counter_offer_available": True,
                "counter_offer_tier": "Solo Starter",
                "counter_offer_tier_id": "solo-starter",
                "counter_offer_amount": 49.99,
                "counter_offer_mandate_hash": solo_hash,
                "mandate_proof_hash": solo_hash,
                "ap2_intent_mandate": issued["ap2_mandate"],
                "monthly_budget_cap": round(monthly_budget_cap, 2),
                "monthly_cap_remaining": remaining_after_solo,
                "reason": (
                    f"Requested plan '{tier_id}' lists at ${standard_price:.2f}/mo which exceeds monthly budget cap of ${monthly_budget_cap:.2f}. "
                    f"Counter-offer: Down-tier to 'Solo Starter' at $49.99/mo (100 screening minutes), leaving ${remaining_after_solo:.2f} in your monthly budget. "
                    f"A pre-signed mandateProofHash is included; call purchase_subscription with tier_id='solo-starter' "
                    f"and agreed_monthly_rate=49.99 to bind instantly."
                ),
            }

        # 3. Budget below minimum viable tier ($49.99)
        return {
            "status": "REJECTED",
            "approved": False,
            "original_request_approved": False,
            "tier_id": tier_id,
            "counter_offer_available": False,
            "monthly_budget_cap": round(monthly_budget_cap, 2),
            "monthly_cap_remaining": round(monthly_budget_cap, 2),
            "reason": f"Monthly budget cap of ${monthly_budget_cap:.2f} is below minimum viable tier (Solo Starter at $49.99/mo).",
        }

    async def verify_spending_mandate(
        self,
        buyer_agent_id: str,
        amount: float,
        recurrence: str,
        category: str,
        monthly_budget_cap: float,
    ) -> Dict[str, Any]:
        """Tool implementation: Enforces buyer spending limits."""
        req = SpendingMandateRequest(
            buyerAgentId=buyer_agent_id,
            amount=amount,
            recurrence=RecurrenceType(recurrence),
            category=category,
            monthlyBudgetCap=monthly_budget_cap,
        )
        res = evaluate_spending_mandate(req)
        return res.model_dump(by_alias=True)

    async def purchase_subscription(
        self,
        tier_id: str,
        agreed_monthly_rate: float,
        mandate_proof_hash: str,
        contractor_email: str,
    ) -> Dict[str, Any]:
        """
        Tool implementation: Binds verified AP2 Intent Mandate to PayPal Recurring Vault.
        Cryptographically verifies the mandate proof against tier, rate, and contractor identity.
        Replayed requests return the identical, immutable subscription record (idempotency).
        """
        # 1. Anti-Tamper & Identity Verification (always runs, even for replays)
        valid, reason = verify_authorized_mandate(
            proof_hash=mandate_proof_hash,
            tier_id=tier_id,
            agreed_rate=agreed_monthly_rate,
            contractor_email=contractor_email,
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
        if mandate_proof_hash in _COMPLETED_SUBSCRIPTIONS:
            return _COMPLETED_SUBSCRIPTIONS[mandate_proof_hash]

        # Mandates issued without an email are locked to their first redeemer
        bind_mandate_email(mandate_proof_hash, contractor_email)
        auth = get_authorized_mandate(mandate_proof_hash) or {}

        # 3. Record spend in ledger on actual checkout completion
        ledger.record_spend(
            agreed_monthly_rate,
            {
                "contractor_email": contractor_email,
                "tier_id": tier_id,
                "mandate_proof_hash": mandate_proof_hash,
            },
        )

        # 4. Deterministic Subscription ID
        seed = f"{mandate_proof_hash}:{tier_id}:{agreed_monthly_rate:.2f}"
        stable_int = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16) % 10000000
        sub_id = f"I-A2A-VAULT-{stable_int:07d}"

        utc_now = datetime.datetime.now(datetime.timezone.utc)
        created_time = utc_now.isoformat()
        next_billing = (utc_now + datetime.timedelta(days=30)).isoformat()
        negotiation_id = auth.get("negotiation_id") or f"neg_{hashlib.sha256(mandate_proof_hash.encode()).hexdigest()[:12]}"
        payer_id = f"PAYER-{hashlib.sha256(contractor_email.strip().lower().encode()).hexdigest()[:12].upper()}"
        vault_id = f"vault_tok_{sub_id.lower().replace('-', '_')}"
        payment_token = f"tok_{hashlib.sha256(f'{sub_id}:payment'.encode()).hexdigest()[:16]}"
        paypal_req_id = f"req_{hashlib.sha256(sub_id.encode()).hexdigest()[:16]}"

        # Return the exact signed mandate issued at negotiation, unchanged
        ap2_mandate = auth.get("ap2_mandate")
        if ap2_mandate is None:
            ap2_mandate = build_ap2_intent_mandate(
                buyer_agent_id=auth.get("buyer_agent_id", "unknown"),
                amount=agreed_monthly_rate,
                recurrence="monthly",
                category="TELEPHONY_AI_SCREENER",
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

        hateoas_links = [
            {
                "href": f"https://api.sandbox.paypal.com/v1/billing/subscriptions/{sub_id}",
                "rel": "self",
                "method": "GET",
            },
            {
                "href": f"https://www.sandbox.paypal.com/checkoutnow?token=BA-{sub_id}",
                "rel": "approve",
                "method": "GET",
            },
        ]

        response = {
            "status": "ACTIVE",
            "subscription_id": sub_id,
            "negotiation_id": negotiation_id,
            "plan_id": f"P-FLSMITH-{tier_id.upper().replace('-', '_')}",
            "product_id": "PROD-FIELDSMITH-A2A-TELEPHONY",
            "payer_id": payer_id,
            "vault_id": vault_id,
            "payment_token": payment_token,
            "tier_id": tier_id,
            "agreed_monthly_rate": round(agreed_monthly_rate, 2),
            "billing_cycle": "monthly",
            "billing_cycles": billing_cycles,
            "currency": "USD",
            "mandate_proof_hash": mandate_proof_hash,
            "contractor_email": contractor_email,
            "paypal_vault_status": "VAULT_BOUND",
            "paypal_environment": "sandbox",
            "paypal_request_id": paypal_req_id,
            "create_time": created_time,
            "next_billing_time": next_billing,
            "hateoas_links": hateoas_links,
            "ap2_intent_mandate": ap2_mandate,
            "message": f"Successfully bound PayPal subscription {sub_id} at ${agreed_monthly_rate:.2f}/mo under verified AP2 Intent Mandate.",
        }

        # Cache for strict idempotency
        _COMPLETED_SUBSCRIPTIONS[mandate_proof_hash] = response
        _COMPLETED_SUBSCRIPTIONS[sub_id] = response
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
        req = ProvisionRequest(
            subscriptionId=subscription_id,
            contractorEmail=contractor_email,
            areaCode=area_code,
            simulateExhaustion=simulate_exhaustion,
        )
        res = await telnyx_provisioner.provision_did(req, simulate_exhaustion=simulate_exhaustion)
        return res.model_dump(by_alias=True)

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
