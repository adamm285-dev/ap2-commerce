"""
Pydantic data models for FieldSmith Pro A2A Commerce & Multi-Agent Network.
Maps directly to openapi.yaml schemas.
"""

from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict


class RecurrenceType(str, Enum):
    ONE_TIME = "one_time"
    MONTHLY = "monthly"
    ANNUAL = "annual"


# --- Service Catalog Models ---
class TradeService(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    title: str
    monthly_subscription: float = Field(alias="monthlySubscription")
    deposit_range: str = Field(alias="depositRange")
    description: str


class CatalogResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: str = "active"
    currency: str = "USD"
    trades: List[TradeService]


# --- Quoting & Scoping Models ---
class QuoteRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    trade_id: str = Field(alias="tradeId")
    square_footage: float = Field(alias="squareFootage")
    material_type: str = Field(alias="materialType")
    postal_code: str = Field(alias="postalCode")


class QuoteResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    trade_id: str = Field(alias="tradeId")
    estimated_labor_range: str = Field(alias="estimatedLaborRange")
    waste_allowance_sq_ft: float = Field(alias="wasteAllowanceSqFt")
    required_deposit: float = Field(alias="requiredDeposit")
    deposit_policy: str = Field(alias="depositPolicy")


# --- Spending Mandate Models ---
class SpendingMandateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    buyer_agent_id: str = Field(alias="buyerAgentId")
    amount: float
    recurrence: RecurrenceType
    category: str
    monthly_budget_cap: Optional[float] = Field(
        default=100.00, alias="monthlyBudgetCap"
    )
    contractor_email: Optional[str] = Field(
        default=None, alias="contractorEmail"
    )


class SpendingMandateResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    approved: bool
    authorized_amount: float = Field(alias="authorizedAmount")
    monthly_cap_remaining: float = Field(alias="monthlyCapRemaining")
    mandate_proof_hash: str = Field(alias="mandateProofHash")
    reason: Optional[str] = None
    counter_offer_available: Optional[bool] = Field(
        default=False, alias="counterOfferAvailable"
    )
    counter_offer_tier: Optional[str] = Field(
        default=None, alias="counterOfferTier"
    )
    counter_offer_amount: Optional[float] = Field(
        default=None, alias="counterOfferAmount"
    )
    counter_offer_plan_id: Optional[str] = Field(
        default=None, alias="counterOfferPlanId"
    )
    counter_offer_tier_id: Optional[str] = Field(
        default=None, alias="counterOfferTierId"
    )
    counter_offer_mandate_hash: Optional[str] = Field(
        default=None, alias="counterOfferMandateHash"
    )
    tier_id: Optional[str] = Field(default=None, alias="tierId")
    ap2_intent_mandate: Optional[Dict[str, Any]] = Field(
        default=None, alias="ap2IntentMandate"
    )
    signature_algorithm: Optional[str] = Field(
        default="Ed25519", alias="signatureAlgorithm"
    )
    error: Optional[str] = Field(default=None, alias="error")
    active_subscription_id: Optional[str] = Field(
        default=None, alias="activeSubscriptionId"
    )


# --- Telephony Provisioning Models ---
class ProvisionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    subscription_id: str = Field(alias="subscriptionId")
    contractor_email: str = Field(alias="contractorEmail")
    area_code: str = Field(default="863", alias="areaCode")
    simulate_exhaustion: Optional[bool] = Field(
        default=False, alias="simulateExhaustion"
    )


class ProvisionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: str
    assigned_did: str = Field(alias="assignedDid")
    carrier: str
    routing_state: str = Field(alias="routingState")
    subscription_id: str = Field(alias="subscriptionId")
    failover_triggered: Optional[bool] = Field(
        default=False, alias="failoverTriggered"
    )
    region: Optional[str] = None
    retained_from_subscription: Optional[str] = Field(
        default=None, alias="retainedFromSubscription"
    )


# --- Territory Dispatch Models ---
class DispatchLockRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    lead_id: str = Field(alias="leadId")
    territory_zone: str = Field(alias="territoryZone")
    slot_start_iso: str = Field(alias="slotStartIso")
    paypal_transaction_id: str = Field(alias="paypalTransactionId")


class DispatchLockResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    success: bool
    slot_locked_until: str = Field(alias="slotLockedUntil")
    crew_assigned: str = Field(alias="crewAssigned")
    territory_zone: str = Field(alias="territoryZone")


# --- Zapier MCP & Back-Office Export Models ---
class ZapierSyncRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    workflow_type: Optional[str] = Field(default=None, alias="workflowType")
    lead_id: Optional[str] = Field(default="lead-a2a-onboarding", alias="leadId")
    customer_name: Optional[str] = Field(default="Marcus Miller", alias="customerName")
    customer_phone: Optional[str] = Field(default="+1 (863) 267-8902", alias="customerPhone")
    property_address: Optional[str] = Field(default="Lakeland, FL", alias="propertyAddress")
    deposit_amount: Optional[float] = Field(default=79.99, alias="depositAmount")
    paypal_txn_id: Optional[str] = Field(default="I-AUTONOMOUS-8902", alias="paypalTxnId")

    # A2A Contractor Onboarding specific attributes
    contractor_name: Optional[str] = Field(default="Marcus Miller", alias="contractorName")
    business_entity: Optional[str] = Field(default="Miller Custom Flooring LLC", alias="businessEntity")
    allocated_did: Optional[str] = Field(default="+1 (863) 267-8902", alias="allocatedDid")
    trade_vertical: Optional[str] = Field(default="Tile & Custom Flooring", alias="tradeVertical")
    monthly_subscription_fee: Optional[float] = Field(default=79.99, alias="monthlySubscriptionFee")
    paypal_subscription_id: Optional[str] = Field(default="I-AUTONOMOUS-8902", alias="paypalSubscriptionId")
    contractor_email: Optional[str] = Field(default="marcus@millercustomfloors.com", alias="contractorEmail")
    mandate_proof_hash: Optional[str] = Field(default=None, alias="mandateProofHash")
    webhook_url: Optional[str] = Field(default=None, alias="webhookUrl")
    dry_run: Optional[bool] = Field(default=True, alias="dryRun")


class ZapierSyncResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    jobber_quote_id: str = Field(alias="jobberQuoteId")
    qbo_draft_invoice_id: str = Field(alias="qboDraftInvoiceId")
    google_calendar_event_id: str = Field(alias="googleCalendarEventId")
    status: str
    workflow_type: str = Field(default="a2a_onboarding", alias="workflowType")
    jobber_payload: Optional[Dict[str, Any]] = Field(default=None, alias="jobberPayload")
    qbo_payload: Optional[Dict[str, Any]] = Field(default=None, alias="qboPayload")
    webhook_delivery_id: Optional[str] = Field(default=None, alias="webhookDeliveryId")
    webhook_dispatched: Optional[bool] = Field(default=False, alias="webhookDispatched")
    webhook_status_code: Optional[int] = Field(default=None, alias="webhookStatusCode")


# --- PayPal Order Management Models ---
class PayPalOrderCreateRequest(BaseModel):
    amount: float
    currency: str = "USD"
    description: str
    custom_id: Optional[str] = None


class PayPalOrderResponse(BaseModel):
    order_id: str
    status: str
    approval_url: Optional[str] = None
    mock_mode: bool


# --- Dynamic Buyer Key Onboarding Models ---
class BuyerKeyChallengeResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    challenge: str = Field(description="Cryptographically random nonce to sign")
    timestamp: int = Field(description="Unix timestamp of challenge creation")
    expires_in: int = Field(default=300, alias="expiresIn", description="Challenge lifetime in seconds")
    algorithm: str = Field(default="Ed25519", description="Expected cryptographic signature algorithm")
    message: str = Field(description="Instructions for autonomous buyer onboarding")


class BuyerKeyRegistrationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    kid: str = Field(min_length=3, max_length=64, description="Unique key identifier for buyer agent")
    public_key_hex: str = Field(alias="publicKeyHex", min_length=64, max_length=64, description="64-hex-character Ed25519 public key")
    contractor_email: str = Field(alias="contractorEmail", description="Contractor email address (US domestic)")
    business_entity: str = Field(alias="businessEntity", min_length=2, max_length=128, description="Verified legal business entity name")
    challenge: str = Field(min_length=10, description="Challenge string provided by /api/agent/keys/challenge")
    challenge_signature: str = Field(alias="challengeSignature", min_length=128, max_length=128, description="128-hex-character Ed25519 challenge signature")
    monthly_budget_cap: Optional[float] = Field(default=100.0, alias="monthlyBudgetCap", description="Monthly spending cap in USD")
    allowed_tiers: Optional[List[str]] = Field(default=["solo-starter", "fieldsmith-pro"], alias="allowedTiers", description="Permitted subscription tiers")


class BuyerKeyRegistrationResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: str = Field(description="Registration outcome status (REGISTERED / REJECTED)")
    kid: str = Field(description="Key identifier")
    public_key_hex: str = Field(alias="publicKeyHex", description="Registered public key hex")
    contractor_email: str = Field(alias="contractorEmail", description="Associated contractor email")
    business_entity: str = Field(alias="businessEntity", description="Associated legal entity")
    registered_at: str = Field(alias="registeredAt", description="ISO registration timestamp")
    verified: bool = Field(description="Whether cryptographic challenge-response signature was verified")
    message: str = Field(description="Human-readable onboarding status message")


class BuyerKeyRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    kid: str
    public_key_hex: str = Field(alias="publicKeyHex")
    contractor_email: Optional[str] = Field(default=None, alias="contractorEmail")
    business_name: Optional[str] = Field(default=None, alias="businessName")
    registered_at: str = Field(alias="registeredAt")


class BuyerKeyRegistryResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: str = "active"
    count: int
    keys: List[BuyerKeyRecord]

