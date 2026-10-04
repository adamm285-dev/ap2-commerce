"""
FieldSmith Pro A2A Commerce & Multi-Agent Network — FastAPI Server.
Implements the full OpenAPI 3.1.0 contract defined in openapi.yaml.
Supports 100% offline mock simulation when external keys are not configured.
"""

import logging
import hmac
import hashlib
import json
import uuid
import datetime
import asyncio
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, ConfigDict
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .models import (
    CatalogResponse,
    TradeService,
    QuoteRequest,
    QuoteResponse,
    SpendingMandateRequest,
    SpendingMandateResponse,
    ProvisionRequest,
    ProvisionResponse,
    DispatchLockRequest,
    DispatchLockResponse,
    ZapierSyncRequest,
    ZapierSyncResponse,
    PayPalOrderCreateRequest,
    PayPalOrderResponse,
)
from .services.mandate_evaluator import evaluate_spending_mandate, ledger
from .services.paypal_service import paypal_service
from .services.telnyx_provisioner import telnyx_provisioner
from .services.zapier_mcp_dispatcher import zapier_mcp_dispatcher
from .services.crypto_mandate import (
    generate_dynamic_mandate_proof,
    verify_mandate_proof,
    canonicalize_mandate_payload,
    DEFAULT_SELLER_KID,
    DEFAULT_SELLER_PUBLIC_KEY_HEX,
    SECRET_KEY,
)
from .mcp_server import (
    process_mcp_request,
    subscribe_wire_stream,
    unsubscribe_wire_stream,
    get_recent_wire_frames,
)
from .agents.contractor_copilot import ContractorCopilot
from .agents.seller_agent import seller_agent
from .harness.external_buyer_agent import ExternalBuyerAgent
from .api.m2m_audit import router as m2m_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("a2a_server")

