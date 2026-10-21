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
from backend.wallet.wallet import BuyerWallet, WalletRefusal, init_agent_key, pin_merchant_key

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
    assert "Amount 7999 exceeds maximum 6000" in refused["reason"]
    assert refused["message"] == "$79.99 exceeds the owner's $60.00 per-purchase limit"
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
    assert "Cumulative spend 14997 exceeds budget limit 10000" in exc.value.reason
    assert exc.value.message == "$49.99 exceeds the remaining budget of $0.02 ($100.00 limit, $99.98 already spent)"
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
    assert set(by_name) == {"get_spending_limits", "preview_checkout", "sign_checkout", "record_renewal_receipt"}
    assert by_name["preview_checkout"]["inputSchema"]["required"] == ["checkout_jwt"]
    assert by_name["sign_checkout"]["inputSchema"]["required"] == ["checkout_jwt"]
    assert by_name["record_renewal_receipt"]["inputSchema"]["required"] == ["renewal_receipt_jwt"]

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


# ── P1 & P2: Dry-run preview, step-up escalation, multi-merchant, renewal sync ─


@pytest.mark.asyncio
async def test_preview_checkout_dry_run_verifies_without_reserving_budget(demo):
    nego = await _seller("negotiate_tier_terms", {
        "buyer_agent_id": "claude-desktop-preview",
        "buyer_email": demo.email,
        "tier_id": "ap2-gateway",
        "monthly_budget_cap": 60.0,
    })
    assert nego["status"] == "COUNTER_OFFER"

    preview, is_error = _wallet(demo, "preview_checkout", {"checkout_jwt": nego["checkout_jwt"]})
    assert not is_error
    assert preview["status"] == "WOULD_SIGN"
    assert preview["dry_run"] is True
    assert preview["tier_id"] == "ap2-batch"
    assert preview["amount_cents"] == 4999
    assert preview["already_signed"] is False
    assert preview["budget_impact"]["signed_before_cents"] == 0
    assert preview["budget_impact"]["signed_after_cents"] == 4999
    assert preview["budget_impact"]["purchases_before"] == 0
    assert preview["budget_impact"]["purchases_after"] == 1
    assert "checkout_mandate_chain" not in preview

    # sign_checkout with dry_run=True behaves identically and also leaves ledger untouched
    dry_sign, is_error = _wallet(demo, "sign_checkout", {"checkout_jwt": nego["checkout_jwt"], "dry_run": True})
    assert not is_error
    assert dry_sign["status"] == "WOULD_SIGN"
    assert dry_sign["dry_run"] is True

    limits_after, _ = _wallet(demo, "get_spending_limits")
    assert limits_after["signed_so_far_cents"] == 0
    assert limits_after["purchases_signed"] == 0
    assert not (demo.dir / "ledger.json").exists()


def test_wallet_refusal_includes_structured_step_up_escalation(demo):
    # 1. Per-purchase cap violation ($79.99 vs $60.00 cap -> 1999 cents shortfall)
    over_cap = create_merchant_checkout(tier_id="ap2-gateway", monthly_price=79.99, contractor_email=demo.email)
    refused, is_error = _wallet(demo, "preview_checkout", {"checkout_jwt": over_cap["checkout_jwt"]})
    assert is_error
    assert refused["error"] == "PAYMENT_CONSTRAINT_VIOLATION"
    esc = refused["escalation"]
    assert esc["requires_human_approval"] is True
    assert esc["action"] == "INCREASE_SPENDING_LIMITS"
    assert esc["requested_amount_cents"] == 7999
    assert esc["current_max_per_purchase_cents"] == 6000
    assert esc["required_max_per_purchase_cents"] == 7999
    assert esc["per_purchase_shortfall_cents"] == 1999

    # 2. Disallowed tier violation
    demo.sign_limits(cap=100.0, tiers=["ap2-batch"])
    wrong_tier = create_merchant_checkout(tier_id="ap2-gateway", monthly_price=79.99, contractor_email=demo.email)
    refused_tier, is_error = _wallet(demo, "sign_checkout", {"checkout_jwt": wrong_tier["checkout_jwt"]})
    assert is_error
    assert refused_tier["error"] == "CHECKOUT_CONSTRAINT_VIOLATION"
    esc_tier = refused_tier["escalation"]
    assert esc_tier["requires_human_approval"] is True
    assert esc_tier["action"] == "APPROVE_CHECKOUT_EXCEPTION"
    assert esc_tier["requested_tier_id"] == "ap2-gateway"
    assert esc_tier["allowed_tiers"] == ["ap2-batch"]

    # 3. Expired owner limits
    demo.sign_limits(validity=-60)
    valid_chk = create_merchant_checkout(tier_id="ap2-batch", monthly_price=49.99, contractor_email=demo.email)
    refused_exp, is_error = _wallet(demo, "sign_checkout", {"checkout_jwt": valid_chk["checkout_jwt"]})
    assert is_error
    assert refused_exp["error"] == "OWNER_LIMITS_EXPIRED"
    esc_exp = refused_exp["escalation"]
    assert esc_exp["requires_human_approval"] is True
    assert esc_exp["action"] == "REAUTHORIZE_EXPIRED_LIMITS"
    assert esc_exp["buyer_email"] == demo.email


