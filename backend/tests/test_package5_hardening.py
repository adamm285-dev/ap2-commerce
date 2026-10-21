import json
import subprocess
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.server import app

client = TestClient(app)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_well_known_mcp_discovery_hardening():
    """GET /.well-known/mcp.json must use backend.wallet.mcp_server, no public SSE URL, no Ed25519, no immutable audit."""
    res = client.get("/.well-known/mcp.json")
    assert res.status_code == 200
    data = res.json()

    # Wallet server command
    companion = data.get("companion_wallet_server", {})
    assert companion.get("name") == "ap2-buyer-wallet"
    assert companion.get("command") == "python -m backend.wallet.mcp_server"

    # No public SSE URL in mcp_server
    mcp_srv = data.get("mcp_server", {})
    assert "sse_url" not in mcp_srv
    assert "https://api.ap2-commerce.org/sse" not in json.dumps(data)

    # Agent instructions point to /llms.txt
    assert data.get("agent_instructions") == "https://api.ap2-commerce.org/llms.txt"

    # No immutable audit or Ed25519 purchase claims
    compliance = data.get("regulatory_compliance", {})
    assert compliance.get("ap2_mandate_verification") is True
    assert compliance.get("sd_jwt_es256_signatures") is True
    assert "ed25519_signatures" not in compliance
    assert "audit_trail_retention" not in compliance
    assert "immutable" not in json.dumps(compliance).lower()


def test_public_well_known_mcp_file():
    """public/.well-known/mcp.json file matches security hardening criteria."""
    manifest_path = REPO_ROOT / "public" / ".well-known" / "mcp.json"
    assert manifest_path.exists()
    content = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Companion wallet command
    assert content["companion_wallet_server"]["command"] == "python -m backend.wallet.mcp_server"

    # No sse_url
    assert "sse_url" not in content["mcp_server"]
    assert "https://api.ap2-commerce.org/sse" not in json.dumps(content)

    # No Ed25519 in purchase claims and no immutable audit claims
    attestation = content.get("cryptographic_attestation", {})
    assert "Ed25519" not in attestation.get("signature_standard", "")
    assert "ES256" in attestation.get("signature_standard", "")
    assert "immutable" not in json.dumps(content).lower()


def test_agents_json_discovery():
    """GET /agents.json points at /llms.txt and inspect_subscription_tiers, no public SSE or tile labor catalog."""
    res = client.get("/agents.json")
    assert res.status_code == 200
    data = res.json()

    # Points at /llms.txt, not /public/llms.txt
    assert "/public/llms.txt" not in data.get("notice", "")
    assert "/llms.txt" in data.get("notice", "")
    assert data.get("instructions") == "/llms.txt"

    # Endpoints point to inspect_subscription_tiers, not /api/agent/catalog
    endpoints = data.get("endpoints", {})
    assert "inspect_subscription_tiers" in endpoints
    assert "/api/agent/catalog" not in json.dumps(endpoints)
    assert "sse" not in endpoints


def test_agent_discovery_card_endpoint():
    """GET /.well-known/agent.json points to /llms.txt and inspect_subscription_tiers, no SSE or Ed25519 purchase."""
    res = client.get("/.well-known/agent.json")
    assert res.status_code == 200
    data = res.json()

    assert "/public/llms.txt" not in data.get("notice", "")
    assert "/llms.txt" in data.get("notice", "")
    assert data.get("instructions") == "/llms.txt"

    endpoints = data.get("endpoints", {})
    assert "inspect_subscription_tiers" in endpoints
    assert "/api/agent/catalog" not in json.dumps(endpoints)
    assert "sse" not in endpoints
    assert "wire_stream" not in endpoints

    # Authentication algorithms for AP2 purchase mandate chains
    algos = data.get("authentication", {}).get("algorithms", [])
    assert "ES256" in algos
    assert "Ed25519" not in algos


def test_mcp_config_json_starts_seller_and_wallet():
    """mcp_config.json starts ap2-seller-node and ap2-buyer-wallet (not two seller clients)."""
    cfg_path = REPO_ROOT / "mcp_config.json"
    assert cfg_path.exists()
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    servers = cfg.get("mcpServers", {})
    assert "ap2-seller-node" in servers
    assert "ap2-buyer-wallet" in servers
    assert "ap2-seller-http" not in servers

    seller_args = servers["ap2-seller-node"].get("args", [])
    assert "-m" in seller_args and "backend.mcp_server" in seller_args

    wallet_args = servers["ap2-buyer-wallet"].get("args", [])
    assert "-m" in wallet_args and "backend.wallet.mcp_server" in wallet_args


def test_wallet_command_starts_wallet():
    """Verify that python -m backend.wallet.mcp_server is runnable and starts properly."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "backend.wallet.mcp_server"],
        cwd=str(REPO_ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        # Send an initialize JSON-RPC request to confirm it answers over stdio
        req = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        }) + "\n"
        stdout, _ = proc.communicate(input=req, timeout=5)
        resp = json.loads(stdout.strip())
        assert resp.get("id") == 1
        assert "serverInfo" in resp.get("result", {})
        assert resp["result"]["serverInfo"]["name"] == "ap2-buyer-wallet"
    finally:
        if proc.poll() is None:
            proc.kill()


def test_deck_purchase_404_when_mock_external_apis_is_false(monkeypatch):
    """When mock mode is off, POST /api/agent/deck-purchase returns 404."""
    from backend.config import settings
    monkeypatch.setattr(settings, "mock_external_apis", False)

    res = client.post(
        "/api/agent/deck-purchase",
        json={
            "tier_id": "ap2-gateway",
            "agreed_monthly_rate": 79.99,
            "buyer_email": "test@example.com",
            "contractor_name": "AutonomousBuyerAgent",
            "business_entity": "Acme Compute Co",
            "monthly_budget_cap": 100.0,
        },
    )
    assert res.status_code == 404
