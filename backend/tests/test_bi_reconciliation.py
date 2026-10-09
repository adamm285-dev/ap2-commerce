"""
Automated Evaluation of BI Suite & Header Financial Reconciliation
==================================================================
Asserts that the dynamic BI tradeImpact derivation:
1. Places each active transaction into EXACTLY ONE capability tier (disjoint partitioning).
2. Sum of BI annualized_gmv matches the Header ARR to the exact cent.
3. Sum of BI mandates_cleared matches the Header active subscriptions count.
4. Holds true across pre-simulation and all simulated purchase tiers ($49.99, $79.99, $179.99).
"""

import pytest
from copy import deepcopy

# Canonical initial transaction seed matching telemetryData.ts / fleet database
INITIAL_TRANSACTIONS = [
    {
        "id": "TXN-AP2-9021",
        "trade_vertical": "High-Throughput Batch Worker",
        "monthly_amount": 49.99,
        "status": "PENDING_DEPOSIT",
    },
    {
        "id": "TXN-AP2-9022",
        "trade_vertical": "Dedicated AI Service Gateway",
        "monthly_amount": 79.99,
        "status": "ACTIVE_STREAMING",
    },
    {
        "id": "TXN-AP2-9023",
        "trade_vertical": "Enterprise Cluster Node",
        "monthly_amount": 179.99,
        "status": "ACTIVE_STREAMING",
    },
    {
        "id": "TXN-AP2-9024",
        "trade_vertical": "Dedicated AI Service Gateway",
        "monthly_amount": 79.99,
        "status": "ACTIVE_STREAMING",
    },
    {
        "id": "TXN-AP2-9025",
        "trade_vertical": "High-Throughput Batch Worker",
        "monthly_amount": 49.99,
        "status": "ACTIVE_STREAMING",
    },
    {
        "id": "TXN-AP2-9026",
        "trade_vertical": "Dedicated AI Service Gateway",
        "monthly_amount": 79.99,
        "status": "ACTIVE_STREAMING",
    },
    {
        "id": "TXN-AP2-9027",
        "trade_vertical": "High-Throughput Batch Worker",
        "monthly_amount": 49.99,
        "status": "ACTIVE_STREAMING",
    },
    {
        "id": "TXN-AP2-9028",
        "trade_vertical": "Dedicated AI Service Gateway",
        "monthly_amount": 79.99,
        "status": "ACTIVE_STREAMING",
    },
    {
        "id": "TXN-AP2-9029",
        "trade_vertical": "Enterprise Cluster Node",
        "monthly_amount": 179.99,
        "status": "ACTIVE_STREAMING",
    },
    {
        "id": "TXN-AP2-9030",
        "trade_vertical": "Dedicated AI Service Gateway",
        "monthly_amount": 79.99,
        "status": "ACTIVE_STREAMING",
    },
    {
        "id": "TXN-AP2-9031",
        "trade_vertical": "High-Throughput Batch Worker",
        "monthly_amount": 49.99,
        "status": "ACTIVE_STREAMING",
    },
    {
        "id": "TXN-AP2-9032",
        "trade_vertical": "Dedicated AI Service Gateway",
        "monthly_amount": 79.99,
        "status": "ACTIVE_STREAMING",
    },
    {
        "id": "TXN-AP2-9033",
        "trade_vertical": "Enterprise Cluster Node",
        "monthly_amount": 179.99,
        "status": "ACTIVE_STREAMING",
    },
    {
        "id": "TXN-AP2-9034",
        "trade_vertical": "High-Throughput Batch Worker",
        "monthly_amount": 49.99,
        "status": "ACTIVE_STREAMING",
    },
]

TIER_ORDER = [
    {"trade": "High-Throughput Batch Worker", "plan_rate": 49.99},
    {"trade": "Dedicated AI Service Gateway", "plan_rate": 79.99},
    {"trade": "Enterprise Cluster Node", "plan_rate": 179.99},
]
KNOWN_TIERS = {t["trade"] for t in TIER_ORDER}


def get_tier_for_transaction(t: dict) -> str:
    """Matches the exact TS logic in telemetryData.ts buildTradeImpactFromTransactions."""
    vertical = t.get("trade_vertical")
    if vertical and vertical in KNOWN_TIERS:
        return vertical
    amount = float(t.get("monthly_amount") or 0.0)
    if abs(amount - 49.99) < 0.05:
        return "High-Throughput Batch Worker"
    if abs(amount - 179.99) < 0.05:
        return "Enterprise Cluster Node"
    return "Dedicated AI Service Gateway"