def test_multi_merchant_key_pinning_and_conflict_refusal(demo):
    # Remove single merchant_public.jwk and use merchant_keys.json instead
    (demo.dir / "merchant_public.jwk").unlink()
    primary_pub = get_merchant_public_jwk()
    secondary_key = _new_key("merchant-secondary")

    pin_merchant_key("merchant-ap2-autonomous", primary_pub, demo.dir)
    pin_merchant_key("merchant-ap2-autonomous", primary_pub, demo.dir)  # idempotent with same key
    pin_merchant_key("merchant-secondary-cloud", secondary_key.export_public(as_dict=True), demo.dir)

    # Overwriting an existing merchant_id with a different key is refused
    with pytest.raises(WalletRefusal) as exc:
        pin_merchant_key("merchant-ap2-autonomous", _new_key("impostor").export_public(as_dict=True), demo.dir)
    assert exc.value.code == "MERCHANT_KEY_CONFLICT"

    # Private key material is refused when pinning
    with pytest.raises(WalletRefusal) as exc_priv:
        pin_merchant_key("merchant-leak", json.loads(_new_key("leak").export_private()), demo.dir)
    assert exc_priv.value.code == "PINNED_KEY_HAS_PRIVATE_PART"

    # Valid checkout signed by merchant-ap2-autonomous succeeds via merchant_keys.json
    chk = create_merchant_checkout(tier_id="ap2-batch", monthly_price=49.99, contractor_email=demo.email)
    res = demo.wallet.preview_checkout(chk["checkout_jwt"])
    assert res["status"] == "WOULD_SIGN"
    assert res["merchant_id"] == "merchant-ap2-autonomous"

    # Checkout claiming to be merchant-ap2-autonomous but signed by secondary_key is refused
    payload = json.loads(b64url_decode(chk["checkout_jwt"].split(".")[1]))
    cross_signed = create_jwt({"alg": "ES256", "typ": "JWT", "kid": secondary_key.kid}, payload, secondary_key)
    assert _refusal_code(demo.wallet.preview_checkout, cross_signed) == "CHECKOUT_SIGNATURE_INVALID"


@pytest.mark.asyncio
async def test_renewal_receipt_sync_updates_wallet_ledger_without_double_counting_initial_sale(demo):
    import datetime
    from backend.services.recurring_mandate_service import evaluate_sale
    from backend.agents.seller_agent import _COMPLETED_SUBSCRIPTIONS

    nego = await _seller("negotiate_tier_terms", {
        "buyer_agent_id": "claude-renewal-test",
        "buyer_email": demo.email,
        "tier_id": "ap2-batch",
        "monthly_budget_cap": 60.0,
    })
    signed, is_error = _wallet(demo, "sign_checkout", {"checkout_jwt": nego["checkout_jwt"]})
    assert not is_error

    purchase = await _seller("purchase_subscription", {
        "offer_id": nego["offer_id"],
        "buyer_email": demo.email,
        "checkout_mandate_chain": signed["checkout_mandate_chain"],
        "payment_mandate_chain": signed["payment_mandate_chain"],
    })
    assert purchase["status"] == "ACTIVE"
    sub_id = purchase["subscription_id"]
    sub_rec = _COMPLETED_SUBSCRIPTIONS.get(sub_id)

    now = datetime.datetime.now(datetime.timezone.utc)
    # 1. Initial PayPal sale webhook -> INITIAL renewal receipt does not double-count
    init_decision = evaluate_sale(
        {
            "id": f"SALE-INIT-{uuid.uuid4().hex[:8]}",
            "billing_agreement_id": sub_id,
            "create_time": now.isoformat(),
            "amount": {"total": "49.99", "currency": "USD"},
        },
        sub_rec,
        now=now,
    )
    assert init_decision["outcome"] == "INITIAL"
    assert "renewal_receipt_jwt" in init_decision

    sync_init, is_error = _wallet(
        demo, "record_renewal_receipt", {"renewal_receipt_jwt": init_decision["renewal_receipt_jwt"]}
    )
    assert not is_error
    assert sync_init["outcome"] == "INITIAL"
    assert sync_init["signed_so_far_cents"] == 4999
    assert sync_init["purchases_signed"] == 1
    assert sync_init["renewals_recorded"] == 0

    # 2. Month-2 renewal sale -> VERIFIED renewal receipt increments wallet usage
    month2 = now + datetime.timedelta(days=31)
    ren_decision = evaluate_sale(
        {
            "id": f"SALE-REN2-{uuid.uuid4().hex[:8]}",
            "billing_agreement_id": sub_id,
            "create_time": month2.isoformat(),
            "amount": {"total": "49.99", "currency": "USD"},
        },
        sub_rec,
        now=month2,
    )
    assert ren_decision["outcome"] == "VERIFIED"
    assert "renewal_receipt_jwt" in ren_decision

    sync_ren, is_error = _wallet(
        demo, "record_renewal_receipt", {"renewal_receipt_jwt": ren_decision["renewal_receipt_jwt"]}
    )
    assert not is_error
    assert sync_ren["outcome"] == "VERIFIED"
    assert sync_ren["signed_so_far_cents"] == 9998
    assert sync_ren["purchases_signed"] == 2
    assert sync_ren["renewals_recorded"] == 1
    assert sync_ren["renewal_spend_cents"] == 4999

    # Re-submitting the same renewal receipt is idempotent
    sync_again, is_error = _wallet(
        demo, "record_renewal_receipt", {"renewal_receipt_jwt": ren_decision["renewal_receipt_jwt"]}
    )
    assert not is_error
    assert sync_again["signed_so_far_cents"] == 9998
    assert sync_again["purchases_signed"] == 2

    # Forged renewal receipt is refused
    payload = json.loads(b64url_decode(ren_decision["renewal_receipt_jwt"].split(".")[1]))
    forged = create_jwt({"alg": "ES256", "typ": "JWT", "kid": "attacker"}, payload, _new_key("attacker"))
    assert _refusal_code(demo.wallet.record_renewal_receipt, forged) == "RECEIPT_SIGNATURE_INVALID"

    # End-to-end MCP discovery: get_subscription_details exposes renewal_receipts with hashed sub (no cleartext PII)
    details = await _seller("get_subscription_details", {"subscription_id": sub_id})
    assert demo.email not in json.dumps(details)
    receipts = details.get("renewal_receipts", [])
    assert [r["outcome"] for r in receipts] == ["INITIAL", "VERIFIED"]
    for r in receipts:
        jwt_payload = json.loads(b64url_decode(r["renewal_receipt_jwt"].split(".")[1]))
        assert demo.email not in json.dumps(jwt_payload)

    # Previewing an already-signed checkout reports accurate before/after usage
    prev_again, is_error = _wallet(demo, "preview_checkout", {"checkout_jwt": nego["checkout_jwt"]})
    assert not is_error
    assert prev_again["already_signed"] is True
    assert prev_again["budget_impact"]["signed_before_cents"] == 9998
    assert prev_again["budget_impact"]["signed_after_cents"] == 9998

    # Conflicting replay of an already-recorded sale_id is refused
    conflict_payload = dict(payload, outcome="INITIAL")
    from backend.services.ap2_keys import get_merchant_key
    m_key = get_merchant_key()
    conflict_jwt = create_jwt({"alg": "ES256", "typ": "JWT", "kid": m_key.kid}, conflict_payload, m_key)
    assert _refusal_code(demo.wallet.record_renewal_receipt, conflict_jwt) == "RECEIPT_CONFLICT"


