"""
AP2 Autonomous Model Context Protocol (MCP) Server.
Implements the JSON-RPC 2.0 MCP specification over HTTP (POST /mcp) and stdio.
Allows external autonomous agents (Grok, ChatGPT, Claude, Cursor) to discover
and invoke AP2 compute capabilities, mandate evaluation, and node provisioning.
"""

import os
import re
import sys
import json
import math
import logging
import asyncio
import datetime
from typing import Dict, Any, Optional, List, Set
from pydantic import ValidationError
from .agents.seller_agent import seller_agent, SELLER_MCP_TOOLS
from .config import settings
from .services.plan_catalog import plan_summary

logger = logging.getLogger("ap2_mcp_server")

PROTOCOL_VERSION = "2024-11-05"

SERVER_INFO = {
    "name": "ap2-seller-node",
    "version": "1.0.0",
}

_MCP_WIRE_FRAMES: List[Dict[str, Any]] = []
_MAX_WIRE_FRAMES = 100
_WIRE_SUBSCRIBERS: Set[asyncio.Queue] = set()

# The public wire inspector shows protocol shape, never identities or redeemable tokens
_REDACTED_KEYS = {
    "contractor_email", "contractorEmail", "email", "payer_email", "buyer_email", "buyerEmail",
    "offer_id", "offerId", "mandate_proof_hash", "mandateProofHash", "proof_hash",
    "counter_offer_mandate_hash", "counterOfferMandateHash", "traceable_proof",
    "subscription_id", "active_subscription_id", "replaces_subscription_id",
    "current_subscription_id", "paypal_subscription_id", "approval_url",
    "payment_token", "vault_id", "payer_id",
}
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_OFFER_RE = re.compile(r"\boff_[A-Za-z0-9_]+")
_SUB_ID_RE = re.compile(r"\bI-[A-Z0-9][A-Z0-9-]{5,}")


