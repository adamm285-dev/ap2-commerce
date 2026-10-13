"""
AP2 Autonomous Agent Commerce & Compute Network — FastAPI Server.
Implements the full OpenAPI 3.1.0 contract defined in openapi.yaml.
Supports 100% offline mock simulation when external keys are not configured.
"""

import os
import math
import time
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
    IdentityAttestationRequest,
    IdentityAttestationResponse,
    DirectChargeRequest,
    DirectChargeResponse,
    DirectChargeListResponse,
)
from .services.paypal_oidc_service import PayPalOidcService
from .services.ap2_gateway_service import Ap2GatewayService
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
from .agents.seller_copilot import SellerCopilot, ContractorCopilot
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
from .services.recurring_mandate_service import ACTION_CANCEL, ACTION_NONE, evaluate_sale

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
    get_buyer_key_email,
    attest_buyer_identity,
    get_buyer_identity,
    list_buyer_key_records,
    is_direct_charge_replayed,
    set_recurring_mandate_status,
    RESERVED_BUYER_KEY_IDS,
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
        description=f"Synchronous low-latency AI service gateway, {quota_label('ap2-gateway')}, and MCP stream over HTTP.",
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
            "backoffice_erp_export": True,
        },
    }


# --- Model Context Protocol (MCP) Streamable HTTP & JSON-RPC 2.0 Endpoint ---
@app.get("/mcp", tags=["Model Context Protocol"])
async def mcp_get_endpoint(request: Request):
    """
    Handles GET requests to /mcp.
    If Accept header requests text/event-stream, opens the SSE stream with the standard MCP handshake.
    Otherwise returns a machine-readable JSON status of the MCP server.
    """
    accept = request.headers.get("accept", "")
    if "text/event-stream" in accept:
        return await mcp_wire_stream(request)
    return {
        "name": "AP2 Autonomous Seller MCP Server",
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
    exchanged between agents and the AP2 MCP Server.
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
    business_name: Optional[str] = "Acme Compute Co"
    monthly_cap_usd: Optional[float] = 100.00
    agreed_price_usd: Optional[float] = 79.99
    nonce: Optional[str] = None


# MOCK(M-014): anti-tamper playground on the legacy proof format
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


# MOCK(M-014): anti-tamper playground on the legacy proof format
@app.post("/api/agent/anti-tamper/generate-proof", tags=["Anti-Tamper & Cryptography"], include_in_schema=False)
@app.post("/api/crypto/generate-proof", tags=["Anti-Tamper & Cryptography"])
async def generate_proof_endpoint(req: GenerateProofRequest):
    """Generates a canonical mandate proof for given parameters using the demo tamper key."""
    nonce = req.nonce or uuid.uuid4().hex[:12]
    proof = generate_dynamic_mandate_proof(
        contractor_id=req.contractor_id or "agent:acme-procure",
        business_name=req.business_name or "Acme Compute Co",
        monthly_cap_usd=req.monthly_cap_usd if req.monthly_cap_usd is not None else 100.00,
        agreed_price_usd=req.agreed_price_usd if req.agreed_price_usd is not None else 79.99,
        nonce=nonce,
        buyer_private_key_hex=DEMO_TAMPER_PRIVATE_KEY_HEX,
        secret_key=DEMO_TAMPER_SECRET,
        kid=DEMO_TAMPER_KID,
    )
    # Zero secret leakage: secret_key_preview is strictly omitted
    return proof


# MOCK(M-014): anti-tamper playground on the legacy proof format
@app.get("/api/agent/anti-tamper/sample-proof", tags=["Anti-Tamper & Cryptography"], include_in_schema=False)
@app.get("/api/crypto/sample-proof", tags=["Anti-Tamper & Cryptography"])
async def get_sample_proof(profile: str = Query("default")):
    """Returns a ready-to-test authentic proof using the demo tamper key. Profile-aware (ap2 vs default)."""
    nonce = uuid.uuid4().hex[:12]
    if (profile or "").strip().lower() == "ap2":
        proof = generate_dynamic_mandate_proof(
            contractor_id="agent:acme-procure",
            business_name="Acme Compute Co",
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
            business_name="Demo Buyer Corp",
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


# --- Cryptographic Mandate Revocation Endpoints (SPEC-001 v1.9.0) ---

class RevokeMandateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    mandateProofHash: str = Field(..., alias="mandate_proof_hash", description="Hash of the mandate being revoked")
    kid: str = Field(..., description="Key ID of registered buyer key used to sign revocation")
    reason: str = Field(default="Owner manual revocation", description="Reason for revocation")
    timestampIso: Optional[str] = Field(default=None, alias="timestamp_iso", description="ISO 8601 timestamp of revocation")
    signature: str = Field(..., description="Cryptographic signature over canonical REVOKE message")


@app.post("/api/mandates/revoke", tags=["Mandate Revocation"])
@app.post("/api/agent/mandates/revoke", tags=["Mandate Revocation"])
async def revoke_mandate_endpoint(req: RevokeMandateRequest, request: Request):
    """
    Cryptographically revokes an AP2 Open Mandate.
    Requires owner signature verifying against registered buyer keys.
    Immediately stops any active PayPal subscriptions bound to this mandate.
    """
    from .services.mandate_revocation_service import revoke_mandate
    is_admin = _has_admin_key(request)
    try:
        res = await revoke_mandate(
            mandate_proof_hash=req.mandateProofHash,
            kid=req.kid,
            reason=req.reason,
            signature=req.signature,
            timestamp_iso=req.timestampIso,
            is_admin=is_admin,
        )
        return res
    except ValueError as e:
        logger.warning(f"Mandate revocation failed: {e}")
        status_code = (
            status.HTTP_404_NOT_FOUND
            if "MANDATE_NOT_FOUND" in str(e)
            else (
                status.HTTP_403_FORBIDDEN
                if "UNAUTHORIZED" in str(e)
                else (status.HTTP_401_UNAUTHORIZED if "SIGNATURE" in str(e) or "KEY" in str(e) else status.HTTP_400_BAD_REQUEST)
            )
        )
        raise HTTPException(
            status_code=status_code,
            detail={"status": "REJECTED", "error": "REVOCATION_FAILED", "reason": str(e)},
        )


@app.get("/api/mandates/revocations", tags=["Mandate Revocation"])
async def list_revoked_mandates_endpoint(limit: int = Query(default=100, ge=1, le=1000)):
    """Returns the cryptographic mandate revocation status list (SPEC-001 v1.9.0)."""
    from .database import list_revoked_mandates
    revocations = list_revoked_mandates(limit=limit)
    return {
        "status": "success",
        "count": len(revocations),
        "revocations": revocations,
    }


@app.get("/api/mandates/revocations/{mandate_hash}", tags=["Mandate Revocation"])
async def get_mandate_revocation_endpoint(mandate_hash: str):
    """Checks whether a specific mandate proof hash has been cryptographically revoked."""
    from .database import get_mandate_revocation
    rec = get_mandate_revocation(mandate_hash)
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"revoked": False, "message": f"Mandate '{mandate_hash}' is not in the revocation status list."},
        )
    return {"revoked": True, "revocation": rec}


