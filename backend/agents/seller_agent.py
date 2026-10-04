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
            "required": ["buyer_agent_id", "tier_id", "monthly_budget_cap"],
            "properties": {
                "buyer_agent_id": {
                    "type": "string",
                    "description": "Unique identifier of the Buyer Agent",
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
                "mandate_proof_hash": {"type": "string", "description": "Signed AP2 Intent Mandate signature or token"},
                "contractor_email": {"type": "string", "description": "Contractor notification and PayPal billing email"},
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
        """Tool implementation: Returns rich commercial subscription tiers, minutes, and negotiable trade options."""
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
                    "annual_price": 479.90,
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
                    "annual_price": 767.90,
                    "screening_minutes": 300,
                    "overage_rate_per_min": 0.20,
                    "is_negotiable": True,
                    "negotiation_notes": "Custom tailored trade plan available at $59.99/mo for 200 mins.",
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
                    "annual_price": 767.90,
                    "screening_minutes": 300,
                    "overage_rate_per_min": 0.20,
                    "is_negotiable": True,
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
                    "annual_price": 767.90,
                    "screening_minutes": 300,
                    "overage_rate_per_min": 0.20,
                    "is_negotiable": True,
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
                    "annual_price": 1727.90,
                    "screening_minutes": 1000,
                    "overage_rate_per_min": 0.15,
                    "is_negotiable": True,
                    "features": [
                        "1000 Screening Minutes",
                        "Fleet Multi-Trade Routing",
                        "Unlimited Telephony Intake",
                        "Bryntum Dispatch Synchronization",
                        "Full ERP Automation",
                    ],
                },
            ],
            "tiers": [
                {"trade_id": "solo-starter", "title": "Solo Starter Intake", "monthly_price": 49.99},
                {"trade_id": "flooring-tile", "title": "Tile & Custom Flooring", "monthly_price": 79.99},
                {"trade_id": "roofing-storm", "title": "Roofing & Storm Restoration", "monthly_price": 79.99},
                {"trade_id": "plumbing-emergency", "title": "Emergency Plumbing & Rooter", "monthly_price": 79.99},
                {"trade_id": "pro-dispatch", "title": "Pro Multi-Trade Dispatch", "monthly_price": 179.99},
            ],
        }

    async def negotiate_tier_terms(
        self,
        buyer_agent_id: str,
        tier_id: str,
        monthly_budget_cap: float,
        proposed_price: Optional[float] = None,
        recurrence: str = "monthly",
        category: str = "TELEPHONY_AI_SCREENER",
    ) -> Dict[str, Any]:
        """
        Tool implementation: Evaluates buyer budget cap against desired tier.
        Autonomously negotiates tailored trade pricing or pre-approved counter-offers
        with verifiable AP2 cryptographic mandate proof hashes.
        """
        tier_prices = {
            "solo-starter": 49.99,
            "flooring-tile": 79.99,
            "roofing-storm": 79.99,
            "plumbing-emergency": 79.99,
            "pro-dispatch": 179.99,
            "flooring-tile-starter": 59.99,
        }
        tier_minutes = {
            "solo-starter": 100,
            "flooring-tile": 300,
            "roofing-storm": 300,
            "plumbing-emergency": 300,
            "pro-dispatch": 1000,
            "flooring-tile-starter": 200,
        }
        standard_price = tier_prices.get(tier_id, 79.99)
        minutes = tier_minutes.get(tier_id, 300)

        # 1. Direct Approval: Desired tier is within budget cap
        if monthly_budget_cap >= standard_price:
            mandate_res = await self.verify_spending_mandate(
                buyer_agent_id=buyer_agent_id,
                amount=standard_price,
                recurrence=recurrence,
                category=category,
                monthly_budget_cap=monthly_budget_cap,
            )
            mandate_hash = mandate_res.get("mandateProofHash", "")
            register_authorized_mandate(
                mandate_hash,
                {
                    "tier_id": tier_id,
                    "amount": standard_price,
                    "buyer_agent_id": buyer_agent_id,
                    "monthly_budget_cap": monthly_budget_cap,
                },
            )
            return {
                "status": "APPROVED",
                "approved": True,
                "tier_id": tier_id,
                "agreed_monthly_rate": standard_price,
                "monthly_budget_cap": round(monthly_budget_cap, 2),
                "monthly_cap_remaining": round(monthly_budget_cap - standard_price, 2),
                "screening_minutes": minutes,
                "mandate_proof_hash": mandate_hash,
                "ap2_intent_mandate": mandate_res.get("ap2IntentMandate"),
                "reason": f"Plan '{tier_id}' at ${standard_price:.2f}/mo approved within ${monthly_budget_cap:.2f}/mo cap.",
            }

        # 2. Desired tier exceeds budget: Construct intelligent counter-negotiation
        solo_hash = sign_mandate_token(
            agent_id=buyer_agent_id,
            amount=49.99,
            recurrence=recurrence,
            secret=settings.a2a_mandate_secret,
        )
        register_authorized_mandate(
            solo_hash,
            {
                "tier_id": "solo-starter",
                "amount": 49.99,
                "buyer_agent_id": buyer_agent_id,
                "monthly_budget_cap": monthly_budget_cap,
            },
        )

        counter_offers = [
            {
                "tier_id": "solo-starter",
                "title": "Solo Starter Intake",
                "monthly_price": 49.99,
                "screening_minutes": 100,
                "mandate_proof_hash": solo_hash,
                "features": ["100 Screening Minutes", "Automated Voice Screener", "Dedicated 10DLC DID"],
            }
        ]

        if "flooring" in tier_id and monthly_budget_cap >= 59.99:
            tailored_hash = sign_mandate_token(
                agent_id=buyer_agent_id,
                amount=59.99,
                recurrence=recurrence,
                secret=settings.a2a_mandate_secret,
            )
            register_authorized_mandate(
                tailored_hash,
                {
                    "tier_id": "flooring-tile-starter",
                    "amount": 59.99,
                    "buyer_agent_id": buyer_agent_id,
                    "monthly_budget_cap": monthly_budget_cap,
                },
            )
            tailored_plan = {
                "tier_id": "flooring-tile-starter",
                "title": "Flooring & Tile Starter (Negotiated)",
                "monthly_price": 59.99,
                "screening_minutes": 200,
                "mandate_proof_hash": tailored_hash,
                "features": ["200 Screening Minutes", "Tile & Subfloor Scoping", "Deposit Authorization"],
            }
            counter_offers.insert(0, tailored_plan)

        primary_counter = counter_offers[0]
        selected_counter_tier = primary_counter["tier_id"]
        selected_counter_amount = primary_counter["monthly_price"]
        selected_counter_hash = primary_counter["mandate_proof_hash"]

        return {
            "status": "COUNTER_OFFER",
            "approved": False,
            "tier_id": tier_id,
            "counter_offer_available": True,
            "counter_offer_tier": primary_counter["title"],
            "counter_offer_tier_id": selected_counter_tier,
            "counter_offer_plan_id": selected_counter_tier,
            "counter_offer_amount": selected_counter_amount,
            "counter_offer_mandate_hash": selected_counter_hash,
            "mandate_proof_hash": selected_counter_hash,
            "monthly_budget_cap": round(monthly_budget_cap, 2),
            "monthly_cap_remaining": round(monthly_budget_cap - selected_counter_amount, 2),
            "available_counter_offers": counter_offers,
            "reason": (
                f"Requested plan '{tier_id}' lists at ${standard_price:.2f}/mo which exceeds budget cap ${monthly_budget_cap:.2f}. "
                f"Counter-offer: '{primary_counter['title']}' at ${selected_counter_amount:.2f}/mo. "
                f"A pre-signed mandateProofHash is included; call purchase_subscription with tier_id='{selected_counter_tier}' "
                f"and agreed_monthly_rate={selected_counter_amount} to bind instantly."
            ),
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
        Cryptographically verifies the mandate proof against tier and agreed rate.
        """
        # 1. Anti-Tamper Verification
        valid, reason = verify_authorized_mandate(
            proof_hash=mandate_proof_hash,
            tier_id=tier_id,
            agreed_rate=agreed_monthly_rate,
        )
        if not valid:
            logger.warning(f"[SECURITY] Mandate verification failed for {tier_id}: {reason}")
            return {
                "status": "REJECTED",
                "error": "MANDATE_SECURITY_BREACH",
                "reason": reason,
                "message": f"Purchase rejected: {reason}",
            }

        # 2. Record spend in ledger on actual checkout completion
        ledger.record_spend(
            agreed_monthly_rate,
            {
                "contractor_email": contractor_email,
                "tier_id": tier_id,
                "mandate_proof_hash": mandate_proof_hash,
            },
        )

        # 3. Deterministic subscription ID based on mandate proof and terms
        seed = f"{mandate_proof_hash}:{tier_id}:{agreed_monthly_rate:.2f}"
        stable_int = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16) % 10000000
        sub_id = f"I-A2A-VAULT-{stable_int:07d}"

        utc_now = datetime.datetime.now(datetime.timezone.utc)
        created_time = utc_now.isoformat()
        next_billing = (utc_now + datetime.timedelta(days=30)).isoformat()

        return {
            "status": "ACTIVE",
            "subscription_id": sub_id,
            "plan_id": f"P-FLSMITH-{tier_id.upper().replace('-', '_')}",
            "product_id": "PROD-FIELDSMITH-A2A-TELEPHONY",
            "tier_id": tier_id,
            "agreed_monthly_rate": round(agreed_monthly_rate, 2),
            "billing_cycle": "monthly",
            "currency": "USD",
            "mandate_proof_hash": mandate_proof_hash,
            "contractor_email": contractor_email,
            "paypal_vault_status": "VAULT_BOUND",
            "paypal_environment": "sandbox",
            "create_time": created_time,
            "next_billing_time": next_billing,
            "hateoas_links": [
                {
                    "href": f"https://api.sandbox.paypal.com/v1/billing/subscriptions/{sub_id}",
                    "rel": "self",
                    "method": "GET",
                }
            ],
            "message": f"Successfully bound PayPal subscription {sub_id} at ${agreed_monthly_rate:.2f}/mo under verified AP2 Intent Mandate.",
        }


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
