"""
Integration tests verifying database persistence across database reconnections and process boundaries.
Ensures subscriptions, authorized mandates, contractor budget caps, spend commitments,
processed webhook IDs, and buyer public keys survive reconnections and process recycles.
"""

import time
import pytest
from pathlib import Path
from ..database import (
    init_db,
    get_connection,
    save_subscription,
    get_subscription,
    save_subscription_alias,
    SubscriptionsDictProxy,
    ActiveContractorSubscriptionsProxy,
    save_mandate,
    get_mandate,
    AuthorizedMandatesProxy,
    ProcessedWebhooksProxy,
    record_processed_webhook,
    is_webhook_processed,
    BuyerKeysProxy,
    register_buyer_key,
    get_buyer_key,
    set_contractor_cap as db_set_contractor_cap,
    get_contractor_cap as db_get_contractor_cap,
    get_contractor_committed_spend as db_get_contractor_committed_spend,
    sync_contractor_commitment as db_sync_contractor_commitment,
    record_spend_entry as db_record_spend_entry,
    list_spend_history as db_list_spend_history,
)


@pytest.fixture
def persist_db(tmp_path: Path) -> Path:
    """Provides a fresh, initialized SQLite database file for persistence testing."""
    db_file = tmp_path / "test_persist.db"
    init_db(db_file)
    return db_file


def test_subscription_persistence_across_connections(persist_db: Path):
    """Subscriptions with complex payloads must survive SQLite disconnection and re-hydration."""
    db_file = persist_db
    
    sub_data = {
        "subscription_id": "I-PERSIST-TEST-001",
        "status": "ACTIVE",
        "contractor_email": "agent-alpha@example.com",
        "contractor_name": "Autonomous Compute Buyer",
        "business_entity": "Demo Buyer Corp",
        "tier_id": "ap2-gateway",
        "agreed_monthly_rate": 79.99,
        "plan_id": "P-AP2-SERVICE-GATEWAY",
        "assigned_did": "mcp+https://gateway-01.ap2.market",
        "carrier": "FastMCP Gateway",
        "routing_state": "FL",
        "subscriber_country_code": "US",
        "paypal_vault_status": "VAULT_BOUND",
        "vault_billing_authorized": True,
        "vault_customer_present": False,
        "mandate_proof_hash": "proof_hash_abc_123",
        "offer_id": "offer_xyz_789",
        "erp_payload": {"client_id": "client_99", "routing_id": "q_4421"},
    }
    
    # 1. Save subscription using first connection
    save_subscription(sub_data, db_path=db_file)
    
    # 2. Simulate process restart by querying on a clean independent proxy
    proxy = SubscriptionsDictProxy(db_path=db_file)
    assert "I-PERSIST-TEST-001" in proxy
    hydrated = proxy["I-PERSIST-TEST-001"]
    
    assert hydrated["subscription_id"] == "I-PERSIST-TEST-001"
    assert hydrated["status"] == "ACTIVE"
    assert hydrated["contractor_email"] == "agent-alpha@example.com"
    assert hydrated["agreed_monthly_rate"] == 79.99
    assert hydrated["assigned_did"] == "mcp+https://gateway-01.ap2.market"
    assert hydrated["vault_billing_authorized"] is True
    assert hydrated["vault_customer_present"] is False
    assert hydrated["erp_payload"]["client_id"] == "client_99"


def test_subscription_aliases_and_in_place_mutations(persist_db: Path):
    """Aliases must resolve to the underlying record, and in-place mutations must persist immediately."""
    db_file = persist_db
    proxy = SubscriptionsDictProxy(db_path=db_file)
    
    sub_data = {
        "subscription_id": "I-MAIN-SUB-77",
        "status": "ACTIVE",
        "contractor_email": "alias@example.com",
        "tier_id": "ap2-batch",
        "agreed_monthly_rate": 49.99,
    }
    # Save under primary ID and under offer alias
    proxy["I-MAIN-SUB-77"] = sub_data
    proxy["OFFER-ALIAS-77"] = sub_data
    
    # Verify lookup by alias returns primary record
    assert "OFFER-ALIAS-77" in proxy
    by_alias = proxy["OFFER-ALIAS-77"]
    assert by_alias["subscription_id"] == "I-MAIN-SUB-77"
    
    # Mutate in-place (simulating status update)
    by_alias["status"] = "REPLACED"
    by_alias["pending_replacement"] = "I-NEW-SUB-88"
    
    # Query fresh proxy instance from disk
    fresh_proxy = SubscriptionsDictProxy(db_path=db_file)
    verified = fresh_proxy["I-MAIN-SUB-77"]
    assert verified["status"] == "REPLACED"
    assert verified["pending_replacement"] == "I-NEW-SUB-88"


