"""
Exhaustive Test Suite: Two-Sided Marketplace & Compute Node Operator PayPal Payouts.
SPEC-001 v1.9.0 / Milestone S2-SETTLE (Sprint 2).

Verifies:
1. Strict Rule 6 integer-cents arithmetic (zero float drift, exact penny conservation).
2. Node operator onboarding, validation, and pattern matching.
3. Automated monthly batch disbursements via PayPal Payouts REST API (POST /v1/payments/payouts).
4. Cycle-level payout deduplication (idempotent no-op on re-runs).
5. QuickBooks Online v3 Bill Payment export (Debit Account 5000 COGS / Credit Account 99 Clearing).
6. Marketplace revenue summary, settlement ledger, and REST API endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from backend.server import app
from backend.services.marketplace_payout_service import (
    calculate_split_amounts_cents,
    dollars_to_integer_cents,
    integer_cents_to_dollars_string,
    marketplace_payout_service,
    MarketplacePayoutService,
    DEFAULT_OPERATOR_SPLIT_BPS,
)
from backend.database import (
    register_node_operator,
    get_node_operator,
    get_operator_by_email,
    get_operator_for_node,
    list_node_operators,
    list_payout_batches,
    list_payout_items,
    get_payout_batch,
    save_subscription,
    reset_all_data,
)


@pytest.fixture(autouse=True)
def clean_marketplace_state():
    """Ensure clean isolated database before each test."""
    reset_all_data()
    yield
    reset_all_data()


# ---------------------------------------------------------------------------
# 1. Rule 6: Integer Cents Margin Arithmetic & Precision Invariant Tests
# ---------------------------------------------------------------------------

def test_calculate_split_amounts_cents_rule6_invariant():
    """Verifies that integer cents calculation never suffers from float rounding drift."""
    test_amounts_cents = [
        0,
        1,
        3,
        7,
        13,
        4999,   # $49.99 Batch Worker
        7999,   # $79.99 Gateway Node
        14999,  # $149.99 Cluster Node
        20000,  # $200.00
        999999, # Large figure
    ]

    for gross in test_amounts_cents:
        for split_bps in [0, 5000, 7000, 8500, 9000, 10000]:
            net_op, platform_fee = calculate_split_amounts_cents(gross, split_bps)
            # Penny conservation invariant: gross must equal net + fee exactly
            assert net_op + platform_fee == gross, f"Failed penny conservation for gross={gross}, split={split_bps}"
            assert net_op >= 0
            assert platform_fee >= 0

    # Specifically for $79.99 (7999 cents) at 85.00%:
    # 7999 * 8500 // 10000 = 6799 cents ($67.99)
    # 7999 - 6799 = 1200 cents ($12.00)
    net_79, fee_79 = calculate_split_amounts_cents(7999, 8500)
    assert net_79 == 6799
    assert fee_79 == 1200
    assert net_79 + fee_79 == 7999

    # For $49.99 (4999 cents) at 85.00%:
    # 4999 * 8500 // 10000 = 4249 cents ($42.49)
    # 4999 - 4249 = 750 cents ($7.50)
    net_49, fee_49 = calculate_split_amounts_cents(4999, 8500)
    assert net_49 == 4249
    assert fee_49 == 750
    assert net_49 + fee_49 == 4999


def test_calculate_split_amounts_cents_fail_closed():
    """Verifies that invalid inputs fail closed immediately."""
    with pytest.raises(ValueError, match="non-negative"):
        calculate_split_amounts_cents(-100, 8500)

    with pytest.raises(ValueError, match="split_bps must be between 0 and 10000"):
        calculate_split_amounts_cents(1000, 10001)

    with pytest.raises(ValueError, match="split_bps must be between 0 and 10000"):
        calculate_split_amounts_cents(1000, -1)


def test_dollar_cents_conversions():
    assert dollars_to_integer_cents(79.99) == 7999
    assert dollars_to_integer_cents(49.99) == 4999
    assert dollars_to_integer_cents(0.01) == 1
    assert dollars_to_integer_cents(0.0) == 0

    assert integer_cents_to_dollars_string(7999) == "79.99"
    assert integer_cents_to_dollars_string(4999) == "49.99"
    assert integer_cents_to_dollars_string(7) == "0.07"
    assert integer_cents_to_dollars_string(0) == "0.00"


# ---------------------------------------------------------------------------
# 2. Operator Onboarding & Pattern Resolution Tests
# ---------------------------------------------------------------------------

def test_operator_registration_and_lookup():
    op = marketplace_payout_service.register_operator(
        name="Custom HyperScale GPU Provider",
        email="payouts@hyperscalegpu.io",
        assigned_nodes=["node-hyperscale-", "node-h100-"],
        split_bps=8800,  # 88%
        operator_id="op_hyperscale_01",
    )

    assert op["operator_id"] == "op_hyperscale_01"
    assert op["name"] == "Custom HyperScale GPU Provider"
    assert op["email"] == "payouts@hyperscalegpu.io"
    assert op["split_bps"] == 8800
    assert op["assigned_nodes"] == ["node-hyperscale-", "node-h100-"]

    # Lookup by ID
    looked_up = marketplace_payout_service.get_operator("op_hyperscale_01")
    assert looked_up is not None
    assert looked_up["name"] == "Custom HyperScale GPU Provider"

    # Lookup by Node Pattern
    matched = get_operator_for_node("node-hyperscale-east-01")
    assert matched is not None
    assert matched["operator_id"] == "op_hyperscale_01"

    # Fallback to default operator for unmatched node
    matched_default = get_operator_for_node("node-unknown-cluster-99")
    assert matched_default is not None
    assert matched_default["operator_id"] in ("op_lambda_gpu", "op_equinix_metal", "op_coreweave_cluster", "op_hyperscale_01")


def test_operator_registration_validation_fail_closed():
    with pytest.raises(ValueError, match="Valid operator PayPal email"):
        marketplace_payout_service.register_operator(name="Bad Operator", email="invalid-email")

    with pytest.raises(ValueError, match="split_bps must be between"):
        marketplace_payout_service.register_operator(
            name="Bad Operator",
            email="bad@example.com",
            split_bps=12000,
        )


# ---------------------------------------------------------------------------
# 3. Batch Disbursement Execution via PayPal Payouts & QBO Bills
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_fleet_payout_batch_mock_mode():
    """Tests full execution of batch payouts in sandbox/mock mode with QBO Bill exports."""
    # Seed an active subscription in SQLite
    sub_data = {
        "subscription_id": "I-TEST-PAYOUT-SUB-01",
        "status": "ACTIVE",
        "contractor_email": "agent-payout-test@example.com",
        "agreed_monthly_rate": 79.99,
        "tier_id": "ap2-gateway",
        "assigned_did": "mcp+https://gateway-01.example.com/agents/node-gateway-test01",
    }
    save_subscription(sub_data)

    res = await marketplace_payout_service.execute_fleet_payout_batch(
        cycle_id="2026-10",
        subscription_ids=["I-TEST-PAYOUT-SUB-01"],
        dry_run=False,
    )

    assert res["status"] == "SUCCESS"
    assert res["item_count"] == 1
    assert res["total_gross_cents"] == 7999
    assert res["total_payout_cents"] == 6799
    assert res["total_platform_fee_cents"] == 1200
    assert res["total_gross_dollars"] == 79.99
    assert res["total_payout_dollars"] == 67.99
    assert res["total_platform_fee_dollars"] == 12.00
    assert res["effective_take_rate_bps"] == 1500  # 15.00%
    assert res["qbo_bills_exported"] == 1

    sample_bill = res["sample_qbo_bill"]
    assert sample_bill["entity"] == "QuickBooks_Online"
    assert sample_bill["target_endpoint"] == "https://quickbooks.api.intuit.com/v3/company/{realmId}/bill"
    assert sample_bill["payload"]["Bill"]["TotalAmt"] == 67.99
    assert sample_bill["account_mapping"]["cogs_account"].startswith("5000")

    # Verify batch is saved in database
    batch_in_db = get_payout_batch(res["batch_id"])
    assert batch_in_db is not None
    assert batch_in_db["item_count"] == 1
    assert len(batch_in_db["items"]) == 1
    assert batch_in_db["items"][0]["subscription_id"] == "I-TEST-PAYOUT-SUB-01"
    assert batch_in_db["items"][0]["net_payout_cents"] == 6799


@pytest.mark.asyncio
async def test_payout_batch_deduplication_idempotency():
    """Verifies that re-running a batch payout for the same cycle is idempotent."""
    sub_data = {
        "subscription_id": "I-TEST-IDEM-01",
        "status": "ACTIVE",
        "contractor_email": "agent-idem@example.com",
        "agreed_monthly_rate": 49.99,
        "tier_id": "ap2-batch",
        "assigned_did": "mcp+https://batch-01.example.com/agents/node-batch-idem01",
    }
    save_subscription(sub_data)

    # First run: settles
    res1 = await marketplace_payout_service.execute_fleet_payout_batch(
        cycle_id="2026-10",
        subscription_ids=["I-TEST-IDEM-01"],
    )
    assert res1["status"] == "SUCCESS"
    assert res1["item_count"] == 1

    # Second run without explicit override: detects already settled, returns IDEMPOTENT_NOOP
    res2 = await marketplace_payout_service.execute_fleet_payout_batch(
        cycle_id="2026-10",
    )
    # The subscription was already disbursed, so no new items for it
    disbursed_ids = [d["subscription_id"] for d in res2.get("disbursements", [])]
    assert "I-TEST-IDEM-01" not in disbursed_ids


@pytest.mark.asyncio
async def test_payout_dry_run_mode():
    """Verifies that dry_run computes exact margins without touching database records."""
    sub_data = {
        "subscription_id": "I-TEST-DRYRUN-01",
        "status": "ACTIVE",
        "contractor_email": "agent-dry@example.com",
        "agreed_monthly_rate": 149.99,
        "tier_id": "ap2-cluster",
    }
    save_subscription(sub_data)

    res = await marketplace_payout_service.execute_fleet_payout_batch(
        cycle_id="2026-10",
        subscription_ids=["I-TEST-DRYRUN-01"],
        dry_run=True,
    )
    assert res["status"] == "DRY_RUN"
    assert res["total_gross_cents"] == 14999
    # Verify no payout batch was recorded in database
    batches = list_payout_batches()
    assert len(batches) == 0


# ---------------------------------------------------------------------------
# 4. Financial Summary & Ledger Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_marketplace_revenue_summary_and_settlement_ledger():
    # Execute a batch
    sub_data = {
        "subscription_id": "I-TEST-SUMM-01",
        "status": "ACTIVE",
        "contractor_email": "agent-summ@example.com",
        "agreed_monthly_rate": 79.99,
        "tier_id": "ap2-gateway",
    }
    save_subscription(sub_data)

    await marketplace_payout_service.execute_fleet_payout_batch(
        cycle_id="2026-10",
        subscription_ids=["I-TEST-SUMM-01"],
    )

    summary = marketplace_payout_service.get_marketplace_revenue_summary()
    assert summary["total_gmv_cents"] >= 7999
    assert summary["total_operator_payouts_cents"] >= 6799
    assert summary["total_platform_revenue_cents"] >= 1200
    assert summary["active_operators_count"] >= 3
    assert summary["disbursed_batches_count"] >= 1
    assert summary["effective_take_rate_pct"] == "15.00%"

    ledger = marketplace_payout_service.get_operator_settlement_ledger()
    assert len(ledger) >= 1
    item = ledger[0]
    assert "operator_name" in item
    assert "gross_amount_dollars" in item
    assert "net_payout_dollars" in item
    assert "platform_fee_dollars" in item


# ---------------------------------------------------------------------------
# 5. REST API Endpoints Verification
# ---------------------------------------------------------------------------

def test_marketplace_rest_endpoints():
    client = TestClient(app)

    # 1. Register operator
    reg_payload = {
        "name": "Datacenter Alpha Nodes",
        "email": "alpha-payouts@datacenter.net",
        "assigned_nodes": ["node-alpha-"],
        "split_bps": 8500,
        "operator_id": "op_alpha_dc",
    }
    res = client.post("/api/marketplace/operators/register", json=reg_payload)
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "SUCCESS"
    assert body["operator"]["operator_id"] == "op_alpha_dc"

    # 2. List operators
    res_list = client.get("/api/marketplace/operators")
    assert res_list.status_code == 200
    ops = res_list.json()["operators"]
    assert any(o["operator_id"] == "op_alpha_dc" for o in ops)

    # 3. Get operator details
    res_get = client.get("/api/marketplace/operators/op_alpha_dc")
    assert res_get.status_code == 200
    assert res_get.json()["operator"]["name"] == "Datacenter Alpha Nodes"

    # 4. Get unknown operator (404)
    res_404 = client.get("/api/marketplace/operators/op_nonexistent")
    assert res_404.status_code == 404

    # 5. Execute batch payout endpoint
    sub_data = {
        "subscription_id": "I-API-TEST-SUB-01",
        "status": "ACTIVE",
        "contractor_email": "api-agent@example.com",
        "agreed_monthly_rate": 79.99,
        "tier_id": "ap2-gateway",
        "assigned_did": "mcp+https://gateway-01.example.com/agents/node-alpha-01",
    }
    save_subscription(sub_data)

    payout_req = {
        "cycle_id": "2026-10",
        "subscription_ids": ["I-API-TEST-SUB-01"],
        "dry_run": False,
    }
    res_batch = client.post("/api/marketplace/payouts/execute-batch", json=payout_req)
    assert res_batch.status_code == 200
    batch_json = res_batch.json()
    assert batch_json["status"] == "SUCCESS"
    assert batch_json["total_gross_cents"] == 7999
    assert batch_json["total_payout_cents"] == 6799
    batch_id = batch_json["batch_id"]

    # 6. List payout batches
    res_batches = client.get("/api/marketplace/payouts/batches")
    assert res_batches.status_code == 200
    assert res_batches.json()["count"] >= 1

    # 7. Get specific batch
    res_single = client.get(f"/api/marketplace/payouts/batches/{batch_id}")
    assert res_single.status_code == 200
    assert res_single.json()["batch"]["batch_id"] == batch_id

    # 8. Settlement ledger
    res_ledger = client.get("/api/marketplace/payouts/ledger")
    assert res_ledger.status_code == 200
    assert res_ledger.json()["count"] >= 1

    # 9. Revenue summary
    res_summary = client.get("/api/marketplace/revenue-summary")
    assert res_summary.status_code == 200
    summary_data = res_summary.json()["summary"]
    assert summary_data["total_gmv_cents"] >= 7999
    assert summary_data["effective_take_rate_pct"] == "15.00%"
