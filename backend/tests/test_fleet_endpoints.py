"""
Tests verifying Enterprise Fleet Ledger, AG Studio stats, and Bryntum Scheduling endpoints.
Validates dynamic database hydration, real-time MRR and GMV reconciliation,
and locked territory appointment scheduling.
"""

import pytest
from fastapi.testclient import TestClient
from ..server import app
from ..database import get_fleet_ledger, get_fleet_stats, get_fleet_schedule, list_dispatch_slots

client = TestClient(app)


def test_get_fleet_ledger_endpoint():
    """GET /api/fleet/ledger returns all 14 fleet contractor subscriptions from SQLite."""
    response = client.get("/api/fleet/ledger")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "active"
    assert data["count"] == 14
    txns = data["transactions"]
    assert len(txns) == 14

    # Verify AutonomousBuyerAgent-Alpha-Batch starts in ledger
    alpha = next((t for t in txns if t["contractor_name"] == "AutonomousBuyerAgent-Alpha-Batch"), None)
    assert alpha is not None
    assert alpha["status"] in ("PENDING_DEPOSIT", "ACTIVE_STREAMING")

    # Verify other agent is ACTIVE_STREAMING
    nexus = next((t for t in txns if t["contractor_name"] == "AutonomousBuyerAgent-Nexus-Gateway"), None)
    assert nexus is not None
    assert nexus["status"] == "ACTIVE_STREAMING"
    assert nexus["allocated_did"] == "mcp+https://gateway-01.acme-systems.io/mcp"
    assert "Ed25519" in nexus["kyc_status"]


def test_get_fleet_stats_endpoint():
    """GET /api/fleet/stats returns aggregated metrics matching database state."""
    response = client.get("/api/fleet/stats")
    assert response.status_code == 200
    stats = response.json()

    assert stats["total_subscribers"] == 14
    assert stats["active_lines"] in (13, 14)
    assert stats["total_mrr"] in (1219.87, 1269.86)
    assert stats["annualized_gmv"] == round(stats["total_mrr"] * 12, 2)
    assert stats["mandates_cleared"] == stats["active_lines"]
    assert "FastMCP" in stats["carrier_resporg"]
    assert len(stats["trade_breakdown"]) > 0


def test_get_fleet_schedule_and_lock_slot():
    """Bryntum schedule returns resources, 24/7 shifts, and locked territory appointment windows."""
    # 1. Initial schedule check
    sched_resp = client.get("/api/fleet/schedule")
    assert sched_resp.status_code == 200
    sched = sched_resp.json()
    assert len(sched["resources"]) == 14
    assert len(sched["events"]) >= 14

    # Initial event for node-1 is orange or has mandate ingestion
    alpha_event = next((e for e in sched["events"] if "Mandate Ingestion" in e["name"] or "Awaiting" in e.get("depositStatus", "")), None)
    assert alpha_event is not None

    # 2. Lock a dispatch slot via POST /api/agent/dispatch/lock-slot
    lock_payload = {
        "leadId": "lead_test_bryntum_01",
        "territoryZone": "Zone 2 - South Lakeland",
        "slotStartIso": "2026-10-02 14:00",
        "paypalTransactionId": "PAY-DEP-9921",
    }
    lock_resp = client.post("/api/agent/dispatch/lock-slot", json=lock_payload)
    assert lock_resp.status_code == 200
    lock_data = lock_resp.json()
    assert lock_data["success"] is True

    # 3. Schedule now includes the locked appointment slot
    sched_resp2 = client.get("/api/fleet/schedule")
    assert sched_resp2.status_code == 200
    sched2 = sched_resp2.json()
    slot_event = next((e for e in sched2["events"] if "Takeoff:" in e["name"]), None)
    assert slot_event is not None
    assert slot_event["eventColor"] == "blue"
    assert "DEPOSIT VERIFIED" in slot_event["depositStatus"]


