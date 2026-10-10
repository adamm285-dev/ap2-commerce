"""
Buyer wallet (backend/wallet) tests.

The wallet is the separate-process signer that sits next to the seller MCP server in
Claude Desktop. Covers: the full negotiate -> sign -> purchase flow through both MCP
request handlers, every refusal path, budget and recurrence accounting, process
separation from seller code, the merchant key file, and launching both servers from
outside the repository (the Claude Desktop config fix), including the setup script.
"""

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from jwcrypto.jwk import JWK

from ap2.sdk.jwt_helper import create_jwt
from ap2.sdk.utils import b64url_decode, b64url_encode

from backend.mcp_server import process_mcp_request
from backend.server import app
from backend.services import ap2_keys
from backend.services.ap2_keys import get_merchant_public_jwk
from backend.services.ap2_service import create_merchant_checkout
from backend.services.crypto_mandate import sign_es256_challenge
from backend.services.trusted_surface_service import create_trusted_surface_open_mandates
from backend.wallet import mcp_server as wallet_mcp
from backend.wallet.wallet import BuyerWallet, WalletRefusal, init_agent_key

REPO_ROOT = Path(__file__).resolve().parents[2]
client = TestClient(app)


def _new_key(prefix: str) -> JWK:
    return JWK.generate(kty="EC", crv="P-256", kid=f"{prefix}-{uuid.uuid4().hex[:8]}")


def _enroll_owner(owner_key: JWK, email: str) -> None:
    challenge = client.get("/api/agent/keys/challenge").json()["challenge"]
    res = client.post(
        "/api/agent/keys/register",
        json={
            "kid": owner_key.kid,
            "publicKeyJwk": owner_key.export_public(as_dict=True),
            "contractorEmail": email,
            "businessEntity": "Wallet Test Corp",
            "challenge": challenge,
            "challengeSignature": sign_es256_challenge(challenge, owner_key),
        },
    )
    assert res.status_code == 201, res.text


@pytest.fixture
def demo(tmp_path):
    """A configured wallet: agent key, pinned merchant + enrolled owner key, $60/mo owner limits."""
    wdir = tmp_path / "wallet"
    agent_pub = init_agent_key(wdir)
    owner = _new_key("owner-wallet-test")
    email = f"wallet-owner-{uuid.uuid4().hex[:8]}@example.com"
    _enroll_owner(owner, email)
    (wdir / "merchant_public.jwk").write_text(json.dumps(get_merchant_public_jwk()), encoding="utf-8")
    (wdir / "owner_public.jwk").write_text(owner.export_public(), encoding="utf-8")

    def sign_limits(cap=60.0, agent=agent_pub, signer=owner, validity=3600, tiers=None, ceiling=None):
        lim = create_trusted_surface_open_mandates(
            buyer_email=email,
            monthly_budget_cap=cap,
            yearly_budget_ceiling=ceiling,
            allowed_tiers=tiers,
            agent_key=JWK(**agent),
            user_key=signer,
            validity_seconds=validity,
        )
        (wdir / "owner_limits.json").write_text(json.dumps({
            "buyer_email": email,
            "open_checkout_mandate_token": lim["open_checkout_mandate_token"],
            "open_payment_mandate_token": lim["open_payment_mandate_token"],
        }), encoding="utf-8")

    sign_limits()
    return SimpleNamespace(dir=wdir, wallet=BuyerWallet(wdir), owner=owner, email=email, sign_limits=sign_limits)


async def _seller(tool: str, args: dict) -> dict:
    resp = await process_mcp_request(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": args}}
    )
    assert "result" in resp, resp
    return json.loads(resp["result"]["content"][0]["text"])


def _wallet(demo, tool: str, args: dict = None):
    resp = wallet_mcp.handle_request(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": args or {}}},
        demo.wallet,
    )
    result = resp["result"]
    return json.loads(result["content"][0]["text"]), result["isError"]


def _refusal_code(fn, *args) -> str:
    with pytest.raises(WalletRefusal) as exc:
        fn(*args)
    return exc.value.code