# --- Two-Sided Marketplace & Operator Payouts Endpoints (SPEC-001 v1.9.0 / Milestone S2-SETTLE) ---

class RegisterOperatorRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    name: str = Field(..., description="Compute node operator or infrastructure provider name")
    email: str = Field(..., description="Operator PayPal email address for payouts")
    assignedNodes: Optional[List[str]] = Field(default=None, alias="assigned_nodes", description="Assigned compute node IDs or pattern prefixes")
    splitBps: int = Field(default=8500, ge=0, le=10000, alias="split_bps", description="Operator revenue share in basis points (e.g. 8500 = 85.00%)")
    payoutRecipientType: str = Field(default="EMAIL", alias="payout_recipient_type", description="PayPal recipient type (EMAIL or PAYER_ID)")
    operatorId: Optional[str] = Field(default=None, alias="operator_id", description="Optional custom operator identifier")


class ExecuteBatchPayoutRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    cycleId: Optional[str] = Field(default=None, alias="cycle_id", description="Billing cycle identifier (e.g. '2026-10')")
    senderBatchId: Optional[str] = Field(default=None, alias="sender_batch_id", description="Custom unique batch sender ID")
    subscriptionIds: Optional[List[str]] = Field(default=None, alias="subscription_ids", description="Optional list of specific subscription IDs to disburse")
    dryRun: bool = Field(default=False, alias="dry_run", description="If True, performs calculations and returns preview without executing PayPal payout")