def test_renewal_receipt_refuses_orphan_and_mismatched_initial_receipt(demo):
    from backend.services.ap2_service import create_renewal_receipt_jwt

    # 1. Before any checkout is signed, an orphan renewal receipt is refused
    orphan_jwt = create_renewal_receipt_jwt(
        sale_id="SALE-ORPHAN-1",
        subscription_id="I-SUB-ORPHAN",
        mandate_hash=demo.wallet._load_limits().canonical_payment_hash,
        buyer_email=demo.email,
        amount_cents=4999,
        currency="USD",
        outcome="VERIFIED",
        charged_at="2026-10-20T00:00:00Z",
    )
    assert _refusal_code(demo.wallet.record_renewal_receipt, orphan_jwt) == "NO_SIGNED_CHECKOUT"

    # 2. Sign a $49.99 checkout, then present an INITIAL receipt with a mismatched amount
    chk = create_merchant_checkout(tier_id="ap2-batch", monthly_price=49.99, contractor_email=demo.email)
    demo.wallet.sign_checkout(chk["checkout_jwt"])
    bad_init_jwt = create_renewal_receipt_jwt(
        sale_id="SALE-BAD-INIT",
        subscription_id="I-SUB-1",
        mandate_hash=demo.wallet._load_limits().canonical_payment_hash,
        buyer_email=demo.email,
        amount_cents=1999,
        currency="USD",
        outcome="INITIAL",
        charged_at="2026-10-20T00:00:00Z",
    )
    assert _refusal_code(demo.wallet.record_renewal_receipt, bad_init_jwt) == "RECEIPT_AMOUNT_MISMATCH"

    # 3. Malformed charged_at is refused (fail closed)
    bad_ts_jwt = create_renewal_receipt_jwt(
        sale_id="SALE-BAD-TS",
        subscription_id="I-SUB-1",
        mandate_hash=demo.wallet._load_limits().canonical_payment_hash,
        buyer_email=demo.email,
        amount_cents=4999,
        currency="USD",
        outcome="VERIFIED",
        charged_at="not-a-timestamp",
    )
    assert _refusal_code(demo.wallet.record_renewal_receipt, bad_ts_jwt) == "RECEIPT_MALFORMED"


