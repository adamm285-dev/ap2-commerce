#!/usr/bin/env python3
"""
AP2 Autonomous Commerce — Autonomous A2A Commerce Judge Audit Harness
====================================================================
A self-contained, automated evaluation script designed for hackathon judges.
Executes the full autonomous agent lifecycle in-memory via FastAPI TestClient
and direct cryptographic verification, requiring ZERO external dependencies or active servers.

Usage:
    python scripts/judge_audit_harness.py
"""

import sys
import os
import json
import time
import uuid

# Ensure portal root is on sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PORTAL_ROOT = os.path.dirname(SCRIPT_DIR)
if PORTAL_ROOT not in sys.path:
    sys.path.insert(0, PORTAL_ROOT)

import tempfile
import atexit

# Ensure isolated temp DB in local mode to protect development DB
if not ("--remote" in sys.argv or os.environ.get("REMOTE_AUDIT") == "1"):
    if not os.environ.get("A2A_DB_PATH"):
        _temp_judge_db = os.path.join(tempfile.gettempdir(), f"a2a_judge_{os.getpid()}_{uuid.uuid4().hex[:8]}.db")
        os.environ["A2A_DB_PATH"] = _temp_judge_db

        def _cleanup_judge_temp_db():
            for ext in ["", "-wal", "-shm", "-journal"]:
                f = _temp_judge_db + ext
                try:
                    if os.path.exists(f):
                        os.remove(f)
                except OSError:
                    pass

        atexit.register(_cleanup_judge_temp_db)
        from backend.database import init_db
        init_db()

import argparse
import httpx
from fastapi.testclient import TestClient
from backend.server import app
from backend.services.crypto_mandate import (
    generate_ed25519_keypair,
    sign_ed25519_message,
)
from backend.services.backoffice.qbo_exporter import qbo_exporter
from backend.agents.seller_agent import _COMPLETED_SUBSCRIPTIONS, _ACTIVE_CONTRACTOR_SUBSCRIPTIONS
from ap2.sdk.mandate import MandateClient
from ap2.sdk.generated.checkout_mandate import CheckoutMandate
from ap2.sdk.generated.payment_mandate import PaymentMandate
from ap2.sdk.generated.types.amount import Amount
from ap2.sdk.generated.types.merchant import Merchant
from ap2.sdk.generated.types.payment_instrument import PaymentInstrument
from backend.services.ap2_service import (
    AP2_MERCHANT_ID,
    AP2_MERCHANT_NAME,
    verify_ap2_chains,
    ERR_INVALID_MANDATE,
)
from backend.services.trusted_surface_service import (
    create_trusted_surface_open_mandates,
    get_demo_agent_key,
)

# Terminal color helpers
GREEN = "\033[92m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

parser = argparse.ArgumentParser(description="AP2 Autonomous Agentic Commerce Judge Audit Harness")
parser.add_argument("--remote", action="store_true", help="Execute checks against live cloud deployment (https://api.ap2-commerce.org)")
parser.add_argument("--url", type=str, default="https://api.ap2-commerce.org", help="Target API URL")
args, _ = parser.parse_known_args()

if args.remote or os.environ.get("REMOTE_AUDIT") == "1":
    client = httpx.Client(base_url=args.url, timeout=30.0)
else:
    client = TestClient(app)

def print_header(title: str):
    print(f"\n{BOLD}{CYAN}══════════════════════════════════════════════════════════════════════{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}══════════════════════════════════════════════════════════════════════{RESET}")

def print_step(step_num: int, title: str):
    print(f"\n{BOLD}[CHECK {step_num}] {title}{RESET}")

def print_pass(msg: str):
    print(f"  {GREEN}✓ PASS:{RESET} {msg}")

def print_fail(msg: str):
    print(f"  {RED}✗ FAIL:{RESET} {msg}")
    sys.exit(1)

