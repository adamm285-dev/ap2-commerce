"""
FieldSmith Pro Model Context Protocol (MCP) Server.
Implements the JSON-RPC 2.0 MCP specification over HTTP (POST /mcp) and stdio.
Allows external autonomous agents (Grok, ChatGPT, Claude, Cursor) to discover
and invoke FieldSmith telephony capabilities, mandate evaluation, and line provisioning.
"""

import os
import sys
import json
import logging
import asyncio
import datetime
from typing import Dict, Any, Optional, List, Set
from .agents.seller_agent import seller_agent, SELLER_MCP_TOOLS

logger = logging.getLogger("fieldsmith_mcp_server")

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {
    "name": "fieldsmith-pro-a2a-seller",
    "version": "1.0.0",
}

_MCP_WIRE_FRAMES: List[Dict[str, Any]] = []
_MAX_WIRE_FRAMES = 100
_WIRE_SUBSCRIBERS: Set[asyncio.Queue] = set()


def broadcast_wire_frame(direction: str, frame: Dict[str, Any], method: Optional[str] = None):
    entry = {
        "id": f"frame-{len(_MCP_WIRE_FRAMES) + 1}",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "direction": direction,
        "method": method or frame.get("method") or "response",
        "frame": frame,
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


async def process_mcp_request(request_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Processes a single JSON-RPC 2.0 MCP request and returns the standard response.
    Broadcasts wire frames to real-time subscribers.
    """
    method = request_data.get("method")
    broadcast_wire_frame("incoming", request_data, method=method)
    resp = await _handle_mcp_request_internal(request_data)
    if resp is not None:
        broadcast_wire_frame("outgoing", resp, method=method)
    return resp


async def _handle_mcp_request_internal(request_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    jsonrpc = request_data.get("jsonrpc", "2.0")
    req_id = request_data.get("id")
    method = request_data.get("method")
    params = request_data.get("params", {})

    logger.info(f"[MCP] Received method: '{method}' (id: {req_id})")

    # 1. Handle initialize handshake
    if method == "initialize":
        return {
            "jsonrpc": jsonrpc,
            "id": req_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {"listChanged": False},
                },
                "serverInfo": SERVER_INFO,
                "instructions": (
                    "FieldSmith Pro Autonomous Agent-to-Agent (A2A) Commerce Protocol Engine.\n"
                    "FieldSmith is a SaaS telephony AI voice receptionist and screening platform for trade contractors (Flooring, Roofing, Plumbing, Remodeling, etc.).\n"
                    "FieldSmith Monthly Subscription Plans:\n"
                    "- 'solo-starter': $49.99/mo (100 AI screening minutes, dedicated 10DLC phone line)\n"
                    "- 'fieldsmith-pro' (or 'flooring-tile'): $79.99/mo (300 AI screening minutes, specialized trade takeoff scoping)\n"
                    "- 'pro-dispatch': $179.99/mo (1,000 AI screening minutes, multi-crew dispatch, ERP automation)\n"
                    "Recommended buyer procurement workflow:\n"
                    "1. inspect_subscription_tiers: Inspect FieldSmith SaaS subscription plans, quotas (screening minutes), and pricing tiers ($49.99 / $79.99 / $179.99).\n"
                    "2. negotiate_tier_terms: Submit desired tier_id, buyer_agent_id, contractor_email, and monthly_budget_cap. If budget < asking price, returns pre-approved counter-offer down-tiering to a plan within budget with a signed AP2 Intent Mandate.\n"
                    "3. purchase_subscription: Bind agreed tier_id, agreed_monthly_rate, mandate_proof_hash, and contractor_email to PayPal Recurring Vault for automated billing.\n"
                    "4. provision_telecom_line: (Optional) Allocate dedicated local 10DLC telephone DID upon verified subscription."
                ),
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
        # Format tools according to MCP specification
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
        arguments = params.get("arguments", {})
        logger.info(f"[MCP] Invoking tool '{tool_name}' with arguments: {arguments}")

        try:
            if tool_name == "inspect_subscription_tiers":
                result = await seller_agent.inspect_subscription_tiers()

            elif tool_name == "get_service_catalog":
                result = await seller_agent.get_service_catalog()

            elif tool_name == "negotiate_tier_terms":
                result = await seller_agent.negotiate_tier_terms(
                    buyer_agent_id=arguments.get("buyer_agent_id", "buyer-agent-01"),
                    tier_id=arguments.get("tier_id", "flooring-tile"),
                    monthly_budget_cap=float(arguments.get("monthly_budget_cap", 60.00)),
                    contractor_email=arguments.get("contractor_email"),
                    proposed_price=float(arguments["proposed_price"]) if "proposed_price" in arguments and arguments["proposed_price"] is not None else None,
                    recurrence=arguments.get("recurrence", "monthly"),
                    category=arguments.get("category", "TELEPHONY_AI_SCREENER"),
                    buyer_intent_mandate=arguments.get("buyer_intent_mandate"),
                )

            elif tool_name == "purchase_subscription":
                raw_rate = arguments.get("agreed_monthly_rate")
                result = await seller_agent.purchase_subscription(
                    tier_id=arguments.get("tier_id"),
                    agreed_monthly_rate=float(raw_rate) if raw_rate is not None else None,
                    mandate_proof_hash=arguments.get("mandate_proof_hash"),
                    contractor_email=arguments.get("contractor_email"),
                    offer_id=arguments.get("offer_id"),
                )

            elif tool_name == "evaluate_spending_mandate":
                # Ensure no silent $100 default; preserve buyer's explicit cap
                mb_cap = arguments.get("monthly_budget_cap")
                if mb_cap is None:
                    mb_cap = arguments.get("amount", 79.99)
                result = await seller_agent.verify_spending_mandate(
                    buyer_agent_id=arguments.get("buyer_agent_id", "buyer-agent-01"),
                    amount=float(arguments.get("amount", 79.99)),
                    recurrence=arguments.get("recurrence", "monthly"),
                    category=arguments.get("category", "TELEPHONY_AI_SCREENER"),
                    monthly_budget_cap=float(mb_cap),
                )

            elif tool_name == "calculate_quote":
                result = await seller_agent.calculate_quote(
                    trade_id=arguments.get("trade_id", "flooring-tile"),
                    square_footage=float(arguments.get("square_footage", 500)),
                    material_type=arguments.get("material_type", "Porcelain"),
                    postal_code=arguments.get("postal_code", "33801"),
                )

            elif tool_name == "provision_telecom_line":
                default_email = os.getenv("A2A_DEFAULT_EMAIL", "contractor@example.com")
                result = await seller_agent.provision_telecom_line(
                    subscription_id=arguments.get("subscription_id", "I-MOCK-SUB-01"),
                    contractor_email=arguments.get("contractor_email", default_email),
                    area_code=arguments.get("area_code", "863"),
                    simulate_exhaustion=arguments.get("simulate_exhaustion", False),
                )

            elif tool_name == "dispatch_zapier_mcp":
                result = await seller_agent.dispatch_zapier_mcp(
                    workflow_type=arguments.get("workflow_type", "a2a_onboarding"),
                    contractor_name=arguments.get("contractor_name", "Marcus Miller"),
                    business_entity=arguments.get("business_entity", "Miller Custom Flooring LLC"),
                    allocated_did=arguments.get("allocated_did", "+1 (863) 267-8902"),
                    trade_vertical=arguments.get("trade_vertical", "Tile & Custom Flooring"),
                    monthly_subscription_fee=float(arguments.get("monthly_subscription_fee", 79.99)),
                    paypal_subscription_id=arguments.get("paypal_subscription_id", "I-AUTONOMOUS-8902"),
                    contractor_email=arguments.get("contractor_email", "marcus@millercustomfloors.com"),
                    mandate_proof_hash=arguments.get("mandate_proof_hash"),
                    webhook_url=arguments.get("webhook_url"),
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

        except Exception as e:
            logger.error(f"[MCP] Error executing tool '{tool_name}': {e}", exc_info=True)
            return {
                "jsonrpc": jsonrpc,
                "id": req_id,
                "error": {
                    "code": -32000,
                    "message": f"Tool execution failed: {str(e)}",
                },
            }

    # Unknown method
    return {
        "jsonrpc": jsonrpc,
        "id": req_id,
        "error": {
            "code": -32601,
            "message": f"Method '{method}' not supported by FieldSmith MCP Server.",
        },
    }


def run_stdio_server():
    """Runs standard I/O loop for desktop MCP clients (Claude Desktop, Cursor, etc.). Cross-platform Windows & POSIX."""
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    )
    logger.info("[MCP] FieldSmith Pro MCP Server starting over stdio (PID: %d)...", os.getpid())
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
        logger.info("[MCP] stdin closed; FieldSmith MCP Server exiting cleanly (PID: %d).", os.getpid())


if __name__ == "__main__":
    run_stdio_server()