def test_renewal_receipt_succeeds_after_checkout_window_expires_and_verify_chains_counts_renewals(demo):
    import datetime
    from backend.services.ap2_service import create_renewal_receipt_jwt, verify_ap2_chains
    from backend.services.recurring_mandate_service import evaluate_sale
    from backend.agents.seller_agent import _COMPLETED_SUBSCRIPTIONS

    # Owner signs a $100 total ceiling ($60/mo cap -> room for 2 x $49.99 charges)
    demo.sign_limits(cap=60.0, ceiling=100.0, validity=3600)
    import asyncio
    nego1 = asyncio.run(_seller("negotiate_tier_terms", {
        "buyer_agent_id": "claude-renewal-window-test",
        "buyer_email": demo.email,
        "tier_id": "ap2-batch",
        "monthly_budget_cap": 60.0,
    }))
    signed1 = demo.wallet.sign_checkout(nego1["checkout_jwt"])

    # Settle first purchase on seller
    purchase = asyncio.run(_seller("purchase_subscription", {
        "offer_id": nego1["offer_id"],
        "buyer_email": demo.email,
        "checkout_mandate_chain": signed1["checkout_mandate_chain"],
        "payment_mandate_chain": signed1["payment_mandate_chain"],
    }))
    assert purchase["status"] == "ACTIVE"
    sub_id = purchase["subscription_id"]
    sub_rec = _COMPLETED_SUBSCRIPTIONS.get(sub_id)

    now = datetime.datetime.now(datetime.timezone.utc)
    evaluate_sale(
        {"id": "SALE-M1", "billing_agreement_id": sub_id, "create_time": now.isoformat(),
         "amount": {"total": "49.99", "currency": "USD"}},
        sub_rec, now=now,
    )
    month2 = now + datetime.timedelta(days=31)
    ren_m2 = evaluate_sale(
        {"id": "SALE-M2", "billing_agreement_id": sub_id, "create_time": month2.isoformat(),
         "amount": {"total": "49.99", "currency": "USD"}},
        sub_rec, now=month2,
    )
    assert ren_m2["outcome"] == "VERIFIED"

    # Re-calling evaluate_sale for the same sale_id returns ALREADY_PROCESSED with renewal_receipt_jwt
    replay_m2 = evaluate_sale(
        {"id": "SALE-M2", "billing_agreement_id": sub_id, "create_time": month2.isoformat(),
         "amount": {"total": "49.99", "currency": "USD"}},
        sub_rec, now=month2,
    )
    assert replay_m2["outcome"] == "ALREADY_PROCESSED"
    assert "renewal_receipt_jwt" in replay_m2

    # Seller's verify_ap2_chains now sees 2 charges (9998 cents) under this open payment mandate,
    # so a second checkout presentation on the same open payment mandate is rejected for exceeding $100 budget!
    chk2 = create_merchant_checkout(tier_id="ap2-batch", monthly_price=49.99, contractor_email=demo.email)
    signed2 = demo.wallet.sign_checkout(chk2["checkout_jwt"])
    ver2 = verify_ap2_chains(
        signed2["checkout_mandate_chain"],
        signed2["payment_mandate_chain"],
        chk2["checkout_jwt"],
        expected_aud="merchant-ap2-autonomous",
        expected_nonce=chk2["nonce"],
        buyer_email=demo.email,
    )
    assert ver2["valid"] is False
    assert "exceeds budget limit 10000" in ver2["error_description"]

    # Simulate the 24-hour checkout mandate window expiring while the 12-month payment mandate remains valid
    raw_limits = json.loads((demo.dir / "owner_limits.json").read_text(encoding="utf-8"))
    expired_chk_limits = create_trusted_surface_open_mandates(
        buyer_email=demo.email,
        monthly_budget_cap=60.0,
        yearly_budget_ceiling=100.0,
        agent_key=demo.wallet._agent_key(),
        user_key=demo.owner,
        validity_seconds=-60,
    )
    raw_limits["open_checkout_mandate_token"] = expired_chk_limits["open_checkout_mandate_token"]
    (demo.dir / "owner_limits.json").write_text(json.dumps(raw_limits), encoding="utf-8")

    # Starting a new checkout is refused because open_checkout_mandate expired,
    # but recording the initial sale receipt under the still-valid open_payment_mandate succeeds!
    assert _refusal_code(demo.wallet.sign_checkout, nego1["checkout_jwt"]) == "OWNER_LIMITS_EXPIRED"
    init_jwt = create_renewal_receipt_jwt(
        sale_id="SALE-M1",
        subscription_id=sub_id,
        mandate_hash=demo.wallet._load_limits(require_unexpired_checkout=False).canonical_payment_hash,
        buyer_email=demo.email,
        amount_cents=4999,
        currency="USD",
        outcome="INITIAL",
        charged_at=now.isoformat(),
    )
    synced = demo.wallet.record_renewal_receipt(init_jwt)
    assert synced["status"] == "RECORDED"


def test_provision_rejection_includes_ap2_payment_challenge_and_header():
    res = client.post(
        "/api/agent/provision",
        json={"subscriptionId": "I-MISSING-SUB-0000", "contractorEmail": "buyer@example.com"},
    )
    assert res.status_code == 404
    assert "X-AP2-Payment-Required" in res.headers
    detail = res.json()["detail"]
    assert detail["error"] == "SUBSCRIPTION_NOT_FOUND"
    challenge = detail["ap2_payment_challenge"]
    assert challenge["protocol"] == "AP2-v0.2"
    assert challenge["mcp_endpoint"] == "/mcp"
    assert challenge["negotiation_tool"] == "negotiate_tier_terms"
    assert challenge["wallet_preview_tool"] == "preview_checkout"
    assert challenge["wallet_sign_tool"] == "sign_checkout"
    assert challenge["purchase_tool"] == "purchase_subscription"


# ── Wave 1 Adversarial Review Regression Tests ──────────────────────────────


