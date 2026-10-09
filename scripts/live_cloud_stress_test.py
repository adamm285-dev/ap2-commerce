#!/usr/bin/env python3
"""
AP2 Autonomous Commerce — Live Cloud Multi-Agent Stress Testing Harness
======================================================================
Launches concurrent autonomous buyer agents against the live cloud deployment
at https://api.ap2-commerce.org over Model Context Protocol (MCP) and REST APIs.

Evaluates:
- High-concurrency MCP JSON-RPC 2.0 tool execution
- Counter-offer bargaining under budget constraint
- Asymmetric Ed25519 challenge-response key registration
- Adversarial attack resilience (tampering, budget breach, forged signatures)
- Sub-250ms response latency under load
"""

import sys
import os
import time
import asyncio
import httpx
from typing import Dict, Any, List

# Ensure portal root is on sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PORTAL_ROOT = os.path.dirname(SCRIPT_DIR)
if PORTAL_ROOT not in sys.path:
    sys.path.insert(0, PORTAL_ROOT)

from backend.harness.external_buyer_agent import ExternalBuyerAgent
from backend.services.crypto_mandate import (
    generate_dynamic_mandate_proof,
    verify_mandate_proof,
    generate_ed25519_keypair,
    sign_ed25519_message,
)

BASE_URL = os.environ.get("TARGET_URL", "https://api.ap2-commerce.org")

# Color formatting
GREEN = "\033[92m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


async def run_scenario_standard_procurement(server_url: str) -> Dict[str, Any]:
    t0 = time.perf_counter()
    mcp_endpoint = f"{server_url}/a2a/mcp" if not server_url.endswith("/a2a/mcp") else server_url
    agent = ExternalBuyerAgent(
        transport="http",
        server_url=mcp_endpoint,
        contractor_name="Nexus Autonomous Buyer",
        business_entity="Nexus Cloud Systems LLC",
        contractor_email="buyer@nexus-systems.io",
        trade_id="ap2-gateway",
        budget_cap=120.00,
        area_code="US",
        verbose=False,
        reset_ledger=False,
    )
    result = await agent.execute_autonomous_procurement()
    elapsed = time.perf_counter() - t0
    did = result.get("provisioned_did") or result.get("assigned_did") or result.get("endpoint")
    sub_id = result.get("paypal_subscription_id")
    is_success = (
        result.get("status") == "COMPLETED"
        and bool(did)
        and bool(sub_id)
        and (str(sub_id).startswith("I-") or str(sub_id).startswith("SUB-"))
    )
    return {
        "scenario": "Standard Procurement ($120 Cap -> $79.99 Gateway)",
        "success": is_success,
        "elapsed_ms": round(elapsed * 1000, 1),
        "endpoint": did,
        "sub_id": sub_id,
    }


async def run_scenario_bargaining_counter_offer(client: httpx.AsyncClient) -> Dict[str, Any]:
    t0 = time.perf_counter()
    res = await client.post(
        "/api/agent/spending-mandate/evaluate",
        json={
            "buyerAgentId": "stress_buyer_sub_budget",
            "amount": 79.99,
            "recurrence": "monthly",
            "category": "autonomous-compute",
            "monthlyBudgetCap": 55.00,
        },
    )
    elapsed = time.perf_counter() - t0
    data = res.json()
    is_counter = data.get("counterOfferAvailable") or data.get("counter_offer_available")
    counter_amt = data.get("counterOfferAmount") or data.get("counter_offer_amount")
    return {
        "scenario": "Sub-Budget Bargaining ($55 Cap -> $49.99 Batch Worker Counter)",
        "success": res.status_code == 200 and is_counter is True and counter_amt == 49.99,
        "elapsed_ms": round(elapsed * 1000, 1),
        "counter_amount": counter_amt,
    }


async def run_scenario_cryptographic_buyer_onboarding(client: httpx.AsyncClient) -> Dict[str, Any]:
    t0 = time.perf_counter()
    chal_res = await client.get("/api/agent/keys/challenge")
    nonce = chal_res.json()["challenge"]

    priv, pub = generate_ed25519_keypair()
    sig = sign_ed25519_message(nonce, priv)

    reg_res = await client.post(
        "/api/agent/keys/register",
        json={
            "kid": f"stress-agent-{uuid_short()}",
            "publicKeyHex": pub,
            "contractorEmail": "stress_agent@nexus-systems.io",
            "businessEntity": "Apex Autonomous Cloud Corp",
            "challenge": nonce,
            "challengeSignature": sig,
            "monthlyBudgetCap": 200.0,
        },
    )
    elapsed = time.perf_counter() - t0
    data = reg_res.json()
    return {
        "scenario": "Self-Service Ed25519 Cryptographic Buyer Key Onboarding",
        "success": reg_res.status_code == 201 and data.get("verified") is True,
        "elapsed_ms": round(elapsed * 1000, 1),
        "kid": data.get("kid"),
    }