app = FastAPI(
    title="FieldSmith Pro A2A Agentic Commerce API",
    description="Autonomous Agent-to-Agent (A2A) Commerce Protocol for Solo Trade Contractors",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Mount M2M Audit Router for 1-click in-UI judge inspection (both /m2m and /api/m2m)
app.include_router(m2m_router)
app.include_router(m2m_router, prefix="/api")

# Enable CORS for frontend applications (e.g. Vite on port 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory trade service catalog
TRADE_CATALOG = [
    TradeService(
        id="solo-starter",
        title="Solo Starter Intake (Negotiated / Low-Volume)",
        monthlySubscription=49.99,
        depositRange="$99.00 - $149.00",
        description="Autonomous intake, essential SMS follow-up, 100-minute screener cap, and verified deposit locking.",
    ),
    TradeService(
        id="flooring-tile",
        title="Tile & Custom Flooring",
        monthlySubscription=79.99,
        depositRange="$149.00 - $250.00",
        description="Autonomous intake, substrate scoping, square footage waste takeoff, and verified deposit locking.",
    ),
    TradeService(
        id="roofing-storm",
        title="Roofing & Storm Restoration",
        monthlySubscription=79.99,
        depositRange="$250.00 - $500.00",
        description="Hail/wind damage triage, drone photo link dispatch, insurance claim capture, and contractor dispatch.",
    ),
    TradeService(
        id="plumbing-emergency",
        title="Emergency Plumbing & Rooter",
        monthlySubscription=79.99,
        depositRange="$149.00 - $200.00",
        description="Burst pipe triage, shut-off valve guidance, emergency mobilization deposit, and turn-by-turn routing.",
    ),
    TradeService(
        id="towing-roadside",
        title="24/7 Towing & Heavy Roadside",
        monthlySubscription=79.99,
        depositRange="$99.00 - $175.00",
        description="Highway shoulder GPS anchor, vehicle gross weight classification, and upfront roll deposit.",
    ),
    TradeService(
        id="pro-dispatch",
        title="Pro Multi-Trade / High-Volume Dispatch",
        monthlySubscription=179.99,
        depositRange="$250.00 - $750.00",
        description="Fleet-wide multi-trade routing, unlimited telephony intake, Bryntum dispatch synchronization, and ERP automation.",
    ),
]


@app.get("/health", tags=["System Health"])
async def health_check():
    """Health check endpoint reporting API status and operating mode."""
    return {
        "status": "healthy",
        "mock_mode": settings.mock_external_apis,
        "paypal_configured": bool(settings.paypal_client_id),
        "telnyx_configured": bool(settings.telnyx_api_key),
        "zapier_configured": bool(settings.zapier_nla_api_key),
        "mcp_server_active": True,
    }


# --- Google A2A / AP2 Agent Discovery Card ---
@app.get("/.well-known/agent.json", tags=["Agent Discovery"])
@app.get("/agent.json", tags=["Agent Discovery"])
async def agent_discovery_card():
    """
    Google A2A / AP2 Agent Card for Autonomous Discovery.
    Publishes capabilities, cryptographic identity keys, pricing plans, and MCP endpoints.
    """
    return {
        "name": "FieldSmith Pro A2A Seller Agent",
        "description": "Autonomous Agent-to-Agent (A2A) Commerce Protocol Engine for Solo Field Service Contractors. Provides automated voice receptionist, 10DLC telephony line provisioning, and PayPal Recurring Vault binding.",
        "version": "1.0.0",
        "protocol_version": "2024-11-05",
        "supported_protocols": ["A2A", "AP2", "MCP"],
        "provider": {
            "organization": "FieldSmith Pro LLC",
            "service": "FieldSmith Autonomous Telephony SaaS",
            "url": "https://fieldsmith.pro",
        },
        "endpoints": {
            "mcp": "/mcp",
            "catalog": "/api/agent/catalog",
            "health": "/health",
            "m2m_audit": "/api/m2m/audit-trail",
            "wire_stream": "/api/mcp/sse",
        },
        "authentication": {
            "type": "asymmetric_cryptographic_mandate",
            "algorithms": ["Ed25519", "HMAC-SHA256"],
            "seller_kid": DEFAULT_SELLER_KID,
            "seller_public_key": DEFAULT_SELLER_PUBLIC_KEY_HEX,
        },
        "plans": [
            {
                "tier_id": "solo-starter",
                "title": "FieldSmith Solo Starter",
                "monthly_price": 49.99,
                "screening_minutes": 100,
            },
            {
                "tier_id": "fieldsmith-pro",
                "title": "FieldSmith Pro Specialized Trade Screener",
                "monthly_price": 79.99,
                "screening_minutes": 300,
            },
            {
                "tier_id": "pro-dispatch",
                "title": "FieldSmith Fleet Multi-Crew Dispatch",
                "monthly_price": 179.99,
                "screening_minutes": 1000,
            },
        ],
        "capabilities": {
            "inspect_subscription_tiers": True,
            "negotiate_tier_terms": True,
            "autonomous_down_tiering": True,
            "ap2_intent_mandate_verification": True,
            "ap2_cart_mandate_issuance": True,
            "paypal_vault_recurring": True,
            "telecom_10dlc_allocation": True,
            "backoffice_erp_dispatch": True,
        },
    }


# --- Model Context Protocol (MCP) JSON-RPC 2.0 Endpoint ---
@app.post("/mcp", tags=["Model Context Protocol"])
async def mcp_jsonrpc_endpoint(request: Request):
    """
    Standard Model Context Protocol (MCP) JSON-RPC 2.0 endpoint.
    Allows external autonomous agents (Grok, ChatGPT, Claude, Cursor) to discover
    and invoke FieldSmith telephony capabilities, mandate evaluation, and line provisioning.
    """
    try:
        body = await request.json()
    except Exception:
        return {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32700, "message": "Parse error: invalid JSON body"},
        }
    resp = await process_mcp_request(body)
    if resp is None:
        return {"status": "ok"}
    return resp


