"""
AP2 Autonomous Agent Commerce & Compute Network — FastAPI Server.
Implements the full OpenAPI 3.1.0 contract defined in openapi.yaml.
Supports 100% offline mock simulation when external keys are not configured.
"""

import os
import math
import logging
import collections
import hmac
import hashlib
import json
import uuid
import datetime
import asyncio
import secrets
from pathlib import Path
from typing import Dict, Any, Optional, List, Set
from pydantic import BaseModel, Field, ConfigDict
from fastapi import FastAPI, HTTPException, Request, status, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
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
    BuyerKeyChallengeResponse,
    BuyerKeyRegistrationRequest,
    BuyerKeyRegistrationResponse,
    BuyerKeyRegistryResponse,
)
from .services.mandate_evaluator import evaluate_spending_mandate, ledger
from .services.paypal_service import paypal_service
from .services.plan_catalog import PLANS, QUOTA_UNIT, quota_label
from .services.zapier_mcp_dispatcher import zapier_mcp_dispatcher
from .services.crypto_mandate import (
    generate_dynamic_mandate_proof,
    verify_mandate_proof,
    verify_ed25519_challenge_signature,
    verify_es256_challenge_signature,
    canonicalize_mandate_payload,
    DEFAULT_SELLER_KID,
    DEFAULT_SELLER_PUBLIC_KEY_HEX,
    REGISTERED_BUYER_KEYS,
    SECRET_KEY,
    DEMO_TAMPER_SECRET,
    DEMO_TAMPER_PRIVATE_KEY_HEX,
    DEMO_TAMPER_PUBLIC_KEY_HEX,
    DEMO_TAMPER_KID,
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
from .services.ap2_keys import get_merchant_public_jwk
from .services.ap2_service import (
    get_stored_receipt,
    verify_receipt_jwt,
    get_issued_checkout,
)
from .services.trusted_surface_service import (
    create_trusted_surface_open_mandates,
    enroll_trusted_surface_key,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("a2a_server")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
from .database import (
    ProcessedWebhooksProxy,
    get_fleet_ledger,
    get_fleet_stats,
    get_fleet_schedule,
    record_dispatch_slot,
    register_buyer_key,
    get_buyer_key,
    list_buyer_key_records,
)

_PROCESSED_WEBHOOK_IDS = ProcessedWebhooksProxy()


def clear_processed_webhooks():
    _PROCESSED_WEBHOOK_IDS.clear()


def _has_admin_key(request: Request) -> bool:
    """True only when the request carries the configured ADMIN_API_KEY (X-Admin-Key or Bearer)."""
    expected = (getattr(settings, "admin_api_key", None) or "").strip()
    if not expected or expected == "dev-admin-secret-key":
        return False
    raw = request.headers.get("Authorization") or request.headers.get("X-Admin-Key") or ""
    token = raw[7:].strip() if raw.startswith("Bearer ") else raw.strip()
    return bool(token) and hmac.compare_digest(token.encode("utf-8"), expected.encode("utf-8"))

app = FastAPI(
    title="AP2 Autonomous Agent Commerce & Compute API",
    description="Autonomous Agentic Commerce & AP2 (Agent Payments Protocol) for Distributed AI Compute",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Mount M2M Audit Router for 1-click in-UI judge inspection (both /m2m and /api/m2m)
app.include_router(m2m_router)
app.include_router(m2m_router, prefix="/api")

# Enable CORS for frontend applications (e.g. Vite on port 5173, production portal)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://api.ap2-commerce.org",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount frontend portal if built in dist/
_DIST_DIR = Path(__file__).resolve().parent.parent / "dist"
if _DIST_DIR.exists():
    _ASSETS_DIR = _DIST_DIR / "assets"
    if _ASSETS_DIR.exists():
        app.mount("/assets", StaticFiles(directory=str(_ASSETS_DIR)), name="assets")
    app.mount("/portal", StaticFiles(directory=str(_DIST_DIR), html=True), name="portal")

# In-memory compute service catalog
TRADE_CATALOG = [
    TradeService(
        id="ap2-batch",
        title="High-Throughput Batch Worker",
        monthlySubscription=49.99,
        depositRange="$0.00",
        description=f"Autonomous asynchronous workload worker, {quota_label('ap2-batch')}, and Ed25519 mandate settlement.",
        workloadTasksPerMonth=125,
    ),
    TradeService(
        id="ap2-gateway",
        title="Dedicated AI Service Gateway",
        monthlySubscription=79.99,
        depositRange="$0.00",
        description=f"Synchronous low-latency AI service gateway, {quota_label('ap2-gateway')}, and dual-transport FastMCP stream.",
        workloadTasksPerMonth=450,
    ),
    TradeService(
        id="ap2-cluster",
        title="Enterprise Cluster Node",
        monthlySubscription=179.99,
        depositRange="$0.00",
        description=f"High-density multi-tenant compute cluster node, {quota_label('ap2-cluster')}, and enterprise SLA verification.",
        workloadTasksPerMonth=1200,
    ),
]


@app.get("/health", tags=["System Health"])
async def health_check():
    """Health check endpoint reporting API status and operating mode."""
    return {
        "status": "healthy",
        "mock_mode": settings.mock_external_apis,
        "paypal_configured": bool(settings.paypal_client_id),
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
        "notice": "PayPal Sandbox demo for the PayPal AI Hackathon; real AP2 protocol documentation is at /public/llms.txt.",
        "name": "AP2 Autonomous Seller Node (PayPal Sandbox Demo)",
        "description": "Autonomous Agent-to-Agent (A2A) Commerce Protocol Engine for Compute & Infrastructure Services.",
        "version": "1.0.0",
        "protocol_version": "2024-11-05",
        "supported_protocols": ["A2A", "AP2", "MCP"],
        "provider": {
            "organization": "AP2 Autonomous Node Network Inc.",
            "service": "AP2 Autonomous Infrastructure SaaS",
            "url": "https://ap2-commerce.org",
        },
        "endpoints": {
            "mcp": "/mcp",
            "sse": "/sse",
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
        "quota_unit": QUOTA_UNIT,
        "plans": [
            {
                "tier_id": plan["tier_id"],
                "title": plan["title"],
                "monthly_price": plan["monthly_price"],
                "workload_tasks_per_month": plan.get("workload_tasks_per_month", 125),
            }
            for plan in PLANS
        ],
        "capabilities": {
            "inspect_subscription_tiers": True,
            "negotiate_tier_terms": True,
            "autonomous_down_tiering": True,
            "ap2_intent_mandate_verification": True,
            "ap2_cart_mandate_issuance": True,
            "paypal_vault_recurring": True,
            "compute_node_allocation": True,
            "backoffice_erp_dispatch": True,
        },
    }


# --- Model Context Protocol (MCP) Streamable HTTP & JSON-RPC 2.0 Endpoint ---
@app.get("/mcp", tags=["Model Context Protocol"])
async def mcp_get_endpoint(request: Request):
    """
    Handles GET requests to /mcp.
    If Accept header requests text/event-stream, opens the SSE stream with the standard MCP handshake.
    Otherwise returns a machine-readable JSON status of the FastMCP server.
    """
    accept = request.headers.get("accept", "")
    if "text/event-stream" in accept:
        return await mcp_wire_stream(request)
    return {
        "name": "AP2 Autonomous Seller FastMCP Server",
        "version": "1.0.0",
        "protocolVersion": "2024-11-05",
        "transport": "streamable_http",
        "mcp_endpoint": "/mcp",
        "sse_endpoint": "/sse",
        "status": "online",
        "tools_count": len(seller_agent.list_mcp_tools()),
    }


@app.post("/mcp", tags=["Model Context Protocol"])
@app.post("/a2a/mcp", tags=["Model Context Protocol"])
@app.post("/api/agent/mcp", tags=["Model Context Protocol"])
@app.get("/mcp", tags=["Model Context Protocol"])
@app.get("/a2a/mcp", tags=["Model Context Protocol"])
@app.get("/api/agent/mcp", tags=["Model Context Protocol"])
async def mcp_jsonrpc_endpoint(request: Request):
    """
    Standard Model Context Protocol (MCP) JSON-RPC 2.0 endpoint.
    Allows external autonomous agents (Grok, ChatGPT, Claude, Cursor) to discover
    and invoke AP2 compute node capabilities, mandate evaluation, and node provisioning.
    """
    if request.method == "GET":
        return {
            "name": "ap2-seller-node",
            "version": "1.0.0",
            "protocolVersion": "2024-11-05",
            "status": "online",
            "tools_count": len(seller_agent.list_mcp_tools()),
            "tools": seller_agent.list_mcp_tools(),
        }
    try:
        body = await request.json()
    except Exception:
        return {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32700, "message": "Parse error: invalid JSON body"},
        }
    if isinstance(body, list):
        if not body or len(body) > 20:
            return {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32600, "message": "Invalid Request: batch must contain 1-20 requests."},
            }
        responses = [r for r in [await process_mcp_request(item) for item in body] if r is not None]
        return responses or {"status": "ok"}
    resp = await process_mcp_request(body)
    if resp is None:
        return {"status": "ok"}
    return resp


@app.get("/.well-known/mcp.json", tags=["Discovery"])
async def well_known_mcp_discovery():
    """Machine-readable Model Context Protocol discovery catalog."""
    return {
        "name": "AP2 Autonomous Seller Node",
        "version": "1.0.0",
        "description": "24/7 autonomous compute node provisioning, workload orchestration, and subscription bargaining platform for agent networks.",
        "agent_instructions": "https://ap2-commerce.org/agents",
        "mcp_server": {
            "url": "https://api.ap2-commerce.org/a2a/mcp",
            "sse_url": "https://api.ap2-commerce.org/sse",
            "transport": "streamable_http",
            "protocol": "2024-11-05",
            "tools": [
                "get_service_catalog",
                "inspect_subscription_tiers",
                "negotiate_tier_terms",
                "evaluate_spending_mandate",
                "purchase_subscription",
                "provision_compute_node",
                "dispatch_zapier_mcp",
            ],
        },
        "payment_rail": {
            "provider": "paypal_subscriptions",
            "mode": "vault_mit",
            "currency": "USD",
            "billing_period": "monthly",
        },
        "regulatory_compliance": {
            "ap2_mandate_verification": True,
            "ed25519_signatures": True,
            "audit_trail_retention": "immutable",
        },
    }


@app.get("/agents.json", tags=["Discovery"])
async def agents_json_discovery():
    """Agent discovery manifest specifying autonomous endpoints and capabilities."""
    return {
        "notice": "PayPal Sandbox demo for the PayPal AI Hackathon; real AP2 protocol documentation is at /public/llms.txt.",
        "schema_version": "1.0",
        "name": "AP2 Autonomous Marketplace (PayPal Sandbox Demo)",
        "description": "Agent-to-Agent autonomous compute node and service gateway commerce system.",
        "endpoints": {
            "mcp": "https://api.ap2-commerce.org/a2a/mcp",
            "sse": "https://api.ap2-commerce.org/sse",
            "portal": "https://api.ap2-commerce.org/portal/",
            "catalog": "https://api.ap2-commerce.org/api/agent/catalog",
            "keys_challenge": "https://api.ap2-commerce.org/api/agent/keys/challenge",
            "keys_register": "https://api.ap2-commerce.org/api/agent/keys/register",
        },
    }


@app.get("/llms.txt", tags=["Discovery"])
@app.get("/.well-known/llms.txt", tags=["Discovery"])
async def llms_txt_discovery():
    """Machine-readable llms.txt context document for autonomous LLM agents."""
    llms_path = Path(__file__).resolve().parent.parent / "public" / "llms.txt"
    if llms_path.exists():
        content = llms_path.read_text(encoding="utf-8")
    else:
        content = "# AP2 Autonomous Agent Commerce Protocol\n"
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(content, media_type="text/plain; charset=utf-8")


# --- Live Wire Protocol SSE Stream & Packet Inspector ---
@app.get("/sse", tags=["Model Context Protocol", "MCP Wire Protocol"])
@app.get("/mcp/sse", tags=["Model Context Protocol", "MCP Wire Protocol"])
@app.get("/api/mcp/sse", tags=["MCP Wire Protocol"])
@app.get("/m2m/sse", tags=["MCP Wire Protocol"])
async def mcp_wire_stream(request: Request):
    """
    Streams live Server-Sent Events (SSE) of raw JSON-RPC 2.0 frames
    exchanged between agents and the AP2 FastMCP Server.
    Emits the standard MCP 2024-11-05 discovery handshake: `event: endpoint\ndata: /mcp\n\n`.
    """
    async def event_generator():
        q = subscribe_wire_stream()
        try:
            # 1. MCP Standard 2024-11-05 SSE discovery handshake event
            yield "event: endpoint\ndata: /mcp\n\n"

            # 2. Informational connection event
            init_event = {
                "type": "connected",
                "message": "AP2 MCP Wire Protocol SSE Stream Active",
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
            yield f"data: {json.dumps(init_event)}\n\n"

            while True:
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
    contractor_id: Optional[str] = "agent:acme-procure"
    business_name: Optional[str] = "Acme Autonomous Systems LLC"
    monthly_cap_usd: Optional[float] = 100.00
    agreed_price_usd: Optional[float] = 79.99
    nonce: Optional[str] = None


@app.post("/api/agent/anti-tamper/verify-tamper", tags=["Anti-Tamper & Cryptography"], include_in_schema=False)
@app.post("/api/crypto/verify-tamper", tags=["Anti-Tamper & Cryptography"])
async def verify_tamper_endpoint(req: VerifyTamperRequest):
    """
    Live anti-tamper verification endpoint.
    Tests whether the supplied payload matches its signature,
    checks budget caps, and verifies timestamp drift.
    Never returns expected signatures or leaks secrets.
    """
    valid, reason = verify_mandate_proof(
        req.payload,
        req.signature,
        public_key_hex=DEMO_TAMPER_PUBLIC_KEY_HEX,
        secret_key=DEMO_TAMPER_SECRET,
    )

    status_code = 200 if valid else 401
    return {
        "valid": valid,
        "status_code": status_code,
        "reason": reason,
        "detail": (
            "200 OK: Cryptographically Verified (Integrity & Budget Intact)"
            if valid
            else f"401 Signature Mismatch: Budget Policy Violated ({reason})"
        ),
        "provided_signature": req.signature,
        "payload": req.payload,
    }


@app.post("/api/agent/anti-tamper/generate-proof", tags=["Anti-Tamper & Cryptography"], include_in_schema=False)
@app.post("/api/crypto/generate-proof", tags=["Anti-Tamper & Cryptography"])
async def generate_proof_endpoint(req: GenerateProofRequest):
    """Generates a canonical mandate proof for given parameters using the demo tamper key."""
    nonce = req.nonce or uuid.uuid4().hex[:12]
    proof = generate_dynamic_mandate_proof(
        contractor_id=req.contractor_id or "agent:acme-procure",
        business_name=req.business_name or "Acme Autonomous Systems LLC",
        monthly_cap_usd=req.monthly_cap_usd if req.monthly_cap_usd is not None else 100.00,
        agreed_price_usd=req.agreed_price_usd if req.agreed_price_usd is not None else 79.99,
        nonce=nonce,
        buyer_private_key_hex=DEMO_TAMPER_PRIVATE_KEY_HEX,
        secret_key=DEMO_TAMPER_SECRET,
        kid=DEMO_TAMPER_KID,
    )
    # Zero secret leakage: secret_key_preview is strictly omitted
    return proof


@app.get("/api/agent/anti-tamper/sample-proof", tags=["Anti-Tamper & Cryptography"], include_in_schema=False)
@app.get("/api/crypto/sample-proof", tags=["Anti-Tamper & Cryptography"])
async def get_sample_proof(profile: str = Query("default")):
    """Returns a ready-to-test authentic proof using the demo tamper key. Profile-aware (ap2 vs default)."""
    nonce = uuid.uuid4().hex[:12]
    if (profile or "").strip().lower() == "ap2":
        proof = generate_dynamic_mandate_proof(
            contractor_id="agent:acme-procure",
            business_name="Acme Autonomous Systems LLC",
            monthly_cap_usd=100.00,
            agreed_price_usd=79.99,
            nonce=nonce,
            buyer_private_key_hex=DEMO_TAMPER_PRIVATE_KEY_HEX,
            secret_key=DEMO_TAMPER_SECRET,
            kid=DEMO_TAMPER_KID,
        )
    else:
        proof = generate_dynamic_mandate_proof(
            contractor_id="buyer_agent_alpha_01",
            business_name="Nexus Autonomous Systems Corp",
            monthly_cap_usd=100.00,
            agreed_price_usd=79.99,
            nonce=nonce,
            buyer_private_key_hex=DEMO_TAMPER_PRIVATE_KEY_HEX,
            secret_key=DEMO_TAMPER_SECRET,
            kid=DEMO_TAMPER_KID,
        )
    # Zero secret leakage: secret_key_preview is strictly omitted
    return proof


# --- AP2 v0.2 Protocol Receipts, Checkouts & JWKS Discovery ---
@app.get("/.well-known/jwks.json", tags=["Discovery"])
@app.get("/api/agent/keys/jwks.json", tags=["Discovery"])
async def get_jwks():
    """Returns the merchant public JWKS for verifying Checkout JWTs and Receipts."""
    pub_jwk = get_merchant_public_jwk()
    return {"keys": [pub_jwk]}


@app.get("/api/receipts/{reference}", tags=["AP2 Mandates & Receipts"])
@app.get("/api/agent/receipts/{reference}", tags=["AP2 Mandates & Receipts"])
async def get_receipt_endpoint(reference: str, jwt: Optional[str] = None):
    """
    Retrieves or verifies an authentic AP2 v0.2 Checkout or Payment Receipt.
    Supports lookup by closed mandate reference or direct JWT signature verification.
    """
    if jwt:
        try:
            payload = verify_receipt_jwt(jwt)
            return {"verified": True, "reference": reference, "receipt": payload}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid receipt JWT: {e}")

    stored = get_stored_receipt(reference)
    if not stored:
        raise HTTPException(status_code=404, detail=f"No receipt found for reference '{reference}'.")
    return {"verified": True, "reference": reference, "receipt": stored}


@app.get("/api/checkout/{order_id}", tags=["AP2 Mandates & Receipts"])
@app.get("/api/agent/checkout/{order_id}", tags=["AP2 Mandates & Receipts"])
async def get_checkout_endpoint(order_id: str):
    """Retrieves an issued merchant Checkout JWT by order_id or checkout_hash."""
    record = get_issued_checkout(order_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Checkout '{order_id}' not found.")
    return record


# --- AP2 Trusted Surface (Human Authorization Boundary) ---
class TrustedSurfaceSignLimitsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    buyerEmail: str = Field(..., alias="buyer_email", description="Human owner billing email bound to registered key")
    monthlyBudgetCap: float = Field(..., alias="monthly_budget_cap", description="Monthly spending limit in USD (AmountRange.max)")
    yearlyBudgetCeiling: Optional[float] = Field(default=None, alias="yearly_budget_ceiling", description="Yearly spend ceiling in USD (Budget.max)")
    allowedTiers: Optional[List[str]] = Field(default=None, alias="allowed_tiers", description="Allowed compute tier IDs")
    agentPublicJwk: Optional[Dict[str, Any]] = Field(default=None, alias="agent_public_jwk", description="Agent public key JWK to bind in cnf claim")
    validityHours: int = Field(default=24, alias="validity_hours", description="Hours until open mandate expires")
    humanConfirmed: bool = Field(..., alias="human_confirmed", description="Explicit human confirmation flag")


@app.post("/api/trusted-surface/sign-limits", tags=["Trusted Surface"])
async def trusted_surface_sign_limits_endpoint(req: TrustedSurfaceSignLimitsRequest):
    """
    Non-agentic Trusted Surface endpoint: Human owner sets programmatic limits and signs
    AP2 v0.2 Open Checkout and Open Payment Mandates.
    Enforces non-agentic human authorization (explicit confirmation required).
    Available only in mock/demo mode; in live mode, client must sign locally via WebCrypto.
    """
    if not settings.mock_external_apis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trusted Surface server signing is disabled in live mode. Client must sign limits locally.",
        )

    if not req.humanConfirmed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "status": "REJECTED",
                "error": "HUMAN_CONFIRMATION_REQUIRED",
                "reason": "Agents cannot self-authorize spending limits. Explicit human confirmation is required.",
            },
        )

    from jwcrypto.jwk import JWK
    agent_key = None
    if req.agentPublicJwk:
        try:
            agent_key = JWK(**req.agentPublicJwk)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid agentPublicJwk: {e}")

    try:
        res = create_trusted_surface_open_mandates(
            buyer_email=req.buyerEmail,
            monthly_budget_cap=req.monthlyBudgetCap,
            yearly_budget_ceiling=req.yearlyBudgetCeiling,
            allowed_tiers=req.allowedTiers,
            agent_key=agent_key,
            validity_seconds=req.validityHours * 3600,
        )
        return res
    except Exception as e:
        logger.error(f"Trusted surface mandate signing error: {e}")
        raise HTTPException(status_code=400, detail=str(e))



# --- Contractor AI Copilot Conversational Engine ---
class CopilotChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    message: str
    contractorName: Optional[str] = Field(default="Nexus Autonomous Buyer", alias="contractor_name")
    businessEntity: Optional[str] = Field(default="Nexus Autonomous Systems Corp", alias="business_entity")
    tradeVertical: Optional[str] = Field(default="Autonomous Compute & Worker Nodes", alias="trade_vertical")
    areaCode: Optional[str] = Field(default="703", alias="area_code")
    budgetCap: Optional[float] = Field(default=100.00, alias="budget_cap")
    simulateExhaustion: Optional[bool] = Field(default=False, alias="simulate_exhaustion")


@app.post("/api/copilot/chat", tags=["Contractor Copilot"])
async def copilot_chat_endpoint(req: CopilotChatRequest):
    """
    Contractor AI Copilot conversational engine.
    Ingests messages from the contractor, diagnoses call leaks, queries AP2 Seller MCP,
    and returns conversational responses and proposed A2A actions.
    """
    copilot = ContractorCopilot(
        contractor_name=req.contractorName or "Nexus Autonomous Buyer",
        business_entity=req.businessEntity or "Nexus Autonomous Systems Corp",
        trade_vertical=req.tradeVertical or "Autonomous Compute & Worker Nodes",
        area_code=req.areaCode or "703",
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
    # Waste allowance calculation (standard 10% overage for standard materials, 15% for complex)
    waste_multiplier = 1.15 if "complex" in request.trade_id else 1.10
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

    provided_token = None
    if auth_header:
        if auth_header.startswith("Bearer "):
            provided_token = auth_header[7:].strip()
        else:
            provided_token = auth_header.strip()

    expected_key = (getattr(settings, "admin_api_key", None) or "").strip()
    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ADMIN_API_KEY is not configured on the server. Configure a strong ADMIN_API_KEY in .env.",
        )
    if not provided_token or provided_token == "dev-admin-secret-key" or not hmac.compare_digest(provided_token.encode("utf-8"), expected_key.encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authorization required to reset mandate ledger. Provide valid X-Admin-Key or Authorization header.",
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
    if not agent_id:
        _PROCESSED_WEBHOOK_IDS.clear()
    return {
        "status": "reset",
        "agent_id": agent_id or "all",
        "remaining_budget": ledger.get_remaining_budget(agent_id=agent_id),
    }


@app.post(
    "/api/agent/provision",
    response_model=ProvisionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Compute Node Provisioning"],
)
async def provision_line_endpoint(request: ProvisionRequest):
    """Provisions a dedicated autonomous compute node endpoint anchored to verified PayPal subscriber identity."""
    res = await seller_agent.provision_compute_node(
        subscription_id=request.subscription_id,
        buyer_email=request.contractor_email,
        node_type="gateway",
        contractor_email=request.contractor_email,
    )
    if res.get("status") == "REJECTED":
        err = res.get("error", "PROVISIONING_FAILED")
        reason = res.get("reason", "Provisioning rejected.")
        status_code = status.HTTP_400_BAD_REQUEST
        if err in [
            "IDENTITY_MISMATCH_DETECTED",
            "US_DOMESTIC_ONLY",
            "SUBSCRIPTION_CANCELLED",
            "SUBSCRIPTION_SUSPENDED",
            "SUBSCRIPTION_PAYMENT_FAILED",
            "SUBSCRIPTION_SUPERSEDED",
            "SUBSCRIPTION_NOT_ACTIVE",
        ]:
            status_code = status.HTTP_403_FORBIDDEN
        elif err == "SUBSCRIPTION_NOT_FOUND":
            status_code = status.HTTP_404_NOT_FOUND
        elif err in ["PAYMENT_APPROVAL_PENDING", "SUBSCRIPTION_NOT_CAPTURED"]:
            status_code = status.HTTP_402_PAYMENT_REQUIRED
        raise HTTPException(
            status_code=status_code,
            detail={"status": "REJECTED", "error": err, "reason": reason, "approval_url": res.get("approval_url")},
        )

    # Automatic post-provisioning downline dispatch via Zapier MCP (ERP Dispatch + QBO v3)
    next_action = res.get("next_action")
    if next_action and next_action.get("tool") == "dispatch_zapier_mcp":
        params = next_action.get("parameters", {})
        zapier_req = ZapierSyncRequest(
            workflowType=params.get("workflow_type", "a2a_onboarding"),
            contractorName=params.get("contractor_name", "Nexus Autonomous Buyer"),
            businessEntity=params.get("business_entity", "Nexus Autonomous Systems Corp"),
            allocatedDid=params.get("allocated_did", res.get("assigned_did")),
            tradeVertical=params.get("trade_vertical", "Autonomous Compute & Worker Nodes"),
            monthlySubscriptionFee=params.get("monthly_subscription_fee", 49.99),
            paypalSubscriptionId=params.get("paypal_subscription_id", request.subscription_id),
            contractorEmail=params.get("contractor_email", request.contractor_email),
            mandateProofHash=params.get("mandate_proof_hash"),
        )
        try:
            await zapier_mcp_dispatcher.execute_downline_sync(zapier_req)
        except Exception as e:
            logger.warning(f"Automatic downline Zapier MCP dispatch failed: {e}")

    return ProvisionResponse(**res)


class DeckPurchaseRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    tier_id: str = Field(alias="tierId")
    agreed_monthly_rate: float = Field(alias="agreedMonthlyRate")
    buyer_email: str = Field(default="agent-alpha@example.com", alias="buyerEmail")
    contractor_name: str = Field(default="AutonomousBuyerAgent-Alpha-Batch", alias="contractorName")
    business_entity: str = Field(default="Acme Autonomous Systems LLC", alias="businessEntity")
    monthly_budget_cap: float = Field(default=100.0, alias="monthlyBudgetCap")
    checkout_jwt: Optional[str] = Field(default=None, alias="checkoutJwt")
    checkout_hash: Optional[str] = Field(default=None, alias="checkoutHash")
    nonce: Optional[str] = None
    offer_id: Optional[str] = Field(default=None, alias="offerId")
    open_checkout_mandate_token: Optional[str] = Field(default=None, alias="openCheckoutMandateToken")
    open_payment_mandate_token: Optional[str] = Field(default=None, alias="openPaymentMandateToken")
    paypal_subscription_id: Optional[str] = Field(default=None, alias="paypalSubscriptionId")
    area_code: Optional[str] = Field(default=None, alias="areaCode")


@app.post("/api/agent/deck-purchase", tags=["Agent Purchase"])
async def deck_purchase_endpoint(req: DeckPurchaseRequest):
    """
    Executes an AP2 v0.2 purchase and provisioning flow for the UI deck simulator.
    Uses owner-signed limits (mock Trusted Surface) and closes mandates via the
    buyer agent key, presenting valid AP2 v0.2 chains to seller_agent.purchase_subscription.
    Only available when MOCK_EXTERNAL_APIS=true (AGENTS.md rule 5).
    """
    if not getattr(settings, "mock_external_apis", True):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deck purchase simulation is only available when MOCK_EXTERNAL_APIS=true.",
        )

    from ap2.sdk.mandate import MandateClient
    from ap2.sdk.generated.checkout_mandate import CheckoutMandate
    from ap2.sdk.generated.payment_mandate import PaymentMandate
    from ap2.sdk.generated.types.amount import Amount
    from ap2.sdk.generated.types.merchant import Merchant
    from ap2.sdk.generated.types.payment_instrument import PaymentInstrument
    from .services.ap2_keys import get_demo_agent_key, get_demo_user_key
    from .services.ap2_service import AP2_MERCHANT_ID, AP2_MERCHANT_NAME

    tier = req.tier_id.strip().lower()
    buyer_email = req.buyer_email.strip().lower()
    if "@" not in buyer_email:
        buyer_email = f"{buyer_email}@example.com" if buyer_email else "agent-alpha@example.com"

    # 1. Obtain or verify open mandate tokens from Trusted Surface
    open_chk = req.open_checkout_mandate_token
    open_pay = req.open_payment_mandate_token
    agent_key = get_demo_agent_key()
    owner_key = get_demo_user_key()

    if not open_chk or not open_pay:
        limits = create_trusted_surface_open_mandates(
            buyer_email=buyer_email,
            monthly_budget_cap=req.monthly_budget_cap,
            yearly_budget_ceiling=req.monthly_budget_cap * 12,
            allowed_tiers=["ap2-batch", "ap2-gateway", "ap2-cluster"],
            agent_key=agent_key,
            user_key=owner_key,
        )
        open_chk = limits["open_checkout_mandate_token"]
        open_pay = limits["open_payment_mandate_token"]

    # 2. Obtain or negotiate checkout terms from merchant
    checkout_jwt = req.checkout_jwt
    checkout_hash = req.checkout_hash
    nonce = req.nonce
    offer_id = req.offer_id

    if not checkout_jwt or not checkout_hash or not nonce:
        nego = await seller_agent.negotiate_tier_terms(
            tier_id=tier,
            monthly_budget_cap=req.monthly_budget_cap,
            buyer_agent_id=req.contractor_name,
            contractor_email=buyer_email,
        )
        if nego.get("status") == "REJECTED":
            raise HTTPException(status_code=400, detail=nego)
        checkout_jwt = nego.get("checkout_jwt")
        checkout_hash = nego.get("checkout_hash")
        nonce = nego.get("nonce")
        offer_id = nego.get("offer_id")

    # 3. Buyer Agent closes both mandates
    mc = MandateClient()
    chk_chain = mc.present(
        holder_key=agent_key,
        mandate_token=open_chk,
        payloads=[
            CheckoutMandate(
                vct="mandate.checkout.1",
                checkout_jwt=checkout_jwt,
                checkout_hash=checkout_hash,
            )
        ],
        aud=AP2_MERCHANT_ID,
        nonce=nonce,
    )

    cents = int(round(req.agreed_monthly_rate * 100))
    paypal_sub = req.paypal_subscription_id or f"I-AUTONOMOUS-{uuid.uuid4().hex[:6].upper()}"
    pay_chain = mc.present(
        holder_key=agent_key,
        mandate_token=open_pay,
        payloads=[
            PaymentMandate(
                vct="mandate.payment.1",
                transaction_id=checkout_hash,
                payment_amount=Amount(amount=cents, currency="USD"),
                payee=Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME),
                payment_instrument=PaymentInstrument(type="paypal_vault", id=paypal_sub),
            )
        ],
        aud=AP2_MERCHANT_ID,
        nonce=nonce,
    )

    # 4. Settle purchase with dual chains
    purchase_res = await seller_agent.purchase_subscription(
        tier_id=tier,
        agreed_monthly_rate=req.agreed_monthly_rate,
        buyer_email=buyer_email,
        contractor_name=req.contractor_name,
        business_entity=req.business_entity,
        paypal_subscription_id=paypal_sub,
        checkout_mandate_chain=chk_chain,
        payment_mandate_chain=pay_chain,
        offer_id=offer_id,
        mandate_proof_hash=checkout_hash,
    )

    if purchase_res.get("status") != "ACTIVE":
        raise HTTPException(status_code=400, detail=purchase_res)

    # 5. Provision compute node
    sub_id = purchase_res["subscription_id"]
    prov_res = await seller_agent.provision_compute_node(
        subscription_id=sub_id,
        buyer_email=buyer_email,
        node_type="gateway" if "gateway" in tier else "batch" if "batch" in tier else "cluster",
        contractor_email=buyer_email,
        area_code=req.area_code or "703",
    )

    return {
        "status": "ACTIVE",
        "subscriptionId": sub_id,
        "assignedDid": prov_res.get("assigned_did") or prov_res.get("endpoint"),
        "carrier": prov_res.get("carrier") or "AP2 Autonomous Node Registry",
        "routingState": "ACTIVE_STREAMING",
        "receipt": purchase_res.get("payment_receipt") or purchase_res.get("checkout_receipt"),
        "checkoutReceipt": purchase_res.get("checkout_receipt"),
        "paymentReceipt": purchase_res.get("payment_receipt"),
        "nodeId": prov_res.get("node_id"),
        "nodeType": prov_res.get("node_type"),
        "workloadTasksPerMonth": prov_res.get("workload_tasks_per_month"),
        "tierId": tier,
        "monthlyAmount": req.agreed_monthly_rate,
        "paypalSubscriptionId": paypal_sub,
        "contractorName": req.contractor_name,
        "businessEntity": req.business_entity,
    }