# ── Happy path through both MCP servers ─────────────────────────────────────


@pytest.mark.asyncio
async def test_negotiate_sign_purchase_through_seller_and_wallet_mcp(demo):
    limits, is_error = _wallet(demo, "get_spending_limits")
    assert not is_error
    assert limits["monthly_budget_cap"] == 60.0
    assert limits["buyer_email"] == demo.email

    nego = await _seller("negotiate_tier_terms", {
        "buyer_agent_id": "claude-desktop-test",
        "buyer_email": limits["buyer_email"],
        "tier_id": "ap2-gateway",
        "monthly_budget_cap": limits["monthly_budget_cap"],
    })
    assert nego["status"] == "COUNTER_OFFER"

    signed, is_error = _wallet(demo, "sign_checkout", {"checkout_jwt": nego["checkout_jwt"]})
    assert not is_error
    assert signed["status"] == "SIGNED"
    assert signed["tier_id"] == "ap2-batch"
    assert signed["amount_cents"] == 4999

    purchase = await _seller("purchase_subscription", {
        "offer_id": nego["offer_id"],
        "buyer_email": signed["buyer_email"],
        "checkout_mandate_chain": signed["checkout_mandate_chain"],
        "payment_mandate_chain": signed["payment_mandate_chain"],
    })
    assert purchase["status"] == "ACTIVE", purchase

    after, _ = _wallet(demo, "get_spending_limits")
    assert after["signed_so_far_cents"] == 4999
    assert after["purchases_signed"] == 1


# ── Refusals: nothing is signed ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_wallet_refuses_price_above_owner_cap_even_if_agent_overstates_budget(demo):
    # The agent tells the seller its budget is $200; the owner only signed $60
    nego = await _seller("negotiate_tier_terms", {
        "buyer_agent_id": "claude-desktop-test",
        "buyer_email": demo.email,
        "tier_id": "ap2-gateway",
        "monthly_budget_cap": 200.0,
    })
    assert nego["status"] == "APPROVED"

    refused, is_error = _wallet(demo, "sign_checkout", {"checkout_jwt": nego["checkout_jwt"]})
    assert is_error
    assert refused["status"] == "REFUSED"
    assert refused["error"] == "PAYMENT_CONSTRAINT_VIOLATION"
    assert "checkout_mandate_chain" not in refused and "payment_mandate_chain" not in refused

    after, _ = _wallet(demo, "get_spending_limits")
    assert after["signed_so_far_cents"] == 0
    assert after["purchases_signed"] == 0


def test_wallet_refuses_checkout_signed_by_another_key(demo):
    real = create_merchant_checkout(tier_id="ap2-batch", monthly_price=49.99, contractor_email=demo.email)
    payload = json.loads(b64url_decode(real["checkout_jwt"].split(".")[1]))
    forged = create_jwt({"alg": "ES256", "typ": "JWT", "kid": "attacker"}, payload, _new_key("attacker"))
    assert _refusal_code(demo.wallet.sign_checkout, forged) == "CHECKOUT_SIGNATURE_INVALID"


def test_wallet_refuses_checkout_with_tampered_price(demo):
    real = create_merchant_checkout(tier_id="ap2-batch", monthly_price=49.99, contractor_email=demo.email)
    header, body, sig = real["checkout_jwt"].split(".")
    payload = json.loads(b64url_decode(body))
    for total in payload["totals"]:
        total["amount"] = 100
    tampered = ".".join([header, b64url_encode(json.dumps(payload).encode("utf-8")), sig])
    assert _refusal_code(demo.wallet.sign_checkout, tampered) == "CHECKOUT_SIGNATURE_INVALID"


def test_wallet_refuses_tier_the_owner_did_not_allow(demo):
    demo.sign_limits(tiers=["ap2-batch"])
    within_cap_but_wrong_tier = create_merchant_checkout(
        tier_id="ap2-gateway", monthly_price=55.00, contractor_email=demo.email
    )
    code = _refusal_code(demo.wallet.sign_checkout, within_cap_but_wrong_tier["checkout_jwt"])
    assert code == "CHECKOUT_CONSTRAINT_VIOLATION"