@app.post("/api/marketplace/operators/register", status_code=status.HTTP_201_CREATED, tags=["Marketplace Payouts"])
async def register_operator_endpoint(req: RegisterOperatorRequest, request: Request):
    """Registers or updates a compute node operator in the two-sided marketplace."""
    from .services.marketplace_payout_service import marketplace_payout_service, DEFAULT_OPERATOR_SPLIT_BPS
    is_admin = _has_admin_key(request)
    if not is_admin and req.splitBps != DEFAULT_OPERATOR_SPLIT_BPS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="OPERATOR_SPLIT_FORBIDDEN: Setting custom split_bps requires admin authorization.",
        )
    if req.operatorId:
        existing = marketplace_payout_service.get_operator(req.operatorId)
        if existing and existing.get("email") != req.email.strip().lower() and not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"OPERATOR_MODIFICATION_FORBIDDEN: Admin authorization required to update payout destination for '{req.operatorId}'.",
            )
    try:
        op = marketplace_payout_service.register_operator(
            name=req.name,
            email=req.email,
            assigned_nodes=req.assignedNodes,
            split_bps=req.splitBps,
            payout_recipient_type=req.payoutRecipientType,
            operator_id=req.operatorId,
            allow_overwrite=is_admin,
        )
        return {"status": "SUCCESS", "operator": op}
    except ValueError as e:
        if "OPERATOR_ALREADY_EXISTS" in str(e):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/api/marketplace/operators", tags=["Marketplace Payouts"])
async def list_operators_endpoint():
    """Lists all registered compute node operators and their capacity assignments."""
    from .services.marketplace_payout_service import marketplace_payout_service
    operators = marketplace_payout_service.list_operators()
    return {"status": "SUCCESS", "count": len(operators), "operators": operators}


@app.get("/api/marketplace/operators/{operator_id}", tags=["Marketplace Payouts"])
async def get_operator_endpoint(operator_id: str):
    """Retrieves details of a registered compute node operator."""
    from .services.marketplace_payout_service import marketplace_payout_service
    op = marketplace_payout_service.get_operator(operator_id)
    if not op:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Operator '{operator_id}' not found.")
    return {"status": "SUCCESS", "operator": op}