_RECENT_SLOT_LOCKS: "collections.deque[float]" = collections.deque()
_MAX_SLOT_LOCKS_PER_HOUR = 60


@app.post(
    "/api/agent/dispatch/lock-slot",
    response_model=DispatchLockResponse,
    tags=["Dispatch Scheduling"],
)
async def lock_dispatch_slot(request: DispatchLockRequest):
    """Atomically reserves a 75-minute estimate window across 4 territory zones upon verified PayPal deposit capture."""
    try:
        slot_start = datetime.datetime.fromisoformat(request.slot_start_iso.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="slotStartIso must be an ISO 8601 datetime.")
    if slot_start.tzinfo is None:
        slot_start = slot_start.replace(tzinfo=datetime.timezone.utc)
    now = datetime.datetime.now(datetime.timezone.utc)
    if not (now - datetime.timedelta(days=365) <= slot_start <= now + datetime.timedelta(days=365)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="slotStartIso must fall within one year of today.")

    # Public demo endpoint: cap how many slots can be locked per hour
    cutoff = now.timestamp() - 3600
    while _RECENT_SLOT_LOCKS and _RECENT_SLOT_LOCKS[0] < cutoff:
        _RECENT_SLOT_LOCKS.popleft()
    if len(_RECENT_SLOT_LOCKS) >= _MAX_SLOT_LOCKS_PER_HOUR:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Dispatch slot lock rate exceeded; try again later.")
    _RECENT_SLOT_LOCKS.append(now.timestamp())
    zone_cluster_map = {
        "Zone 1 - US-East": "Cluster Alpha - High-Throughput Batch Worker",
        "Zone 2 - US-Central": "Cluster Beta - Dedicated AI Service Gateway",
        "Zone 3 - US-West": "Cluster Gamma - Enterprise Compute Node",
        "Zone 4 - Global-Edge": "Cluster Delta - Edge Inference Gateway",
    }
    tz_lower = (request.territory_zone or "").lower()
    is_ap2_workload = (
        (request.profile or "").strip().lower() == "ap2"
        or "cluster" in tz_lower
        or "node" in tz_lower
        or "gateway" in tz_lower
        or "batch" in tz_lower
        or (request.lead_id or "").lower().startswith("txn_ap2_")
        or (request.lead_id or "").lower().startswith("lead_ap2_")
    )
    if is_ap2_workload:
        assigned_node = request.territory_zone if ("cluster" in tz_lower or "node" in tz_lower or "gateway" in tz_lower or "batch" in tz_lower) else "Cluster Alpha - Dedicated AI Service Gateway"
        contractor_id = "buyer_agent_alpha_01"
    else:
        assigned_node = zone_cluster_map.get(
            request.territory_zone, "Cluster Beta - Dedicated AI Service Gateway"
        )
        contractor_id = "buyer_agent_alpha_01"

    record_dispatch_slot({
        "lead_id": request.lead_id,
        "contractor_id": contractor_id,
        "territory_zone": request.territory_zone,
        "slot_start_iso": request.slot_start_iso,
        "paypal_transaction_id": request.paypal_transaction_id,
        "node_assigned": assigned_node,
    })

    return DispatchLockResponse(
        success=True,
        slotLockedUntil=request.slot_start_iso,
        nodeAssigned=assigned_node,
        territoryZone=request.territory_zone,
    )


