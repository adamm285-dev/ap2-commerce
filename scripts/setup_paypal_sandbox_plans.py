#!/usr/bin/env python3
"""
AP2 Autonomous Commerce — PayPal Sandbox Product & Billing Plans Provisioner
============================================================================
Automates creation of the AP2 Catalog Product and the 3 subscription
billing plans (AP2 Batch Worker $49.99, AP2 Service Gateway $79.99, AP2 Cluster Node $179.99)
on PayPal Developer Sandbox.

Outputs ready-to-paste environment variables for .env:
  PAYPAL_PLAN_ID_SOLO=P-...
  PAYPAL_PLAN_ID_PRO=P-...
  PAYPAL_PLAN_ID_DISPATCH=P-...

Usage:
  python scripts/setup_paypal_sandbox_plans.py
  python scripts/setup_paypal_sandbox_plans.py --dry-run
"""

import sys
import os
import argparse
import asyncio
import hashlib
from typing import Dict, Any, Optional
import httpx

# Ensure portal root is on sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PORTAL_ROOT = os.path.dirname(SCRIPT_DIR)
if PORTAL_ROOT not in sys.path:
    sys.path.insert(0, PORTAL_ROOT)

from backend.config import settings

GREEN = "\033[92m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


async def get_sandbox_token(client: httpx.AsyncClient, client_id: str, client_secret: str, base_url: str) -> str:
    """Authenticates with PayPal OAuth2 to acquire a bearer access token."""
    res = await client.post(
        f"{base_url}/v1/oauth2/token",
        auth=(client_id, client_secret),
        data={"grant_type": "client_credentials"},
        headers={"Accept": "application/json", "Accept-Language": "en_US"},
        timeout=15.0,
    )
    res.raise_for_status()
    data = res.json()
    return data.get("access_token", "")


async def create_catalog_product(client: httpx.AsyncClient, token: str, base_url: str) -> str:
    """Creates the AP2 Autonomous Compute Network Catalog Product."""
    payload = {
        "name": "AP2 Autonomous Compute Network",
        "description": "Autonomous Agent Payments Protocol (AP2) compute node provisioning and service gateways.",
        "type": "SERVICE",
        "category": "COMPUTER_SOFTWARE",
    }
    res = await client.post(
        f"{base_url}/v1/catalogs/products",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=15.0,
    )
    res.raise_for_status()
    return res.json().get("id", "")


async def create_billing_plan(
    client: httpx.AsyncClient,
    token: str,
    base_url: str,
    product_id: str,
    name: str,
    description: str,
    monthly_price: float,
) -> str:
    """Creates an active monthly recurring billing plan under the specified product."""
    payload = {
        "product_id": product_id,
        "name": name,
        "description": description,
        "status": "ACTIVE",
        "billing_cycles": [
            {
                "frequency": {"interval_unit": "MONTH", "interval_count": 1},
                "tenure_type": "REGULAR",
                "sequence": 1,
                "total_cycles": 0,
                "pricing_scheme": {
                    "fixed_price": {
                        "value": f"{monthly_price:.2f}",
                        "currency_code": "USD",
                    }
                },
            }
        ],
        "payment_preferences": {
            "auto_bill_outstanding": True,
            "setup_fee_failure_action": "CONTINUE",
            "payment_failure_threshold": 3,
        },
    }
    res = await client.post(
        f"{base_url}/v1/billing/plans",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=15.0,
    )
    res.raise_for_status()
    return res.json().get("id", "")