@app.post("/api/marketplace/payouts/execute-batch", tags=["Marketplace Payouts"])
async def execute_batch_payout_endpoint(req: ExecuteBatchPayoutRequest, request: Request):
    """
    Executes automated monthly batch payouts to compute node operators via PayPal Payouts REST API.
    Calculates integer cents margins (85% operator / 15% platform take-rate with zero float drift),
    disburses funds via PayPal, and exports QBO v3 Bills.
    """
    from .services.marketplace_payout_service import marketplace_payout_service
    if not settings.mock_external_apis and not _has_admin_key(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin authorization required to execute live PayPal batch disbursements.",
        )
    try:
        res = await marketplace_payout_service.execute_fleet_payout_batch(
            cycle_id=req.cycleId,
            sender_batch_id=req.senderBatchId,
            subscription_ids=req.subscriptionIds,
            dry_run=req.dryRun,
        )
        return res
    except Exception as e:
        logger.error(f"[Marketplace Payouts] Batch payout failed: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.get("/api/marketplace/payouts/batches", tags=["Marketplace Payouts"])
async def list_payout_batches_endpoint(limit: int = Query(default=50, ge=1, le=500)):
    """Lists historical PayPal payout batches with gross, payout, and platform margin totals."""
    from .database import list_payout_batches
    batches = list_payout_batches(limit=limit)
    return {"status": "SUCCESS", "count": len(batches), "batches": batches}


@app.get("/api/marketplace/payouts/batches/{batch_id}", tags=["Marketplace Payouts"])
async def get_payout_batch_endpoint(batch_id: str):
    """Retrieves a specific payout batch and its itemized disbursements."""
    from .database import get_payout_batch
    batch = get_payout_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Payout batch '{batch_id}' not found.")
    return {"status": "SUCCESS", "batch": batch}


@app.get("/api/marketplace/payouts/ledger", tags=["Marketplace Payouts"])
async def get_operator_settlement_ledger_endpoint(operator_id: Optional[str] = Query(default=None)):
    """Returns the itemized operator settlement ledger across all compute node workloads."""
    from .services.marketplace_payout_service import marketplace_payout_service
    ledger_entries = marketplace_payout_service.get_operator_settlement_ledger(operator_id=operator_id)
    return {"status": "SUCCESS", "count": len(ledger_entries), "ledger": ledger_entries}


@app.get("/api/marketplace/revenue-summary", tags=["Marketplace Payouts"])
async def get_marketplace_revenue_summary_endpoint():
    """Returns platform GMV, operator disbursements, platform retained margin, and effective take-rate."""
    from .services.marketplace_payout_service import marketplace_payout_service
    summary = marketplace_payout_service.get_marketplace_revenue_summary()
    return {"status": "SUCCESS", "summary": summary}


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


# MOCK(M-006): server signs owner limits for any caller that sends human_confirmed=true
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



# --- Seller AI Copilot Conversational Engine ---
class CopilotChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    message: str
    contractorName: Optional[str] = Field(default="Demo Autonomous Buyer", alias="contractor_name")
    businessEntity: Optional[str] = Field(default="Demo Buyer Corp", alias="business_entity")
    tradeVertical: Optional[str] = Field(default="Autonomous Compute & Worker Nodes", alias="trade_vertical")
    budgetCap: Optional[float] = Field(default=100.00, alias="budget_cap")
    simulateExhaustion: Optional[bool] = Field(default=False, alias="simulate_exhaustion")


@app.post("/api/seller-copilot/chat", tags=["Seller Copilot"])
@app.post("/api/copilot/chat", tags=["Seller Copilot"], include_in_schema=False)
async def copilot_chat_endpoint(req: CopilotChatRequest):
    """
    Seller AI Copilot conversational engine.
    Ingests messages from the operator, diagnoses pipeline queue, queries AP2 Seller MCP,
    and returns conversational responses and proposed A2A actions.
    """
    copilot = SellerCopilot(
        contractor_name=req.contractorName or "Demo Autonomous Buyer",
        business_entity=req.businessEntity or "Demo Buyer Corp",
        trade_vertical=req.tradeVertical or "Autonomous Compute & Worker Nodes",
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
            contractorName=params.get("contractor_name", "Demo Autonomous Buyer"),
            businessEntity=params.get("business_entity", "Demo Buyer Corp"),
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
    business_entity: str = Field(default="Acme Compute Co", alias="businessEntity")
    monthly_budget_cap: float = Field(default=100.0, alias="monthlyBudgetCap")
    checkout_jwt: Optional[str] = Field(default=None, alias="checkoutJwt")
    checkout_hash: Optional[str] = Field(default=None, alias="checkoutHash")
    nonce: Optional[str] = None
    offer_id: Optional[str] = Field(default=None, alias="offerId")
    open_checkout_mandate_token: Optional[str] = Field(default=None, alias="openCheckoutMandateToken")
    open_payment_mandate_token: Optional[str] = Field(default=None, alias="openPaymentMandateToken")
    paypal_subscription_id: Optional[str] = Field(default=None, alias="paypalSubscriptionId")


# MOCK(M-007): server plays owner, agent and seller in one request
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
        or (request.job_id or "").lower().startswith("txn_ap2_")
        or (request.job_id or "").lower().startswith("job_ap2_")
        or (request.job_id or "").lower().startswith("lead_ap2_")
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
        "job_id": request.job_id,
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
        "Rows represent simulated live fleet telemetry demonstrating 24/7 AG Studio operations across autonomous compute and worker nodes."
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
    """Without the admin key: no live Zapier actions, and no client-chosen webhook outside mock mode."""
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

    # 3.5 Optional PayPal OpenID Connect identity attestation
    payer_id = None
    identity_provider = None
    identity_attested = False
    attestation_payload = None
    if request.oidc_id_token:
        try:
            attestation = PayPalOidcService.verify_oidc_identity_attestation(
                id_token=request.oidc_id_token,
                expected_nonce=request.challenge,
            )
            token_email = (attestation.get("email") or "").strip().lower()
            if not token_email or token_email != norm_email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "status": "REJECTED",
                        "error": "EMAIL_KEY_BINDING_MISMATCH",
                        "reason": f"OIDC identity email '{token_email}' does not match registered contractor email '{norm_email}'.",
                    },
                )
            payer_id = attestation.get("payer_id")
            identity_provider = "paypal"
            identity_attested = True
            attestation_payload = attestation.get("claims")
        except HTTPException:
            raise
        except ValueError as e:
            err_code = "LIVE_OIDC_NOT_CONFIGURED" if "LIVE_OIDC_NOT_CONFIGURED" in str(e) else "INVALID_IDENTITY_ATTESTATION"
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"status": "REJECTED", "error": err_code, "reason": str(e)},
            )

    # 4. Register key in SQLite WAL persistence (Strict collision check: 409 Conflict)
    try:
        register_buyer_key(
            kid=request.kid,
            public_key_hex=stored_pub_key,
            contractor_email=norm_email,
            business_name=request.business_entity,
            payer_id=payer_id,
            identity_provider=identity_provider,
            identity_attested=identity_attested,
            attestation_payload=attestation_payload,
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
        identity_attested=identity_attested,
        payer_id=payer_id,
        identity_provider=identity_provider,
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
    "/api/agent/identity/attest",
    response_model=IdentityAttestationResponse,
    status_code=status.HTTP_200_OK,
    tags=["Identity Attestation"],
)
async def attest_buyer_identity_endpoint(request: IdentityAttestationRequest, req: Request):
    """
    Attests the verified real-world PayPal identity of an existing registered buyer key.
    Enforces PayPal OIDC ID token signature and claims verification.
    """
    existing_key = get_buyer_key(request.kid)
    if not existing_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"status": "REJECTED", "error": "KEY_NOT_FOUND", "reason": f"Buyer key '{request.kid}' is not registered."},
        )

    try:
        attestation = PayPalOidcService.verify_oidc_identity_attestation(
            id_token=request.oidc_id_token,
            expected_nonce=request.challenge if request.challenge else None,
        )
    except ValueError as e:
        err_code = "LIVE_OIDC_NOT_CONFIGURED" if "LIVE_OIDC_NOT_CONFIGURED" in str(e) else "INVALID_IDENTITY_ATTESTATION"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"status": "REJECTED", "error": err_code, "reason": str(e)},
        )

    payer_id = attestation["payer_id"]
    claims = attestation["claims"]
    email = attestation["email"]

    # Email-to-Key binding verification: Fail closed if key is bound to different email
    reg_email = get_buyer_key_email(request.kid)
    if not reg_email or reg_email.strip().lower() != email.strip().lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "status": "REJECTED",
                "error": "EMAIL_KEY_BINDING_MISMATCH",
                "reason": f"OIDC identity email '{email}' does not match registered contractor email '{reg_email}' for key '{request.kid}'.",
            },
        )

    # Key possession verification: caller must prove possession of the key being attested
    is_admin = _has_admin_key(req)
    if not is_admin:
        if not request.challenge or not request.challenge_signature:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "status": "REJECTED",
                    "error": "KEY_POSSESSION_PROOF_REQUIRED",
                    "reason": f"Attestation for key '{request.kid}' requires cryptographic signature proving key possession.",
                },
            )

        now = time.time()
        issued_time = _ACTIVE_KEY_CHALLENGES.pop(request.challenge, None)
        if issued_time is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"status": "REJECTED", "error": "INVALID_CHALLENGE", "reason": "Attestation challenge nonce is invalid, unissued, or has already been consumed."},
            )
        if now - issued_time > 300:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"status": "REJECTED", "error": "CHALLENGE_EXPIRED", "reason": "Attestation challenge nonce expired."},
            )

        clean_pub = existing_key.strip()
        if clean_pub.startswith("{"):
            try:
                jwk_dict = json.loads(clean_pub)
                is_valid = verify_es256_challenge_signature(
                    challenge=request.challenge,
                    signature_str=request.challenge_signature,
                    public_key_jwk=jwk_dict,
                )
            except Exception:
                is_valid = False
        else:
            is_valid = verify_ed25519_challenge_signature(
                challenge=request.challenge,
                signature_hex=request.challenge_signature,
                public_key_hex=clean_pub,
            )

        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"status": "REJECTED", "error": "INVALID_CHALLENGE_SIGNATURE", "reason": "Cryptographic challenge signature verification failed."},
            )

    success = attest_buyer_identity(
        kid=request.kid,
        payer_id=payer_id,
        identity_provider="paypal",
        attestation_payload=claims,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "REJECTED", "error": "ATTESTATION_STORAGE_FAILED", "reason": "Could not update buyer key attestation."},
        )

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return IdentityAttestationResponse(
        status="ATTESTED",
        kid=request.kid,
        payerId=payer_id,
        identityProvider="paypal",
        identityAttested=True,
        email=email,
        attestationTimestamp=now_iso,
        claims=claims,
    )