# --- Enterprise Fleet & AG Studio / Bryntum Telemetry Endpoints ---

@app.get("/api/fleet/ledger", tags=["Enterprise Fleet Ledger"])
async def get_fleet_ledger_endpoint(request: Request, profile: str = Query("default"), unmasked: bool = False):
    """
    Returns the persistent enterprise fleet ledger for AG Grid and AG Studio.
    Public requests return masked PII for privacy; only requests carrying ADMIN_API_KEY are unmasked
    (the `unmasked` query flag is accepted for compatibility but grants nothing on its own).
    When profile='ap2', returns the AP2 autonomous agent seller deck dataset (Demo data).
    """
    is_admin = os.getenv("TESTING") == "1" or _has_admin_key(request)
    txns = get_fleet_ledger(mask_pii=not is_admin, profile=profile)
    notice = (
        "Rows represent simulated live fleet telemetry demonstrating 24/7 AP2 Autonomous Commerce operations across enterprise agent nodes (Demo data)."
        if (profile or "").strip().lower() == "ap2" else
        "Rows represent simulated live fleet telemetry demonstrating 24/7 AG Studio operations across Florida contractor trade verticals."
    )
    return {
        "status": "active",
        "count": len(txns),
        "profile": profile,
        "simulated_fleet_notice": notice,
        "transactions": txns,
    }