def build_trade_impact(txns: list) -> list:
    active_rows = [t for t in txns if t.get("status") == "ACTIVE_STREAMING"]
    tiers = []
    for tier in TIER_ORDER:
        active_for_tier = [t for t in active_rows if get_tier_for_transaction(t) == tier["trade"]]
        count = len(active_for_tier)
        monthly = round(sum(float(t.get("monthly_amount") or tier["plan_rate"]) for t in active_for_tier), 2)
        annualized = round(monthly * 12, 2)
        tiers.append({
            "trade": tier["trade"],
            "count": count,
            "mandates_cleared": count,
            "monthly_settlement": monthly,
            "annualized_gmv": annualized,
        })
    return tiers


def compute_header_metrics(txns: list) -> dict:
    active_rows = [t for t in txns if t.get("status") == "ACTIVE_STREAMING"]
    active_count = len(active_rows)
    mrr = round(sum(float(t.get("monthly_amount") or 0.0) for t in active_rows), 2)
    arr = round(mrr * 12, 2)
    return {"active_count": active_count, "mrr": mrr, "arr": arr}


def test_bi_suite_reconciliation_before_purchase():
    """Verify initial seed telemetry matches across Header and BI Suite before simulation."""
    header = compute_header_metrics(INITIAL_TRANSACTIONS)
    bi_tiers = build_trade_impact(INITIAL_TRANSACTIONS)

    bi_total_arr = round(sum(t["annualized_gmv"] for t in bi_tiers), 2)
    bi_total_mandates = sum(t["mandates_cleared"] for t in bi_tiers)

    assert header["active_count"] == 13
    assert header["mrr"] == 1219.87
    assert header["arr"] == 14638.44

    assert bi_total_mandates == 13
    assert bi_total_mandates == header["active_count"]
    assert bi_total_arr == 14638.44
    assert bi_total_arr == header["arr"]


def test_bi_suite_reconciliation_after_gateway_purchase():
    """Simulate $79.99 Gateway purchase and verify 100% ARR and mandate parity."""
    txns = deepcopy(INITIAL_TRANSACTIONS)
    idx = next(i for i, t in enumerate(txns) if t["id"] == "TXN-AP2-9021")
    txns[idx]["status"] = "ACTIVE_STREAMING"
    txns[idx]["monthly_amount"] = 79.99
    txns[idx]["trade_vertical"] = "Dedicated AI Service Gateway"

    header = compute_header_metrics(txns)
    bi_tiers = build_trade_impact(txns)

    bi_total_arr = round(sum(t["annualized_gmv"] for t in bi_tiers), 2)
    bi_total_mandates = sum(t["mandates_cleared"] for t in bi_tiers)

    assert header["active_count"] == 14
    assert header["mrr"] == 1299.86
    assert header["arr"] == 15598.32

    assert bi_total_mandates == 14
    assert bi_total_mandates == header["active_count"]
    assert bi_total_arr == 15598.32
    assert bi_total_arr == header["arr"]


def test_bi_suite_reconciliation_after_counter_offer_batch_purchase():
    """Simulate $49.99 Batch counter-offer purchase and verify 100% ARR and mandate parity."""
    txns = deepcopy(INITIAL_TRANSACTIONS)
    idx = next(i for i, t in enumerate(txns) if t["id"] == "TXN-AP2-9021")
    txns[idx]["status"] = "ACTIVE_STREAMING"
    txns[idx]["monthly_amount"] = 49.99
    txns[idx]["trade_vertical"] = "High-Throughput Batch Worker"

    header = compute_header_metrics(txns)
    bi_tiers = build_trade_impact(txns)

    bi_total_arr = round(sum(t["annualized_gmv"] for t in bi_tiers), 2)
    bi_total_mandates = sum(t["mandates_cleared"] for t in bi_tiers)

    assert header["active_count"] == 14
    assert header["mrr"] == 1269.86
    assert header["arr"] == 15238.32

    assert bi_total_mandates == 14
    assert bi_total_mandates == header["active_count"]
    assert bi_total_arr == 15238.32
    assert bi_total_arr == header["arr"]


def test_bi_suite_reconciliation_after_cluster_node_purchase():
    """Simulate $179.99 Cluster Node purchase and verify 100% ARR and mandate parity."""
    txns = deepcopy(INITIAL_TRANSACTIONS)
    idx = next(i for i, t in enumerate(txns) if t["id"] == "TXN-AP2-9021")
    txns[idx]["status"] = "ACTIVE_STREAMING"
    txns[idx]["monthly_amount"] = 179.99
    txns[idx]["trade_vertical"] = "Enterprise Cluster Node"

    header = compute_header_metrics(txns)
    bi_tiers = build_trade_impact(txns)

    bi_total_arr = round(sum(t["annualized_gmv"] for t in bi_tiers), 2)
    bi_total_mandates = sum(t["mandates_cleared"] for t in bi_tiers)

    assert header["active_count"] == 14
    assert header["mrr"] == 1399.86
    assert header["arr"] == 16798.32

    assert bi_total_mandates == 14
    assert bi_total_mandates == header["active_count"]
    assert bi_total_arr == 16798.32
    assert bi_total_arr == header["arr"]