def test_wallet_refuses_limits_not_signed_by_pinned_owner(demo):
    demo.sign_limits(signer=_new_key("impostor-owner"))
    assert _refusal_code(demo.wallet.describe_limits) == "OWNER_SIGNATURE_INVALID"
    checkout = create_merchant_checkout(tier_id="ap2-batch", monthly_price=49.99, contractor_email=demo.email)
    assert _refusal_code(demo.wallet.sign_checkout, checkout["checkout_jwt"]) == "OWNER_SIGNATURE_INVALID"


def test_wallet_refuses_limits_bound_to_another_agent(demo):
    demo.sign_limits(agent=_new_key("other-agent").export_public(as_dict=True))
    checkout = create_merchant_checkout(tier_id="ap2-batch", monthly_price=49.99, contractor_email=demo.email)
    assert _refusal_code(demo.wallet.sign_checkout, checkout["checkout_jwt"]) == "AGENT_KEY_MISMATCH"


def test_wallet_refuses_expired_limits(demo):
    demo.sign_limits(validity=-60)
    checkout = create_merchant_checkout(tier_id="ap2-batch", monthly_price=49.99, contractor_email=demo.email)
    # The SDK's from_sd_jwt does not check exp, so this is the wallet's own check
    assert _refusal_code(demo.wallet.sign_checkout, checkout["checkout_jwt"]) == "OWNER_LIMITS_EXPIRED"


def test_wallet_refuses_private_key_in_pinned_owner_file(demo):
    (demo.dir / "owner_public.jwk").write_text(demo.owner.export_private(), encoding="utf-8")
    assert _refusal_code(demo.wallet.describe_limits) == "PINNED_KEY_HAS_PRIVATE_PART"


def test_unconfigured_wallet_refuses(tmp_path):
    empty = BuyerWallet(tmp_path / "empty")
    assert _refusal_code(empty.describe_limits) == "WALLET_NOT_CONFIGURED"
    resp = wallet_mcp.handle_request(
        {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
         "params": {"name": "sign_checkout", "arguments": {"checkout_jwt": "a.b.c"}}},
        empty,
    )
    assert resp["result"]["isError"] is True
    assert json.loads(resp["result"]["content"][0]["text"])["error"] == "WALLET_NOT_CONFIGURED"


# ── Budget and recurrence accounting ────────────────────────────────────────


def test_wallet_counts_prior_signatures_against_max_occurrences(demo):
    checkouts = [
        create_merchant_checkout(tier_id="ap2-batch", monthly_price=49.99, contractor_email=demo.email)["checkout_jwt"]
        for _ in range(13)
    ]
    demo.wallet.sign_checkout(checkouts[0])
    demo.wallet.sign_checkout(checkouts[0])  # a retry of the same checkout is not a second use
    assert demo.wallet.describe_limits()["purchases_signed"] == 1

    for jwt in checkouts[1:12]:
        demo.wallet.sign_checkout(jwt)
    assert demo.wallet.describe_limits()["purchases_signed"] == 12

    demo.wallet.sign_checkout(checkouts[11])  # retrying an already-signed checkout still works at the limit
    assert demo.wallet.describe_limits()["purchases_signed"] == 12

    with pytest.raises(WalletRefusal) as exc:
        demo.wallet.sign_checkout(checkouts[12])
    assert exc.value.code == "PAYMENT_CONSTRAINT_VIOLATION"
    assert "Maximum occurrences" in exc.value.reason


def test_wallet_counts_prior_signatures_against_total_budget(demo):
    demo.sign_limits(cap=60.0, ceiling=100.0)
    first, second, third = (
        create_merchant_checkout(tier_id="ap2-batch", monthly_price=49.99, contractor_email=demo.email)["checkout_jwt"]
        for _ in range(3)
    )
    demo.wallet.sign_checkout(first)
    demo.wallet.sign_checkout(second)  # 9998 cents <= 10000
    with pytest.raises(WalletRefusal) as exc:
        demo.wallet.sign_checkout(third)  # 14997 cents > 10000
    assert exc.value.code == "PAYMENT_CONSTRAINT_VIOLATION"
    assert demo.wallet.describe_limits()["signed_so_far_cents"] == 9998