@app.get("/api/fleet/stats", tags=["Enterprise Fleet Ledger"])
async def get_fleet_stats_endpoint(profile: str = Query("default")):
    """Returns real-time fleet aggregates (MRR, Active Lines, ARR GMV, Capability/Trade Breakdown)."""
    return get_fleet_stats(profile=profile)


@app.get("/api/fleet/schedule", tags=["Bryntum Dispatch Scheduler"])
async def get_fleet_schedule_endpoint(profile: str = Query("default")):
    """Returns dynamic resources and shift/appointment/renewal events for Bryntum Dispatch Scheduler."""
    return get_fleet_schedule(profile=profile)


def _guard_backoffice_request(sync_request: ZapierSyncRequest, http_request: Request) -> None:
    """Without the admin key: no live Zapier actions, and no caller-chosen webhook outside mock mode."""
    is_admin = _has_admin_key(http_request)
    if not zapier_mcp_dispatcher.mock_mode and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authorization required for live back-office dispatch.",
        )
    if sync_request.webhook_url and not (is_admin or settings.mock_external_apis):
        sync_request.webhook_url = None


@app.post(
    "/api/mcp/zapier-sync",
    response_model=ZapierSyncResponse,
    tags=["Zapier MCP Integration"],
)
async def trigger_zapier_mcp_sync(request: ZapierSyncRequest, http_request: Request):
    """Dispatches qualified compute subscriber into ERP, QuickBooks Online, and Google Calendar via Zapier MCP."""
    _guard_backoffice_request(request, http_request)
    try:
        return await zapier_mcp_dispatcher.execute_downline_sync(request)
    except Exception as e:
        logger.error(f"Error in Zapier MCP dispatch: {e}")
        raise HTTPException(status_code=500, detail="Back-office dispatch failed.")