def test_fleet_ledger_dynamically_elevates_when_alpha_node_provisioned():
    """When Alpha Batch Worker node is provisioned, fleet ledger and stats update to 14 active lines ($1,269.86 MRR)."""
    from ..agents.seller_agent import _COMPLETED_SUBSCRIPTIONS

    # Save active subscription for Alpha Batch Worker
    sub_id = "I-AUTONOMOUS-8902"
    _COMPLETED_SUBSCRIPTIONS[sub_id] = {
        "subscription_id": sub_id,
        "status": "ACTIVE",
        "contractor_email": "agent-alpha@nexus-systems.io",
        "contractor_name": "AutonomousBuyerAgent-Alpha-Batch",
        "business_entity": "Nexus Autonomous Systems Corp",
        "tier_id": "ap2-batch",
        "agreed_monthly_rate": 49.99,
        "plan_id": "P-AP2-BATCH-WORKER",
        "carrier": "Dual-Transport FastMCP (RFC 8032)",
        "routing_state": "ACTIVE_COMPUTE_NODE",
        "subscriber_country_code": "US",
        "assigned_did": "mcp+https://batch-01.acme-systems.io/mcp",
    }

    # Provision node via API
    prov_resp = client.post(
        "/api/agent/provision",
        json={
            "subscriptionId": sub_id,
            "contractorEmail": "agent-alpha@nexus-systems.io",
            "tierId": "ap2-batch",
        },
    )
    assert prov_resp.status_code == 201

    # Verify fleet ledger reflects Alpha as ACTIVE_STREAMING
    ledger_resp = client.get("/api/fleet/ledger")
    assert ledger_resp.status_code == 200
    txns = ledger_resp.json()["transactions"]
    alpha = next((t for t in txns if t["contractor_name"] == "AutonomousBuyerAgent-Alpha-Batch"), None)
    assert alpha is not None
    assert alpha["status"] == "ACTIVE_STREAMING"
    assert alpha["allocated_did"].startswith("mcp+https://")

    # Verify fleet stats reflect all 14 lines active ($1,269.86 MRR, $15,238.32 ARR)
    stats_resp = client.get("/api/fleet/stats")
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["active_lines"] == 14
    assert stats["total_mrr"] == 1269.86
    assert stats["annualized_gmv"] == 15238.32


def test_ap2_profile_fleet_endpoints():
    """Verify ?profile=ap2 fleet endpoints return AP2 autonomous agent data with exact Node Settings capabilities."""
    # 1. Test /api/fleet/ledger?profile=ap2
    ledger_resp = client.get("/api/fleet/ledger?profile=ap2")
    assert ledger_resp.status_code == 200
    data = ledger_resp.json()
    assert data["status"] == "active"
    assert data["count"] == 14
    assert data["profile"] == "ap2"
    assert "AP2 Autonomous Commerce" in data["simulated_fleet_notice"]
    txns = data["transactions"]
    assert len(txns) == 14

    allowed_capabilities = {
        "High-Throughput Batch Worker",
        "Dedicated AI Service Gateway",
        "Enterprise Cluster Node",
    }
    allowed_tiers = {49.99, 79.99, 179.99}

    for t in txns:
        assert t["data_source"] == "Demo data"
        assert t["trade_vertical"] in allowed_capabilities
        assert t["monthly_amount"] in allowed_tiers
        assert "AutonomousBuyerAgent-" in t["buyer_agent"]
        if t["status"] == "ACTIVE_STREAMING":
            assert t["allocated_did"].startswith("mcp+https://")
            assert "Ed25519" in t["kyc_status"]
        else:
            assert t["status"] == "PENDING_DEPOSIT"
            assert t["allocated_did"] == "AWAITING_ENDPOINT"

    # 2. Test /api/fleet/stats?profile=ap2
    stats_resp = client.get("/api/fleet/stats?profile=ap2")
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["total_subscribers"] == 14
    assert stats["active_lines"] == 13
    assert stats["total_mrr"] > 0
    assert stats["annualized_gmv"] == round(stats["total_mrr"] * 12, 2)
    assert "Ed25519" in stats["compliance_guard"]
    assert "FastMCP" in stats["carrier_resporg"]
    assert len(stats["trade_breakdown"]) == 3
    breakdown_caps = {item["trade"] for item in stats["trade_breakdown"]}
    assert breakdown_caps == allowed_capabilities

    # 3. Test /api/fleet/schedule?profile=ap2
    sched_resp = client.get("/api/fleet/schedule?profile=ap2")
    assert sched_resp.status_code == 200
    sched = sched_resp.json()
    assert len(sched["resources"]) == 14
    assert len(sched["events"]) == 14
    for r in sched["resources"]:
        assert r["trade"] in allowed_capabilities
        if r["status"] == "ACTIVE_STREAMING":
            assert r["did"].startswith("mcp+https://")

