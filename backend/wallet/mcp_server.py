"""
AP2 Buyer Wallet MCP Server (stdio, JSON-RPC 2.0).

Runs next to the seller's MCP server in Claude Desktop. Claude negotiates with the seller,
hands the merchant-signed checkout to this wallet for signing, and passes the signed
mandate chains back to the seller. Claude never sees a private key, and the wallet signs
only what fits the owner's signed limits.

    python -m backend.wallet.mcp_server          # serve over stdio
    python -m backend.wallet.mcp_server --init   # create the agent key, print its public JWK
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Dict, Optional

from .wallet import BuyerWallet, WalletRefusal, init_agent_key

logger = logging.getLogger("ap2_wallet_mcp")

SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
SERVER_INFO = {"name": "ap2-buyer-wallet", "version": "1.0.0"}

INSTRUCTIONS = (
    "AP2 Buyer Wallet. Holds the buyer agent's signing key and the owner's signed spending limits.\n"
    "1. get_spending_limits: read the owner's limits (buyer_email, monthly_budget_cap, allowed tiers, remaining budget).\n"
    "2. Negotiate with the seller using that buyer_email and monthly_budget_cap.\n"
    "3. sign_checkout: pass the seller's checkout_jwt. The wallet signs only if the merchant-signed checkout "
    "fits the owner's limits; otherwise it refuses and explains why.\n"
    "4. Send the returned checkout_mandate_chain and payment_mandate_chain to the seller's purchase_subscription."
)

TOOLS = [
    {
        "name": "get_spending_limits",
        "description": (
            "Returns the owner-signed AP2 spending limits this wallet enforces: buyer_email, monthly_budget_cap, "
            "allowed tiers and merchants, remaining budget, and expiry. Call this before negotiating."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "sign_checkout",
        "description": (
            "Verifies a merchant-signed checkout_jwt (from the seller's negotiate_tier_terms) against the owner's "
            "signed limits and, only if it fits, returns AP2 v0.2 checkout_mandate_chain and payment_mandate_chain "
            "signed by the buyer agent key. Price, tier and merchant are read from the merchant's signature, not "
            "from arguments."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["checkout_jwt"],
            "properties": {
                "checkout_jwt": {
                    "type": "string",
                    "description": "The checkout_jwt returned by the seller's negotiate_tier_terms.",
                },
            },
            "additionalProperties": False,
        },
    },
]


def _rpc_error(req_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _tool_result(payload: Dict[str, Any], is_error: bool) -> Dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(payload, indent=2)}], "isError": is_error}


def handle_request(request: Any, wallet: Optional[BuyerWallet] = None) -> Optional[Dict[str, Any]]:
    """Handles one JSON-RPC message. Returns None for notifications."""
    if not isinstance(request, dict):
        return _rpc_error(None, -32600, "Invalid Request: expected a JSON-RPC 2.0 request object.")
    if "id" not in request:
        # Notifications (e.g. notifications/initialized) never get a response
        return None
    req_id = request.get("id")
    method = request.get("method")
    params = request.get("params")
    if request.get("jsonrpc") != "2.0":
        return _rpc_error(req_id, -32600, "Invalid Request: 'jsonrpc' must be \"2.0\".")
    if not isinstance(method, str) or not method:
        return _rpc_error(req_id, -32600, "Invalid Request: 'method' must be a non-empty string.")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return _rpc_error(req_id, -32602, "Invalid params: 'params' must be an object.")

    if method == "initialize":
        requested = params.get("protocolVersion")
        version = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else SUPPORTED_PROTOCOL_VERSIONS[0]
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
                "instructions": INSTRUCTIONS,
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return _rpc_error(req_id, -32602, "Invalid params: 'arguments' must be an object.")
        w = wallet or BuyerWallet()
        try:
            if name == "get_spending_limits":
                payload = w.describe_limits()
            elif name == "sign_checkout":
                payload = w.sign_checkout(arguments.get("checkout_jwt"))
            else:
                return _rpc_error(req_id, -32601, f"Tool '{name}' not found.")
        except WalletRefusal as refusal:
            logger.warning("[WALLET] Refused %s: %s", name, refusal.code)
            return {"jsonrpc": "2.0", "id": req_id, "result": _tool_result(refusal.to_dict(), is_error=True)}
        except Exception:
            logger.error("[WALLET] Unexpected error in %s", name, exc_info=True)
            return _rpc_error(req_id, -32603, "Internal error: wallet tool failed; nothing was signed.")
        return {"jsonrpc": "2.0", "id": req_id, "result": _tool_result(payload, is_error=False)}

    return _rpc_error(req_id, -32601, f"Method '{method}' not supported by the AP2 Buyer Wallet.")


def run_stdio_server() -> None:
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    )
    logger.info("[WALLET] AP2 Buyer Wallet MCP Server starting over stdio (PID: %d)...", os.getpid())
    wallet = BuyerWallet()
    for line in sys.stdin:
        text = line.strip()
        if not text:
            continue
        try:
            request = json.loads(text)
        except ValueError as e:
            response = _rpc_error(None, -32700, f"Parse error: {e}")
        else:
            response = handle_request(request, wallet)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
    logger.info("[WALLET] stdin closed; exiting (PID: %d).", os.getpid())


if __name__ == "__main__":
    if "--init" in sys.argv[1:]:
        print(json.dumps(init_agent_key()))
    else:
        run_stdio_server()