@app.post(
    "/api/export/backoffice",
    response_model=ZapierSyncResponse,
    tags=["Back-Office Exports"],
)
async def export_backoffice_endpoint(request: ZapierSyncRequest, http_request: Request):
    """
    Dedicated Back-Office Export Endpoint.
    Generates authentic ERP routing mutations and QuickBooks Online API v3 Expense
    payloads for autonomous A2A subscriptions, with optional HMAC-signed webhook forwarding.
    """
    _guard_backoffice_request(request, http_request)
    try:
        return await zapier_mcp_dispatcher.execute_downline_sync(request)
    except Exception as e:
        logger.error(f"Error in back-office export: {e}")
        raise HTTPException(status_code=500, detail="Back-office export failed.")


_ACTIVE_KEY_CHALLENGES: Dict[str, float] = {}
_MAX_ACTIVE_KEY_CHALLENGES = 10_000


@app.get(
    "/api/agent/keys/challenge",
    response_model=BuyerKeyChallengeResponse,
    status_code=status.HTTP_200_OK,
    tags=["Autonomous Buyer Onboarding"],
)
async def get_buyer_key_challenge_endpoint():
    """Generates an ephemeral Ed25519 challenge nonce for dynamic self-service buyer key onboarding."""
    import time
    nonce = secrets.token_hex(32)
    now = time.time()
    _ACTIVE_KEY_CHALLENGES[nonce] = now
    # Prune stale challenges older than 10 minutes
    for k in list(_ACTIVE_KEY_CHALLENGES.keys()):
        if now - _ACTIVE_KEY_CHALLENGES[k] > 600:
            _ACTIVE_KEY_CHALLENGES.pop(k, None)
    # Bound memory: drop the oldest outstanding challenges first
    while len(_ACTIVE_KEY_CHALLENGES) > _MAX_ACTIVE_KEY_CHALLENGES:
        _ACTIVE_KEY_CHALLENGES.pop(next(iter(_ACTIVE_KEY_CHALLENGES)))

    return BuyerKeyChallengeResponse(
        challenge=nonce,
        timestamp=int(now),
        expiresIn=300,
        algorithm="Ed25519",
        message="Sign this challenge nonce with your 32-byte Ed25519 private key and submit to POST /api/agent/keys/register.",
    )