def _redact_frame(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: ("***" if k in _REDACTED_KEYS and v not in (None, "") else _redact_frame(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact_frame(v) for v in obj]
    if isinstance(obj, str):
        if obj.lstrip()[:1] in ("{", "["):
            try:
                return json.dumps(_redact_frame(json.loads(obj)), indent=2)
            except ValueError:
                pass
        obj = _EMAIL_RE.sub("***@***", obj)
        obj = _OFFER_RE.sub("off_***", obj)
        return _SUB_ID_RE.sub("I-***", obj)
    return obj


def broadcast_wire_frame(direction: str, frame: Dict[str, Any], method: Optional[str] = None):
    entry = {
        "id": f"frame-{len(_MCP_WIRE_FRAMES) + 1}",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "direction": direction,
        "method": method or frame.get("method") or "response",
        "frame": _redact_frame(frame),
    }
    _MCP_WIRE_FRAMES.append(entry)
    if len(_MCP_WIRE_FRAMES) > _MAX_WIRE_FRAMES:
        _MCP_WIRE_FRAMES.pop(0)

    dead_queues = []
    for q in list(_WIRE_SUBSCRIBERS):
        try:
            q.put_nowait(entry)
        except asyncio.QueueFull:
            pass
        except Exception:
            dead_queues.append(q)
    for dq in dead_queues:
        _WIRE_SUBSCRIBERS.discard(dq)


def subscribe_wire_stream() -> asyncio.Queue:
    q = asyncio.Queue(maxsize=100)
    _WIRE_SUBSCRIBERS.add(q)
    return q


def unsubscribe_wire_stream(q: asyncio.Queue):
    _WIRE_SUBSCRIBERS.discard(q)


def get_recent_wire_frames() -> List[Dict[str, Any]]:
    return list(_MCP_WIRE_FRAMES)


class InvalidParams(ValueError):
    """Raised for tool arguments that fail validation (JSON-RPC -32602)."""


def _rpc_error(req_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _num(arguments: Dict[str, Any], key: str, default: Any = None, minimum: float = 0.0) -> Optional[float]:
    """Parses a finite numeric tool argument >= minimum; None stays None when the default is None."""
    raw = arguments.get(key, default)
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise InvalidParams(f"'{key}' must be a number.")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise InvalidParams(f"'{key}' must be a number.")
    if not math.isfinite(value) or value < minimum:
        raise InvalidParams(f"'{key}' must be a finite number >= {minimum:g}.")
    return value


async def process_mcp_request(request_data: Any) -> Optional[Dict[str, Any]]:
    """
    Processes a single JSON-RPC 2.0 MCP request and returns the standard response.
    Broadcasts wire frames to real-time subscribers.
    """
    if not isinstance(request_data, dict):
        return _rpc_error(None, -32600, "Invalid Request: expected a JSON-RPC 2.0 request object.")
    method = request_data.get("method")
    broadcast_wire_frame("incoming", request_data, method=method)
    resp = await _handle_mcp_request_internal(request_data)
    if resp is not None:
        broadcast_wire_frame("outgoing", resp, method=method)
    return resp


async def _handle_mcp_request_internal(request_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    jsonrpc = "2.0"
    req_id = request_data.get("id")
    method = request_data.get("method")
    params = request_data.get("params")
    if request_data.get("jsonrpc") != "2.0":
        return _rpc_error(req_id, -32600, "Invalid Request: 'jsonrpc' must be \"2.0\".")
    if not isinstance(method, str) or not method:
        return _rpc_error(req_id, -32600, "Invalid Request: 'method' must be a non-empty string.")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return _rpc_error(req_id, -32602, "Invalid params: 'params' must be an object.")

    logger.info(f"[MCP] Received method: '{method}' (id: {req_id})")

    # 1. Handle initialize handshake
    if method == "initialize":
        instructions = (
            "AP2 Autonomous Compute Protocol Engine.\n"
            "AP2 connects autonomous agent buyers directly to verified compute worker nodes and service gateways with automated PayPal recurring billing.\n"
            "AP2 Monthly Subscription Plans:\n"
            f"- 'ap2-batch': {plan_summary('ap2-batch', profile='ap2')}\n"
            f"- 'ap2-gateway': {plan_summary('ap2-gateway', profile='ap2')}\n"
            f"- 'ap2-cluster': {plan_summary('ap2-cluster', profile='ap2')}\n"
            "Every autonomous workload (batch processing, gateway routing, cluster execution) is supported across all tiers.\n"
            "Recommended buyer procurement workflow:\n"
            "1. inspect_subscription_tiers: Inspect AP2 compute subscription tiers, workload task quotas ($49.99 / $79.99 / $179.99), and compute features.\n"
            "2. negotiate_tier_terms: Submit desired tier_id, buyer_agent_id, buyer_email, and monthly_budget_cap. If budget < asking price, returns pre-approved counter-offer down-tiering to a plan within budget with a signed AP2 Intent Mandate.\n"
            "3. purchase_subscription: Bind agreed tier_id, agreed_monthly_rate, mandate_proof_hash, and buyer_email to PayPal Recurring Vault for automated billing.\n"
            "4. provision_compute_node: (Optional) Allocate dedicated autonomous compute node endpoint (mcp+https) upon verified subscription."
        )
        return {
            "jsonrpc": jsonrpc,
            "id": req_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {"listChanged": False},
                },
                "serverInfo": SERVER_INFO,
                "instructions": instructions,
            },
        }

    # 2. Handle notifications/initialized
    if method == "notifications/initialized":
        logger.info("[MCP] Client completed initialization handshake.")
        return None

    # 3. Handle ping
    if method == "ping":
        return {"jsonrpc": jsonrpc, "id": req_id, "result": {}}

    # 4. Handle tools/list
    if method == "tools/list":
        tools_list = []
        for tool in SELLER_MCP_TOOLS:
            tools_list.append({
                "name": tool["name"],
                "description": tool["description"],
                "inputSchema": tool.get("input_schema", {"type": "object", "properties": {}}),
            })
        return {
            "jsonrpc": jsonrpc,
            "id": req_id,
            "result": {
                "tools": tools_list,
            },
        }

    # 5. Handle tools/call
    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return _rpc_error(req_id, -32602, "Invalid params: 'arguments' must be an object.")
        logger.info(f"[MCP] Invoking tool '{tool_name}' with argument keys: {sorted(arguments)}")

        try:
            if tool_name == "inspect_subscription_tiers":
                result = await seller_agent.inspect_subscription_tiers()

            elif tool_name == "get_service_catalog":
                result = await seller_agent.get_service_catalog()

            elif tool_name == "negotiate_tier_terms":
                email = arguments.get("buyer_email") or arguments.get("contractor_email")
                result = await seller_agent.negotiate_tier_terms(
                    buyer_agent_id=arguments.get("buyer_agent_id", "buyer-agent-01"),
                    tier_id=arguments.get("tier_id", "ap2-gateway"),
                    monthly_budget_cap=_num(arguments, "monthly_budget_cap", 60.00),
                    contractor_email=email,
                    proposed_price=_num(arguments, "proposed_price"),
                    recurrence=arguments.get("recurrence", "monthly"),
                    category=arguments.get("category", "autonomous-node-service"),
                    buyer_intent_mandate=arguments.get("buyer_intent_mandate"),
                    buyer_email=email,
                    checkout_jwt=arguments.get("checkout_jwt"),
                )

            elif tool_name == "purchase_subscription":
                email = arguments.get("buyer_email") or arguments.get("contractor_email")
                result = await seller_agent.purchase_subscription(
                    tier_id=arguments.get("tier_id"),
                    agreed_monthly_rate=_num(arguments, "agreed_monthly_rate"),
                    mandate_proof_hash=arguments.get("mandate_proof_hash"),
                    contractor_email=email,
                    offer_id=arguments.get("offer_id"),
                    buyer_email=email,
                    checkout_mandate_chain=arguments.get("checkout_mandate_chain"),
                    payment_mandate_chain=arguments.get("payment_mandate_chain"),
                    checkout_jwt=arguments.get("checkout_jwt"),
                )

            elif tool_name == "evaluate_spending_mandate":
                amount = _num(arguments, "amount", 79.99, minimum=0.01)
                mb_cap = _num(arguments, "monthly_budget_cap")
                email = arguments.get("buyer_email") or arguments.get("contractor_email")
                result = await seller_agent.verify_spending_mandate(
                    buyer_agent_id=arguments.get("buyer_agent_id", "buyer-agent-01"),
                    amount=amount,
                    recurrence=arguments.get("recurrence", "monthly"),
                    category=arguments.get("category", "autonomous-node-service"),
                    monthly_budget_cap=mb_cap if mb_cap is not None else amount,
                    contractor_email=email,
                )

            elif tool_name == "provision_compute_node":
                buyer_email = arguments.get("buyer_email") or arguments.get("contractor_email") or os.getenv("A2A_DEFAULT_EMAIL", "buyer@example.com")
                result = await seller_agent.provision_compute_node(
                    subscription_id=arguments.get("subscription_id", "I-MOCK-SUB-01"),
                    buyer_email=buyer_email,
                    node_type=arguments.get("node_type", "gateway"),
                )

            elif tool_name == "dispatch_zapier_mcp":
                email = arguments.get("buyer_email") or arguments.get("contractor_email") or "buyer-agent@autonomous-procurement.org"
                endpoint = arguments.get("node_endpoint") or arguments.get("allocated_did") or "mcp+https://gateway-01.acme-systems.io/agents/gateway"
                vertical = arguments.get("service_vertical") or arguments.get("trade_vertical") or "Autonomous Compute"
                sub_name = arguments.get("subscriber_name") or arguments.get("contractor_name") or "Autonomous Buyer Agent"
                entity = arguments.get("business_entity") or "Autonomous Node Network"
                result = await seller_agent.dispatch_zapier_mcp(
                    workflow_type=arguments.get("workflow_type", "a2a_onboarding"),
                    subscriber_name=sub_name,
                    business_entity=entity,
                    node_endpoint=endpoint,
                    service_vertical=vertical,
                    monthly_subscription_fee=_num(arguments, "monthly_subscription_fee", 79.99),
                    paypal_subscription_id=arguments.get("paypal_subscription_id", "I-AUTONOMOUS-8902"),
                    buyer_email=email,
                    mandate_proof_hash=arguments.get("mandate_proof_hash"),
                    webhook_url=arguments.get("webhook_url") if settings.mock_external_apis else None,
                )

            elif tool_name == "get_subscription_details":
                result = await seller_agent.get_subscription_details(
                    subscription_id=arguments.get("subscription_id", ""),
                )

            else:
                return {
                    "jsonrpc": jsonrpc,
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method or Tool '{tool_name}' not found.",
                    },
                }

            return {
                "jsonrpc": jsonrpc,
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, indent=2),
                        }
                    ],
                    "isError": False,
                },
            }

        except InvalidParams as e:
            return _rpc_error(req_id, -32602, f"Invalid params: {e}")
        except ValidationError as e:
            fields = ", ".join(".".join(str(p) for p in err["loc"]) for err in e.errors())
            return _rpc_error(req_id, -32602, f"Invalid params: {fields}")
        except Exception as e:
            logger.error(f"[MCP] Error executing tool '{tool_name}': {e}", exc_info=True)
            return _rpc_error(req_id, -32603, "Internal error: tool execution failed.")

    # Unknown method
    return {
        "jsonrpc": jsonrpc,
        "id": req_id,
        "error": {
            "code": -32601,
            "message": f"Method '{method}' not supported by AP2 MCP Server.",
        },
    }


def run_stdio_server():
    """Runs standard I/O loop for desktop MCP clients (Claude Desktop, Cursor, etc.). Cross-platform Windows & POSIX."""
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    )
    logger.info("[MCP] AP2 Autonomous Seller MCP Server starting over stdio (PID: %d)...", os.getpid())
    try:
        for line in sys.stdin:
            text = line.strip()
            if not text:
                continue
            try:
                req = json.loads(text)
                resp = asyncio.run(process_mcp_request(req))
                if resp is not None:
                    sys.stdout.write(json.dumps(resp) + "\n")
                    sys.stdout.flush()
            except Exception as e:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {str(e)}"},
                }
                sys.stdout.write(json.dumps(err_resp) + "\n")
                sys.stdout.flush()
    finally:
        logger.info("[MCP] stdin closed; AP2 MCP Server exiting cleanly (PID: %d).", os.getpid())


if __name__ == "__main__":
    run_stdio_server()