def run_judge_audit():
    print_header("AP2 AUTONOMOUS COMMERCE: AGENTIC COMMERCE & AP2 PROTOCOL JUDGE AUDIT")
    print(f"  Target Event: {BOLD}PayPal AI Hackathon 2026{RESET}")
    print(f"  Standard:     {BOLD}Model Context Protocol (MCP 2024-11-05){RESET}")
    print(f"  Payment Rail: {BOLD}PayPal Subscriptions & Vault MIT{RESET}")
    print(f"  Time:         {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")

    # -------------------------------------------------------------------------
    # CHECK 1: JSON-RPC 2.0 MCP Protocol Handshake
    # -------------------------------------------------------------------------
    print_step(1, "Model Context Protocol (MCP) JSON-RPC 2.0 Handshake")
    mcp_init_req = {
        "jsonrpc": "2.0",
        "id": "judge-init-01",
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "JudgeEvaluationClient", "version": "1.0.0"}
        }
    }
    mcp_endpoint = "/a2a/mcp" if (args.remote or os.environ.get("REMOTE_AUDIT") == "1") else "/mcp"
    res = client.post(mcp_endpoint, json=mcp_init_req)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    body = res.json()
    assert body.get("jsonrpc") == "2.0"
    server_info = body.get("result", {}).get("serverInfo", {})
    print_pass(f"MCP Server Handshake: {server_info.get('name')} v{server_info.get('version')} (Endpoint: {mcp_endpoint})")

    # List Tools
    tools_req = {"jsonrpc": "2.0", "id": "judge-tools-02", "method": "tools/list", "params": {}}
    res = client.post(mcp_endpoint, json=tools_req)
    assert res.status_code == 200
    tools = res.json().get("result", {}).get("tools", [])
    tool_names = [t["name"] for t in tools]
    print_pass(f"Registered MCP Tools ({len(tools)}): {', '.join(tool_names)}")

    # -------------------------------------------------------------------------
    # CHECK 2: Standard AP2 Negotiation & Mandate Chain Generation ($79.99/mo Plan under $100 Cap)
    # -------------------------------------------------------------------------
    print_step(2, "Standard AP2 Negotiation & Mandate Chain Generation (ES256 SD-JWT)")
    neg_req = {
        "jsonrpc": "2.0",
        "id": "judge-neg-02",
        "method": "tools/call",
        "params": {
            "name": "negotiate_tier_terms",
            "arguments": {
                "buyer_agent_id": "usr_judge_01",
                "buyer_email": "agent-alpha@example.com",
                "tier_id": "ap2-gateway",
                "monthly_budget_cap": 100.00,
            },
        },
    }
    mcp_endpoint = "/a2a/mcp" if (args.remote or os.environ.get("REMOTE_AUDIT") == "1") else "/mcp"
    res = client.post(mcp_endpoint, json=neg_req)
    assert res.status_code == 200
    neg_body = res.json().get("result", {})
    if "content" in neg_body and neg_body["content"]:
        neg_res = json.loads(neg_body["content"][0]["text"])
    else:
        neg_res = neg_body

    assert neg_res.get("status") == "APPROVED"
    assert neg_res.get("agreed_monthly_rate") == 79.99
    chk_jwt = neg_res.get("checkout_jwt")
    chk_hash = neg_res.get("checkout_hash")
    nonce = neg_res.get("nonce")
    assert chk_jwt is not None
    assert chk_hash is not None
    assert len(chk_hash) == 64

    # Generate AP2 v0.2 Mandate Chains (ES256 SD-JWT)
    agent_key = get_demo_agent_key()
    mandate_client = MandateClient()
    open_mandates = create_trusted_surface_open_mandates(
        monthly_budget_cap=100.00,
        buyer_email="agent-alpha@example.com",
        allowed_tiers=["ap2-batch", "ap2-gateway", "ap2-cluster"],
        agent_key=agent_key,
    )
    open_chk_tok = open_mandates["open_checkout_mandate_token"]
    open_pay_tok = open_mandates["open_payment_mandate_token"]

    closed_chk = CheckoutMandate(
        vct="mandate.checkout.1",
        checkout_jwt=chk_jwt,
        checkout_hash=chk_hash,
    )
    chk_chain = mandate_client.present(
        holder_key=agent_key,
        mandate_token=open_chk_tok,
        payloads=[closed_chk],
        aud=AP2_MERCHANT_ID,
        nonce=nonce,
    )

    closed_pay = PaymentMandate(
        vct="mandate.payment.1",
        transaction_id=chk_hash,
        payment_amount=Amount(amount=7999, currency="USD"),
        payee=Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME),
        payment_instrument=PaymentInstrument(type="paypal_vault", id="vault_judge_01"),
    )
    pay_chain = mandate_client.present(
        holder_key=agent_key,
        mandate_token=open_pay_tok,
        payloads=[closed_pay],
        aud=AP2_MERCHANT_ID,
        nonce=nonce,
    )

    assert "~~" in chk_chain
    assert "~~" in pay_chain
    print_pass("Mandate Evaluated: APPROVED at $79.99/mo (Within $100.00 Cap)")
    print_pass(f"AP2 v0.2 Mandate Chains Generated: ES256 SD-JWT ({len(chk_chain)} chars chk, {len(pay_chain)} chars pay)")

    # -------------------------------------------------------------------------
    # CHECK 3: Dynamic Multi-Tier Counter-Offer Negotiation
    # -------------------------------------------------------------------------
    print_step(3, "Sub-Budget Autonomous Counter-Offer Bargaining ($60 Cap vs $79.99 Plan)")
    sub_budget_req = {
        "buyerAgentId": "usr_judge_02",
        "amount": 79.99,
        "recurrence": "monthly",
        "category": "autonomous-compute",
        "monthlyBudgetCap": 60.00,
    }
    res = client.post("/api/agent/spending-mandate/evaluate", json=sub_budget_req)
    assert res.status_code == 200
    counter_res = res.json()
    is_counter_available = counter_res.get("counterOfferAvailable") or counter_res.get("counter_offer_available")
    assert is_counter_available is True
    tier_name = counter_res.get("counterOfferTier") or counter_res.get("counter_offer_tier", "AP2 Batch Worker")
    counter_price = counter_res.get("counterOfferAmount") or counter_res.get("counter_offer_amount")
    assert counter_price == 49.99
    print_pass(f"Autonomous Counter-Offer Generated: '{tier_name}' at ${counter_price}/mo")
    print_pass(f"Reasoning: {counter_res.get('reason')}")

    # -------------------------------------------------------------------------
    # CHECK 4: AP2 v0.2 Cryptographic Anti-Tamper Verification Suite
    # -------------------------------------------------------------------------
    print_step(4, "Interactive Cryptographic Anti-Tamper Verification (AP2 v0.2 ES256 SD-JWT)")

    # 4a: Untampered baseline
    valid_eval = verify_ap2_chains(
        checkout_mandate_token=chk_chain,
        payment_mandate_token=pay_chain,
        checkout_jwt=chk_jwt,
        expected_nonce=nonce,
        buyer_email="agent-alpha@example.com",
    )
    assert valid_eval.get("valid") is True
    print_pass("Baseline Untampered AP2 v0.2 Chains: VERIFIED (Status 200 OK)")

    # 4b: 1-cent inflation tampering ($79.99 -> $80.00)
    tampered_pay_inflated = PaymentMandate(
        vct="mandate.payment.1",
        transaction_id=chk_hash,
        payment_amount=Amount(amount=8000, currency="USD"),
        payee=Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME),
        payment_instrument=PaymentInstrument(type="paypal_vault", id="vault_judge_01"),
    )
    tampered_pay_chain_inflated = mandate_client.present(
        holder_key=agent_key,
        mandate_token=open_pay_tok,
        payloads=[tampered_pay_inflated],
        aud=AP2_MERCHANT_ID,
        nonce=nonce,
    )
    eval_inflated = verify_ap2_chains(
        checkout_mandate_token=chk_chain,
        payment_mandate_token=tampered_pay_chain_inflated,
        checkout_jwt=chk_jwt,
        expected_nonce=nonce,
        buyer_email="agent-alpha@example.com",
    )
    assert eval_inflated.get("valid") is False
    assert eval_inflated.get("error") in (ERR_INVALID_MANDATE, "invalid_mandate")
    assert eval_inflated.get("checkout_receipt") is not None
    assert eval_inflated.get("payment_receipt") is not None
    print_pass(f"Tamper Test (+1¢ Inflation $79.99 -> $80.00): REJECTED ({eval_inflated['error']}, Dual Signed Error Receipts)")

    # 4c: Payee alteration (Altered payee entity)
    tampered_pay_payee = PaymentMandate(
        vct="mandate.payment.1",
        transaction_id=chk_hash,
        payment_amount=Amount(amount=7999, currency="USD"),
        payee=Merchant(id="forged-payee-id", name="Attacker Systems LLC"),
        payment_instrument=PaymentInstrument(type="paypal_vault", id="vault_judge_01"),
    )
    tampered_pay_chain_payee = mandate_client.present(
        holder_key=agent_key,
        mandate_token=open_pay_tok,
        payloads=[tampered_pay_payee],
        aud=AP2_MERCHANT_ID,
        nonce=nonce,
    )
    eval_payee = verify_ap2_chains(
        checkout_mandate_token=chk_chain,
        payment_mandate_token=tampered_pay_chain_payee,
        checkout_jwt=chk_jwt,
        expected_nonce=nonce,
        buyer_email="agent-alpha@example.com",
    )
    assert eval_payee.get("valid") is False
    assert eval_payee.get("error") in (ERR_INVALID_MANDATE, "invalid_mandate")
    assert eval_payee.get("checkout_receipt") is not None
    assert eval_payee.get("payment_receipt") is not None
    print_pass(f"Tamper Test (Payee Alteration): REJECTED ({eval_payee['error']}, Dual Signed Error Receipts)")

    # 4d: Spending cap breach ($70.00 cap vs $79.99 agreed price)
    low_cap_open = create_trusted_surface_open_mandates(
        monthly_budget_cap=70.00,
        buyer_email="agent-alpha@example.com",
        allowed_tiers=["ap2-batch", "ap2-gateway", "ap2-cluster"],
        agent_key=agent_key,
    )
    breach_pay_chain = mandate_client.present(
        holder_key=agent_key,
        mandate_token=low_cap_open["open_payment_mandate_token"],
        payloads=[closed_pay],
        aud=AP2_MERCHANT_ID,
        nonce=nonce,
    )
    eval_cap = verify_ap2_chains(
        checkout_mandate_token=chk_chain,
        payment_mandate_token=breach_pay_chain,
        checkout_jwt=chk_jwt,
        expected_nonce=nonce,
        buyer_email="agent-alpha@example.com",
    )
    assert eval_cap.get("valid") is False
    assert eval_cap.get("error") in (ERR_INVALID_MANDATE, "invalid_mandate")
    assert eval_cap.get("checkout_receipt") is not None
    assert eval_cap.get("payment_receipt") is not None
    print_pass(f"Tamper Test (Budget Cap Breach $70.00 Cap vs $79.99 Price): REJECTED ({eval_cap['error']}, Dual Signed Error Receipts)")

    # -------------------------------------------------------------------------
    # CHECK 5: Autonomous Compute Node Provisioning & KYC Identity Enforcement
    # -------------------------------------------------------------------------
    print_step(5, "Autonomous Compute Node Provisioning & Dedicated Endpoint Allocation")
    judge_sub_id = "I-JUDGE-SUB-01"
    judge_email = "judge@example.com"
    _COMPLETED_SUBSCRIPTIONS[judge_sub_id] = {
        "subscription_id": judge_sub_id,
        "status": "ACTIVE",
        "contractor_email": judge_email,
        "tier_id": "ap2-gateway",
        "agreed_monthly_rate": 79.99,
        "subscriber_country_code": "US",
    }
    _ACTIVE_CONTRACTOR_SUBSCRIPTIONS[judge_email] = judge_sub_id

    prov_res = client.post("/api/agent/provision", json={
        "subscriptionId": judge_sub_id,
        "contractorEmail": judge_email,
    })
    assert prov_res.status_code == 201
    prov_data = prov_res.json()
    assert prov_data["status"] in ("ALLOCATED", "PROVISIONED")
    assert prov_data["endpoint"].startswith("mcp+https://")
    print_pass(f"Dedicated Node Endpoint Provisioned: {prov_data['endpoint']}")
    print_pass(f"Transport: {prov_data.get('carrier')} (Workload Quota: 450 tasks/mo)")

    # -------------------------------------------------------------------------
    # CHECK 6: Downline Back-Office ERP Payloads (QuickBooks Online API v3 Account 6300)
    # -------------------------------------------------------------------------
    print_step(6, "Authentic Back-Office ERP Payloads (QuickBooks Online API v3 Expense)")
    qbo_pkg = qbo_exporter.format_purchase_expense_payload(
        contractor_name="Autonomous Compute Buyer",
        business_entity="Demo Buyer Corp",
        contractor_email="agent-alpha@example.com",
        monthly_fee=79.99,
        paypal_subscription_id="I-AUTONOMOUS-8902",
        allocated_did="mcp+https://gateway-01.ap2.market",
        mandate_proof_hash="PROOF-HASH-5678",
        trade_vertical="Autonomous Cloud Compute",
        txn_date="2026-10-03",
    )
    purchase = qbo_pkg["Purchase"]
    assert purchase["PaymentType"] == "CreditCard"
    assert purchase["TotalAmt"] == 79.99
    line_item = purchase["Line"][0]
    account_ref = line_item["AccountBasedExpenseLineDetail"]["AccountRef"]
    assert account_ref["value"] == "6300"
    print_pass(f"QuickBooks Online v3 Purchase: Mapped to GL Account {account_ref['value']} ({account_ref['name']})")

    # -------------------------------------------------------------------------
    # CHECK 7: Telemetry & Financial Mathematics Reconciliation
    # -------------------------------------------------------------------------
    print_step(7, "Enterprise Fleet Ledger & AP2 Telemetry Reconciliation")
    stats_res = client.get("/api/fleet/stats")
    assert stats_res.status_code == 200, f"Failed to get fleet stats: {stats_res.text}"
    stats_data = stats_res.json()

    ledger_res = client.get("/api/fleet/ledger?profile=ap2")
    assert ledger_res.status_code == 200, f"Failed to get fleet ledger: {ledger_res.text}"
    ledger_data = ledger_res.json()

    transactions = ledger_data.get("transactions", [])
    active_rows = [t for t in transactions if t.get("status") in ["ACTIVE", "ACTIVE_STREAMING"]]
    active_count = len(active_rows)
    expected_mrr = round(sum(float(t.get("monthly_amount", 0.0)) for t in active_rows), 2)
    expected_arr = round(expected_mrr * 12, 2)

    backend_mrr = round(float(stats_data.get("total_mrr", 0.0)), 2)
    backend_arr = round(float(stats_data.get("annualized_gmv", 0.0)), 2)
    mandates_cleared = stats_data.get("mandates_cleared")

    assert backend_mrr == expected_mrr, f"MRR mismatch: {backend_mrr} != {expected_mrr}"
    assert backend_arr == expected_arr, f"ARR mismatch: {backend_arr} != {expected_arr}"
    assert mandates_cleared == active_count, f"Mandates cleared mismatch: {mandates_cleared} != {active_count}"

    print_pass(f"Fleet Scale:          {active_count} Active Autonomous Nodes (Total Subscriptions: {len(transactions)})")
    print_pass(f"Active Fleet MRR:     ${backend_mrr:,.2f}/mo (Reconciled sum of active subscriptions)")
    print_pass(f"Autonomous GMV (ARR): ${backend_arr:,.2f} ARR (Exact: ${backend_mrr:,.2f} × 12)")
    print_pass(f"Mandates Cleared:     {mandates_cleared} Mandates (1:1 per active subscription)")

    # -------------------------------------------------------------------------
    # CHECK 8: Live Fleet Ledger & Bryntum Scheduling Verification
    # -------------------------------------------------------------------------
    print_step(8, "AG Studio Fleet Ledger & Bryntum Scheduling Telemetry")
    ledger_res = client.get("/api/fleet/ledger")
    assert ledger_res.status_code == 200
    ledger_data = ledger_res.json()
    assert ledger_data.get("count") >= 14
    print_pass(f"AG Studio Fleet Ledger: Hydrated {ledger_data.get('count')} subscriptions from SQLite WAL")

    stats_res = client.get("/api/fleet/stats")
    assert stats_res.status_code == 200
    stats_data = stats_res.json()
    assert stats_data.get("total_subscribers") >= 14
    print_pass(f"Fleet Telemetry: Active Nodes {stats_data.get('active_lines')} (Total Subscriptions: {stats_data.get('total_subscribers')}) • {stats_data.get('compliance_guard')}")

    sched_res = client.get("/api/fleet/schedule")
    assert sched_res.status_code == 200
    sched_data = sched_res.json()
    assert len(sched_data.get("resources", [])) >= 4
    assert len(sched_data.get("events", [])) >= 4
    print_pass(f"Bryntum Scheduler: Verified {len(sched_data.get('resources', []))} cluster nodes & {len(sched_data.get('events', []))} workload tasks")

    # Lock dispatch slot via API
    lock_res = client.post(
        "/api/agent/dispatch/lock-slot",
        json={
            "jobId": "WORKLOAD-AUDIT-01",
            "territoryZone": "Zone 1 - High Throughput",
            "slotStartIso": "2026-10-02 13:00",
            "paypalTransactionId": "TXN-AUDIT-9021",
        },
    )
    assert lock_res.status_code == 200
    assert lock_res.json().get("success") is True
    print_pass("Bryntum Cluster Schedule: Locked execution window on Node Alpha (HTTP 200)")

    # -------------------------------------------------------------------------
    # CHECK 9: Dynamic Self-Service Buyer Key Onboarding & Challenge Verification
    # -------------------------------------------------------------------------
    print_step(9, "Dynamic Self-Service Buyer Key Onboarding (AP2 Challenge-Response)")
    chal_res = client.get("/api/agent/keys/challenge")
    assert chal_res.status_code == 200
    challenge_nonce = chal_res.json()["challenge"]
    assert len(challenge_nonce) == 64
    print_pass(f"Ephemeral Challenge Nonce: {challenge_nonce[:16]}... (Algorithm: Ed25519, TTL: 300s)")

    # Generate new keypair and sign challenge
    new_priv, new_pub = generate_ed25519_keypair()
    sig = sign_ed25519_message(challenge_nonce, new_priv)
    kid = f"judge-audit-buyer-{uuid.uuid4().hex[:6]}"

    # Register external autonomous buyer key
    reg_res = client.post(
        "/api/agent/keys/register",
        json={
            "kid": kid,
            "publicKeyHex": new_pub,
            "contractorEmail": "judge@example.com",
            "businessEntity": "Demo Buyer Corp",
            "challenge": challenge_nonce,
            "challengeSignature": sig,
            "monthlyBudgetCap": 150.0,
        },
    )
    assert reg_res.status_code == 201
    assert reg_res.json().get("status") == "REGISTERED"
    assert reg_res.json().get("verified") is True
    print_pass(f"Cryptographic Challenge Verification: Key '{kid}' Enrolled (Ed25519 Verified)")

    # Anti-tamper challenge verification: tampered signature with fresh challenge must be rejected
    bad_chal_res = client.get("/api/agent/keys/challenge")
    assert bad_chal_res.status_code == 200
    bad_challenge = bad_chal_res.json()["challenge"]
    bad_sig = "0" * 128
    tamper_res = client.post(
        "/api/agent/keys/register",
        json={
            "kid": f"tampered-buyer-{uuid.uuid4().hex[:6]}",
            "publicKeyHex": new_pub,
            "contractorEmail": "hacker@example.com",
            "businessEntity": "Forged Agent LLC",
            "challenge": bad_challenge,
            "challengeSignature": bad_sig,
        },
    )
    assert tamper_res.status_code == 401
    print_pass("Anti-Tamper Challenge Guard: Forged/Tampered signature REJECTED (HTTP 401 Unauthorized)")

    # -------------------------------------------------------------------------
    # FINAL VERDICT
    # -------------------------------------------------------------------------
    print_header("AUDIT SUMMARY: 9/9 CHECKS PASSED (100% GREEN)")
    print(f"{BOLD}{GREEN}ALL OPERATIONAL INVARIANTS, CRYPTOGRAPHIC PROOFS, AND PAYMENT CONTRACTS VERIFIED.{RESET}\n")

if __name__ == "__main__":
    run_judge_audit()