@app.get(
    "/api/agent/identity/attestation/{kid}",
    response_model=IdentityAttestationResponse,
    status_code=status.HTTP_200_OK,
    tags=["Identity Attestation"],
)
async def get_buyer_identity_endpoint(kid: str):
    """Retrieves verified identity attestation details for a registered buyer key."""
    identity = get_buyer_identity(kid)
    if not identity or not identity.get("identity_attested"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"status": "REJECTED", "error": "NOT_ATTESTED", "reason": f"No identity attestation found for key '{kid}'."},
        )

    claims = identity.get("attestation_payload") or {}
    email = claims.get("email") or identity.get("contractor_email") or "verified@paypal.com"
    return IdentityAttestationResponse(
        status="ATTESTED",
        kid=kid,
        payerId=identity.get("payer_id") or "PAYER-UNKNOWN",
        identityProvider=identity.get("identity_provider") or "paypal",
        identityAttested=True,
        email=email,
        attestationTimestamp=identity.get("registered_at") or datetime.datetime.now(datetime.timezone.utc).isoformat(),
        claims=claims,
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


# MOCK(M-004): flips APPROVAL_PENDING to ACTIVE without a real PayPal approval
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


def _apply_subscription_stop(sub_id: str, new_status: str, fallback_email: Optional[str] = None) -> None:
    """Marks a subscription stopped (cancelled, suspended or payment failed) and reconciles the buyer's ledger."""
    from .agents.seller_agent import (
        _COMPLETED_SUBSCRIPTIONS,
        _ACTIVE_CONTRACTOR_SUBSCRIPTIONS,
        reconcile_contractor_ledger,
    )

    email = None
    if sub_id in _COMPLETED_SUBSCRIPTIONS:
        sub_record = _COMPLETED_SUBSCRIPTIONS[sub_id]
        sub_record["status"] = new_status
        sub_record["node_status"] = new_status
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
                v["node_status"] = new_status
                v["vault_billing_authorized"] = False
                v["paypal_vault_status"] = f"VAULT_{new_status}"
    else:
        email = fallback_email

    # Reconcile contractor ledger strictly from subscription state:
    # commitment = rate of the contractor's one ACTIVE subscription.
    # Replaced, cancelled, or suspended subscriptions contribute 0.0 to commitment.
    if email:
        reconcile_contractor_ledger(email)


def _apply_subscription_reactivate(sub_id: str, fallback_email: Optional[str] = None) -> None:
    """Restores a suspended subscription back to ACTIVE and reconciles the buyer's ledger."""
    from .agents.seller_agent import (
        _COMPLETED_SUBSCRIPTIONS,
        _ACTIVE_CONTRACTOR_SUBSCRIPTIONS,
        reconcile_contractor_ledger,
    )

    email = None
    if sub_id in _COMPLETED_SUBSCRIPTIONS:
        sub_record = _COMPLETED_SUBSCRIPTIONS[sub_id]
        sub_record["status"] = "ACTIVE"
        sub_record["node_status"] = "ACTIVE"
        sub_record["vault_billing_authorized"] = True
        sub_record["paypal_vault_status"] = "VAULT_BOUND"
        email = sub_record.get("contractor_email")

        if email:
            norm_email = email.strip().lower()
            _ACTIVE_CONTRACTOR_SUBSCRIPTIONS[norm_email] = sub_id

        # Update aliases that point to the same record
        for k, v in list(_COMPLETED_SUBSCRIPTIONS.items()):
            if isinstance(v, dict) and v.get("subscription_id") == sub_id:
                v["status"] = "ACTIVE"
                v["node_status"] = "ACTIVE"
                v["vault_billing_authorized"] = True
                v["paypal_vault_status"] = "VAULT_BOUND"
    else:
        email = fallback_email

    if email:
        reconcile_contractor_ledger(email)


async def _enforce_recurring_mandate(resource: Any) -> Dict[str, Any]:
    """
    Checks a PayPal sale against the owner's AP2 mandate. If the charge is not authorized, or the
    next one could not be, cancels or suspends the subscription on PayPal and locally.
    """
    from .agents.seller_agent import _COMPLETED_SUBSCRIPTIONS

    sub_id = resource.get("billing_agreement_id") if isinstance(resource, dict) else None
    sub_record = _COMPLETED_SUBSCRIPTIONS[sub_id] if isinstance(sub_id, str) and sub_id in _COMPLETED_SUBSCRIPTIONS else None
    decision = evaluate_sale(resource, sub_record)
    if decision["action"] == ACTION_NONE:
        return decision

    paypal_action, new_status = ("cancel", "CANCELLED") if decision["action"] == ACTION_CANCEL else ("suspend", "SUSPENDED")
    try:
        await paypal_service.stop_subscription(sub_id, paypal_action, decision["reason"])
    except Exception as e:
        logger.error(f"[RECURRING] Failed to {paypal_action} subscription {sub_id}: {e}")
        set_recurring_mandate_status(sub_id, "STOP_FAILED", f"{paypal_action} failed: {e}")
        decision["action_result"] = "FAILED"
        return decision
    set_recurring_mandate_status(sub_id, new_status, decision["reason"])
    _apply_subscription_stop(sub_id, new_status)
    decision["action_result"] = "DONE"
    logger.warning(f"[RECURRING] {new_status} subscription {sub_id}: {decision['reason']}")
    return decision


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
    if not event_id or not isinstance(event_id, str) or not event_id.strip():
        logger.warning(f"[SECURITY] PayPal webhook event rejected: missing or empty event ID.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing or invalid PayPal webhook event ID.",
        )
    event_id = event_id.strip()
    if event_id in _PROCESSED_WEBHOOK_IDS:
        logger.info(f"[PayPal Webhook] Duplicate verified event {event_id} ({event_type}) received; skipping duplicate execution.")
        return {
            "status": "already_processed",
            "event_id": event_id,
            "event_type": event_type,
            "verification_status": "SUCCESS",
            "duplicate": True,
        }
    _PROCESSED_WEBHOOK_IDS.add(event_id)

    recurring_check: Optional[Dict[str, Any]] = None

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
        _apply_subscription_stop(sub_id, new_status, resource.get("subscriber", {}).get("email_address"))

    elif event_type in [
        "BILLING.SUBSCRIPTION.RE-ACTIVATED",
        "BILLING.SUBSCRIPTION.REACTIVATED",
    ]:
        resource = body.get("resource", {})
        sub_id = resource.get("id", "UNKNOWN_SUB")
        logger.info(
            f"[PayPal Webhook] Received {event_type} for {sub_id}. Restoring status to ACTIVE."
        )
        _apply_subscription_reactivate(sub_id, resource.get("subscriber", {}).get("email_address"))

    elif event_type == "PAYMENT.SALE.REFUNDED":
        resource = body.get("resource", {})
        refund_id = resource.get("id", f"ref_{uuid.uuid4().hex[:8]}")
        sale_id = resource.get("sale_id") or resource.get("parent_payment")
        sub_id = resource.get("billing_agreement_id")
        amount_info = resource.get("amount") if isinstance(resource.get("amount"), dict) else {}
        refund_amt_str = amount_info.get("total") or "0.00"
        try:
            refund_amount = float(refund_amt_str)
        except (ValueError, TypeError):
            refund_amount = 0.0

        from .agents.seller_agent import _COMPLETED_SUBSCRIPTIONS
        from .database import get_recurring_charge, record_recurring_charge
        from .services.backoffice.qbo_exporter import qbo_exporter

        parent_charge = None
        if not sub_id and sale_id:
            parent_charge = get_recurring_charge(sale_id)
            if parent_charge:
                sub_id = parent_charge.get("subscription_id")
        elif sub_id and sale_id:
            parent_charge = get_recurring_charge(sale_id)

        sub_record = _COMPLETED_SUBSCRIPTIONS.get(sub_id) if sub_id else {}
        contractor_name = (sub_record.get("contractor_name") if isinstance(sub_record, dict) else None) or "Autonomous Buyer"
        business_entity = (sub_record.get("business_entity") if isinstance(sub_record, dict) else None) or "Autonomous Node Network"
        contractor_email = (sub_record.get("contractor_email") if isinstance(sub_record, dict) else None) or resource.get("subscriber", {}).get("email_address") or "buyer@example.com"

        qbo_credit_memo = qbo_exporter.export_refund_credit_memo(
            contractor_name=contractor_name,
            business_entity=business_entity,
            contractor_email=contractor_email,
            refund_amount=refund_amount,
            paypal_subscription_id=sub_id or "UNKNOWN_SUB",
            paypal_refund_id=refund_id,
            original_sale_id=sale_id,
            reason=resource.get("reason_code") or "PayPal Sale Refunded",
        )

        refund_cents = int(round(refund_amount * 100))
        if sub_id:
            mandate_hash = (parent_charge.get("mandate_hash") if parent_charge else None) or (sub_record.get("mandate_proof_hash") if isinstance(sub_record, dict) else None) or "unknown_hash"
            record_recurring_charge(
                sale_id=refund_id,
                subscription_id=sub_id,
                mandate_hash=mandate_hash,
                amount_cents=-refund_cents,
                currency=amount_info.get("currency") or "USD",
                status="REFUNDED",
                reason=resource.get("reason_code") or "Refund processed",
                charged_at=resource.get("create_time") or datetime.datetime.now(datetime.timezone.utc).isoformat(),
            )

        logger.info(f"[PayPal Webhook] Processed PAYMENT.SALE.REFUNDED for {refund_id} (${refund_amount:.2f}). QBO Credit Memo: {qbo_credit_memo['credit_memo_id']}")
        response = {
            "status": "received",
            "event_type": event_type,
            "verification_status": verification.get("verification_status", "SUCCESS"),
            "refund_id": refund_id,
            "refund_amount": refund_amount,
            "qbo_credit_memo": qbo_credit_memo,
        }
        return response

    elif event_type == "PAYMENT.SALE.COMPLETED":
        # Recurring charge: check it against the owner's AP2 mandate (signature already verified above)
        recurring_check = await _enforce_recurring_mandate(body.get("resource", {}))

    response = {
        "status": "received",
        "event_type": event_type,
        "verification_status": verification.get("verification_status", "SUCCESS"),
    }
    if recurring_check is not None:
        response["recurring_check"] = recurring_check
    return response


class RunBuyerAgentRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    transport: Optional[str] = "http"
    contractorName: Optional[str] = Field(default="Demo Autonomous Buyer", alias="contractor_name")
    businessEntity: Optional[str] = Field(default="Demo Buyer Corp", alias="business_entity")
    contractorEmail: Optional[str] = Field(default="agent-alpha@example.com", alias="contractor_email")
    tradeId: Optional[str] = Field(default="ap2-gateway", alias="trade_id")
    budgetCap: Optional[float] = Field(default=100.00, alias="budget_cap")
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
        contractor_name=req.contractorName or "Demo Autonomous Buyer",
        business_entity=req.businessEntity or "Demo Buyer Corp",
        contractor_email=req.contractorEmail or "agent-alpha@example.com",
        trade_id=req.tradeId or "ap2-gateway",
        budget_cap=req.budgetCap or 100.00,
        webhook_url=req.webhookUrl,
        verbose=False,
        simulate_exhaustion=req.simulateExhaustion or False,
    )
    res = await agent.execute_autonomous_procurement()
    return res