def test_mandate_persistence_and_email_locking(persist_db: Path):
    """Mandates must persist and dynamically lock to the first contractor email."""
    db_file = persist_db
    mandate_proxy = AuthorizedMandatesProxy(db_path=db_file)
    
    token = "mandate_proof_hash_unique_123"
    mandate_proxy[token] = {
        "proof_hash": token,
        "offer_id": "offer_token_456",
        "tier_id": "ap2-batch",
        "amount": 49.99,
        "buyer_agent_id": "buyer-test-01",
        "monthly_budget_cap": 80.00,
        "registered_at": time.time(),
        "expires_at": time.time() + 1800,
    }
    
    # Read back from fresh proxy
    fresh_proxy = AuthorizedMandatesProxy(db_path=db_file)
    assert token in fresh_proxy
    mandate = fresh_proxy[token]
    assert mandate["amount"] == 49.99
    assert mandate.get("contractor_email") is None
    
    # Lock to first contractor
    mandate["contractor_email"] = "first@example.com"
    
    # Verify persistence of contractor email lock
    locked_check = AuthorizedMandatesProxy(db_path=db_file)[token]
    assert locked_check["contractor_email"] == "first@example.com"


def test_webhook_deduplication_persists_across_reconnect(persist_db: Path):
    """Processed webhook IDs must survive database reconnections to prevent duplicate execution."""
    db_file = persist_db
    
    webhooks = ProcessedWebhooksProxy(db_path=db_file)
    event_id = "WH-RECONNECT-TEST-999"
    assert event_id not in webhooks
    
    webhooks.add(event_id)
    assert event_id in webhooks
    
    # Reconnect with a new proxy instance
    fresh_webhooks = ProcessedWebhooksProxy(db_path=db_file)
    assert event_id in fresh_webhooks
    assert is_webhook_processed(event_id, db_path=db_file) is True


def test_contractor_budget_and_spend_commitments(persist_db: Path):
    """Contractor budgets, committed spend, and audit history must survive process disconnects."""
    db_file = persist_db
    email = "persist-ledger@example.com"
    
    db_set_contractor_cap(email, 150.00, db_path=db_file)
    db_sync_contractor_commitment(email, 79.99, agent_id="buyer-agent-99", db_path=db_file)
    db_record_spend_entry(
        79.99,
        "SUBSCRIPTION_PURCHASE",
        contractor_email=email,
        agent_id="buyer-agent-99",
        metadata={"tier": "ap2-gateway"},
        db_path=db_file,
    )
    
    # Verify from fresh connections
    assert db_get_contractor_cap(email, default_cap=100.0, db_path=db_file) == 150.00
    assert db_get_contractor_committed_spend(email, db_path=db_file) == 79.99
    
    history = db_list_spend_history(contractor_email=email, db_path=db_file)
    assert len(history) == 1
    assert history[0]["amount"] == 79.99
    assert history[0]["action"] == "SUBSCRIPTION_PURCHASE"


def test_buyer_keys_persist_across_reconnect(persist_db: Path):
    """Dynamic buyer agent public keys must survive reconnections."""
    db_file = persist_db
    
    keys = BuyerKeysProxy(db_path=db_file)
    custom_kid = "buyer-ed25519-custom-key-88"
    pub_hex = "bb" * 32
    
    keys[custom_kid] = pub_hex
    assert custom_kid in keys
    assert keys[custom_kid] == pub_hex
    
    # Reconnect with fresh proxy
    fresh_keys = BuyerKeysProxy(db_path=db_file)
    assert custom_kid in fresh_keys
    assert fresh_keys[custom_kid] == pub_hex
    assert get_buyer_key(custom_kid, db_path=db_file) == pub_hex


def test_active_contractor_subscriptions_pointer(persist_db: Path):
    """Active contractor pointer must persist and allow unlinking without deleting subscriptions."""
    db_file = persist_db
    
    active_ptr = ActiveContractorSubscriptionsProxy(db_path=db_file)
    email = "pointer@example.com"
    sub_id = "I-POINTER-SUB-10"
    
    active_ptr[email] = sub_id
    assert active_ptr[email] == sub_id
    assert email in active_ptr
    
    # Reconnect
    fresh_ptr = ActiveContractorSubscriptionsProxy(db_path=db_file)
    assert fresh_ptr.get(email) == sub_id
    
    # Pop pointer
    popped = fresh_ptr.pop(email)
    assert popped == sub_id
    assert email not in fresh_ptr
