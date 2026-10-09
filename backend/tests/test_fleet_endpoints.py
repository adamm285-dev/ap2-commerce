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

    # Verify Marcus Miller starts with PENDING_DEPOSIT
    marcus = next((t for t in txns if t["contractor_name"] == "Marcus Miller"), None)
    assert marcus is not None
    assert marcus["status"] == "PENDING_DEPOSIT"
    assert marcus["allocated_did"] == "AWAITING_DEPOSIT"

    # Verify other contractors are ACTIVE_STREAMING
    dave = next((t for t in txns if t["contractor_name"] == "Dave Vance"), None)
    assert dave is not None
    assert dave["status"] == "ACTIVE_STREAMING"
    assert dave["allocated_did"] == "+1 (863) 356-7801"
    assert dave["kyc_status"] == "VERIFIED (PayPal Identity Bound)"


def test_get_fleet_stats_endpoint():
    """GET /api/fleet/stats returns aggregated metrics matching database state."""
    response = client.get("/api/fleet/stats")
    assert response.status_code == 200
    stats = response.json()

    assert stats["total_subscribers"] == 14
    # 13 active * 79.99 = 1039.87
    assert stats["active_lines"] == 13
    assert stats["total_mrr"] == 1039.87
    assert stats["annualized_gmv"] == round(1039.87 * 12, 2)
    assert stats["mandates_cleared"] == stats["active_lines"]
    assert "CITNRYD" in stats["carrier_resporg"]
    assert len(stats["trade_breakdown"]) > 0


def test_get_fleet_schedule_and_lock_slot():
    """Bryntum schedule returns resources, 24/7 shifts, and locked territory appointment windows."""
    # 1. Initial schedule check
    sched_resp = client.get("/api/fleet/schedule")
    assert sched_resp.status_code == 200
    sched = sched_resp.json()
    assert len(sched["resources"]) == 14
    assert len(sched["events"]) >= 14

    # Marcus Miller's initial event is orange (pending)
    marcus_event = next((e for e in sched["events"] if "Awaiting PayPal" in e["name"]), None)
    assert marcus_event is not None
    assert marcus_event["eventColor"] == "orange"

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
    assert lock_data["crewAssigned"] == "Crew B - Custom Tile & Precision Master"

    # 3. Schedule now includes the locked appointment slot
    sched_resp2 = client.get("/api/fleet/schedule")
    assert sched_resp2.status_code == 200
    sched2 = sched_resp2.json()
    slot_event = next((e for e in sched2["events"] if "Takeoff:" in e["name"]), None)
    assert slot_event is not None
    assert slot_event["eventColor"] == "blue"
    assert "DEPOSIT VERIFIED" in slot_event["depositStatus"]


def test_fleet_ledger_dynamically_elevates_when_marcus_line_provisioned():
    """When Marcus Miller's line is provisioned, fleet ledger and stats update to 14 active lines ($1119.86 MRR)."""
    from ..agents.seller_agent import _COMPLETED_SUBSCRIPTIONS

    # Save active subscription for Marcus Miller
    sub_id = "I-AUTONOMOUS-8902"
    _COMPLETED_SUBSCRIPTIONS[sub_id] = {
        "subscription_id": sub_id,
        "status": "ACTIVE",
        "contractor_email": "marcus@millercustomfloors.com",
        "contractor_name": "Marcus Miller",
        "business_entity": "Miller Custom Flooring LLC",
        "tier_id": "fieldsmith-pro",
        "agreed_monthly_rate": 79.99,
        "plan_id": "P-FLSMITH-PRO",
        "carrier": "Telnyx",
        "routing_state": "FL",
        "subscriber_country_code": "US",
    }

    # Provision line via API
    prov_resp = client.post(
        "/api/agent/provision",
        json={
            "subscriptionId": sub_id,
            "contractorEmail": "marcus@millercustomfloors.com",
            "areaCode": "863",
        },
    )
    assert prov_resp.status_code == 201

    # Verify fleet ledger reflects Marcus Miller as ACTIVE_STREAMING
    ledger_resp = client.get("/api/fleet/ledger")
    assert ledger_resp.status_code == 200
    txns = ledger_resp.json()["transactions"]
    marcus = next((t for t in txns if t["contractor_name"] == "Marcus Miller"), None)
    assert marcus is not None
    assert marcus["status"] == "ACTIVE_STREAMING"
    assert marcus["allocated_did"].startswith("+1863") or marcus["allocated_did"].startswith("+1 (863)")

    # Verify fleet stats reflect all 14 lines active ($1,119.86 MRR, $13,438.32 ARR)
    stats_resp = client.get("/api/fleet/stats")
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["active_lines"] == 14
    assert stats["total_mrr"] == 1119.86
    assert stats["annualized_gmv"] == 13438.32