async def main():
    parser = argparse.ArgumentParser(description="Setup PayPal Sandbox Catalog Product and Billing Plans")
    parser.add_argument("--dry-run", action="store_true", help="Simulate plan creation without contacting PayPal API")
    args = parser.parse_args()

    client_id = settings.paypal_client_id.strip() if settings.paypal_client_id else ""
    client_secret = settings.paypal_client_secret.strip() if settings.paypal_client_secret else ""
    base_url = settings.paypal_base_url.rstrip("/")

    print(f"\n{BOLD}{CYAN}══════════════════════════════════════════════════════════════════════{RESET}")
    print(f"{BOLD}{CYAN}  AP2 Autonomous Commerce — PayPal Sandbox Billing Plans Provisioner{RESET}")
    print(f"{BOLD}{CYAN}══════════════════════════════════════════════════════════════════════{RESET}\n")

    is_dry_run = args.dry_run or not client_id or not client_secret

    if is_dry_run:
        if not client_id or not client_secret:
            print(f"{YELLOW}[NOTICE] PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET not configured in .env.{RESET}")
            print(f"{YELLOW}Running in DRY-RUN simulation mode.{RESET}\n")
        else:
            print(f"{YELLOW}[DRY-RUN] Simulating plan creation as requested.{RESET}\n")

        # Deterministic simulated plan IDs
        sim_solo = "P-AP2-BATCH-WORKER"
        sim_pro = "P-AP2-SERVICE-GATEWAY"
        sim_dispatch = "P-AP2-CLUSTER-NODE"

        print(f"{GREEN}✓ Simulated Catalog Product:{RESET} PROD-AP2-AUTONOMOUS-COMPUTE")
        print(f"{GREEN}✓ Plan 1:{RESET} AP2 Batch Worker ($49.99/mo)       --> {BOLD}{sim_solo}{RESET}")
        print(f"{GREEN}✓ Plan 2:{RESET} AP2 Service Gateway ($79.99/mo)     --> {BOLD}{sim_pro}{RESET}")
        print(f"{GREEN}✓ Plan 3:{RESET} AP2 Cluster Node ($179.99/mo)       --> {BOLD}{sim_dispatch}{RESET}\n")

        print(f"{CYAN}Configuration to paste into your .env file:{RESET}")
        print(f"--------------------------------------------------")
        print(f"PAYPAL_PLAN_ID_SOLO={sim_solo}")
        print(f"PAYPAL_PLAN_ID_PRO={sim_pro}")
        print(f"PAYPAL_PLAN_ID_DISPATCH={sim_dispatch}")
        print(f"--------------------------------------------------\n")
        return 0

    print(f"{CYAN}[1/4] Authenticating with PayPal Sandbox ({base_url})...{RESET}")
    async with httpx.AsyncClient() as client:
        try:
            token = await get_sandbox_token(client, client_id, client_secret, base_url)
            print(f"  {GREEN}✓ Access Token acquired successfully.{RESET}")
        except Exception as e:
            print(f"  {RED}✗ Authentication failed: {e}{RESET}")
            return 1

        print(f"{CYAN}[2/4] Creating Catalog Product 'AP2 Autonomous Compute Network'...{RESET}")
        try:
            product_id = await create_catalog_product(client, token, base_url)
            print(f"  {GREEN}✓ Product Created:{RESET} {BOLD}{product_id}{RESET}")
        except Exception as e:
            print(f"  {RED}✗ Product creation failed: {e}{RESET}")
            return 1

        print(f"{CYAN}[3/4] Creating 3 Recurring Billing Plans...{RESET}")
        try:
            solo_id = await create_billing_plan(
                client, token, base_url, product_id,
                name="AP2 Batch Worker",
                description="High-throughput batch worker compute node with 125 operations/mo.",
                monthly_price=49.99,
            )
            print(f"  {GREEN}✓ Batch Worker ($49.99/mo):{RESET} {BOLD}{solo_id}{RESET}")

            pro_id = await create_billing_plan(
                client, token, base_url, product_id,
                name="AP2 Service Gateway",
                description="Dedicated AI service gateway compute node with 450 operations/mo.",
                monthly_price=79.99,
            )
            print(f"  {GREEN}✓ Service Gateway ($79.99/mo):{RESET} {BOLD}{pro_id}{RESET}")

            dispatch_id = await create_billing_plan(
                client, token, base_url, product_id,
                name="AP2 Cluster Node",
                description="Enterprise cluster compute node with 1,200 operations/mo.",
                monthly_price=179.99,
            )
            print(f"  {GREEN}✓ Cluster Node ($179.99/mo):{RESET} {BOLD}{dispatch_id}{RESET}")
        except Exception as e:
            print(f"  {RED}✗ Plan creation failed: {e}{RESET}")
            return 1

    print(f"\n{BOLD}{GREEN}[4/4] SUCCESS: PayPal Sandbox Plans Provisioned!{RESET}\n")
    print(f"{CYAN}Copy and paste these lines into your .env file:{RESET}")
    print(f"--------------------------------------------------")
    print(f"PAYPAL_PLAN_ID_SOLO={solo_id}")
    print(f"PAYPAL_PLAN_ID_PRO={pro_id}")
    print(f"PAYPAL_PLAN_ID_DISPATCH={dispatch_id}")
    print(f"--------------------------------------------------\n")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