@pytest.mark.asyncio
async def test_public_discovery_surfaces_match_ap2_v02_and_two_server_model():
    llms_txt = (REPO_ROOT / "public" / "llms.txt").read_text(encoding="utf-8")
    for stale in ("provision_execution_node", "solo-driver", "pro-driver", "fleet-dispatch"):
        assert stale not in llms_txt
    for expected in (
        "provision_compute_node",
        "get_subscription_details",
        "ap2-buyer-wallet",
        "preview_checkout",
        "sign_checkout",
        "record_renewal_receipt",
        "checkout_mandate_chain",
        "payment_mandate_chain",
        "ES256",
    ):
        assert expected in llms_txt

    mcp_manifest = json.loads((REPO_ROOT / "public" / ".well-known" / "mcp.json").read_text(encoding="utf-8"))
    manifest_tools = set(mcp_manifest["mcp_server"]["tools"])
    assert manifest_tools == {
        "get_service_catalog",
        "inspect_subscription_tiers",
        "negotiate_tier_terms",
        "evaluate_spending_mandate",
        "purchase_subscription",
        "provision_compute_node",
        "get_subscription_details",
        "dispatch_zapier_mcp",
    }
    assert mcp_manifest["companion_wallet_server"]["tools"] == [
        "get_spending_limits",
        "preview_checkout",
        "sign_checkout",
        "record_renewal_receipt",
    ]

    api_mcp = client.get("/.well-known/mcp.json").json()
    assert set(api_mcp["mcp_server"]["tools"]) == manifest_tools
    assert api_mcp["companion_wallet_server"]["name"] == "ap2-buyer-wallet"
    assert api_mcp["companion_wallet_server"]["command"] == "python -m backend.wallet.mcp_server"

    agent_card = client.get("/.well-known/agent.json").json()
    assert "ES256" in agent_card["authentication"]["algorithms"]

    init_resp = await process_mcp_request(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}
    )
    instructions = init_resp["result"]["instructions"]
    assert "record_renewal_receipt" in instructions
    assert "get_subscription_details" in instructions
    assert "preview_checkout" in instructions