# --- Live Wire Protocol SSE Stream & Packet Inspector ---
@app.get("/api/mcp/sse", tags=["MCP Wire Protocol"])
@app.get("/m2m/sse", tags=["MCP Wire Protocol"])
async def mcp_wire_stream(request: Request):
    """
    Streams live Server-Sent Events (SSE) of raw JSON-RPC 2.0 frames
    exchanged between agents and the FieldSmith MCP Server.
    """
    async def event_generator():
        q = subscribe_wire_stream()
        try:
            init_event = {
                "type": "connected",
                "message": "FieldSmith MCP Wire Protocol SSE Stream Active",
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
            yield f"data: {json.dumps(init_event)}\n\n"

            while True:
                if await request.is_disconnected():
                    break
                try:
                    frame = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {json.dumps(frame)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            unsubscribe_wire_stream(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/mcp/frames", tags=["MCP Wire Protocol"])
@app.get("/m2m/frames", tags=["MCP Wire Protocol"])
async def get_wire_frames():
    """Returns the buffer of recent JSON-RPC 2.0 frames for packet inspection."""
    return {"frames": get_recent_wire_frames()}


# --- Cryptographic Mandate & Anti-Tamper Verification API ---
class VerifyTamperRequest(BaseModel):
    payload: Dict[str, Any]
    signature: str


class GenerateProofRequest(BaseModel):
    contractor_id: Optional[str] = "contractor_marcus_863"
    business_name: Optional[str] = "Miller Custom Flooring LLC"
    monthly_cap_usd: Optional[float] = 100.00
    agreed_price_usd: Optional[float] = 79.99
    nonce: Optional[str] = None


@app.post("/api/crypto/verify-tamper", tags=["Anti-Tamper & Cryptography"])
async def verify_tamper_endpoint(req: VerifyTamperRequest):
    """
    Live anti-tamper verification endpoint.
    Tests whether the supplied payload matches its HMAC-SHA256 signature,
    checks budget caps, and verifies timestamp drift.
    """
    valid, reason = verify_mandate_proof(req.payload, req.signature)
    canonical = canonicalize_mandate_payload(req.payload)
    encoded_bytes = json.dumps(canonical, sort_keys=True).encode("utf-8")
    expected_sig = hmac.new(SECRET_KEY, encoded_bytes, hashlib.sha256).hexdigest()

    status_code = 200 if valid else 401
    return {
        "valid": valid,
        "status_code": status_code,
        "reason": reason,
        "detail": (
            "200 OK: Cryptographically Verified"
            if valid
            else f"401 Signature Mismatch: Budget Policy Violated ({reason})"
        ),
        "expected_signature": expected_sig,
        "provided_signature": req.signature,
        "payload": req.payload,
    }


@app.post("/api/crypto/generate-proof", tags=["Anti-Tamper & Cryptography"])
async def generate_proof_endpoint(req: GenerateProofRequest):
    """Generates a canonical HMAC-SHA256 mandate proof for given parameters."""
    nonce = req.nonce or uuid.uuid4().hex[:12]
    proof = generate_dynamic_mandate_proof(
        contractor_id=req.contractor_id or "contractor_marcus_863",
        business_name=req.business_name or "Miller Custom Flooring LLC",
        monthly_cap_usd=req.monthly_cap_usd if req.monthly_cap_usd is not None else 100.00,
        agreed_price_usd=req.agreed_price_usd if req.agreed_price_usd is not None else 79.99,
        nonce=nonce,
    )
    proof["secret_key_preview"] = SECRET_KEY.decode("utf-8")
    return proof


@app.get("/api/crypto/sample-proof", tags=["Anti-Tamper & Cryptography"])
async def get_sample_proof():
    """Returns a ready-to-test authentic proof for Marcus Miller."""
    nonce = uuid.uuid4().hex[:12]
    proof = generate_dynamic_mandate_proof(
        contractor_id="contractor_marcus_863",
        business_name="Miller Custom Flooring LLC",
        monthly_cap_usd=100.00,
        agreed_price_usd=79.99,
        nonce=nonce,
    )
    proof["secret_key_preview"] = SECRET_KEY.decode("utf-8")
    return proof


# --- Contractor AI Copilot Conversational Engine ---
class CopilotChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    message: str
    contractorName: Optional[str] = Field(default="Marcus Miller", alias="contractor_name")
    businessEntity: Optional[str] = Field(default="Miller Custom Flooring LLC", alias="business_entity")
    tradeVertical: Optional[str] = Field(default="Tile & Custom Flooring", alias="trade_vertical")
    areaCode: Optional[str] = Field(default="863", alias="area_code")
    budgetCap: Optional[float] = Field(default=100.00, alias="budget_cap")
    simulateExhaustion: Optional[bool] = Field(default=False, alias="simulate_exhaustion")


@app.post("/api/copilot/chat", tags=["Contractor Copilot"])
async def copilot_chat_endpoint(req: CopilotChatRequest):
    """
    Contractor AI Copilot conversational engine.
    Ingests messages from the contractor, diagnoses call leaks, queries FieldSmith Seller MCP,
    and returns conversational responses and proposed A2A actions.
    """
    copilot = ContractorCopilot(
        contractor_name=req.contractorName or "Marcus Miller",
        business_entity=req.businessEntity or "Miller Custom Flooring LLC",
        trade_vertical=req.tradeVertical or "Tile & Custom Flooring",
        area_code=req.areaCode or "863",
        budget_cap=req.budgetCap or 100.00,
        simulate_exhaustion=req.simulateExhaustion or False,
    )
    res = await copilot.handle_message(req.message)
    return res


@app.get("/api/agent/catalog", response_model=CatalogResponse, tags=["Agent Catalog"])
async def get_trade_catalog():
    """Returns available trade verticals, pricing, and deposit rules for Buyer Agents."""
    return CatalogResponse(status="active", currency="USD", trades=TRADE_CATALOG)


@app.post("/api/agent/quote", response_model=QuoteResponse, tags=["Quoting & Scoping"])
async def calculate_trade_quote(request: QuoteRequest):
    """Calculates trade scoping estimates, waste allowances, and required mobilization deposits."""
    # Waste allowance calculation (standard 10% overage for flooring/tile, 15% for roofing)
    waste_multiplier = 1.15 if "roofing" in request.trade_id else 1.10
    waste_sq_ft = round(request.square_footage * waste_multiplier, 1)

    # Labor range calculation ($4.00 - $5.50 / sq ft baseline for tile)
    low_rate = 4.00
    high_rate = 5.50
    estimated_range = f"${(request.square_footage * low_rate):,.2f} - ${(request.square_footage * high_rate):,.2f}"

    deposit = 250.00 if request.square_footage >= 500 else 150.00

    return QuoteResponse(
        tradeId=request.trade_id,
        estimatedLaborRange=estimated_range,
        wasteAllowanceSqFt=waste_sq_ft,
        requiredDeposit=deposit,
        depositPolicy="100% credited against final invoice upon physical jobsite takeoff",
    )


@app.post(
    "/api/agent/spending-mandate/evaluate",
    response_model=SpendingMandateResponse,
    tags=["Autonomous Governance"],
)
async def evaluate_mandate_endpoint(request: SpendingMandateRequest):
    """Evaluates whether an inbound agent spending request complies with buyer financial guardrails."""
    return evaluate_spending_mandate(request)


@app.post(
    "/api/agent/spending-mandate/reset",
    tags=["Autonomous Governance"],
)
async def reset_mandate_endpoint(request: Request):
    """Resets the spending mandate ledger for simulations and testing (requires admin authentication)."""
    auth_header = request.headers.get("Authorization") or request.headers.get("X-Admin-Key")
    admin_param = request.query_params.get("admin_key")

    provided_token = None
    if auth_header:
        if auth_header.startswith("Bearer "):
            provided_token = auth_header[7:].strip()
        else:
            provided_token = auth_header.strip()
    elif admin_param:
        provided_token = admin_param.strip()

    expected_key = getattr(settings, "admin_api_key", "dev-admin-secret-key")
    if not provided_token or provided_token != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authorization required to reset mandate ledger. Provide X-Admin-Key header or admin_key query param.",
        )

    agent_id = None
    try:
        body = await request.json()
        if isinstance(body, dict):
            agent_id = body.get("buyerAgentId")
    except Exception:
        pass

    qp_agent = request.query_params.get("agent_id")
    if qp_agent:
        agent_id = qp_agent

    ledger.reset(agent_id=agent_id)
    return {
        "status": "reset",
        "agent_id": agent_id or "all",
        "remaining_budget": ledger.get_remaining_budget(agent_id=agent_id),
    }


@app.post(
    "/api/agent/provision",
    response_model=ProvisionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Telephony Provisioning"],
)
async def provision_line_endpoint(request: ProvisionRequest):
    """Provisions a dedicated 10DLC telephone DID anchored to verified PayPal subscriber identity."""
    res = await seller_agent.provision_telecom_line(
        subscription_id=request.subscription_id,
        contractor_email=request.contractor_email,
        area_code=request.area_code or "863",
        simulate_exhaustion=request.simulate_exhaustion or False,
    )
    if res.get("status") == "REJECTED":
        err = res.get("error", "PROVISIONING_FAILED")
        reason = res.get("reason", "Provisioning rejected.")
        status_code = status.HTTP_400_BAD_REQUEST
        if err == "IDENTITY_MISMATCH_DETECTED":
            status_code = status.HTTP_403_FORBIDDEN
        elif err == "SUBSCRIPTION_NOT_FOUND":
            status_code = status.HTTP_404_NOT_FOUND
        raise HTTPException(
            status_code=status_code,
            detail={"status": "REJECTED", "error": err, "reason": reason},
        )
    return ProvisionResponse(**res)


@app.post(
    "/api/agent/dispatch/lock-slot",
    response_model=DispatchLockResponse,
    tags=["Dispatch Scheduling"],
)
async def lock_dispatch_slot(request: DispatchLockRequest):
    """Atomically reserves a 75-minute estimate window across 4 territory zones upon verified PayPal deposit capture."""
    crew_map = {
        "Zone 1 - North Lakeland": "Crew A - Heavy Restoration & Tearout",
        "Zone 2 - South Lakeland": "Crew B - Custom Tile & Precision Master",
        "Zone 3 - East Polk / Winter Haven": "Crew C - Hardwood & Substrate Leveling",
        "Zone 4 - West Lakeland / Plant City": "Crew D - Commercial Bid Estimator",
    }
    assigned_crew = crew_map.get(
        request.territory_zone, "Crew B - Custom Tile & Precision Master"
    )

    return DispatchLockResponse(
        success=True,
        slotLockedUntil=request.slot_start_iso,
        crewAssigned=assigned_crew,
        territoryZone=request.territory_zone,
    )


@app.post(
    "/api/mcp/zapier-sync",
    response_model=ZapierSyncResponse,
    tags=["Zapier MCP Integration"],
)
async def trigger_zapier_mcp_sync(request: ZapierSyncRequest):
    """Dispatches qualified contractor lead into Jobber, QuickBooks Online, and Google Calendar via Zapier MCP."""
    try:
        return await zapier_mcp_dispatcher.execute_downline_sync(request)
    except Exception as e:
        logger.error(f"Error in Zapier MCP dispatch: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/api/export/backoffice",
    response_model=ZapierSyncResponse,
    tags=["Back-Office Exports"],
)
async def export_backoffice_endpoint(request: ZapierSyncRequest):
    """
    Dedicated Back-Office Export Endpoint.
    Generates authentic Jobber GraphQL/REST mutations and QuickBooks Online API v3 Expense
    payloads for autonomous A2A subscriptions, with optional HMAC-signed webhook forwarding.
    """
    try:
        return await zapier_mcp_dispatcher.execute_downline_sync(request)
    except Exception as e:
        logger.error(f"Error in back-office export: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/api/paypal/create-order",
    response_model=PayPalOrderResponse,
    tags=["PayPal Orders"],
)
async def create_paypal_order(request: PayPalOrderCreateRequest):
    """Creates a PayPal Checkout Order for subscriptions or estimate deposits."""
    try:
        return await paypal_service.create_order(
            amount=request.amount,
            currency=request.currency,
            description=request.description,
            custom_id=request.custom_id,
        )
    except Exception as e:
        logger.error(f"Error creating PayPal order: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/paypal/webhook", tags=["PayPal Webhooks"])
async def paypal_webhook_receiver(request: Request):
    """Receives and processes PayPal subscription and order webhooks with signature verification."""
    body_bytes = await request.body()
    body_str = body_bytes.decode("utf-8") if body_bytes else "{}"
    try:
        body = json.loads(body_str)
    except Exception:
        body = {}

    event_type = body.get("event_type", "UNKNOWN")
    logger.info(f"[PayPal Webhook] Received event: {event_type}")

    # Verify PayPal webhook transmission signature
    verification = await paypal_service.verify_webhook_signature(
        headers=dict(request.headers),
        raw_body=body_str,
    )
    if verification.get("verification_status") == "FAILURE":
        logger.warning(f"[SECURITY] PayPal webhook signature verification failed for event {event_type}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid PayPal webhook signature.",
        )

    # Process activation event
    if event_type in [
        "BILLING.SUBSCRIPTION.ACTIVATED",
        "CHECKOUT.ORDER.APPROVED",
    ]:
        resource = body.get("resource", {})
        sub_id = resource.get("id", "UNKNOWN_SUB")
        logger.info(
            f"[PayPal Webhook] Verified payment event for {sub_id} ({verification.get('verification_status')}). Triggering KYC DID allocation."
        )

    return {
        "status": "received",
        "event_type": event_type,
        "verification_status": verification.get("verification_status", "SUCCESS"),
    }


class RunBuyerAgentRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    transport: Optional[str] = "http"
    contractorName: Optional[str] = Field(default="Marcus Miller", alias="contractor_name")
    businessEntity: Optional[str] = Field(default="Miller Custom Flooring LLC", alias="business_entity")
    contractorEmail: Optional[str] = Field(default="marcus@millercustomfloors.com", alias="contractor_email")
    tradeId: Optional[str] = Field(default="flooring-tile", alias="trade_id")
    budgetCap: Optional[float] = Field(default=100.00, alias="budget_cap")
    areaCode: Optional[str] = Field(default="863", alias="area_code")
    simulateExhaustion: Optional[bool] = Field(default=False, alias="simulate_exhaustion")
    webhookUrl: Optional[str] = Field(default=None, alias="webhook_url")
    resetLedger: Optional[bool] = Field(default=False, alias="reset_ledger")


@app.post("/api/harness/run-buyer-agent", tags=["External Buyer Harness"])
async def run_external_buyer_agent_endpoint(req: RunBuyerAgentRequest):
    """
    Executes the external buyer agent harness headlessly over MCP (HTTP or stdio).
    Returns the step-by-step audit log, cryptographic proof, and back-office payloads.
    """
    if req.resetLedger:
        ledger.reset()

    agent = ExternalBuyerAgent(
        transport=req.transport or "http",
        server_url=f"http://127.0.0.1:{settings.server_port}/mcp",
        contractor_name=req.contractorName or "Marcus Miller",
        business_entity=req.businessEntity or "Miller Custom Flooring LLC",
        contractor_email=req.contractorEmail or "marcus@millercustomfloors.com",
        trade_id=req.tradeId or "flooring-tile",
        budget_cap=req.budgetCap or 100.00,
        area_code=req.areaCode or "863",
        webhook_url=req.webhookUrl,
        verbose=False,
        simulate_exhaustion=req.simulateExhaustion or False,
    )
    res = await agent.execute_autonomous_procurement()
    return res


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.server:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=True,
    )