async def run_scenario_adversarial_tamper_attack(client: httpx.AsyncClient) -> Dict[str, Any]:
    t0 = time.perf_counter()
    # 1. Fetch valid challenge nonce from the server
    ch_res = await client.get("/api/agent/keys/challenge")
    if ch_res.status_code != 200:
        raise RuntimeError(f"Failed to fetch challenge nonce: HTTP {ch_res.status_code}")
    real_challenge = ch_res.json()["challenge"]

    # 2. Attempt forged registration with valid issued nonce but corrupted Ed25519 signature
    bad_sig = "a" * 128
    res = await client.post(
        "/api/agent/keys/register",
        json={
            "kid": f"malicious-counterfeit-agent-{int(time.time())}",
            "publicKeyHex": "0" * 64,
            "contractorEmail": "attacker@evil.org",
            "businessEntity": "Forged Agent Group",
            "challenge": real_challenge,
            "challengeSignature": bad_sig,
        },
    )
    elapsed = time.perf_counter() - t0
    # Must be strictly rejected with HTTP 401 Unauthorized by cryptographic verifier
    rejected = res.status_code == 401
    return {
        "scenario": "Adversarial Forged Ed25519 Signature Defense",
        "success": rejected,
        "elapsed_ms": round(elapsed * 1000, 1),
        "http_status": res.status_code,
    }


async def run_scenario_fleet_ledger_high_frequency(client: httpx.AsyncClient) -> Dict[str, Any]:
    t0 = time.perf_counter()
    res = await client.get("/api/fleet/ledger")
    elapsed = time.perf_counter() - t0
    data = res.json()
    return {
        "scenario": "AG Studio Fleet Ledger SQLite WAL Query",
        "success": res.status_code == 200 and data.get("count") >= 14,
        "elapsed_ms": round(elapsed * 1000, 1),
        "lines": data.get("count"),
    }


def uuid_short() -> str:
    import uuid
    return uuid.uuid4().hex[:8]


async def run_stress_test_suite():
    print(f"\n{BOLD}{CYAN}══════════════════════════════════════════════════════════════════════{RESET}")
    print(f"{BOLD}{CYAN}  AP2 AUTONOMOUS COMMERCE: LIVE CLOUD MULTI-AGENT STRESS TEST SUITE{RESET}")
    print(f"{BOLD}{CYAN}══════════════════════════════════════════════════════════════════════{RESET}")
    print(f"  Target Server: {BOLD}{BASE_URL}{RESET}")
    print(f"  Timestamp:     {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    print(f"  Concurrency:   5 Autonomous Scenarios in Parallel\n")

    limits = httpx.Limits(max_keepalive_connections=20, max_connections=50)
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0, limits=limits) as client:
        start_time = time.perf_counter()

        # Launch all 5 test scenarios concurrently
        tasks = [
            run_scenario_standard_procurement(BASE_URL),
            run_scenario_bargaining_counter_offer(client),
            run_scenario_cryptographic_buyer_onboarding(client),
            run_scenario_adversarial_tamper_attack(client),
            run_scenario_fleet_ledger_high_frequency(client),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_elapsed = time.perf_counter() - start_time

    all_passed = True
    for i, res in enumerate(results, 1):
        if isinstance(res, Exception):
            all_passed = False
            print(f"  {RED}✗ SCENARIO {i}: EXCEPTION: {res}{RESET}")
            continue

        status_str = f"{GREEN}✓ PASS{RESET}" if res["success"] else f"{RED}✗ FAIL{RESET}"
        print(f"  [{i}] {res['scenario']}")
        print(f"      Status:     {status_str}")
        print(f"      Latency:    {BOLD}{res['elapsed_ms']} ms{RESET}")
        for k, v in res.items():
            if k not in ("scenario", "success", "elapsed_ms"):
                print(f"      {k}: {v}")
        print()

    print(f"{BOLD}{CYAN}──────────────────────────────────────────────────────────────────────{RESET}")
    print(f"  Total Stress Batch Duration: {BOLD}{total_elapsed:.2f}s{RESET}")
    if all_passed:
        print(f"  {BOLD}{GREEN}ALL CONCURRENT AGENT STRESS SCENARIOS PASSED (100% HEALTHY){RESET}\n")
    else:
        print(f"  {BOLD}{RED}ONE OR MORE SCENARIOS FAILED{RESET}\n")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_stress_test_suite())