@pytest.mark.asyncio
async def test_seller_mcp_sets_is_error_true_on_rejected_tool_results(demo, monkeypatch):
    from backend.agents.seller_agent import seller_agent

    # 1. status == "REJECTED" (purchase rejected for missing chains) -> isError must be True
    pur_resp = await process_mcp_request({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "purchase_subscription",
            "arguments": {"tier_id": "ap2-batch", "agreed_monthly_rate": 49.99},
        },
    })
    assert pur_resp["result"]["isError"] is True
    pur_body = json.loads(pur_resp["result"]["content"][0]["text"])
    assert pur_body["status"] == "REJECTED"

    # 2. status == "REJECTED" (negotiation rejected for budget below minimum tier) -> isError must be True
    neg_rej = await process_mcp_request({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "negotiate_tier_terms",
            "arguments": {
                "buyer_agent_id": "wave1-agent",
                "buyer_email": "wave1@example.com",
                "tier_id": "ap2-gateway",
                "monthly_budget_cap": 20.0,
            },
        },
    })
    assert neg_rej["result"]["isError"] is True
    assert json.loads(neg_rej["result"]["content"][0]["text"])["status"] == "REJECTED"

    # 3. status == "COUNTER_OFFER" -> actionable offer with checkout_jwt, isError must be False
    neg_co = await process_mcp_request({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "negotiate_tier_terms",
            "arguments": {
                "buyer_agent_id": "wave1-agent",
                "buyer_email": demo.email,
                "tier_id": "ap2-gateway",
                "monthly_budget_cap": 60.0,
            },
        },
    })
    assert neg_co["result"]["isError"] is False
    neg_co_body = json.loads(neg_co["result"]["content"][0]["text"])
    assert neg_co_body["status"] == "COUNTER_OFFER"

    # 4. status == "APPROVED" -> isError must be False
    neg_ok = await process_mcp_request({
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "negotiate_tier_terms",
            "arguments": {
                "buyer_agent_id": "wave1-agent",
                "buyer_email": demo.email,
                "tier_id": "ap2-batch",
                "monthly_budget_cap": 60.0,
            },
        },
    })
    assert neg_ok["result"]["isError"] is False
    neg_ok_body = json.loads(neg_ok["result"]["content"][0]["text"])
    assert neg_ok_body["status"] == "APPROVED"

    # Settle ap2-batch subscription for demo.email so we can test ACTIVE, PROVISIONED, ALREADY_SUBSCRIBED, NO_BETTER_OFFER
    signed = demo.wallet.sign_checkout(neg_ok_body["checkout_jwt"])
    pur_ok = await process_mcp_request({
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {
            "name": "purchase_subscription",
            "arguments": {
                "offer_id": neg_ok_body["offer_id"],
                "buyer_email": demo.email,
                "checkout_mandate_chain": signed["checkout_mandate_chain"],
                "payment_mandate_chain": signed["payment_mandate_chain"],
            },
        },
    })
    assert pur_ok["result"]["isError"] is False
    pur_ok_body = json.loads(pur_ok["result"]["content"][0]["text"])
    assert pur_ok_body["status"] == "ACTIVE"

    # 5. status == "PROVISIONED" -> isError must be False
    prov_ok = await process_mcp_request({
        "jsonrpc": "2.0",
        "id": 6,
        "method": "tools/call",
        "params": {
            "name": "provision_compute_node",
            "arguments": {
                "subscription_id": pur_ok_body["subscription_id"],
                "buyer_email": demo.email,
            },
        },
    })
    assert prov_ok["result"]["isError"] is False
    assert json.loads(prov_ok["result"]["content"][0]["text"])["status"] == "PROVISIONED"

    # 6. status == "ALREADY_SUBSCRIBED" -> isError must be True
    already_resp = await process_mcp_request({
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/call",
        "params": {
            "name": "negotiate_tier_terms",
            "arguments": {
                "buyer_agent_id": "wave1-agent",
                "buyer_email": demo.email,
                "tier_id": "ap2-batch",
                "monthly_budget_cap": 60.0,
            },
        },
    })
    assert already_resp["result"]["isError"] is True
    assert json.loads(already_resp["result"]["content"][0]["text"])["status"] == "ALREADY_SUBSCRIBED"

    # 7. status == "NO_BETTER_OFFER" -> isError must be True
    no_better_resp = await process_mcp_request({
        "jsonrpc": "2.0",
        "id": 8,
        "method": "tools/call",
        "params": {
            "name": "negotiate_tier_terms",
            "arguments": {
                "buyer_agent_id": "wave1-agent",
                "buyer_email": demo.email,
                "tier_id": "ap2-gateway",
                "monthly_budget_cap": 60.0,
            },
        },
    })
    assert no_better_resp["result"]["isError"] is True
    assert json.loads(no_better_resp["result"]["content"][0]["text"])["status"] == "NO_BETTER_OFFER"

    # 8. approved: False without status (evaluate_spending_mandate over budget) -> isError must be True
    eval_rej = await process_mcp_request({
        "jsonrpc": "2.0",
        "id": 9,
        "method": "tools/call",
        "params": {
            "name": "evaluate_spending_mandate",
            "arguments": {
                "buyer_agent_id": "wave1-agent",
                "amount": 95.0,
                "monthly_budget_cap": 50.0,
            },
        },
    })
    assert eval_rej["result"]["isError"] is True
    eval_body = json.loads(eval_rej["result"]["content"][0]["text"])
    assert eval_body["approved"] is False

    # 9. status == "REFUSED" and status == "ERROR" -> isError must be True
    for idx, st in enumerate(("REFUSED", "ERROR"), start=10):
        async def _fake_status(*args, _st=st, **kwargs):
            return {"status": _st, "reason": f"simulated {_st}"}
        monkeypatch.setattr(seller_agent, "get_subscription_details", _fake_status)
        st_resp = await process_mcp_request({
            "jsonrpc": "2.0",
            "id": idx,
            "method": "tools/call",
            "params": {
                "name": "get_subscription_details",
                "arguments": {"subscription_id": "I-TEST-STATUS"},
            },
        })
        assert st_resp["result"]["isError"] is True
        assert json.loads(st_resp["result"]["content"][0]["text"])["status"] == st


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name, bad_args", [
    # Missing buyer_agent_id, tier_id, budget, or email on negotiate_tier_terms
    ("negotiate_tier_terms", {"tier_id": "ap2-gateway", "monthly_budget_cap": 60.0, "buyer_email": "a@b.com"}),
    ("negotiate_tier_terms", {"buyer_agent_id": "ag1", "monthly_budget_cap": 60.0, "buyer_email": "a@b.com"}),
    ("negotiate_tier_terms", {"buyer_agent_id": "ag1", "tier_id": "ap2-gateway", "buyer_email": "a@b.com"}),
    ("negotiate_tier_terms", {"buyer_agent_id": "ag1", "tier_id": "ap2-gateway", "monthly_budget_cap": 60.0}),
    # Missing subscription_id or buyer_email on provision_compute_node
    ("provision_compute_node", {"buyer_email": "a@b.com"}),
    ("provision_compute_node", {"subscription_id": "I-SUB-1"}),
    # Missing subscription_id on dispatch_zapier_mcp or get_subscription_details
    ("dispatch_zapier_mcp", {"event_type": "PROVISIONED"}),
    ("get_subscription_details", {}),
    # Missing buyer_agent_id or amount on evaluate_spending_mandate
    ("evaluate_spending_mandate", {"amount": 49.99}),
    ("evaluate_spending_mandate", {"buyer_agent_id": "ag1"}),
])
async def test_seller_mcp_omitted_arguments_fail_closed_with_invalid_params(tool_name, bad_args):
    resp = await process_mcp_request({
        "jsonrpc": "2.0",
        "id": 99,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": bad_args},
    })
    assert "error" in resp, f"Expected JSON-RPC error for {tool_name}({bad_args}), got {resp}"
    assert resp["error"]["code"] == -32602


@pytest.mark.asyncio
async def test_seller_mcp_accepts_integer_cents_and_rejects_float_cents_disagreement(demo):
    # 1. Integer cents only on negotiate_tier_terms
    nego = await _seller("negotiate_tier_terms", {
        "buyer_agent_id": "cents-agent",
        "buyer_email": demo.email,
        "tier_id": "ap2-batch",
        "monthly_budget_cap_cents": 6000,
    })
    assert nego["status"] == "APPROVED"
    assert nego["price_cents"] == 4999
    assert nego["agreed_monthly_rate_cents"] == 4999
    assert nego["monthly_budget_cap_cents"] == 6000
    assert nego["monthly_cap_remaining_cents"] == 1001

    # 2. Disagreement between monthly_budget_cap_cents and monthly_budget_cap -> -32602
    disagree = await process_mcp_request({
        "jsonrpc": "2.0",
        "id": 10,
        "method": "tools/call",
        "params": {
            "name": "negotiate_tier_terms",
            "arguments": {
                "buyer_agent_id": "cents-agent",
                "buyer_email": demo.email,
                "tier_id": "ap2-batch",
                "monthly_budget_cap": 60.0,
                "monthly_budget_cap_cents": 5000,
            },
        },
    })
    assert disagree["error"]["code"] == -32602

    # 3. Purchase using agreed_monthly_rate_cents
    signed = demo.wallet.sign_checkout(nego["checkout_jwt"])
    pur = await _seller("purchase_subscription", {
        "offer_id": nego["offer_id"],
        "tier_id": "ap2-batch",
        "agreed_monthly_rate_cents": 4999,
        "buyer_email": demo.email,
        "checkout_mandate_chain": signed["checkout_mandate_chain"],
        "payment_mandate_chain": signed["payment_mandate_chain"],
    })
    assert pur["status"] == "ACTIVE"
    assert pur["agreed_monthly_rate_cents"] == 4999
    assert pur["monthly_budget_cap_cents"] == 6000