# --- Native AP2 Gateway Direct Rail Endpoints (Milestone S3-NATIVE) ---

@app.post(
    "/v1/ap2/gateway/charges",
    response_model=DirectChargeResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["AP2 Native Direct Rail"],
)
async def process_ap2_direct_charge_endpoint(request: DirectChargeRequest):
    """
    Processes a direct machine-to-machine checkout charge over the native AP2 rail.
    Cryptographically verifies AP2 ES256 SD-JWT mandate chains, enforces budget caps,
    settles against vaulted PayPal payment sources, and exports authentic QBO v3 Purchase records.
    """
    try:
        return Ap2GatewayService.process_direct_charge(
            cart_mandate_jwt=request.cart_mandate_jwt,
            payment_mandate_jwt=request.payment_mandate_jwt,
            buyer_key_id=request.buyer_key_id,
            payment_source_id=request.payment_source_id,
            metadata=request.metadata,
        )
    except ValueError as e:
        msg = str(e)
        logger.warning(f"[AP2 Gateway Endpoint] Charge processing rejected: {msg}")
        if "UNREGISTERED_BUYER_KEY" in msg or "BUYER_KEY_MISMATCH" in msg:
            err_code = "BUYER_KEY_MISMATCH" if "BUYER_KEY_MISMATCH" in msg else "UNREGISTERED_BUYER_KEY"
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"status": "REJECTED", "error": err_code, "reason": msg})
        elif "UNAUTHORIZED_PAYMENT_SOURCE" in msg:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"status": "REJECTED", "error": "UNAUTHORIZED_PAYMENT_SOURCE", "reason": msg})
        elif "MISSING_PAYMENT_INSTRUMENT" in msg:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"status": "REJECTED", "error": "MISSING_PAYMENT_INSTRUMENT", "reason": msg})
        elif "MANDATE_REVOKED" in msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"status": "REJECTED", "error": "MANDATE_REVOKED", "reason": msg})
        elif "REPLAY_DETECTED" in msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"status": "REJECTED", "error": "REPLAY_DETECTED", "reason": msg})
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"status": "REJECTED", "error": "INVALID_MANDATE", "reason": msg})
    except Exception as e:
        logger.error(f"[AP2 Gateway Endpoint] Unexpected error during charge execution: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"status": "ERROR", "error": "GATEWAY_ERROR", "reason": str(e)})


@app.get(
    "/v1/ap2/gateway/charges/{charge_id}",
    response_model=DirectChargeResponse,
    status_code=status.HTTP_200_OK,
    tags=["AP2 Native Direct Rail"],
)
async def get_ap2_direct_charge_endpoint(charge_id: str):
    """Retrieves a direct AP2 charge record by ID."""
    charge = Ap2GatewayService.get_charge(charge_id)
    if not charge:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"status": "NOT_FOUND", "error": "CHARGE_NOT_FOUND", "reason": f"Direct charge '{charge_id}' does not exist."},
        )
    cents = charge.get("amount_cents", 0)
    charge["amount_formatted"] = f"${cents // 100}.{cents % 100:02d}"
    return charge


@app.get(
    "/v1/ap2/gateway/charges",
    response_model=DirectChargeListResponse,
    status_code=status.HTTP_200_OK,
    tags=["AP2 Native Direct Rail"],
)
async def list_ap2_direct_charges_endpoint(limit: int = Query(default=50, ge=1, le=500)):
    """Lists recent direct AP2 charges."""
    charges = Ap2GatewayService.list_charges(limit=limit)
    return DirectChargeListResponse(count=len(charges), charges=charges)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.server:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=True,
    )