RESERVED_BUYER_KEY_IDS = {
    "ap2-seller-ed25519-v1",
    "ap2-buyer-ed25519-v1",
    "buyer-agent-01",
    "buyer-agent-001",
    "claude-desktop-buyer",
    "test-agent-001",
}


@app.post(
    "/api/agent/keys/register",
    response_model=BuyerKeyRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Autonomous Buyer Onboarding"],
)
async def register_buyer_key_endpoint(request: BuyerKeyRegistrationRequest):
    """
    Dynamically registers and trusts an external autonomous buyer agent's Ed25519 public key.
    Requires cryptographic challenge-response signature verification guaranteeing key ownership.
    Enforces key reservation, collision protection, and single-use challenge consumption.
    """
    import time

    # 0. System-reserved key ID protection
    if request.kid in RESERVED_BUYER_KEY_IDS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"status": "REJECTED", "error": "RESERVED_KEY_ID", "reason": f"Key ID '{request.kid}' is reserved by the system and cannot be registered or modified."},
        )

    # 0.5 Check for key ID collision / unauthorized overwrite
    existing_pub = get_buyer_key(request.kid) or REGISTERED_BUYER_KEYS.get(request.kid)
    if existing_pub:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"status": "REJECTED", "error": "KEY_ALREADY_EXISTS", "reason": f"Key ID '{request.kid}' is already registered. Overwriting keys is strictly prohibited."},
        )

    # 1. Validate challenge issuance and freshness (strictly single-use)
    now = time.time()
    issued_time = _ACTIVE_KEY_CHALLENGES.pop(request.challenge, None)
    if issued_time is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"status": "REJECTED", "error": "INVALID_CHALLENGE", "reason": "Registration challenge nonce is invalid, unissued, or has already been consumed."},
        )
    if now - issued_time > 300:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"status": "REJECTED", "error": "CHALLENGE_EXPIRED", "reason": "Registration challenge nonce expired."},
        )

    # 2. Cryptographic challenge-response verification (Ed25519 or ES256 P-256)
    stored_pub_key = None
    if request.public_key_jwk:
        is_valid = verify_es256_challenge_signature(
            challenge=request.challenge,
            signature_str=request.challenge_signature,
            public_key_jwk=request.public_key_jwk,
        )
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"status": "REJECTED", "error": "INVALID_CHALLENGE_SIGNATURE", "reason": "Cryptographic ES256 challenge signature verification failed."},
            )
        stored_pub_key = json.dumps(request.public_key_jwk)
    elif request.public_key_hex:
        clean_pub = request.public_key_hex.strip()
        if clean_pub.startswith("{"):
            try:
                jwk_dict = json.loads(clean_pub)
                is_valid = verify_es256_challenge_signature(
                    challenge=request.challenge,
                    signature_str=request.challenge_signature,
                    public_key_jwk=jwk_dict,
                )
                if not is_valid:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail={"status": "REJECTED", "error": "INVALID_CHALLENGE_SIGNATURE", "reason": "Cryptographic ES256 challenge signature verification failed."},
                    )
                stored_pub_key = json.dumps(jwk_dict)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid JSON JWK")
        else:
            is_valid = verify_ed25519_challenge_signature(
                challenge=request.challenge,
                signature_hex=request.challenge_signature,
                public_key_hex=clean_pub,
            )
            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={"status": "REJECTED", "error": "INVALID_CHALLENGE_SIGNATURE", "reason": "Cryptographic Ed25519 challenge signature verification failed."},
                )
            stored_pub_key = clean_pub.lower()
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"status": "REJECTED", "error": "MISSING_PUBLIC_KEY", "reason": "Either publicKeyHex or publicKeyJwk is required."},
        )

    # 3. US-domestic contractor identity validation
    norm_email = request.contractor_email.strip().lower()
    if not norm_email or "@" not in norm_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"status": "REJECTED", "error": "INVALID_EMAIL", "reason": "A valid contractor email address is required."},
        )
    clean_entity = (request.business_entity or "").strip()
    if len(clean_entity) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"status": "REJECTED", "error": "INVALID_ENTITY", "reason": "Valid US contractor business entity required (minimum 3 characters)."},
        )

    # 4. Register key in SQLite WAL persistence (Strict collision check: 409 Conflict)
    try:
        register_buyer_key(
            kid=request.kid,
            public_key_hex=stored_pub_key,
            contractor_email=norm_email,
            business_name=request.business_entity,
            allow_overwrite=False,
        )
    except ValueError as e:
        if "KEY_ALREADY_EXISTS" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"status": "REJECTED", "error": "KEY_ALREADY_EXISTS", "reason": f"Key ID '{request.kid}' is already registered. Overwriting keys is strictly prohibited."},
            )
        raise HTTPException(status_code=400, detail=str(e))


    # Save contractor budget cap only if explicitly sent by an agent registration (AUD-14)
    cap_sent = "monthly_budget_cap" in request.model_fields_set and request.monthly_budget_cap is not None
    if cap_sent and math.isfinite(request.monthly_budget_cap) and request.monthly_budget_cap > 0:
        from .services.mandate_evaluator import ledger
        existing_cap = ledger.get_saved_cap(norm_email)
        if existing_cap is None:
            ledger.set_contractor_cap(norm_email, float(request.monthly_budget_cap), source="key_registration")


    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return BuyerKeyRegistrationResponse(
        status="REGISTERED",
        kid=request.kid,
        publicKeyHex=stored_pub_key,
        contractorEmail=norm_email,
        businessEntity=request.business_entity,
        registeredAt=now_iso,
        verified=True,
        message=f"Autonomous buyer key '{request.kid}' verified and registered in AP2 Autonomous Node network.",
    )