@pytest.mark.asyncio
async def test_seller_rejections_include_structured_step_up_escalation_with_integer_cents(demo):
    # 1. Negotiation below minimum tier ($20.00 vs $49.99 minimum and $79.99 requested)
    neg_rej = await _seller("negotiate_tier_terms", {
        "buyer_agent_id": "stepup-agent",
        "buyer_email": demo.email,
        "tier_id": "ap2-gateway",
        "monthly_budget_cap_cents": 2000,
    })
    assert neg_rej["status"] == "REJECTED"
    esc = neg_rej["escalation"]
    assert esc["type"] == "human_step_up_required"
    assert esc["action"] == "increase_spending_limits"
    assert esc["requested_amount_cents"] == 7999
    assert esc["minimum_viable_amount_cents"] == 4999
    assert esc["monthly_budget_cap_cents"] == 2000
    assert esc["shortfall_cents"] == 5999
    assert esc["minimum_viable_shortfall_cents"] == 2999


@pytest.mark.asyncio
async def test_email_and_offer_binding_enforced_even_when_buyer_email_omitted(demo):
    # Negotiate two distinct checkouts
    nego_batch = await _seller("negotiate_tier_terms", {
        "buyer_agent_id": "binding-agent",
        "buyer_email": demo.email,
        "tier_id": "ap2-batch",
        "monthly_budget_cap_cents": 6000,
    })
    other_chk = create_merchant_checkout(tier_id="ap2-batch", monthly_price=49.99, contractor_email=demo.email)
    signed_other = demo.wallet.sign_checkout(other_chk["checkout_jwt"])

    # 1. Presenting signed chains for other_chk against nego_batch's offer_id (even with other_chk's nonce) is rejected
    from backend.agents.seller_agent import seller_agent
    mismatch_offer = await seller_agent.purchase_subscription(
        offer_id=nego_batch["offer_id"],
        checkout_mandate_chain=signed_other["checkout_mandate_chain"],
        payment_mandate_chain=signed_other["payment_mandate_chain"],
        checkout_jwt=other_chk["checkout_jwt"],
        nonce=other_chk["nonce"],
    )
    assert mismatch_offer["status"] == "REJECTED"
    assert mismatch_offer["error"] == "OFFER_MISMATCH_DETECTED"

    # 2. Enrolling an impostor owner key and trying to redeem a checkout issued for demo.email without passing buyer_email
    impostor_key = _new_key("owner-impostor-wave1")
    _enroll_owner(impostor_key, "impostor@example.com")
    impostor_limits = create_trusted_surface_open_mandates(
        buyer_email="impostor@example.com",
        monthly_budget_cap=100.0,
        yearly_budget_ceiling=500.0,
        agent_key=demo.wallet._agent_key(),
        user_key=impostor_key,
    )
    from ap2.sdk.mandate import MandateClient
    from ap2.sdk.generated.checkout_mandate import CheckoutMandate
    from ap2.sdk.generated.payment_mandate import PaymentMandate
    from ap2.sdk.generated.types.amount import Amount
    from ap2.sdk.generated.types.merchant import Merchant
    from ap2.sdk.generated.types.payment_instrument import PaymentInstrument
    mc = MandateClient()
    imp_chk_chain = mc.present(
        holder_key=demo.wallet._agent_key(),
        mandate_token=impostor_limits["open_checkout_mandate_token"],
        payloads=[CheckoutMandate(vct="mandate.checkout.1", checkout_jwt=nego_batch["checkout_jwt"], checkout_hash=nego_batch["checkout_hash"])],
        aud="merchant-ap2-autonomous",
        nonce=nego_batch["nonce"],
    )
    imp_pay_chain = mc.present(
        holder_key=demo.wallet._agent_key(),
        mandate_token=impostor_limits["open_payment_mandate_token"],
        payloads=[PaymentMandate(
            vct="mandate.payment.1",
            transaction_id=nego_batch["checkout_hash"],
            payment_amount=Amount(amount=4999, currency="USD"),
            payee=Merchant(id="merchant-ap2-autonomous", name="AP2 Autonomous Node Network"),
            payment_instrument=PaymentInstrument(type="paypal_vault", id="vault_imp"),
        )],
        aud="merchant-ap2-autonomous",
        nonce=nego_batch["nonce"],
    )
    # Omitting buyer_email still catches that impostor_key's registered email != nego_batch's issued email
    imp_pur = await _seller("purchase_subscription", {
        "checkout_mandate_chain": imp_chk_chain,
        "payment_mandate_chain": imp_pay_chain,
        "checkout_jwt": nego_batch["checkout_jwt"],
    })
    assert imp_pur["status"] == "REJECTED"
    assert "EMAIL_KEY_BINDING_MISMATCH" in imp_pur["reason"]

    # 3. Valid purchase omitting both buyer_email and checkout_jwt recovers checkout_jwt from SD-JWT disclosure
    # and binds verified_buyer_email from demo's registered key
    signed_valid = demo.wallet.sign_checkout(nego_batch["checkout_jwt"])
    valid_pur = await _seller("purchase_subscription", {
        "checkout_mandate_chain": signed_valid["checkout_mandate_chain"],
        "payment_mandate_chain": signed_valid["payment_mandate_chain"],
    })
    assert valid_pur["status"] == "ACTIVE"
    assert valid_pur["buyer_email"] == demo.email