# ── MCP protocol surface ────────────────────────────────────────────────────


def test_wallet_mcp_protocol_surface(demo):
    init = wallet_mcp.handle_request(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}
    )
    assert init["result"]["protocolVersion"] == "2025-06-18"
    assert init["result"]["serverInfo"]["name"] == "ap2-buyer-wallet"
    unknown_version = wallet_mcp.handle_request(
        {"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}}
    )
    assert unknown_version["result"]["protocolVersion"] in wallet_mcp.SUPPORTED_PROTOCOL_VERSIONS

    assert wallet_mcp.handle_request({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None

    tools = wallet_mcp.handle_request({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})["result"]["tools"]
    by_name = {t["name"]: t for t in tools}
    assert set(by_name) == {"get_spending_limits", "sign_checkout"}
    assert by_name["sign_checkout"]["inputSchema"]["required"] == ["checkout_jwt"]

    unknown_tool = wallet_mcp.handle_request(
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "sign_anything"}}, demo.wallet
    )
    assert unknown_tool["error"]["code"] == -32601
    bad_args = wallet_mcp.handle_request(
        {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "sign_checkout", "arguments": []}},
        demo.wallet,
    )
    assert bad_args["error"]["code"] == -32602

    missing, is_error = _wallet(demo, "sign_checkout", {})
    assert is_error and missing["error"] == "MISSING_CHECKOUT_JWT"


# ── Process separation and launching outside the repo ──────────────────────


def _subprocess_env(tmp_path: Path, **extra) -> dict:
    env = dict(os.environ)
    env.update({
        "PYTHONPATH": str(REPO_ROOT),
        "A2A_DB_PATH": str(tmp_path / "subprocess.db"),
        "AP2_WALLET_DIR": str(tmp_path / "wallet"),
        "MOCK_EXTERNAL_APIS": "true",
    })
    env.pop("AP2_MERCHANT_PRIVATE_KEY_FILE", None)
    env.update(extra)
    return env


def test_wallet_process_never_imports_seller_side_code(tmp_path):
    probe = (
        "import json, sys, backend.wallet.mcp_server\n"
        "seller = ('backend.agents', 'backend.services', 'backend.database', 'backend.server', "
        "'backend.api', 'backend.config', 'backend.mcp_server')\n"
        "print(json.dumps(sorted(m for m in sys.modules if m.startswith(seller))))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", probe], cwd=str(tmp_path), env=_subprocess_env(tmp_path),
        capture_output=True, text=True, timeout=60,
    )
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout.strip().splitlines()[-1]) == []


class _StdioServer:
    def __init__(self, command, args, env, cwd):
        self.proc = subprocess.Popen(
            [command, *args], cwd=str(cwd), env=env, text=True,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        self._next_id = 0

    def rpc(self, method, params=None):
        self._next_id += 1
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params or {}}) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        assert line, f"{method}: server closed stdout"
        return json.loads(line)

    def call(self, tool, arguments):
        result = self.rpc("tools/call", {"name": tool, "arguments": arguments})["result"]
        return json.loads(result["content"][0]["text"]), result["isError"]

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=30)


@pytest.mark.parametrize("module, server_name, expected_tool", [
    ("backend.mcp_server", "ap2-seller-node", "purchase_subscription"),
    ("backend.wallet.mcp_server", "ap2-buyer-wallet", "sign_checkout"),
])
def test_mcp_servers_start_from_outside_the_repo(tmp_path, module, server_name, expected_tool):
    elsewhere = tmp_path / "launch-dir"
    elsewhere.mkdir()
    server = _StdioServer(sys.executable, ["-m", module], _subprocess_env(tmp_path), elsewhere)
    try:
        init = server.rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}})
        assert init["result"]["serverInfo"]["name"] == server_name
        names = [t["name"] for t in server.rpc("tools/list")["result"]["tools"]]
        assert expected_tool in names
    finally:
        server.close()