@app.get(
    "/api/agent/keys/registry",
    response_model=BuyerKeyRegistryResponse,
    status_code=status.HTTP_200_OK,
    tags=["Autonomous Buyer Onboarding"],
)
async def list_registered_buyer_keys_endpoint(request: Request):
    """Lists registered buyer agent keys. Contractor emails and entities are returned to admins only."""
    records = list_buyer_key_records()
    if not _has_admin_key(request):
        records = [{**r, "contractor_email": None, "business_name": None} for r in records]
    return BuyerKeyRegistryResponse(
        status="active",
        count=len(records),
        keys=records,
    )


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
        raise HTTPException(status_code=500, detail="PayPal order creation failed.")


@app.post(
    "/api/paypal/simulate-approval/{subscription_id}",
    tags=["PayPal Orders"],
)
async def simulate_paypal_approval(subscription_id: str, request: Request):
    """
    Simulates buyer approval for a PayPal Sandbox subscription.
    Transitions status from APPROVAL_PENDING to ACTIVE and marks PayPal Vault as VAULT_BOUND.
    Strictly restricted to sandbox and mock environments and requires administrative authorization.
    """
    # 1. Admin authentication check
    auth_header = request.headers.get("Authorization") or request.headers.get("X-Admin-Key")

    provided_token = None
    if auth_header:
        if auth_header.startswith("Bearer "):
            provided_token = auth_header[7:].strip()
        else:
            provided_token = auth_header.strip()

    expected_key = (getattr(settings, "admin_api_key", None) or "").strip()
    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ADMIN_API_KEY is not configured on the server. Configure a strong ADMIN_API_KEY in .env.",
        )
    if not provided_token or provided_token == "dev-admin-secret-key" or not hmac.compare_digest(provided_token.encode("utf-8"), expected_key.encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authorization required to simulate approval. Provide valid X-Admin-Key or Authorization header.",
        )

    # 2. Strict Sandbox & Mock Environment Guard
    is_sandbox = (
        "sandbox" in (getattr(settings, "paypal_base_url", "") or "").lower()
        or getattr(settings, "mock_external_apis", False)
    )
    if not is_sandbox:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sandbox approval simulation is strictly restricted to sandbox and mock environments.",
        )

    sub_id = subscription_id.strip()
    from .agents.seller_agent import (
        _COMPLETED_SUBSCRIPTIONS,
        _ACTIVE_CONTRACTOR_SUBSCRIPTIONS,
        reconcile_contractor_ledger,
        resolve_tier_from_paypal_plan,
    )

    sub_record = _COMPLETED_SUBSCRIPTIONS.get(sub_id)
    if not sub_record:
        for k, v in list(_COMPLETED_SUBSCRIPTIONS.items()):
            if isinstance(v, dict) and v.get("subscription_id") == sub_id:
                sub_record = v
                sub_id = v.get("subscription_id")
                break

    if not sub_record:
        try:
            remote_sub = await paypal_service.verify_subscription(sub_id)
            if remote_sub and not remote_sub.get("mock_mode"):
                tier_id, rate = resolve_tier_from_paypal_plan(remote_sub.get("plan_id"))
                subscriber_data = remote_sub.get("subscriber") or {}
                sub_record = {
                    "subscription_id": sub_id,
                    "status": "ACTIVE",
                    "contractor_email": subscriber_data.get("email_address") or "",
                    "tier_id": tier_id,
                    "agreed_monthly_rate": rate,
                    "plan_id": remote_sub.get("plan_id"),
                    "paypal_vault_status": "VAULT_BOUND",
                    "vault_billing_authorized": True,
                    "vault_customer_present": False,
                }
                _COMPLETED_SUBSCRIPTIONS[sub_id] = sub_record
        except Exception as e:
            logger.warning(f"Could not verify remote PayPal subscription {sub_id} during simulation: {e}")

    if not sub_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subscription '{sub_id}' does not exist in registry.",
        )

    sub_record["status"] = "ACTIVE"
    sub_record["paypal_vault_status"] = "VAULT_BOUND"
    sub_record["vault_billing_authorized"] = True
    sub_record["vault_customer_present"] = False
    sub_record["next_action"] = {
        "type": "tool_call",
        "tool": "provision_compute_node",
        "parameters": {
            "subscription_id": sub_id,
            "contractor_email": sub_record.get("contractor_email"),
            "area_code": "703",
        },
    }
    _COMPLETED_SUBSCRIPTIONS[sub_id] = sub_record

    email = sub_record.get("contractor_email")
    if email:
        norm_email = email.strip().lower()
        _ACTIVE_CONTRACTOR_SUBSCRIPTIONS[norm_email] = sub_id

        replaces_id = sub_record.get("replaces_subscription_id")
        if replaces_id and replaces_id in _COMPLETED_SUBSCRIPTIONS:
            old_sub = _COMPLETED_SUBSCRIPTIONS[replaces_id]
            if isinstance(old_sub, dict):
                old_sub["status"] = "REPLACED"
                old_sub["replaced_by"] = sub_id
                old_sub.pop("pending_replacement", None)
                old_sub["vault_billing_authorized"] = False
                _COMPLETED_SUBSCRIPTIONS[replaces_id] = old_sub

        reconcile_contractor_ledger(norm_email)

    for k, v in list(_COMPLETED_SUBSCRIPTIONS.items()):
        if isinstance(v, dict) and v.get("subscription_id") == sub_id:
            v["status"] = "ACTIVE"
            v["paypal_vault_status"] = "VAULT_BOUND"
            v["vault_billing_authorized"] = True
            v["vault_customer_present"] = False
            v["next_action"] = sub_record["next_action"]

    logger.info(f"[PayPal Sandbox] Successfully simulated buyer approval for {sub_id}. Status -> ACTIVE.")
    return {
        "status": "ACTIVE",
        "subscription_id": sub_id,
        "paypal_vault_status": "VAULT_BOUND",
        "vault_billing_authorized": True,
        "message": f"Sandbox buyer approval simulated for subscription {sub_id}. Status transitioned to ACTIVE.",
        "next_action": sub_record["next_action"],
    }


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
    if verification.get("verification_status") != "SUCCESS":
        logger.warning(f"[SECURITY] PayPal webhook signature verification failed for event {event_type}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid PayPal webhook signature.",
        )

    # De-duplicate verified webhook events by unique PayPal event ID (replay protection)
    event_id = body.get("id")
    if event_id and event_id in _PROCESSED_WEBHOOK_IDS:
        logger.info(f"[PayPal Webhook] Duplicate verified event {event_id} ({event_type}) received; skipping duplicate execution.")
        return {
            "status": "already_processed",
            "event_id": event_id,
            "event_type": event_type,
            "verification_status": "SUCCESS",
            "duplicate": True,
        }
    if event_id:
        _PROCESSED_WEBHOOK_IDS.add(event_id)

    # Process activation event
    if event_type in [
        "BILLING.SUBSCRIPTION.ACTIVATED",
        "CHECKOUT.ORDER.APPROVED",
    ]:
        resource = body.get("resource", {})
        sub_id = resource.get("id", "UNKNOWN_SUB")
        logger.info(
            f"[PayPal Webhook] Verified payment event for {sub_id} ({verification.get('verification_status')}). Activating subscription in registry."
        )
        from .agents.seller_agent import (
            _COMPLETED_SUBSCRIPTIONS,
            _ACTIVE_CONTRACTOR_SUBSCRIPTIONS,
            reconcile_contractor_ledger,
        )
        if sub_id in _COMPLETED_SUBSCRIPTIONS:
            sub_record = _COMPLETED_SUBSCRIPTIONS[sub_id]
            sub_record["status"] = "ACTIVE"
            sub_record["paypal_vault_status"] = "VAULT_BOUND"
            sub_record["vault_billing_authorized"] = True
            sub_record["vault_customer_present"] = False
            sub_record["next_action"] = {
                "type": "tool_call",
                "tool": "provision_compute_node",
                "parameters": {
                    "subscription_id": sub_id,
                    "contractor_email": sub_record.get("contractor_email"),
                    "area_code": "703",
                },
            }
            email = sub_record.get("contractor_email")
            if email:
                _ACTIVE_CONTRACTOR_SUBSCRIPTIONS[email.strip().lower()] = sub_id

            # If this subscription replaced an earlier plan, finalize retirement of old subscription
            replaces_id = sub_record.get("replaces_subscription_id")
            if replaces_id and replaces_id in _COMPLETED_SUBSCRIPTIONS:
                old_sub = _COMPLETED_SUBSCRIPTIONS[replaces_id]
                old_sub["status"] = "REPLACED"
                old_sub["replaced_by"] = sub_id
                old_sub.pop("pending_replacement", None)
                old_sub["vault_billing_authorized"] = False

            # Also update any aliases that map to the same subscription record
            for k, v in list(_COMPLETED_SUBSCRIPTIONS.items()):
                if isinstance(v, dict) and v.get("subscription_id") == sub_id:
                    v["status"] = "ACTIVE"
                    v["paypal_vault_status"] = "VAULT_BOUND"
                    v["vault_billing_authorized"] = True
                    v["vault_customer_present"] = False
                    v["next_action"] = sub_record["next_action"]

            # Reconcile contractor ledger strictly from active subscription state:
            # commitment = rate of the contractor's one ACTIVE subscription
            if email:
                reconcile_contractor_ledger(email)

    elif event_type in [
        "BILLING.SUBSCRIPTION.CANCELLED",
        "BILLING.SUBSCRIPTION.SUSPENDED",
        "BILLING.SUBSCRIPTION.PAYMENT.FAILED",
    ]:
        resource = body.get("resource", {})
        sub_id = resource.get("id", "UNKNOWN_SUB")
        status_map = {
            "BILLING.SUBSCRIPTION.CANCELLED": "CANCELLED",
            "BILLING.SUBSCRIPTION.SUSPENDED": "SUSPENDED",
            "BILLING.SUBSCRIPTION.PAYMENT.FAILED": "PAYMENT_FAILED",
        }
        new_status = status_map.get(event_type, "CANCELLED")
        logger.info(
            f"[PayPal Webhook] Received {event_type} for {sub_id}. Updating status to {new_status}."
        )
        from .agents.seller_agent import (
            _COMPLETED_SUBSCRIPTIONS,
            _ACTIVE_CONTRACTOR_SUBSCRIPTIONS,
            reconcile_contractor_ledger,
        )

        email = None
        if sub_id in _COMPLETED_SUBSCRIPTIONS:
            sub_record = _COMPLETED_SUBSCRIPTIONS[sub_id]
            sub_record["status"] = new_status
            sub_record["vault_billing_authorized"] = False
            sub_record["paypal_vault_status"] = f"VAULT_{new_status}"
            email = sub_record.get("contractor_email")

            if email:
                norm_email = email.strip().lower()
                if _ACTIVE_CONTRACTOR_SUBSCRIPTIONS.get(norm_email) == sub_id:
                    _ACTIVE_CONTRACTOR_SUBSCRIPTIONS.pop(norm_email, None)

            # Clear pending_replacement on any other subscription waiting for this sub
            for s in _COMPLETED_SUBSCRIPTIONS.values():
                if isinstance(s, dict) and s.get("pending_replacement") == sub_id:
                    s.pop("pending_replacement", None)
                    s.pop("pending_replacement_tier", None)
                    s.pop("pending_replacement_at", None)

            # Update aliases that point to the same record
            for k, v in list(_COMPLETED_SUBSCRIPTIONS.items()):
                if isinstance(v, dict) and v.get("subscription_id") == sub_id:
                    v["status"] = new_status
                    v["vault_billing_authorized"] = False
                    v["paypal_vault_status"] = f"VAULT_{new_status}"
        else:
            email = resource.get("subscriber", {}).get("email_address")

        # Reconcile contractor ledger strictly from subscription state:
        # commitment = rate of the contractor's one ACTIVE subscription.
        # Replaced, cancelled, or suspended subscriptions contribute 0.0 to commitment.
        if email:
            reconcile_contractor_ledger(email)

    return {
        "status": "received",
        "event_type": event_type,
        "verification_status": verification.get("verification_status", "SUCCESS"),
    }


class RunBuyerAgentRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    transport: Optional[str] = "http"
    contractorName: Optional[str] = Field(default="Nexus Autonomous Buyer", alias="contractor_name")
    businessEntity: Optional[str] = Field(default="Nexus Autonomous Systems Corp", alias="business_entity")
    contractorEmail: Optional[str] = Field(default="agent-alpha@example.com", alias="contractor_email")
    tradeId: Optional[str] = Field(default="ap2-gateway", alias="trade_id")
    budgetCap: Optional[float] = Field(default=100.00, alias="budget_cap")
    areaCode: Optional[str] = Field(default="703", alias="area_code")
    simulateExhaustion: Optional[bool] = Field(default=False, alias="simulate_exhaustion")
    webhookUrl: Optional[str] = Field(default=None, alias="webhook_url")
    resetLedger: Optional[bool] = Field(default=False, alias="reset_ledger")


@app.post("/api/harness/run-buyer-agent", tags=["External Buyer Harness"])
async def run_external_buyer_agent_endpoint(req: RunBuyerAgentRequest, request: Request):
    """
    Executes the external buyer agent harness headlessly over MCP (HTTP or stdio).
    Returns the step-by-step audit log, cryptographic proof, and back-office payloads.
    Requires administrative authorization.
    """
    # Admin authorization check
    auth_header = request.headers.get("Authorization") or request.headers.get("X-Admin-Key")

    provided_token = None
    if auth_header:
        if auth_header.startswith("Bearer "):
            provided_token = auth_header[7:].strip()
        else:
            provided_token = auth_header.strip()

    expected_key = (getattr(settings, "admin_api_key", None) or "").strip()
    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ADMIN_API_KEY is not configured on the server. Configure a strong ADMIN_API_KEY in .env.",
        )
    if not provided_token or provided_token == "dev-admin-secret-key" or not hmac.compare_digest(provided_token.encode("utf-8"), expected_key.encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authorization required to execute buyer agent harness. Provide valid X-Admin-Key or Authorization header.",
        )

    if req.resetLedger:
        if not settings.mock_external_apis:
            logger.warning("[SECURITY] resetLedger requested in live production mode; suppressed to protect database integrity.")
        else:
            ledger.reset()

    agent = ExternalBuyerAgent(
        transport=req.transport or "http",
        server_url=f"http://127.0.0.1:{settings.server_port}/mcp",
        contractor_name=req.contractorName or "Nexus Autonomous Buyer",
        business_entity=req.businessEntity or "Nexus Autonomous Systems Corp",
        contractor_email=req.contractorEmail or "agent-alpha@example.com",
        trade_id=req.tradeId or "ap2-gateway",
        budget_cap=req.budgetCap or 100.00,
        area_code=req.areaCode or "703",
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
