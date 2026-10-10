"""
Sets up the Claude Desktop demo: seller MCP server + buyer wallet MCP server.

Three parties, three keys, three places on disk (all under the gitignored .ap2_local/):
  merchant/merchant_key.jwk   seller signs checkouts (loaded via AP2_MERCHANT_PRIVATE_KEY_FILE)
  wallet/agent_key.jwk        buyer agent signs closed mandates (created by the wallet process itself)
  owner/owner_key.jwk         owner signs spending limits once, here, and is never given to the wallet

Steps:
  1. Create (or reuse) the merchant key and pin its public key in the wallet.
  2. Ask the wallet process to create (or reuse) its agent key and report the public key.
  3. Create (or reuse) the owner key and enroll it through the seller's challenge flow
     (GET /api/agent/keys/challenge -> POST /api/agent/keys/register) in the demo database.
  4. Owner signs AP2 v0.2 open mandates (cap, tiers, merchant) bound to the agent key.
  5. Write claude_desktop_config.local.json with absolute paths for both servers.

Uses its own database (backend/data/claude_desktop_demo.db by default), never the dev database.

    python scripts/setup_claude_desktop_demo.py --monthly-cap 60
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DEV_DB = (ROOT_DIR / "backend" / "data" / "a2a_commerce.db").resolve()


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Set up the Claude Desktop seller + buyer wallet demo.")
    p.add_argument("--email", default="demo-owner@example.com", help="Owner billing email the limits are bound to")
    p.add_argument("--business", default="Demo Buyer Corp", help="Owner business entity for key enrollment")
    p.add_argument("--monthly-cap", type=float, default=60.00, help="Monthly spending cap in USD")
    p.add_argument("--tiers", default="ap2-batch,ap2-gateway,ap2-cluster", help="Comma-separated allowed tiers")
    p.add_argument("--valid-hours", type=int, default=24, help="Hours until the owner's limits expire")
    p.add_argument("--local-dir", default=str(ROOT_DIR / ".ap2_local"), help="Directory for demo keys and wallet state")
    p.add_argument("--db-path", default=str(ROOT_DIR / "backend" / "data" / "claude_desktop_demo.db"),
                   help="Database shared by the setup and the seller MCP server")
    p.add_argument("--config-out", default=str(ROOT_DIR / "claude_desktop_config.local.json"),
                   help="Where to write the generated Claude Desktop config")
    return p.parse_args()


def _new_key_file(path: Path, kid: str):
    """Returns the key stored at `path`, creating it first if it does not exist."""
    from jwcrypto.jwk import JWK

    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        key = JWK.generate(kty="EC", crv="P-256", kid=kid)
        with open(path, "x", encoding="utf-8") as f:
            f.write(key.export_private())
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return JWK.from_json(path.read_text(encoding="utf-8"))


def main() -> int:
    args = _parse_args()
    local_dir = Path(args.local_dir).resolve()
    db_path = Path(args.db_path).resolve()
    config_out = Path(args.config_out).resolve()
    wallet_dir = local_dir / "wallet"
    merchant_key_path = local_dir / "merchant" / "merchant_key.jwk"
    owner_key_path = local_dir / "owner" / "owner_key.jwk"
    tiers = [t.strip().lower() for t in args.tiers.split(",") if t.strip()]

    if db_path == DEV_DB:
        print(f"Refusing to use the dev database ({DEV_DB}). Pass a different --db-path.", file=sys.stderr)
        return 2
    if not (args.monthly_cap > 0):
        print("--monthly-cap must be greater than 0.", file=sys.stderr)
        return 2
    if args.valid_hours <= 0:
        print("--valid-hours must be greater than 0.", file=sys.stderr)
        return 2

    # Must be set before anything imports backend.config
    os.environ["A2A_DB_PATH"] = str(db_path)
    os.environ["MOCK_EXTERNAL_APIS"] = "true"
    os.environ["AP2_MERCHANT_PRIVATE_KEY_FILE"] = str(merchant_key_path)
    os.environ["AP2_WALLET_DIR"] = str(wallet_dir)
    sys.path.insert(0, str(ROOT_DIR))

    # 1. Merchant key (seller side); the wallet gets only the public half
    merchant_key = _new_key_file(merchant_key_path, f"ap2-merchant-demo-{secrets.token_hex(4)}")
    wallet_dir.mkdir(parents=True, exist_ok=True)
    (wallet_dir / "merchant_public.jwk").write_text(merchant_key.export_public(), encoding="utf-8")
    print(f"[1/5] Merchant key ready      kid={merchant_key.kid}")

    # 2. Agent key, created by the wallet process so this script never holds it
    env = dict(os.environ, PYTHONPATH=str(ROOT_DIR))
    init = subprocess.run(
        [sys.executable, "-m", "backend.wallet.mcp_server", "--init"],
        cwd=str(ROOT_DIR), env=env, capture_output=True, text=True, timeout=60,
    )
    if init.returncode != 0:
        print(f"Wallet --init failed:\n{init.stderr}", file=sys.stderr)
        return 1
    agent_pub = json.loads(init.stdout.strip().splitlines()[-1])
    print(f"[2/5] Wallet agent key ready  kid={agent_pub.get('kid')}")

    from fastapi.testclient import TestClient
    from jwcrypto.jwk import JWK

    from backend.database import get_buyer_key, get_buyer_key_email
    from backend.server import app
    from backend.services.ap2_keys import get_merchant_public_jwk
    from backend.services.crypto_mandate import sign_es256_challenge
    from backend.services.trusted_surface_service import create_trusted_surface_open_mandates

    # The seller process must sign with the key the wallet just pinned
    if JWK(**get_merchant_public_jwk()).thumbprint() != merchant_key.thumbprint():
        print(
            "The seller is loading a different merchant key (is AP2_MERCHANT_PRIVATE_KEY_JWK set in .env?). "
            "Unset it so AP2_MERCHANT_PRIVATE_KEY_FILE is used.",
            file=sys.stderr,
        )
        return 1

    # 3. Owner key, enrolled through the seller's challenge flow
    owner_key = _new_key_file(owner_key_path, f"owner-{secrets.token_hex(4)}")
    email = args.email.strip().lower()
    with TestClient(app) as client:
        challenge = client.get("/api/agent/keys/challenge").json()["challenge"]
        res = client.post(
            "/api/agent/keys/register",
            json={
                "kid": owner_key.kid,
                "publicKeyJwk": owner_key.export_public(as_dict=True),
                "contractorEmail": email,
                "businessEntity": args.business,
                "challenge": challenge,
                "challengeSignature": sign_es256_challenge(challenge, owner_key),
            },
        )
    if res.status_code == 201:
        print(f"[3/5] Owner key enrolled      kid={owner_key.kid} email={email}")
    elif res.status_code == 409:
        stored = get_buyer_key(owner_key.kid)
        same_key = bool(stored) and JWK(**json.loads(stored)).thumbprint() == owner_key.thumbprint()
        same_email = (get_buyer_key_email(owner_key.kid) or "").strip().lower() == email
        if not (same_key and same_email):
            print(f"Key id {owner_key.kid} is registered to a different key or email; refusing.", file=sys.stderr)
            return 1
        print(f"[3/5] Owner key already enrolled kid={owner_key.kid} email={email}")
    else:
        print(f"Owner key enrollment failed ({res.status_code}): {res.text}", file=sys.stderr)
        return 1

    # 4. Owner signs the spending limits, bound to the wallet's agent key
    limits = create_trusted_surface_open_mandates(
        buyer_email=email,
        monthly_budget_cap=args.monthly_cap,
        allowed_tiers=tiers,
        agent_key=JWK(**agent_pub),
        user_key=owner_key,
        validity_seconds=args.valid_hours * 3600,
    )
    owner_limits = {
        "buyer_email": email,
        "owner_kid": limits["owner_kid"],
        "agent_kid": limits["agent_kid"],
        "open_checkout_mandate_token": limits["open_checkout_mandate_token"],
        "open_payment_mandate_token": limits["open_payment_mandate_token"],
        "constraints": limits["constraints"],
        "expires_at": limits["expires_at"],
        "billing_term_expires_at": limits["billing_term_expires_at"],
    }
    (wallet_dir / "owner_limits.json").write_text(json.dumps(owner_limits, indent=2), encoding="utf-8")
    (wallet_dir / "owner_public.jwk").write_text(owner_key.export_public(), encoding="utf-8")
    print(f"[4/5] Owner limits signed     cap=${args.monthly_cap:.2f}/mo tiers={','.join(tiers)}")
    print(f"      Purchase window until {limits['expires_at']}; renewals authorized until {limits['billing_term_expires_at']}")

    # 5. Claude Desktop config with absolute paths (works no matter which directory Claude launches from)
    common_env = {"PYTHONPATH": str(ROOT_DIR), "PYTHONUNBUFFERED": "1"}
    config = {
        "mcpServers": {
            "ap2-seller-node": {
                "command": sys.executable,
                "args": ["-m", "backend.mcp_server"],
                "env": {
                    **common_env,
                    "MOCK_EXTERNAL_APIS": "true",
                    "A2A_DB_PATH": str(db_path),
                    "AP2_MERCHANT_PRIVATE_KEY_FILE": str(merchant_key_path),
                },
            },
            "ap2-buyer-wallet": {
                "command": sys.executable,
                "args": ["-m", "backend.wallet.mcp_server"],
                "env": {**common_env, "AP2_WALLET_DIR": str(wallet_dir)},
            },
        }
    }
    config_out.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(f"[5/5] Claude Desktop config   {config_out}")

    if os.name == "nt":
        backend_cmd = (
            f'$env:A2A_DB_PATH="{db_path}"; $env:AP2_MERCHANT_PRIVATE_KEY_FILE="{merchant_key_path}"; '
            "python -m backend.server"
        )
    else:
        backend_cmd = f'A2A_DB_PATH="{db_path}" AP2_MERCHANT_PRIVATE_KEY_FILE="{merchant_key_path}" python -m backend.server'
    print(
        "\nNext:\n"
        f"  - Copy both entries from {config_out.name} into Claude Desktop's claude_desktop_config.json\n"
        "    (Windows: %APPDATA%\\Claude\\, macOS: ~/Library/Application Support/Claude/), then restart Claude Desktop.\n"
        "  - To watch purchases in the portal, start the backend against the same database and merchant key:\n"
        f"      {backend_cmd}\n"
        "  - Re-run this script any time to sign fresh limits (new cap, or after they expire)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