def test_setup_script_produces_a_working_claude_desktop_config(tmp_path):
    local_dir = tmp_path / ".ap2_local"
    config_path = tmp_path / "claude_desktop_config.local.json"
    setup = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "setup_claude_desktop_demo.py"),
         "--local-dir", str(local_dir), "--db-path", str(tmp_path / "demo.db"),
         "--config-out", str(config_path), "--monthly-cap", "60"],
        cwd=str(tmp_path), env=_subprocess_env(tmp_path), capture_output=True, text=True, timeout=180,
    )
    assert setup.returncode == 0, setup.stderr
    assert (local_dir / "wallet" / "agent_key.jwk").exists()
    assert not JWK.from_json((local_dir / "wallet" / "owner_public.jwk").read_text()).has_private
    assert not JWK.from_json((local_dir / "wallet" / "merchant_public.jwk").read_text()).has_private

    # Launch both servers exactly as Claude Desktop would, from an unrelated directory
    servers = json.loads(config_path.read_text())["mcpServers"]
    elsewhere = tmp_path / "claude-desktop-cwd"
    elsewhere.mkdir()
    base_env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "AP2_WALLET_DIR")}
    base_env["A2A_DB_PATH"] = str(tmp_path / "unused-by-config.db")
    running = {
        name: _StdioServer(spec["command"], spec["args"], {**base_env, **spec["env"]}, elsewhere)
        for name, spec in servers.items()
    }
    seller, wallet = running["ap2-seller-node"], running["ap2-buyer-wallet"]
    try:
        for s in (seller, wallet):
            s.rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}})

        limits, _ = wallet.call("get_spending_limits", {})
        assert limits["status"] == "AUTHORIZED"
        nego, _ = seller.call("negotiate_tier_terms", {
            "buyer_agent_id": "claude-desktop", "buyer_email": limits["buyer_email"],
            "tier_id": "ap2-gateway", "monthly_budget_cap": limits["monthly_budget_cap"],
        })
        signed, is_error = wallet.call("sign_checkout", {"checkout_jwt": nego["checkout_jwt"]})
        assert not is_error, signed
        purchase, _ = seller.call("purchase_subscription", {
            "offer_id": nego["offer_id"], "buyer_email": signed["buyer_email"],
            "checkout_mandate_chain": signed["checkout_mandate_chain"],
            "payment_mandate_chain": signed["payment_mandate_chain"],
        })
        assert purchase["status"] == "ACTIVE", purchase
    finally:
        for s in running.values():
            s.close()


# ── Merchant key file (shared by separate seller processes) ─────────────────


def _use_merchant_key_file(monkeypatch, path: Path):
    monkeypatch.setattr(ap2_keys, "_MERCHANT_KEY", None)
    monkeypatch.setattr(ap2_keys.settings, "ap2_merchant_private_key_jwk", "")
    monkeypatch.delenv("AP2_MERCHANT_PRIVATE_KEY_JWK", raising=False)
    monkeypatch.setattr(ap2_keys.settings, "ap2_merchant_private_key_file", str(path))


def test_merchant_key_is_loaded_from_file(tmp_path, monkeypatch):
    key = _new_key("merchant-file")
    path = tmp_path / "merchant_key.jwk"
    path.write_text(key.export_private(), encoding="utf-8")
    _use_merchant_key_file(monkeypatch, path)
    assert ap2_keys.get_merchant_key().thumbprint() == key.thumbprint()


@pytest.mark.parametrize("content", [None, "not a jwk", "public-only"])
def test_unusable_merchant_key_file_fails_closed(tmp_path, monkeypatch, content):
    path = tmp_path / "merchant_key.jwk"
    if content == "public-only":
        path.write_text(_new_key("merchant-public").export_public(), encoding="utf-8")
    elif content is not None:
        path.write_text(content, encoding="utf-8")
    _use_merchant_key_file(monkeypatch, path)
    with pytest.raises(RuntimeError):
        ap2_keys.get_merchant_key()
    assert ap2_keys._MERCHANT_KEY is None  # no silent fallback to an ephemeral key