@pytest.mark.asyncio
async def test_multi_worker_sqlite_fallback_and_sse_wire_log_redaction(demo):
    from backend.services.ap2_service import (
        _ISSUED_CHECKOUTS,
        _RECEIPT_STORE,
        get_issued_checkout,
        get_stored_receipt,
    )

    nego = await _seller("negotiate_tier_terms", {
        "buyer_agent_id": "worker-test",
        "buyer_email": demo.email,
        "tier_id": "ap2-batch",
        "monthly_budget_cap_cents": 6000,
    })
    signed = demo.wallet.sign_checkout(nego["checkout_jwt"])
    pur = await _seller("purchase_subscription", {
        "offer_id": nego["offer_id"],
        "buyer_email": demo.email,
        "checkout_mandate_chain": signed["checkout_mandate_chain"],
        "payment_mandate_chain": signed["payment_mandate_chain"],
    })
    assert pur["status"] == "ACTIVE"

    # Simulate a second worker / process restart by clearing in-memory caches
    _ISSUED_CHECKOUTS.clear()
    _RECEIPT_STORE.clear()

    recovered_chk = get_issued_checkout(nego["checkout_hash"])
    assert recovered_chk is not None
    assert recovered_chk["checkout_jwt"] == nego["checkout_jwt"]

    recovered_receipt = get_stored_receipt(nego["checkout_hash"])
    assert recovered_receipt is not None
    assert recovered_receipt["status"] == "Success"

    # If the stored SQLite checkout_receipt cannot be verified (corrupted or wrong key),
    # get_stored_receipt must return None rather than fabricating status == "Success",
    # and verify_ap2_chains must not treat an unverifiable receipt as redeemed.
    from backend.database import get_subscription, save_subscription
    from backend.services.ap2_service import verify_ap2_chains
    sub_row = get_subscription(nego["checkout_hash"])
    assert sub_row is not None
    corrupted_row = dict(sub_row, checkout_receipt="eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdGF0dXMiOiJTdWNjZXNzIn0.corrupted_sig")
    save_subscription(corrupted_row)
    _RECEIPT_STORE.clear()
    assert get_stored_receipt(nego["checkout_hash"]) is None
    reverify = verify_ap2_chains(
        checkout_mandate_token=signed["checkout_mandate_chain"],
        payment_mandate_token=signed["payment_mandate_chain"],
        checkout_jwt=nego["checkout_jwt"],
        enforce_replay_defense=True,
        buyer_email=demo.email,
    )
    assert reverify["valid"] is True

    # Restore valid receipt and verify SSE wire log (/api/mcp/frames) redacts all sensitive JWTs and mandate chains
    save_subscription(sub_row)
    frames = client.get("/api/mcp/frames").json()["frames"]
    serialized_frames = json.dumps(frames)
    assert nego["checkout_jwt"] not in serialized_frames
    assert signed["checkout_mandate_chain"] not in serialized_frames
    assert signed["payment_mandate_chain"] not in serialized_frames
    assert pur["checkout_receipt"] not in serialized_frames
    assert pur["payment_receipt"] not in serialized_frames


@pytest.mark.asyncio
async def test_seller_agent_dispatch_zapier_mcp_rejects_missing_or_demo_subscription_id():
    from backend.agents.seller_agent import seller_agent

    # 1. Missing subscription_id on seller_agent.dispatch_zapier_mcp directly -> REJECTED
    missing_res = await seller_agent.dispatch_zapier_mcp()
    assert missing_res["status"] == "REJECTED"
    assert missing_res["error"] == "SUBSCRIPTION_ID_REQUIRED"

    blank_res = await seller_agent.dispatch_zapier_mcp(subscription_id="   ")
    assert blank_res["status"] == "REJECTED"
    assert blank_res["error"] == "SUBSCRIPTION_ID_REQUIRED"

    # 2. Demo placeholder I-AUTONOMOUS-8902 is not exempted on seller_agent.dispatch_zapier_mcp -> REJECTED
    demo_id_res = await seller_agent.dispatch_zapier_mcp(subscription_id="I-AUTONOMOUS-8902")
    assert demo_id_res["status"] == "REJECTED"
    assert demo_id_res["error"] == "SUBSCRIPTION_NOT_FOUND"

    demo_paypal_res = await seller_agent.dispatch_zapier_mcp(paypal_subscription_id="I-AUTONOMOUS-8902")
    assert demo_paypal_res["status"] == "REJECTED"
    assert demo_paypal_res["error"] == "SUBSCRIPTION_NOT_FOUND"



