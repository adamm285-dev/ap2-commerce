"""
Persistent SQLite Database Engine for AP2 Autonomous Agent Commerce Node.
Survives process restarts across subscriptions, mandates, ledger commitments,
processed webhook event IDs, and registered buyer public keys.
Thread-safe with SQLite WAL mode and busy_timeout=5000ms.
Conforms to SPEC-001 v1.4.1.
"""

import os
import json
import time
import sqlite3
import datetime
import logging
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Set, Iterator
from collections.abc import MutableMapping, MutableSet

from .config import settings, get_db_path

logger = logging.getLogger("a2a_database")

RESERVED_BUYER_KEY_IDS: Set[str] = {
    "ap2-seller-ed25519-v1",
    "ap2-buyer-ed25519-v1",
    "buyer-agent-01",
    "buyer-agent-001",
    "claude-desktop-buyer",
    "test-agent-001",
}

_DEFAULT_BUYER_KIDS: Set[str] = {
    "ap2-buyer-ed25519-v1",
    "buyer-agent-01",
    "buyer-agent-001",
    "claude-desktop-buyer",
    "test-agent-001",
}

DEFAULT_NODE_OPERATORS: List[Dict[str, Any]] = [
    {
        "operator_id": "op_lambda_gpu",
        "name": "Lambda Autonomous Compute",
        "email": "payouts-lambda@example.com",
        "payout_recipient_type": "EMAIL",
        "assigned_nodes": ["node-batch-", "node-1", "node-2", "node-3", "node-4", "node-5"],
        "split_bps": 8500,
        "status": "ACTIVE",
    },
    {
        "operator_id": "op_equinix_metal",
        "name": "Equinix Metal Nodes",
        "email": "payouts-equinix@example.com",
        "payout_recipient_type": "EMAIL",
        "assigned_nodes": ["node-gateway-", "node-6", "node-7", "node-8", "node-9", "node-10"],
        "split_bps": 8500,
        "status": "ACTIVE",
    },
    {
        "operator_id": "op_coreweave_cluster",
        "name": "CoreWeave Cluster Fleet",
        "email": "payouts-coreweave@example.com",
        "payout_recipient_type": "EMAIL",
        "assigned_nodes": ["node-cluster-", "node-11", "node-12", "node-13", "node-14"],
        "split_bps": 8500,
        "status": "ACTIVE",
    },
]

DEFAULT_NODE_OPERATOR_IDS: Set[str] = {op["operator_id"] for op in DEFAULT_NODE_OPERATORS}


def _dict_factory(cursor: sqlite3.Cursor, row: Tuple[Any, ...]) -> Dict[str, Any]:
    """Row factory converting sqlite3 rows to native Python dictionaries."""
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """
    Creates and configures a thread-safe connection to the SQLite database.
    Enforces WAL journal mode, 5000ms busy timeout, and dictionary row factory.
    """
    target = db_path or get_db_path()
    if str(target) == ":memory:":
        conn = sqlite3.connect(":memory:", timeout=10.0, check_same_thread=False)
    else:
        target_path = Path(target)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(target_path), timeout=10.0, check_same_thread=False)

    conn.row_factory = _dict_factory
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Optional[Path] = None) -> None:
    """Initializes all database tables, indexes, and default key seeds."""
    conn = get_connection(db_path)
    try:
        with conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                subscription_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                contractor_email TEXT NOT NULL,
                contractor_name TEXT,
                business_entity TEXT,
                tier_id TEXT NOT NULL,
                agreed_monthly_rate REAL NOT NULL,
                plan_id TEXT,
                buyer_agent_id TEXT,
                subscriber_country_code TEXT DEFAULT 'US',
                assigned_did TEXT,
                carrier TEXT DEFAULT 'MCP over HTTPS (JSON-RPC 2.0)',
                routing_state TEXT,
                replaced_by TEXT,
                mandate_proof_hash TEXT,
                offer_id TEXT,
                paypal_vault_status TEXT,
                vault_billing_authorized INTEGER DEFAULT 0,
                vault_customer_present INTEGER DEFAULT 0,
                pending_replacement TEXT,
                raw_details_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_subs_contractor_email ON subscriptions(contractor_email);
            CREATE INDEX IF NOT EXISTS idx_subs_status ON subscriptions(status);

            CREATE TABLE IF NOT EXISTS subscription_aliases (
                alias_key TEXT PRIMARY KEY,
                subscription_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sub_aliases_sub_id ON subscription_aliases(subscription_id);

            CREATE TABLE IF NOT EXISTS active_contractor_subscriptions (
                contractor_email TEXT PRIMARY KEY,
                subscription_id TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS authorized_mandates (
                lookup_key TEXT PRIMARY KEY,
                offer_id TEXT,
                proof_hash TEXT NOT NULL,
                buyer_agent_id TEXT NOT NULL,
                contractor_email TEXT,
                tier_id TEXT NOT NULL,
                amount REAL NOT NULL,
                monthly_budget_cap REAL NOT NULL,
                registered_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                details_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_mandates_offer_id ON authorized_mandates(offer_id);
            CREATE INDEX IF NOT EXISTS idx_mandates_proof_hash ON authorized_mandates(proof_hash);

            CREATE TABLE IF NOT EXISTS contractor_budgets (
                contractor_email TEXT PRIMARY KEY,
                monthly_cap REAL NOT NULL,
                committed_spend REAL NOT NULL DEFAULT 0.00,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS contractor_authorized_caps (
                contractor_email TEXT PRIMARY KEY,
                monthly_cap REAL NOT NULL,
                source TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agent_spends (
                agent_id TEXT PRIMARY KEY,
                total_spent REAL NOT NULL DEFAULT 0.00,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS spend_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                amount REAL NOT NULL,
                contractor_email TEXT,
                agent_id TEXT,
                action TEXT NOT NULL,
                metadata_json TEXT
            );

            CREATE TABLE IF NOT EXISTS processed_webhooks (
                event_id TEXT PRIMARY KEY,
                event_type TEXT,
                processed_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS buyer_keys (
                kid TEXT PRIMARY KEY,
                public_key_hex TEXT NOT NULL,
                contractor_email TEXT,
                business_name TEXT,
                registered_at TEXT NOT NULL,
                payer_id TEXT,
                identity_provider TEXT,
                identity_attested INTEGER DEFAULT 0,
                attestation_payload TEXT
            );

            -- Native AP2 Gateway Direct Rail Charges (Milestone S3-NATIVE / SPEC-001 v1.9.0)
            CREATE TABLE IF NOT EXISTS direct_charges (
                charge_id TEXT PRIMARY KEY,
                mandate_id TEXT NOT NULL UNIQUE,
                buyer_key_id TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                currency TEXT NOT NULL DEFAULT 'USD',
                payee_id TEXT NOT NULL,
                payment_source_id TEXT NOT NULL,
                paypal_capture_id TEXT NOT NULL,
                status TEXT NOT NULL,
                merchant_receipt_jwt TEXT NOT NULL,
                qbo_purchase_id TEXT,
                qbo_payload TEXT,
                metadata_json TEXT,
                created_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_direct_charges_mandate_unique ON direct_charges(mandate_id);
            CREATE INDEX IF NOT EXISTS idx_direct_charges_mandate ON direct_charges(mandate_id);
            CREATE INDEX IF NOT EXISTS idx_direct_charges_buyer_key ON direct_charges(buyer_key_id);
            CREATE INDEX IF NOT EXISTS idx_direct_charges_created ON direct_charges(created_at);

            CREATE TABLE IF NOT EXISTS open_mandate_settlements (
                mandate_hash TEXT NOT NULL,
                subscription_id TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                settled_at TEXT NOT NULL,
                PRIMARY KEY (mandate_hash, subscription_id)
            );

            -- Owner-signed open payment mandate behind each agent-purchased subscription
            CREATE TABLE IF NOT EXISTS recurring_mandates (
                subscription_id TEXT PRIMARY KEY,
                mandate_hash TEXT NOT NULL,
                open_payment_mandate_token TEXT NOT NULL,
                buyer_email TEXT NOT NULL,
                agreed_amount_cents INTEGER NOT NULL,
                currency TEXT NOT NULL,
                initial_sale_id TEXT,
                status TEXT NOT NULL,
                status_reason TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            -- Every PayPal sale reported for a mandated subscription, with the verification outcome
            CREATE TABLE IF NOT EXISTS recurring_charges (
                sale_id TEXT PRIMARY KEY,
                subscription_id TEXT NOT NULL,
                mandate_hash TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                currency TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT,
                charged_at TEXT NOT NULL,
                received_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS dispatch_slots (
                slot_id TEXT PRIMARY KEY,
                job_id TEXT,
                contractor_id TEXT,
                territory_zone TEXT NOT NULL,
                slot_start_iso TEXT NOT NULL,
                slot_end_iso TEXT,
                requester_name TEXT,
                workload_scope TEXT,
                payment_id TEXT,
                node_assigned TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            -- Cryptographic mandate revocation status list (AP2 v0.2 / SPEC-001 v1.9.0)
            CREATE TABLE IF NOT EXISTS revoked_mandates (
                revocation_id TEXT PRIMARY KEY,
                mandate_proof_hash TEXT NOT NULL UNIQUE,
                revoked_by_kid TEXT NOT NULL,
                revoked_at TEXT NOT NULL,
                reason TEXT NOT NULL,
                signature_hex TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_revoked_mandates_hash ON revoked_mandates(mandate_proof_hash);

            -- Two-Sided Marketplace: Node Operator Registry & PayPal Payouts (SPEC-001 v1.9.0 / Milestone S2-SETTLE)
            CREATE TABLE IF NOT EXISTS node_operators (
                operator_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                payout_recipient_type TEXT NOT NULL DEFAULT 'EMAIL',
                assigned_nodes TEXT NOT NULL,
                split_bps INTEGER NOT NULL DEFAULT 8500,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_node_operators_email ON node_operators(email);
            CREATE INDEX IF NOT EXISTS idx_node_operators_status ON node_operators(status);

            CREATE TABLE IF NOT EXISTS payout_batches (
                batch_id TEXT PRIMARY KEY,
                sender_batch_id TEXT NOT NULL UNIQUE,
                batch_status TEXT NOT NULL,
                total_gross_cents INTEGER NOT NULL,
                total_payout_cents INTEGER NOT NULL,
                total_platform_fee_cents INTEGER NOT NULL,
                currency TEXT NOT NULL DEFAULT 'USD',
                item_count INTEGER NOT NULL,
                raw_response_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_payout_batches_status ON payout_batches(batch_status);

            CREATE TABLE IF NOT EXISTS payout_items (
                item_id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL,
                operator_id TEXT NOT NULL,
                subscription_id TEXT NOT NULL,
                receiver_email TEXT NOT NULL,
                gross_amount_cents INTEGER NOT NULL,
                platform_fee_cents INTEGER NOT NULL,
                net_payout_cents INTEGER NOT NULL,
                currency TEXT NOT NULL DEFAULT 'USD',
                status TEXT NOT NULL,
                paypal_transaction_id TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_payout_items_batch_id ON payout_items(batch_id);
            CREATE INDEX IF NOT EXISTS idx_payout_items_operator_id ON payout_items(operator_id);
            CREATE INDEX IF NOT EXISTS idx_payout_items_sub_id ON payout_items(subscription_id);
            """)

            cur = conn.cursor()
            # Safe schema migration: rename legacy columns in dispatch_slots if they exist
            cur.execute("PRAGMA table_info(dispatch_slots)")
            slot_cols = [row["name"] for row in cur.fetchall()]
            if "crew_assigned" in slot_cols and "node_assigned" not in slot_cols:
                cur.execute("ALTER TABLE dispatch_slots RENAME COLUMN crew_assigned TO node_assigned")
            if "caller_name" in slot_cols and "requester_name" not in slot_cols:
                cur.execute("ALTER TABLE dispatch_slots RENAME COLUMN caller_name TO requester_name")
            if "lead_id" in slot_cols and "job_id" not in slot_cols:
                cur.execute("ALTER TABLE dispatch_slots RENAME COLUMN lead_id TO job_id")
            if "project_scope" in slot_cols and "workload_scope" not in slot_cols:
                cur.execute("ALTER TABLE dispatch_slots RENAME COLUMN project_scope TO workload_scope")
            if "deposit_payment_id" in slot_cols and "payment_id" not in slot_cols:
                cur.execute("ALTER TABLE dispatch_slots RENAME COLUMN deposit_payment_id TO payment_id")

            # Safe schema migration: add identity attestation columns to buyer_keys if missing
            cur.execute("PRAGMA table_info(buyer_keys)")
            buyer_cols = [row["name"] for row in cur.fetchall()]
            if "payer_id" not in buyer_cols:
                cur.execute("ALTER TABLE buyer_keys ADD COLUMN payer_id TEXT")
            if "identity_provider" not in buyer_cols:
                cur.execute("ALTER TABLE buyer_keys ADD COLUMN identity_provider TEXT")
            if "identity_attested" not in buyer_cols:
                cur.execute("ALTER TABLE buyer_keys ADD COLUMN identity_attested INTEGER DEFAULT 0")
            if "attestation_payload" not in buyer_cols:
                cur.execute("ALTER TABLE buyer_keys ADD COLUMN attestation_payload TEXT")

            # Seed default buyer keys if table is empty in mock/demo mode
            cur.execute("SELECT COUNT(*) as count FROM buyer_keys")
            count = cur.fetchone()["count"]
            # MOCK(M-022): default buyer keys seeded only in mock mode without challenge enrollment
            if count == 0 and getattr(settings, "mock_external_apis", False):
                buyer_pub = (
                    os.getenv("A2A_BUYER_PUBLIC_KEY")
                    or getattr(settings, "a2a_buyer_public_key", None)
                    or "a0" * 32
                ).strip().lower()
                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                for kid in _DEFAULT_BUYER_KIDS:
                    cur.execute(
                        """
                        INSERT OR IGNORE INTO buyer_keys (kid, public_key_hex, contractor_email, business_name, registered_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (kid, buyer_pub, "agent-alpha@example.com", "Demo Buyer Corp", now_iso),
                    )

            # Seed default node operators if table is empty in mock/demo mode
            cur.execute("SELECT COUNT(*) as count FROM node_operators")
            op_count = cur.fetchone()["count"]
            if op_count == 0 and getattr(settings, "mock_external_apis", False):
                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                for op in DEFAULT_NODE_OPERATORS:
                    cur.execute(
                        """
                        INSERT OR IGNORE INTO node_operators 
                        (operator_id, name, email, payout_recipient_type, assigned_nodes, split_bps, status, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            op["operator_id"],
                            op["name"],
                            op["email"],
                            op.get("payout_recipient_type", "EMAIL"),
                            json.dumps(op["assigned_nodes"]),
                            op.get("split_bps", 8500),
                            op.get("status", "ACTIVE"),
                            now_iso,
                            now_iso,
                        ),
                    )
    finally:
        conn.close()


# --- Subscription Storage Operations ---

def save_subscription(sub: Dict[str, Any], db_path: Optional[Path] = None) -> None:
    """Inserts or updates a subscription record, preserving raw nested payloads."""
    sub_id = sub.get("subscription_id")
    if not sub_id:
        return

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    raw_json = json.dumps(sub)

    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO subscriptions (
                    subscription_id, status, contractor_email, contractor_name, business_entity,
                    tier_id, agreed_monthly_rate, plan_id, buyer_agent_id, subscriber_country_code,
                    assigned_did, carrier, routing_state, replaced_by, mandate_proof_hash,
                    offer_id, paypal_vault_status, vault_billing_authorized, vault_customer_present,
                    pending_replacement, raw_details_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(subscription_id) DO UPDATE SET
                    status = excluded.status,
                    contractor_email = excluded.contractor_email,
                    contractor_name = excluded.contractor_name,
                    business_entity = excluded.business_entity,
                    tier_id = excluded.tier_id,
                    agreed_monthly_rate = excluded.agreed_monthly_rate,
                    plan_id = excluded.plan_id,
                    buyer_agent_id = excluded.buyer_agent_id,
                    subscriber_country_code = excluded.subscriber_country_code,
                    assigned_did = excluded.assigned_did,
                    carrier = excluded.carrier,
                    routing_state = excluded.routing_state,
                    replaced_by = excluded.replaced_by,
                    mandate_proof_hash = excluded.mandate_proof_hash,
                    offer_id = excluded.offer_id,
                    paypal_vault_status = excluded.paypal_vault_status,
                    vault_billing_authorized = excluded.vault_billing_authorized,
                    vault_customer_present = excluded.vault_customer_present,
                    pending_replacement = excluded.pending_replacement,
                    raw_details_json = excluded.raw_details_json,
                    updated_at = excluded.updated_at
                """,
                (
                    sub_id,
                    sub.get("status", "ACTIVE"),
                    (sub.get("contractor_email") or "").strip().lower(),
                    sub.get("contractor_name"),
                    sub.get("business_entity"),
                    sub.get("tier_id", "ap2-gateway"),
                    float(sub.get("agreed_monthly_rate") or 0.0),
                    sub.get("plan_id"),
                    sub.get("buyer_agent_id"),
                    sub.get("subscriber_country_code", "US"),
                    sub.get("assigned_did"),
                    sub.get("carrier", "MCP over HTTPS (JSON-RPC 2.0)"),
                    sub.get("routing_state"),
                    sub.get("replaced_by"),
                    sub.get("mandate_proof_hash"),
                    sub.get("offer_id"),
                    sub.get("paypal_vault_status"),
                    1 if sub.get("vault_billing_authorized") else 0,
                    1 if sub.get("vault_customer_present") else 0,
                    sub.get("pending_replacement"),
                    raw_json,
                    now_iso,
                    now_iso,
                ),
            )
    finally:
        conn.close()


class SubscriptionRecordProxy(dict):
    """
    Dictionary proxy representing a subscription row.
    Mutations via __setitem__, pop, and update are automatically synchronized back to SQLite.
    """

    def __init__(self, data: Dict[str, Any], db_path: Optional[Path] = None):
        super().__init__(data)
        self._db_path = db_path

    def __setitem__(self, key: str, value: Any) -> None:
        super().__setitem__(key, value)
        save_subscription(dict(self), db_path=self._db_path)

    def pop(self, key: str, default: Any = None) -> Any:
        res = super().pop(key, default)
        save_subscription(dict(self), db_path=self._db_path)
        return res

    def update(self, *args, **kwargs) -> None:
        super().update(*args, **kwargs)
        save_subscription(dict(self), db_path=self._db_path)


def save_subscription_alias(alias_key: str, subscription_id: str, db_path: Optional[Path] = None) -> None:
    """Records an alias lookup key (e.g. offer_id or mandate_proof_hash) pointing to a subscription ID."""
    if not alias_key or not subscription_id:
        return
    conn = get_connection(db_path)
    try:
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with conn:
            conn.execute(
                """
                INSERT INTO subscription_aliases (alias_key, subscription_id, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(alias_key) DO UPDATE SET subscription_id = excluded.subscription_id
                """,
                (alias_key.strip(), subscription_id.strip(), now_iso),
            )
    finally:
        conn.close()


def get_subscription(subscription_id: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Retrieves a subscription by ID or alias, deserializing raw JSON details into a SubscriptionRecordProxy."""
    if not subscription_id:
        return None
    target_id = subscription_id.strip()
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM subscriptions WHERE subscription_id = ?", (target_id,))
        row = cur.fetchone()
        if not row:
            cur.execute("SELECT subscription_id FROM subscription_aliases WHERE alias_key = ?", (target_id,))
            alias_row = cur.fetchone()
            if alias_row:
                cur.execute("SELECT * FROM subscriptions WHERE subscription_id = ?", (alias_row["subscription_id"],))
                row = cur.fetchone()
        if not row:
            cur.execute(
                "SELECT * FROM subscriptions WHERE offer_id = ? OR mandate_proof_hash = ? ORDER BY rowid DESC LIMIT 1",
                (target_id, target_id)
            )
            row = cur.fetchone()
        if not row:
            return None
        res = dict(row)
        if "vault_billing_authorized" in res and res["vault_billing_authorized"] is not None:
            res["vault_billing_authorized"] = bool(res["vault_billing_authorized"])
        if "vault_customer_present" in res and res["vault_customer_present"] is not None:
            res["vault_customer_present"] = bool(res["vault_customer_present"])
        raw_json = res.pop("raw_details_json", None)
        if raw_json:
            try:
                raw_dict = json.loads(raw_json)
                if isinstance(raw_dict, dict):
                    raw_dict.update({k: v for k, v in res.items() if v is not None})
                    if "vault_billing_authorized" in raw_dict and raw_dict["vault_billing_authorized"] is not None:
                        raw_dict["vault_billing_authorized"] = bool(raw_dict["vault_billing_authorized"])
                    if "vault_customer_present" in raw_dict and raw_dict["vault_customer_present"] is not None:
                        raw_dict["vault_customer_present"] = bool(raw_dict["vault_customer_present"])
                    return SubscriptionRecordProxy(raw_dict, db_path=db_path)
            except Exception:
                pass
        return SubscriptionRecordProxy(res, db_path=db_path)
    finally:
        conn.close()


def delete_subscription(subscription_id: str, db_path: Optional[Path] = None) -> bool:
    """Deletes a subscription record and its aliases from the database."""
    if not subscription_id:
        return False
    target_id = subscription_id.strip()
    conn = get_connection(db_path)
    try:
        with conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM subscriptions WHERE subscription_id = ?", (target_id,))
            deleted = cur.rowcount > 0
            cur.execute("DELETE FROM subscription_aliases WHERE alias_key = ? OR subscription_id = ?", (target_id, target_id))
            return deleted
    finally:
        conn.close()


def list_subscriptions(
    contractor_email: Optional[str] = None,
    status: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Lists subscriptions with optional filtering by email and status."""
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        query = "SELECT * FROM subscriptions WHERE 1=1"
        params: List[Any] = []
        if contractor_email:
            query += " AND LOWER(contractor_email) = ?"
            params.append(contractor_email.strip().lower())
        if status:
            query += " AND status = ?"
            params.append(status.strip())
        query += " ORDER BY updated_at DESC"
        cur.execute(query, params)
        rows = cur.fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            if "vault_billing_authorized" in d and d["vault_billing_authorized"] is not None:
                d["vault_billing_authorized"] = bool(d["vault_billing_authorized"])
            if "vault_customer_present" in d and d["vault_customer_present"] is not None:
                d["vault_customer_present"] = bool(d["vault_customer_present"])
            raw = d.pop("raw_details_json", None)
            if raw:
                try:
                    loaded = json.loads(raw)
                    if isinstance(loaded, dict):
                        loaded.update({k: v for k, v in d.items() if v is not None})
                        if "vault_billing_authorized" in loaded and loaded["vault_billing_authorized"] is not None:
                            loaded["vault_billing_authorized"] = bool(loaded["vault_billing_authorized"])
                        if "vault_customer_present" in loaded and loaded["vault_customer_present"] is not None:
                            loaded["vault_customer_present"] = bool(loaded["vault_customer_present"])
                        out.append(SubscriptionRecordProxy(loaded, db_path=db_path))
                        continue
                except Exception:
                    pass
            out.append(SubscriptionRecordProxy(d, db_path=db_path))
        return out
    finally:
        conn.close()


def clear_subscriptions(db_path: Optional[Path] = None) -> None:
    """Deletes all subscriptions from the database."""
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute("DELETE FROM subscriptions")
            conn.execute("DELETE FROM subscription_aliases")
            conn.execute("DELETE FROM active_contractor_subscriptions")
    finally:
        conn.close()


# --- Authorized Mandates Storage Operations ---

def save_mandate(key: str, details: Dict[str, Any], db_path: Optional[Path] = None) -> None:
    """Registers an authorized mandate and offer under its lookup key."""
    if not key or not details:
        return
    tier_id = (details.get("tier_id") or "").strip()
    if not tier_id or tier_id == "*":
        return
    contractor_email = (details.get("contractor_email") or "").strip().lower() or None
    cap_val = float(details.get("authoritative_budget_cap") or details.get("monthly_budget_cap") or details.get("amount") or 0.0)
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO authorized_mandates (
                    lookup_key, offer_id, proof_hash, buyer_agent_id, contractor_email,
                    tier_id, amount, monthly_budget_cap, registered_at, expires_at, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(lookup_key) DO UPDATE SET
                    offer_id = excluded.offer_id,
                    proof_hash = excluded.proof_hash,
                    buyer_agent_id = excluded.buyer_agent_id,
                    contractor_email = excluded.contractor_email,
                    tier_id = excluded.tier_id,
                    amount = excluded.amount,
                    monthly_budget_cap = excluded.monthly_budget_cap,
                    registered_at = excluded.registered_at,
                    expires_at = excluded.expires_at,
                    details_json = excluded.details_json
                """,
                (
                    key.strip(),
                    details.get("offer_id"),
                    details.get("mandate_proof_hash") or details.get("proof_hash") or key.strip(),
                    details.get("buyer_agent_id", "buyer-agent-01"),
                    contractor_email,
                    tier_id,
                    float(details.get("amount") or 0.0),
                    cap_val,
                    float(details.get("registered_at") or time.time()),
                    float(details.get("expires_at") or (time.time() + 1800)),
                    json.dumps(details),
                ),
            )
    finally:
        conn.close()


class MandateRecordProxy(dict):
    """
    Dictionary proxy representing an authorized mandate row.
    Mutations via __setitem__, pop, and update are automatically synchronized back to SQLite.
    """

    def __init__(self, key: str, data: Dict[str, Any], db_path: Optional[Path] = None):
        super().__init__(data)
        self._key = key
        self._db_path = db_path

    def __setitem__(self, key: str, value: Any) -> None:
        super().__setitem__(key, value)
        save_mandate(self._key, dict(self), db_path=self._db_path)
        offer_id = self.get("offer_id")
        if offer_id and offer_id != self._key:
            save_mandate(offer_id, dict(self), db_path=self._db_path)
        proof_hash = self.get("proof_hash") or self.get("mandate_proof_hash")
        if proof_hash and proof_hash != self._key:
            save_mandate(proof_hash, dict(self), db_path=self._db_path)

    def pop(self, key: str, default: Any = None) -> Any:
        res = super().pop(key, default)
        save_mandate(self._key, dict(self), db_path=self._db_path)
        return res

    def update(self, *args, **kwargs) -> None:
        super().update(*args, **kwargs)
        save_mandate(self._key, dict(self), db_path=self._db_path)


def get_mandate(key: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Retrieves an authorized mandate by lookup key or offer_id as a MandateRecordProxy."""
    if not key:
        return None
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT details_json FROM authorized_mandates WHERE lookup_key = ? OR offer_id = ? LIMIT 1", (key.strip(), key.strip()))
        row = cur.fetchone()
        if not row:
            return None
        data = json.loads(row["details_json"])
        return MandateRecordProxy(key.strip(), data, db_path=db_path)
    finally:
        conn.close()


def delete_mandate(key: str, db_path: Optional[Path] = None) -> bool:
    """Deletes an authorized mandate by lookup key."""
    if not key:
        return False
    conn = get_connection(db_path)
    try:
        with conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM authorized_mandates WHERE lookup_key = ? OR offer_id = ?", (key.strip(), key.strip()))
            return cur.rowcount > 0
    finally:
        conn.close()


def clear_mandates(db_path: Optional[Path] = None) -> None:
    """Deletes all authorized mandates from the database."""
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute("DELETE FROM authorized_mandates")
    finally:
        conn.close()


# --- Processed Webhooks Storage Operations ---

def is_webhook_processed(event_id: str, db_path: Optional[Path] = None) -> bool:
    """Checks whether a PayPal webhook event ID has already been recorded."""
    if not event_id:
        return False
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM processed_webhooks WHERE event_id = ?", (event_id.strip(),))
        return cur.fetchone() is not None
    finally:
        conn.close()


def record_processed_webhook(event_id: str, event_type: Optional[str] = None, db_path: Optional[Path] = None) -> None:
    """Records a processed PayPal webhook event ID for idempotency deduplication."""
    if not event_id:
        return
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO processed_webhooks (event_id, event_type, processed_at)
                VALUES (?, ?, ?)
                """,
                (event_id.strip(), event_type, now_iso),
            )
    finally:
        conn.close()


def clear_processed_webhooks(db_path: Optional[Path] = None) -> None:
    """Deletes all processed webhook records."""
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute("DELETE FROM processed_webhooks")
    finally:
        conn.close()


# --- Buyer Keys Storage Operations ---

def register_buyer_key(
    kid: str,
    public_key_hex: str,
    contractor_email: Optional[str] = None,
    business_name: Optional[str] = None,
    payer_id: Optional[str] = None,
    identity_provider: Optional[str] = None,
    identity_attested: bool = False,
    attestation_payload: Optional[Dict[str, Any]] = None,
    allow_overwrite: bool = False,
    db_path: Optional[Path] = None,
) -> None:
    """Registers a buyer agent's public key (Ed25519 or P-256 JWK). Prevents unauthorized overwrite."""
    if not kid or not public_key_hex:
        return
    cleaned_key = public_key_hex.strip() if public_key_hex.strip().startswith("{") else public_key_hex.strip().lower()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    attestation_str = json.dumps(attestation_payload) if attestation_payload else None
    conn = get_connection(db_path)
    try:
        with conn:
            cur = conn.cursor()
            cur.execute("SELECT kid FROM buyer_keys WHERE kid = ?", (kid.strip(),))
            existing = cur.fetchone()
            if existing and not allow_overwrite:
                raise ValueError(f"KEY_ALREADY_EXISTS: Key ID '{kid.strip()}' is already registered.")
            if existing and allow_overwrite:
                cur.execute(
                    """
                    UPDATE buyer_keys
                    SET public_key_hex = ?, contractor_email = COALESCE(?, contractor_email),
                        business_name = COALESCE(?, business_name), registered_at = ?,
                        payer_id = COALESCE(?, payer_id),
                        identity_provider = COALESCE(?, identity_provider),
                        identity_attested = CASE WHEN ? THEN 1 ELSE identity_attested END,
                        attestation_payload = COALESCE(?, attestation_payload)
                    WHERE kid = ?
                    """,
                    (
                        cleaned_key,
                        contractor_email,
                        business_name,
                        now_iso,
                        payer_id,
                        identity_provider,
                        1 if identity_attested else 0,
                        attestation_str,
                        kid.strip(),
                    ),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO buyer_keys (
                        kid, public_key_hex, contractor_email, business_name, registered_at,
                        payer_id, identity_provider, identity_attested, attestation_payload
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        kid.strip(),
                        cleaned_key,
                        contractor_email,
                        business_name,
                        now_iso,
                        payer_id,
                        identity_provider,
                        1 if identity_attested else 0,
                        attestation_str,
                    ),
                )
    finally:
        conn.close()


def attest_buyer_identity(
    kid: str,
    payer_id: str,
    identity_provider: str = "paypal",
    attestation_payload: Optional[Dict[str, Any]] = None,
    db_path: Optional[Path] = None,
) -> bool:
    """Attests the identity of an existing registered buyer key with verified PayPal OIDC claims."""
    if not kid or not payer_id:
        return False
    payload_str = json.dumps(attestation_payload) if attestation_payload else None
    conn = get_connection(db_path)
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE buyer_keys
                SET payer_id = ?, identity_provider = ?, identity_attested = 1, attestation_payload = ?
                WHERE kid = ?
                """,
                (payer_id.strip(), identity_provider.strip(), payload_str, kid.strip()),
            )
            return cur.rowcount > 0
    finally:
        conn.close()


def get_buyer_identity(kid: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Returns identity attestation details for a registered buyer key, or None."""
    if not kid:
        return None
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT kid, public_key_hex, contractor_email, business_name, payer_id, 
                   identity_provider, identity_attested, attestation_payload, registered_at
            FROM buyer_keys
            WHERE kid = ?
            """,
            (kid.strip(),),
        )
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        d["identity_attested"] = bool(d.get("identity_attested"))
        if d.get("attestation_payload"):
            try:
                d["attestation_payload"] = json.loads(d["attestation_payload"])
            except Exception:
                pass
        return d
    finally:
        conn.close()


# --- Open Mandate Settlements Tracking ---

def get_open_mandate_settlement_totals(
    mandate_hash: str,
    exclude_subscription_id: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> Tuple[int, int]:
    """
    Returns (total_amount_cents, total_uses) for a given open payment mandate hash.
    Used to construct MandateContext for AP2 Budget and AgentRecurrence evaluation.
    If exclude_subscription_id is provided, excludes that subscription's settlement so replays don't double-count.
    """
    if not mandate_hash:
        return 0, 0
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        if exclude_subscription_id:
            cur.execute(
                """
                SELECT COALESCE(SUM(amount_cents), 0) AS total_amount, COUNT(DISTINCT subscription_id) AS total_uses
                FROM open_mandate_settlements
                WHERE mandate_hash = ? AND subscription_id != ?
                """,
                (mandate_hash.strip(), exclude_subscription_id.strip()),
            )
        else:
            cur.execute(
                """
                SELECT COALESCE(SUM(amount_cents), 0) AS total_amount, COUNT(DISTINCT subscription_id) AS total_uses
                FROM open_mandate_settlements
                WHERE mandate_hash = ?
                """,
                (mandate_hash.strip(),),
            )
        row = cur.fetchone()
        if row:
            return int(row.get("total_amount") or 0), int(row.get("total_uses") or 0)
        return 0, 0
    finally:
        conn.close()


def record_open_mandate_settlement(
    mandate_hash: str,
    subscription_id: str,
    amount_cents: int,
    db_path: Optional[Path] = None,
) -> bool:
    """
    Records a settled payment under an open payment mandate hash.
    Idempotent: replays with the same subscription_id are ignored and return False.
    """
    if not mandate_hash or not subscription_id:
        return False
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_connection(db_path)
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT OR IGNORE INTO open_mandate_settlements (mandate_hash, subscription_id, amount_cents, settled_at)
                VALUES (?, ?, ?, ?)
                """,
                (mandate_hash.strip(), subscription_id.strip(), int(amount_cents), now_iso),
            )
            return cur.rowcount > 0
    finally:
        conn.close()


def reset_open_mandate_settlements(db_path: Optional[Path] = None) -> None:
    """Clears all open mandate settlements (test/mock isolation)."""
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute("DELETE FROM open_mandate_settlements")
    finally:
        conn.close()


# --- Recurring (merchant-initiated) charges under open payment mandates ---

def save_recurring_mandate(
    subscription_id: str,
    mandate_hash: str,
    open_payment_mandate_token: str,
    buyer_email: str,
    agreed_amount_cents: int,
    currency: str,
    db_path: Optional[Path] = None,
) -> bool:
    """Stores the owner-signed open payment mandate for a subscription. Never overwrites; returns True if inserted."""
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_connection(db_path)
    try:
        with conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO recurring_mandates
                    (subscription_id, mandate_hash, open_payment_mandate_token, buyer_email,
                     agreed_amount_cents, currency, initial_sale_id, status, status_reason, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, NULL, 'ACTIVE', NULL, ?, ?)
                """,
                (subscription_id.strip(), mandate_hash.strip(), open_payment_mandate_token,
                 buyer_email.strip().lower(), int(agreed_amount_cents), currency, now_iso, now_iso),
            )
            return cur.rowcount > 0
    finally:
        conn.close()


def get_recurring_mandate(subscription_id: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    if not subscription_id:
        return None
    conn = get_connection(db_path)
    try:
        cur = conn.execute("SELECT * FROM recurring_mandates WHERE subscription_id = ?", (subscription_id.strip(),))
        return cur.fetchone()
    finally:
        conn.close()


def set_recurring_mandate_status(subscription_id: str, status: str, reason: Optional[str] = None,
                                 db_path: Optional[Path] = None) -> None:
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                "UPDATE recurring_mandates SET status = ?, status_reason = ?, updated_at = ? WHERE subscription_id = ?",
                (status, reason, now_iso, subscription_id.strip()),
            )
    finally:
        conn.close()


def bind_initial_sale(subscription_id: str, sale_id: str, db_path: Optional[Path] = None) -> bool:
    """Links the first PayPal sale to the purchase-time settlement. Only succeeds once per subscription."""
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_connection(db_path)
    try:
        with conn:
            cur = conn.execute(
                "UPDATE recurring_mandates SET initial_sale_id = ?, updated_at = ? "
                "WHERE subscription_id = ? AND initial_sale_id IS NULL",
                (sale_id.strip(), now_iso, subscription_id.strip()),
            )
            return cur.rowcount > 0
    finally:
        conn.close()


def record_recurring_charge(
    sale_id: str,
    subscription_id: str,
    mandate_hash: str,
    amount_cents: int,
    currency: str,
    status: str,
    reason: Optional[str],
    charged_at: str,
    db_path: Optional[Path] = None,
) -> bool:
    """Records a PayPal sale and its verification outcome. Idempotent per sale_id; returns True if inserted."""
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_connection(db_path)
    try:
        with conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO recurring_charges
                    (sale_id, subscription_id, mandate_hash, amount_cents, currency, status, reason, charged_at, received_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (sale_id.strip(), subscription_id.strip(), mandate_hash, int(amount_cents), currency,
                 status, reason, charged_at, now_iso),
            )
            return cur.rowcount > 0
    finally:
        conn.close()


def get_recurring_charge(sale_id: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    if not sale_id:
        return None
    conn = get_connection(db_path)
    try:
        cur = conn.execute("SELECT * FROM recurring_charges WHERE sale_id = ?", (sale_id.strip(),))
        return cur.fetchone()
    finally:
        conn.close()


def get_open_mandate_total_usage(mandate_hash: str, db_path: Optional[Path] = None) -> Tuple[int, int]:
    """
    Returns (total_amount_cents, total_uses) charged under an open payment mandate:
    purchase-time settlements plus every later PayPal charge recorded for it. INITIAL charges
    are excluded because the purchase-time settlement already counts them.
    """
    if not mandate_hash:
        raise ValueError("mandate_hash is required to compute mandate usage.")
    settled_cents, settled_uses = get_open_mandate_settlement_totals(mandate_hash, db_path=db_path)
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) AS total_amount, COUNT(*) AS total_uses "
            "FROM recurring_charges WHERE mandate_hash = ? AND status != 'INITIAL'",
            (mandate_hash.strip(),),
        )
        row = cur.fetchone() or {}
        return settled_cents + int(row.get("total_amount") or 0), settled_uses + int(row.get("total_uses") or 0)
    finally:
        conn.close()


# --- Cryptographic Mandate Revocation Operations (SPEC-001 v1.9.0) ---

def record_mandate_revocation(
    mandate_proof_hash: str,
    revoked_by_kid: str,
    reason: str,
    signature_hex: str,
    revoked_at: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Records an owner-signed mandate revocation. Fail-closed against duplicate or empty inputs."""
    if not mandate_proof_hash or not revoked_by_kid or not signature_hex:
        raise ValueError("mandate_proof_hash, revoked_by_kid, and signature_hex are required.")

    clean_hash = mandate_proof_hash.strip()
    revocation_id = f"rev_{uuid.uuid4().hex[:12]}"
    now_iso = revoked_at or datetime.datetime.now(datetime.timezone.utc).isoformat()

    existing = get_mandate_revocation(clean_hash, db_path=db_path)
    if existing:
        return existing

    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO revoked_mandates (revocation_id, mandate_proof_hash, revoked_by_kid, revoked_at, reason, signature_hex)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(mandate_proof_hash) DO NOTHING
                """,
                (revocation_id, clean_hash, revoked_by_kid.strip(), now_iso, reason.strip(), signature_hex.strip()),
            )
        return {
            "revocation_id": revocation_id,
            "mandate_proof_hash": clean_hash,
            "revoked_by_kid": revoked_by_kid.strip(),
            "revoked_at": now_iso,
            "reason": reason.strip(),
            "signature_hex": signature_hex.strip(),
        }
    finally:
        conn.close()


def is_mandate_revoked(mandate_proof_hash: Optional[str], db_path: Optional[Path] = None) -> bool:
    """Returns True if the given mandate proof hash or checkout hash is present in the revocation list."""
    if not mandate_proof_hash or not str(mandate_proof_hash).strip():
        return False
    clean_hash = str(mandate_proof_hash).strip()
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM revoked_mandates WHERE mandate_proof_hash = ? LIMIT 1", (clean_hash,))
        return cur.fetchone() is not None
    finally:
        conn.close()


def get_mandate_revocation(mandate_proof_hash: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Retrieves revocation details for a mandate proof hash if revoked."""
    if not mandate_proof_hash or not str(mandate_proof_hash).strip():
        return None
    clean_hash = str(mandate_proof_hash).strip()
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM revoked_mandates WHERE mandate_proof_hash = ? LIMIT 1", (clean_hash,))
        return cur.fetchone()
    finally:
        conn.close()


def list_revoked_mandates(limit: int = 100, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Lists recent cryptographic mandate revocations ordered by revocation time desc."""
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM revoked_mandates ORDER BY revoked_at DESC LIMIT ?", (max(1, int(limit)),))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


# --- Native AP2 Gateway Direct Rail Charge Operations (Milestone S3-NATIVE) ---

def record_direct_charge(
    charge_data: Dict[str, Any],
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Records a settled native AP2 direct rail charge in SQLite."""
    charge_id = charge_data.get("charge_id") or f"chg_{uuid.uuid4().hex[:12]}"
    mandate_id = charge_data["mandate_id"]
    buyer_key_id = charge_data["buyer_key_id"]
    amount_cents = int(charge_data["amount_cents"])
    currency = charge_data.get("currency", "USD")
    payee_id = charge_data["payee_id"]
    payment_source_id = charge_data["payment_source_id"]
    paypal_capture_id = charge_data["paypal_capture_id"]
    status = charge_data.get("status", "CAPTURED")
    merchant_receipt_jwt = charge_data["merchant_receipt_jwt"]
    qbo_purchase_id = charge_data.get("qbo_purchase_id")
    qbo_payload = charge_data.get("qbo_payload")
    qbo_json = json.dumps(qbo_payload) if qbo_payload else None
    metadata = charge_data.get("metadata") or {}
    meta_json = json.dumps(metadata) if metadata else None
    now_iso = charge_data.get("created_at") or datetime.datetime.now(datetime.timezone.utc).isoformat()

    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO direct_charges (
                    charge_id, mandate_id, buyer_key_id, amount_cents, currency,
                    payee_id, payment_source_id, paypal_capture_id, status,
                    merchant_receipt_jwt, qbo_purchase_id, qbo_payload, metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    charge_id,
                    mandate_id,
                    buyer_key_id,
                    amount_cents,
                    currency,
                    payee_id,
                    payment_source_id,
                    paypal_capture_id,
                    status,
                    merchant_receipt_jwt,
                    qbo_purchase_id,
                    qbo_json,
                    meta_json,
                    now_iso,
                ),
            )
        return get_direct_charge(charge_id, db_path=db_path) or {
            "charge_id": charge_id,
            "mandate_id": mandate_id,
            "buyer_key_id": buyer_key_id,
            "amount_cents": amount_cents,
            "currency": currency,
            "payee_id": payee_id,
            "payment_source_id": payment_source_id,
            "paypal_capture_id": paypal_capture_id,
            "status": status,
            "merchant_receipt_jwt": merchant_receipt_jwt,
            "qbo_purchase_id": qbo_purchase_id,
            "qbo_payload": qbo_payload,
            "metadata": metadata,
            "created_at": now_iso,
        }
    except sqlite3.IntegrityError as e:
        raise ValueError(f"REPLAY_DETECTED: Mandate '{mandate_id}' has already been captured and settled.") from e
    finally:
        conn.close()


def get_direct_charge(charge_id: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Retrieves a direct charge record by its ID."""
    if not charge_id:
        return None
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM direct_charges WHERE charge_id = ?", (charge_id.strip(),))
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get("qbo_payload"):
            try:
                d["qbo_payload"] = json.loads(d["qbo_payload"])
            except Exception:
                pass
        if d.get("metadata_json"):
            try:
                d["metadata"] = json.loads(d.pop("metadata_json"))
            except Exception:
                d["metadata"] = {}
        return d
    finally:
        conn.close()


def list_direct_charges(limit: int = 50, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Lists recent direct charges in descending chronological order."""
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM direct_charges ORDER BY created_at DESC LIMIT ?", (max(1, int(limit)),))
        rows = cur.fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            if d.get("qbo_payload"):
                try:
                    d["qbo_payload"] = json.loads(d["qbo_payload"])
                except Exception:
                    pass
            if d.get("metadata_json"):
                try:
                    d["metadata"] = json.loads(d.pop("metadata_json"))
                except Exception:
                    d["metadata"] = {}
            out.append(d)
        return out
    finally:
        conn.close()


def is_direct_charge_replayed(
    mandate_id: Optional[str] = None,
    receipt_jwt: Optional[str] = None,
    checkout_hash: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> bool:
    """Checks whether a direct charge has already been captured for the given mandate identifiers."""
    candidates = [str(x).strip() for x in (mandate_id, checkout_hash) if x and isinstance(x, str) and str(x).strip()]
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        if candidates:
            placeholders = ",".join("?" for _ in candidates)
            query = f"SELECT 1 FROM direct_charges WHERE mandate_id IN ({placeholders}) LIMIT 1"
            cur.execute(query, candidates)
            if cur.fetchone() is not None:
                return True
        if receipt_jwt and isinstance(receipt_jwt, str) and receipt_jwt.strip():
            cur.execute("SELECT 1 FROM direct_charges WHERE merchant_receipt_jwt = ? LIMIT 1", (receipt_jwt.strip(),))
            if cur.fetchone() is not None:
                return True
        return False
    finally:
        conn.close()


# --- Two-Sided Marketplace & Node Operator Operations ---

def register_node_operator(
    operator_data: Dict[str, Any],
    db_path: Optional[Path] = None,
    allow_overwrite: bool = False,
) -> Dict[str, Any]:
    """Registers or updates a compute node operator."""
    op_id = (operator_data.get("operator_id") or f"op_{uuid.uuid4().hex[:10]}").strip()
    name = (operator_data.get("name") or "Autonomous Compute Operator").strip()
    email = (operator_data.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise ValueError("Valid operator PayPal email is required.")

    recipient_type = (operator_data.get("payout_recipient_type") or "EMAIL").strip().upper()
    assigned = operator_data.get("assigned_nodes") or []
    if isinstance(assigned, (list, set)):
        assigned_json = json.dumps(list(assigned))
    elif isinstance(assigned, str):
        assigned_json = json.dumps([assigned])
    else:
        assigned_json = "[]"

    split_bps = int(operator_data.get("split_bps") or 8500)
    if split_bps < 0 or split_bps > 10000:
        raise ValueError(f"split_bps must be between 0 and 10000 (got {split_bps})")

    status = (operator_data.get("status") or "ACTIVE").strip().upper()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    existing = get_node_operator(op_id, db_path=db_path)
    if existing and existing.get("email") != email and not allow_overwrite:
        raise ValueError(f"OPERATOR_ALREADY_EXISTS: Cannot overwrite payout destination for '{op_id}'.")

    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO node_operators (operator_id, name, email, payout_recipient_type, assigned_nodes, split_bps, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(operator_id) DO UPDATE SET
                    name = excluded.name,
                    email = excluded.email,
                    payout_recipient_type = excluded.payout_recipient_type,
                    assigned_nodes = excluded.assigned_nodes,
                    split_bps = excluded.split_bps,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (op_id, name, email, recipient_type, assigned_json, split_bps, status, now_iso, now_iso),
            )
        return {
            "operator_id": op_id,
            "name": name,
            "email": email,
            "payout_recipient_type": recipient_type,
            "assigned_nodes": json.loads(assigned_json),
            "split_bps": split_bps,
            "status": status,
            "created_at": existing["created_at"] if existing else now_iso,
            "updated_at": now_iso,
        }
    finally:
        conn.close()


def get_node_operator(operator_id: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    if not operator_id:
        return None
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM node_operators WHERE operator_id = ?", (operator_id.strip(),))
        row = cur.fetchone()
        if row:
            d = dict(row)
            try:
                d["assigned_nodes"] = json.loads(d["assigned_nodes"])
            except Exception:
                d["assigned_nodes"] = []
            return d
        return None
    finally:
        conn.close()


def get_operator_by_email(email: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    if not email:
        return None
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM node_operators WHERE email = ?", (email.strip().lower(),))
        row = cur.fetchone()
        if row:
            d = dict(row)
            try:
                d["assigned_nodes"] = json.loads(d["assigned_nodes"])
            except Exception:
                d["assigned_nodes"] = []
            return d
        return None
    finally:
        conn.close()


def get_operator_for_node(node_id: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Resolves which registered operator owns a specific compute node ID or node pattern."""
    if not node_id:
        return None
    clean_node = node_id.strip().lower()
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM node_operators WHERE status = 'ACTIVE' ORDER BY created_at ASC")
        rows = cur.fetchall()
        for r in rows:
            d = dict(r)
            try:
                assigned = json.loads(d["assigned_nodes"])
            except Exception:
                assigned = []
            for pattern in assigned:
                pat_clean = str(pattern).strip().lower()
                if pat_clean and (pat_clean in clean_node or clean_node.startswith(pat_clean)):
                    d["assigned_nodes"] = assigned
                    return d
        if rows:
            fallback = dict(rows[0])
            try:
                fallback["assigned_nodes"] = json.loads(fallback["assigned_nodes"])
            except Exception:
                fallback["assigned_nodes"] = []
            return fallback
        return None
    finally:
        conn.close()


def list_node_operators(db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM node_operators ORDER BY created_at ASC")
        result = []
        for r in cur.fetchall():
            d = dict(r)
            try:
                d["assigned_nodes"] = json.loads(d["assigned_nodes"])
            except Exception:
                d["assigned_nodes"] = []
            result.append(d)
        return result
    finally:
        conn.close()


# --- Payout Batches & Line Items Operations ---

def record_payout_batch(
    batch_data: Dict[str, Any],
    items_data: List[Dict[str, Any]],
    db_path: Optional[Path] = None,
) -> None:
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO payout_batches (
                    batch_id, sender_batch_id, batch_status, total_gross_cents, total_payout_cents,
                    total_platform_fee_cents, currency, item_count, raw_response_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(batch_id) DO UPDATE SET
                    batch_status = excluded.batch_status,
                    total_gross_cents = excluded.total_gross_cents,
                    total_payout_cents = excluded.total_payout_cents,
                    total_platform_fee_cents = excluded.total_platform_fee_cents,
                    item_count = excluded.item_count,
                    raw_response_json = excluded.raw_response_json,
                    updated_at = excluded.updated_at
                """,
                (
                    batch_data["batch_id"].strip(),
                    batch_data["sender_batch_id"].strip(),
                    batch_data.get("batch_status", "SUCCESS"),
                    int(batch_data.get("total_gross_cents", 0)),
                    int(batch_data.get("total_payout_cents", 0)),
                    int(batch_data.get("total_platform_fee_cents", 0)),
                    batch_data.get("currency", "USD"),
                    int(batch_data.get("item_count", len(items_data))),
                    json.dumps(batch_data.get("raw_response", {})),
                    batch_data.get("created_at") or now_iso,
                    now_iso,
                ),
            )
            for it in items_data:
                conn.execute(
                    """
                    INSERT INTO payout_items (
                        item_id, batch_id, operator_id, subscription_id, receiver_email,
                        gross_amount_cents, platform_fee_cents, net_payout_cents, currency, status,
                        paypal_transaction_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(item_id) DO UPDATE SET
                        status = excluded.status,
                        paypal_transaction_id = excluded.paypal_transaction_id
                    """,
                    (
                        it["item_id"].strip(),
                        batch_data["batch_id"].strip(),
                        it["operator_id"].strip(),
                        it["subscription_id"].strip(),
                        it["receiver_email"].strip().lower(),
                        int(it["gross_amount_cents"]),
                        int(it["platform_fee_cents"]),
                        int(it["net_payout_cents"]),
                        it.get("currency", "USD"),
                        it.get("status", "SUCCESS"),
                        it.get("paypal_transaction_id"),
                        it.get("created_at") or now_iso,
                    ),
                )
    finally:
        conn.close()


def get_payout_batch(batch_id: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    if not batch_id:
        return None
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM payout_batches WHERE batch_id = ?", (batch_id.strip(),))
        row = cur.fetchone()
        if not row:
            return None
        res = dict(row)
        cur.execute("SELECT * FROM payout_items WHERE batch_id = ?", (batch_id.strip(),))
        res["items"] = [dict(it) for it in cur.fetchall()]
        return res
    finally:
        conn.close()


def list_payout_batches(limit: int = 50, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM payout_batches ORDER BY created_at DESC LIMIT ?", (max(1, int(limit)),))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def list_payout_items(
    batch_id: Optional[str] = None,
    operator_id: Optional[str] = None,
    limit: int = 100,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        if batch_id and operator_id:
            cur.execute("SELECT * FROM payout_items WHERE batch_id = ? AND operator_id = ? ORDER BY created_at DESC LIMIT ?", (batch_id.strip(), operator_id.strip(), max(1, int(limit))))
        elif batch_id:
            cur.execute("SELECT * FROM payout_items WHERE batch_id = ? ORDER BY created_at DESC LIMIT ?", (batch_id.strip(), max(1, int(limit))))
        elif operator_id:
            cur.execute("SELECT * FROM payout_items WHERE operator_id = ? ORDER BY created_at DESC LIMIT ?", (operator_id.strip(), max(1, int(limit))))
        else:
            cur.execute("SELECT * FROM payout_items ORDER BY created_at DESC LIMIT ?", (max(1, int(limit)),))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_buyer_key(kid: str, db_path: Optional[Path] = None) -> Optional[str]:
    """Retrieves a registered public key hex by key ID."""
    if not kid:
        return None
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT public_key_hex FROM buyer_keys WHERE kid = ?", (kid.strip(),))
        row = cur.fetchone()
        return row["public_key_hex"] if row else None
    finally:
        conn.close()


def get_buyer_key_email(kid: str, db_path: Optional[Path] = None) -> Optional[str]:
    """Returns the contractor email a buyer key was registered for, if any."""
    if not kid:
        return None
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT contractor_email FROM buyer_keys WHERE kid = ?", (kid.strip(),))
        row = cur.fetchone()
        email = row["contractor_email"] if row else None
        return email.strip().lower() if email else None
    finally:
        conn.close()


def list_buyer_keys(db_path: Optional[Path] = None) -> Dict[str, str]:
    """Returns a dictionary of all registered buyer keys (kid -> hex)."""
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT kid, public_key_hex FROM buyer_keys")
        return {r["kid"]: r["public_key_hex"] for r in cur.fetchall()}
    finally:
        conn.close()


def list_buyer_key_records(db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Returns all registered buyer key records including metadata."""
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT kid, public_key_hex, contractor_email, business_name, payer_id, identity_provider, identity_attested, registered_at FROM buyer_keys ORDER BY registered_at DESC"
        )
        out = []
        for r in cur.fetchall():
            d = dict(r)
            d["identity_attested"] = bool(d.get("identity_attested"))
            out.append(d)
        return out
    finally:
        conn.close()


# --- Contractor Budgets & Ledger Storage Operations ---

def set_contractor_cap(contractor_email: str, cap: float, db_path: Optional[Path] = None) -> None:
    """Sets the monthly spending cap for a contractor."""
    if not contractor_email:
        return
    norm = contractor_email.strip().lower()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO contractor_budgets (contractor_email, monthly_cap, committed_spend, updated_at)
                VALUES (?, ?, 0.0, ?)
                ON CONFLICT(contractor_email) DO UPDATE SET
                    monthly_cap = excluded.monthly_cap,
                    updated_at = excluded.updated_at
                """,
                (norm, float(cap), now_iso),
            )
    finally:
        conn.close()


def get_contractor_cap(contractor_email: str, default_cap: Optional[float] = None, db_path: Optional[Path] = None) -> Optional[float]:
    """Gets the configured monthly budget cap for a contractor."""
    if not contractor_email:
        return default_cap
    norm = contractor_email.strip().lower()
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT monthly_cap FROM contractor_budgets WHERE contractor_email = ?", (norm,))
        row = cur.fetchone()
        if row:
            return float(row["monthly_cap"])
        cur.execute("SELECT monthly_cap FROM contractor_authorized_caps WHERE contractor_email = ?", (norm,))
        auth_row = cur.fetchone()
        if auth_row:
            return float(auth_row["monthly_cap"])
        return default_cap
    finally:
        conn.close()


def set_authorized_cap(contractor_email: str, cap: float, source: str, db_path: Optional[Path] = None) -> None:
    """Saves a contractor's binding monthly cap (key registration or the contractor's own signed mandate)."""
    if not contractor_email:
        return
    norm = contractor_email.strip().lower()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO contractor_authorized_caps (contractor_email, monthly_cap, source, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(contractor_email) DO UPDATE SET
                    monthly_cap = excluded.monthly_cap,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                (norm, float(cap), source, now_iso),
            )
    finally:
        conn.close()


def get_authorized_cap(contractor_email: str, db_path: Optional[Path] = None) -> Optional[float]:
    """Returns the contractor's binding monthly cap, or None when none has been saved."""
    if not contractor_email:
        return None
    norm = contractor_email.strip().lower()
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT monthly_cap FROM contractor_authorized_caps WHERE contractor_email = ?", (norm,))
        row = cur.fetchone()
        return float(row["monthly_cap"]) if row else None
    finally:
        conn.close()


def get_contractor_committed_spend(contractor_email: str, db_path: Optional[Path] = None) -> float:
    """Gets the active committed monthly subscription rate for a contractor."""
    if not contractor_email:
        return 0.0
    norm = contractor_email.strip().lower()
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        # Query subscriptions table directly for single source of truth
        cur.execute(
            "SELECT agreed_monthly_rate FROM subscriptions WHERE LOWER(contractor_email) = ? AND status = 'ACTIVE' LIMIT 1",
            (norm,),
        )
        row = cur.fetchone()
        if row:
            return float(row["agreed_monthly_rate"])
        # Fallback to budgets table
        cur.execute("SELECT committed_spend FROM contractor_budgets WHERE contractor_email = ?", (norm,))
        b_row = cur.fetchone()
        return float(b_row["committed_spend"]) if b_row else 0.0
    finally:
        conn.close()


def sync_contractor_commitment(
    contractor_email: str,
    active_monthly_rate: float,
    agent_id: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> None:
    """Synchronizes committed spend from subscription status into the budget table."""
    if not contractor_email:
        return
    norm = contractor_email.strip().lower()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    rate = round(max(0.0, float(active_monthly_rate or 0.0)), 2)

    conn = get_connection(db_path)
    try:
        with conn:
            cur = conn.cursor()
            cur.execute("SELECT monthly_cap FROM contractor_authorized_caps WHERE contractor_email = ?", (norm,))
            row = cur.fetchone()
            cap_val = float(row["monthly_cap"]) if row else rate
            conn.execute(
                """
                INSERT INTO contractor_budgets (contractor_email, monthly_cap, committed_spend, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(contractor_email) DO UPDATE SET
                    committed_spend = excluded.committed_spend,
                    updated_at = excluded.updated_at
                """,
                (norm, cap_val, rate, now_iso),
            )
            if agent_id:
                conn.execute(
                    """
                    INSERT INTO agent_spends (agent_id, total_spent, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(agent_id) DO UPDATE SET
                        total_spent = excluded.total_spent,
                        updated_at = excluded.updated_at
                    """,
                    (agent_id.strip(), rate, now_iso),
                )
    finally:
        conn.close()


def record_spend_entry(
    amount: float,
    action: str,
    contractor_email: Optional[str] = None,
    agent_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    db_path: Optional[Path] = None,
) -> None:
    """Records an audit trail ledger entry."""
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO spend_history (timestamp, amount, contractor_email, agent_id, action, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    time.time(),
                    float(amount),
                    contractor_email.strip().lower() if contractor_email else None,
                    agent_id.strip() if agent_id else None,
                    action,
                    json.dumps(metadata or {}),
                ),
            )
    finally:
        conn.close()


def list_spend_history(
    contractor_email: Optional[str] = None,
    agent_id: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Retrieves audit trail spend history."""
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        query = "SELECT * FROM spend_history WHERE 1=1"
        params: List[Any] = []
        if contractor_email:
            query += " AND LOWER(contractor_email) = ?"
            params.append(contractor_email.strip().lower())
        if agent_id:
            query += " AND agent_id = ?"
            params.append(agent_id.strip())
        query += " ORDER BY id ASC"
        cur.execute(query, params)
        rows = cur.fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            meta_json = d.pop("metadata_json", None)
            if meta_json:
                try:
                    d["metadata"] = json.loads(meta_json)
                except Exception:
                    d["metadata"] = {}
            out.append(d)
        return out
    finally:
        conn.close()


get_spend_history = list_spend_history


def reset_all_data(db_path: Optional[Path] = None) -> None:
    """Clears all dynamic tables while preserving schema and default seeds."""
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute("DELETE FROM subscriptions")
            conn.execute("DELETE FROM subscription_aliases")
            conn.execute("DELETE FROM active_contractor_subscriptions")
            conn.execute("DELETE FROM authorized_mandates")
            conn.execute("DELETE FROM contractor_budgets")
            conn.execute("DELETE FROM contractor_authorized_caps")
            conn.execute("DELETE FROM agent_spends")
            conn.execute("DELETE FROM spend_history")
            conn.execute("DELETE FROM processed_webhooks")
            conn.execute("DELETE FROM dispatch_slots")
            conn.execute("DELETE FROM open_mandate_settlements")
            conn.execute("DELETE FROM recurring_mandates")
            conn.execute("DELETE FROM recurring_charges")
            conn.execute("DELETE FROM revoked_mandates")
            conn.execute("DELETE FROM payout_items")
            conn.execute("DELETE FROM payout_batches")
            conn.execute("DELETE FROM direct_charges")
            op_placeholders = ",".join("?" for _ in DEFAULT_NODE_OPERATOR_IDS)
            conn.execute(f"DELETE FROM node_operators WHERE operator_id NOT IN ({op_placeholders})", list(DEFAULT_NODE_OPERATOR_IDS))
            if getattr(settings, "mock_external_apis", False):
                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                for op in DEFAULT_NODE_OPERATORS:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO node_operators 
                        (operator_id, name, email, payout_recipient_type, assigned_nodes, split_bps, status, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            op["operator_id"],
                            op["name"],
                            op["email"],
                            op.get("payout_recipient_type", "EMAIL"),
                            json.dumps(op["assigned_nodes"]),
                            op.get("split_bps", 8500),
                            op.get("status", "ACTIVE"),
                            now_iso,
                            now_iso,
                        ),
                    )
            placeholders = ",".join("?" for _ in _DEFAULT_BUYER_KIDS)
            conn.execute(f"DELETE FROM buyer_keys WHERE kid NOT IN ({placeholders})", list(_DEFAULT_BUYER_KIDS))
    finally:
        conn.close()


# --- Territory Dispatch Slot Operations ---

def record_dispatch_slot(slot_data: Dict[str, Any], db_path: Optional[Path] = None) -> None:
    """Inserts or replaces a locked territory appointment slot in SQLite."""
    slot_id = slot_data.get("slot_id") or uuid.uuid4().hex[:12]
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO dispatch_slots (
                    slot_id, job_id, contractor_id, territory_zone, slot_start_iso,
                    slot_end_iso, requester_name, workload_scope, payment_id,
                    node_assigned, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    slot_id,
                    slot_data.get("job_id") or slot_data.get("jobId"),
                    slot_data.get("contractor_id", "buyer_agent_alpha_01"),
                    slot_data.get("territory_zone", "Zone 1 - US East"),
                    slot_data.get("slot_start_iso", "2026-10-02 14:00"),
                    slot_data.get("slot_end_iso", "2026-10-02 15:15"),
                    slot_data.get("requester_name") or slot_data.get("requesterName", "Demo Autonomous Buyer"),
                    slot_data.get("workload_scope") or slot_data.get("workloadScope", "Dedicated AI Service Gateway Compute Node Provisioning"),
                    slot_data.get("payment_id") or slot_data.get("paymentId", slot_data.get("paypal_transaction_id", "PAY-DEP-9921")),
                    slot_data.get("node_assigned") or slot_data.get("nodeAssigned", "Cluster Node 01"),
                    now_iso,
                ),
            )
    finally:
        conn.close()


def list_dispatch_slots(db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Retrieves all locked territory appointment windows ordered by start time."""
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM dispatch_slots ORDER BY slot_start_iso ASC")
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


# --- Enterprise Fleet Ledger & Dynamic Telemetry ---

# MOCK(M-009): seeded demo fleet (14 node subscriptions)
AP2_FLEET_SEEDED_SUBSCRIPTIONS = [
    {
        "id": "TXN-AP2-9021",
        "timestamp": "2026-10-02 02:14:22",
        "buyer_agent": "AutonomousBuyerAgent-Alpha-Batch",
        "principal_entity": "Demo Buyer Corp",
        "contractor_name": "AutonomousBuyerAgent-Alpha-Batch",
        "trade_vertical": "High-Throughput Batch Worker",
        "service_plan": "High-Throughput Batch Worker ($49.99/mo)",
        "monthly_amount": 49.99,
        "paypal_sub_id": "AWAITING_PAYPAL_TOKEN",
        "kyc_status": "PENDING_MANDATE_CHALLENGE",
        "kyc_legal_entity": "Demo Buyer Corp",
        "allocated_did": "AWAITING_ENDPOINT",
        "tcpa_guard": "PENDING ED25519 ACTIVATION",
        "status": "PENDING_DEPOSIT",
        "email": "agent-alpha@example.com",
        "data_source": "Demo data",
    },
    {
        "id": "TXN-AP2-9022",
        "timestamp": "2026-10-02 01:45:10",
        "buyer_agent": "AutonomousBuyerAgent-Demo-Gateway",
        "principal_entity": "Demo Enterprise Inc",
        "contractor_name": "AutonomousBuyerAgent-Demo-Gateway",
        "trade_vertical": "Dedicated AI Service Gateway",
        "service_plan": "Dedicated AI Service Gateway ($79.99/mo)",
        "monthly_amount": 79.99,
        "paypal_sub_id": "I-BW452NX993L2",
        "kyc_status": "VERIFIED (Ed25519 Mandate Bound)",
        "kyc_legal_entity": "Demo Enterprise Inc",
        "allocated_did": "mcp+https://gateway-01.example.com/mcp",
        "tcpa_guard": "100% ED25519 SIGNED MANDATE",
        "status": "ACTIVE_STREAMING",
        "email": "agent-demo@example.com",
        "data_source": "Demo data",
    },
    {
        "id": "TXN-AP2-9023",
        "timestamp": "2026-10-01 23:18:44",
        "buyer_agent": "AutonomousBuyerAgent-Security-Cluster",
        "principal_entity": "Example Security Co",
        "contractor_name": "AutonomousBuyerAgent-Security-Cluster",
        "trade_vertical": "Enterprise Cluster Node",
        "service_plan": "Enterprise Cluster Node ($179.99/mo)",
        "monthly_amount": 179.99,
        "paypal_sub_id": "I-SC994ZZ331A8",
        "kyc_status": "VERIFIED (Ed25519 Mandate Bound)",
        "kyc_legal_entity": "Example Security Co",
        "allocated_did": "mcp+https://cluster-01.example.com/mcp",
        "tcpa_guard": "100% ED25519 SIGNED MANDATE",
        "status": "ACTIVE_STREAMING",
        "email": "agent-security@example.com",
        "data_source": "Demo data",
    },
    {
        "id": "TXN-AP2-9024",
        "timestamp": "2026-10-01 21:02:15",
        "buyer_agent": "AutonomousBuyerAgent-Valence-Gateway",
        "principal_entity": "Example Intelligence LLC",
        "contractor_name": "AutonomousBuyerAgent-Valence-Gateway",
        "trade_vertical": "Dedicated AI Service Gateway",
        "service_plan": "Dedicated AI Service Gateway ($79.99/mo)",
        "monthly_amount": 79.99,
        "paypal_sub_id": "I-VG551PP882B4",
        "kyc_status": "VERIFIED (Ed25519 Mandate Bound)",
        "kyc_legal_entity": "Example Intelligence LLC",
        "allocated_did": "mcp+https://gateway-02.example.com/mcp",
        "tcpa_guard": "100% ED25519 SIGNED MANDATE",
        "status": "ACTIVE_STREAMING",
        "email": "agent-intelligence@example.com",
        "data_source": "Demo data",
    },
    {
        "id": "TXN-AP2-9025",
        "timestamp": "2026-10-01 19:30:00",
        "buyer_agent": "AutonomousBuyerAgent-Labs-Batch",
        "principal_entity": "Example Labs",
        "contractor_name": "AutonomousBuyerAgent-Labs-Batch",
        "trade_vertical": "High-Throughput Batch Worker",
        "service_plan": "High-Throughput Batch Worker ($49.99/mo)",
        "monthly_amount": 49.99,
        "paypal_sub_id": "I-CX119CC447T1",
        "kyc_status": "VERIFIED (Ed25519 Mandate Bound)",
        "kyc_legal_entity": "Example Labs",
        "allocated_did": "mcp+https://batch-02.example.com/mcp",
        "tcpa_guard": "100% ED25519 SIGNED MANDATE",
        "status": "ACTIVE_STREAMING",
        "email": "agent-labs@example.com",
        "data_source": "Demo data",
    },
    {
        "id": "TXN-AP2-9026",
        "timestamp": "2026-10-01 16:11:58",
        "buyer_agent": "AutonomousBuyerAgent-Audit-Cluster",
        "principal_entity": "Demo Audit Labs",
        "contractor_name": "AutonomousBuyerAgent-Audit-Cluster",
        "trade_vertical": "Enterprise Cluster Node",
        "service_plan": "Enterprise Cluster Node ($179.99/mo)",
        "monthly_amount": 179.99,
        "paypal_sub_id": "I-HY882GG990W3",
        "kyc_status": "VERIFIED (Ed25519 Mandate Bound)",
        "kyc_legal_entity": "Demo Audit Labs",
        "allocated_did": "mcp+https://cluster-02.example.com/mcp",
        "tcpa_guard": "100% ED25519 SIGNED MANDATE",
        "status": "ACTIVE_STREAMING",
        "email": "agent-audit@example.com",
        "data_source": "Demo data",
    },
    {
        "id": "TXN-AP2-9027",
        "timestamp": "2026-10-01 14:05:32",
        "buyer_agent": "AutonomousBuyerAgent-Vector-Batch",
        "principal_entity": "Demo Vector Co",
        "contractor_name": "AutonomousBuyerAgent-Vector-Batch",
        "trade_vertical": "High-Throughput Batch Worker",
        "service_plan": "High-Throughput Batch Worker ($49.99/mo)",
        "monthly_amount": 49.99,
        "paypal_sub_id": "I-VT771MM220K1",
        "kyc_status": "VERIFIED (Ed25519 Mandate Bound)",
        "kyc_legal_entity": "Demo Vector Co",
        "allocated_did": "mcp+https://batch-03.example.com/mcp",
        "tcpa_guard": "100% ED25519 SIGNED MANDATE",
        "status": "ACTIVE_STREAMING",
        "email": "agent-vector@example.com",
        "data_source": "Demo data",
    },
    {
        "id": "TXN-AP2-9028",
        "timestamp": "2026-10-01 11:42:19",
        "buyer_agent": "AutonomousBuyerAgent-Compute-Gateway",
        "principal_entity": "Example Compute PBC",
        "contractor_name": "AutonomousBuyerAgent-Compute-Gateway",
        "trade_vertical": "Dedicated AI Service Gateway",
        "service_plan": "Dedicated AI Service Gateway ($79.99/mo)",
        "monthly_amount": 79.99,
        "paypal_sub_id": "I-DF449EE881V9",
        "kyc_status": "VERIFIED (Ed25519 Mandate Bound)",
        "kyc_legal_entity": "Example Compute PBC",
        "allocated_did": "mcp+https://gateway-03.example.com/mcp",
        "tcpa_guard": "100% ED25519 SIGNED MANDATE",
        "status": "ACTIVE_STREAMING",
        "email": "agent-compute@example.com",
        "data_source": "Demo data",
    },
    {
        "id": "TXN-AP2-9029",
        "timestamp": "2026-10-01 09:15:40",
        "buyer_agent": "AutonomousBuyerAgent-Cloud-Cluster",
        "principal_entity": "Demo Cloud Solutions",
        "contractor_name": "AutonomousBuyerAgent-Cloud-Cluster",
        "trade_vertical": "Enterprise Cluster Node",
        "service_plan": "Enterprise Cluster Node ($179.99/mo)",
        "monthly_amount": 179.99,
        "paypal_sub_id": "I-MR662SS331B2",
        "kyc_status": "VERIFIED (Ed25519 Mandate Bound)",
        "kyc_legal_entity": "Demo Cloud Solutions",
        "allocated_did": "mcp+https://cluster-03.example.com/mcp",
        "tcpa_guard": "100% ED25519 SIGNED MANDATE",
        "status": "ACTIVE_STREAMING",
        "email": "agent-cloud@example.com",
        "data_source": "Demo data",
    },
    {
        "id": "TXN-AP2-9030",
        "timestamp": "2026-10-01 08:30:12",
        "buyer_agent": "AutonomousBuyerAgent-Agentic-Gateway",
        "principal_entity": "Demo Agentic Ltd",
        "contractor_name": "AutonomousBuyerAgent-Agentic-Gateway",
        "trade_vertical": "Dedicated AI Service Gateway",
        "service_plan": "Dedicated AI Service Gateway ($79.99/mo)",
        "monthly_amount": 79.99,
        "paypal_sub_id": "I-CD551AA994M7",
        "kyc_status": "VERIFIED (Ed25519 Mandate Bound)",
        "kyc_legal_entity": "Demo Agentic Ltd",
        "allocated_did": "mcp+https://gateway-04.example.com/mcp",
        "tcpa_guard": "100% ED25519 SIGNED MANDATE",
        "status": "ACTIVE_STREAMING",
        "email": "agent-agentic@example.com",
        "data_source": "Demo data",
    },
    {
        "id": "TXN-AP2-9031",
        "timestamp": "2026-09-30 22:50:04",
        "buyer_agent": "AutonomousBuyerAgent-Omni-Batch",
        "principal_entity": "Demo Model Corp",
        "contractor_name": "AutonomousBuyerAgent-Omni-Batch",
        "trade_vertical": "High-Throughput Batch Worker",
        "service_plan": "High-Throughput Batch Worker ($49.99/mo)",
        "monthly_amount": 49.99,
        "paypal_sub_id": "I-OM882JJ115X4",
        "kyc_status": "VERIFIED (Ed25519 Mandate Bound)",
        "kyc_legal_entity": "Demo Model Corp",
        "allocated_did": "mcp+https://batch-04.example.com/mcp",
        "tcpa_guard": "100% ED25519 SIGNED MANDATE",
        "status": "ACTIVE_STREAMING",
        "email": "agent-model@example.com",
        "data_source": "Demo data",
    },
    {
        "id": "TXN-AP2-9032",
        "timestamp": "2026-09-30 20:18:27",
        "buyer_agent": "AutonomousBuyerAgent-Inference-Gateway",
        "principal_entity": "Example Inference Co",
        "contractor_name": "AutonomousBuyerAgent-Inference-Gateway",
        "trade_vertical": "Dedicated AI Service Gateway",
        "service_plan": "Dedicated AI Service Gateway ($79.99/mo)",
        "monthly_amount": 79.99,
        "paypal_sub_id": "I-PR331DD772Z8",
        "kyc_status": "VERIFIED (Ed25519 Mandate Bound)",
        "kyc_legal_entity": "Example Inference Co",
        "allocated_did": "mcp+https://gateway-05.example.com/mcp",
        "tcpa_guard": "100% ED25519 SIGNED MANDATE",
        "status": "ACTIVE_STREAMING",
        "email": "agent-inference@example.com",
        "data_source": "Demo data",
    },
    {
        "id": "TXN-AP2-9033",
        "timestamp": "2026-09-30 18:04:55",
        "buyer_agent": "AutonomousBuyerAgent-Quant-Batch",
        "principal_entity": "Demo Scale Labs",
        "contractor_name": "AutonomousBuyerAgent-Quant-Batch",
        "trade_vertical": "High-Throughput Batch Worker",
        "service_plan": "High-Throughput Batch Worker ($49.99/mo)",
        "monthly_amount": 49.99,
        "paypal_sub_id": "I-QS224RR661K3",
        "kyc_status": "VERIFIED (Ed25519 Mandate Bound)",
        "kyc_legal_entity": "Demo Scale Labs",
        "allocated_did": "mcp+https://batch-05.example.com/mcp",
        "tcpa_guard": "100% ED25519 SIGNED MANDATE",
        "status": "ACTIVE_STREAMING",
        "email": "agent-scale@example.com",
        "data_source": "Demo data",
    },
    {
        "id": "TXN-AP2-9034",
        "timestamp": "2026-09-30 15:22:10",
        "buyer_agent": "AutonomousBuyerAgent-Reasoning-Gateway",
        "principal_entity": "Demo Reasoning Group",
        "contractor_name": "AutonomousBuyerAgent-Reasoning-Gateway",
        "trade_vertical": "Dedicated AI Service Gateway",
        "service_plan": "Dedicated AI Service Gateway ($79.99/mo)",
        "monthly_amount": 79.99,
        "paypal_sub_id": "I-AR118CC559W2",
        "kyc_status": "VERIFIED (Ed25519 Mandate Bound)",
        "kyc_legal_entity": "Demo Reasoning Group",
        "allocated_did": "mcp+https://gateway-06.example.com/mcp",
        "tcpa_guard": "100% ED25519 SIGNED MANDATE",
        "status": "ACTIVE_STREAMING",
        "email": "agent-reasoning@example.com",
        "data_source": "Demo data",
    },
]

FLEET_SEEDED_SUBSCRIPTIONS = AP2_FLEET_SEEDED_SUBSCRIPTIONS


# MOCK(M-009): writes the seeded demo fleet into the database
def seed_fleet_subscriptions_if_empty(db_path: Optional[Path] = None) -> int:
    """
    Seeds the 14 fleet node subscriptions into SQLite if they are not already present.
    Batch Worker Alpha (TXN-AP2-9021) is seeded as PENDING_DEPOSIT.
    The remaining 13 nodes are seeded as ACTIVE with assigned MCP endpoints.
    Returns the count of seeded subscriptions.
    """
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT subscription_id FROM subscriptions")
        existing_sub_ids = {r["subscription_id"] for r in cur.fetchall()}
    finally:
        conn.close()

    seeded = 0
    for item in FLEET_SEEDED_SUBSCRIPTIONS:
        is_active = item["status"] == "ACTIVE_STREAMING"
        sub_id = item["paypal_sub_id"] if is_active else item["id"]
        if sub_id in existing_sub_ids:
            continue
        norm_email = item["email"].strip().lower()

        raw_details = {
            "buyer_agent": item["buyer_agent"],
            "trade_vertical": item["trade_vertical"],
            "service_plan": item["service_plan"],
            "kyc_status": item["kyc_status"],
            "tcpa_guard": item["tcpa_guard"],
            "initial_txn_id": item["id"],
        }

        monthly_amt = float(item["monthly_amount"])
        tier_id = "ap2-gateway" if monthly_amt == 79.99 else ("ap2-batch" if monthly_amt == 49.99 else "ap2-cluster")
        plan_id = "P-AP2-SERVICE-GATEWAY" if monthly_amt == 79.99 else ("P-AP2-BATCH-WORKER" if monthly_amt == 49.99 else "P-AP2-CLUSTER-NODE")

        sub_record = {
            "subscription_id": sub_id,
            "status": "ACTIVE" if is_active else "PENDING_DEPOSIT",
            "contractor_email": norm_email,
            "contractor_name": item["contractor_name"],
            "business_entity": item["kyc_legal_entity"],
            "tier_id": tier_id,
            "agreed_monthly_rate": monthly_amt,
            "plan_id": plan_id,
            "buyer_agent_id": item["buyer_agent"],
            "assigned_did": item["allocated_did"] if is_active else None,
            "carrier": "MCP over HTTPS (JSON-RPC 2.0)",
            "routing_state": "CLOUD",
            "subscriber_country_code": "US",
            "offer_id": item["id"],
            "paypal_vault_status": "VAULT_BOUND" if is_active else "AWAITING_PAYPAL_TOKEN",
            "vault_billing_authorized": is_active,
            "vault_customer_present": False,
            "raw_details": raw_details,
        }
        save_subscription(sub_record, db_path=db_path)
        save_subscription_alias(item["id"], sub_id, db_path=db_path)
        if is_active:
            conn = get_connection(db_path)
            try:
                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                with conn:
                    conn.execute(
                        """
                        INSERT INTO active_contractor_subscriptions (contractor_email, subscription_id, updated_at)
                        VALUES (?, ?, ?)
                        ON CONFLICT(contractor_email) DO UPDATE SET subscription_id = excluded.subscription_id
                        """,
                        (norm_email, sub_id, now_iso),
                    )
            finally:
                conn.close()
        seeded += 1

    return seeded


def _mask_name(name: Optional[str]) -> str:
    if not name:
        return "Contractor"
    parts = name.strip().split()
    return " ".join([f"{p[0]}***" for p in parts if p])


def _mask_sub_id(sub_id: Optional[str]) -> str:
    if not sub_id or sub_id in ("AWAITING_PAYPAL_TOKEN", "NONE"):
        return sub_id or "AWAITING_PAYPAL_TOKEN"
    if len(sub_id) > 10:
        return f"{sub_id[:6]}***{sub_id[-4:]}"
    return f"{sub_id[:3]}***"


def get_fleet_ledger(
    db_path: Optional[Path] = None,
    mask_pii: bool = False,
    profile: str = "ap2",
) -> List[Dict[str, Any]]:
    """
    Returns the dynamic enterprise fleet ledger formatted for AG Grid and AG Studio.
    Serves the AP2 autonomous agent seller deck dataset (Demo data).
    Masks PII when mask_pii=True for public endpoints.
    """
    conn = get_connection(db_path)
    active_sub = None
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT * FROM subscriptions 
            WHERE status IN ('ACTIVE', 'ACTIVE_STREAMING')
              AND contractor_email = 'agent-alpha@example.com'
              AND subscription_id != 'TXN-AP2-9021'
            ORDER BY updated_at DESC, created_at DESC
            LIMIT 1
            """
        )
        active_sub = cur.fetchone()
    except Exception:
        pass
    finally:
        conn.close()

    if not active_sub:
        try:
            from .agents.seller_agent import _COMPLETED_SUBSCRIPTIONS
            for s_id, s_data in _COMPLETED_SUBSCRIPTIONS.items():
                c_email = (s_data.get("contractor_email") or "").lower()
                if s_data.get("status") in ["ACTIVE", "ACTIVE_STREAMING"] and (
                    c_email == "agent-alpha@example.com"
                ) and s_id != "TXN-AP2-9021":
                    active_sub = s_data
                    break
        except Exception:
            pass

    result = []
    # MOCK(M-009): ledger rows built from the seeded demo fleet
    for item in AP2_FLEET_SEEDED_SUBSCRIPTIONS:
        is_pending_batch = item["id"] == "TXN-AP2-9021"
        if is_pending_batch and active_sub:
            status = "ACTIVE_STREAMING"
            is_active = True
            sub_id = active_sub.get("subscription_id") or "I-AP2-SUB-9021"
            assigned = active_sub.get("assigned_did") or active_sub.get("allocated_did") or active_sub.get("mcp_endpoint")
            if assigned and str(assigned).startswith("mcp+https://"):
                display_endpoint = str(assigned)
            else:
                display_endpoint = "mcp+https://gateway-01.example.com/agents/batch-alpha"
            kyc_status = "VERIFIED (Ed25519 Mandate Bound)"
            anti_tamper = active_sub.get("mandate_proof_hash") or "SHA256 Match (PASS)"
        else:
            status = item["status"]
            is_active = status in ["ACTIVE", "ACTIVE_STREAMING"]
            sub_id = item["paypal_sub_id"]
            display_endpoint = item["allocated_did"]
            kyc_status = item["kyc_status"]
            anti_tamper = None

        display_sub_id = (_mask_sub_id(sub_id) if is_active else "AWAITING_PAYPAL_TOKEN") if mask_pii else (sub_id if is_active else "AWAITING_PAYPAL_TOKEN")
        monthly_float = float(item["monthly_amount"])
        gross_cents = int(round(monthly_float * 100))
        net_cents = (gross_cents * 8500) // 10000
        margin_cents = gross_cents - net_cents
        node_ref = display_endpoint or item.get("allocated_did") or item["trade_vertical"]
        op = get_operator_for_node(node_ref, db_path=db_path)
        op_name = op["name"] if op else "Lambda Autonomous Compute"
        op_email = op["email"] if op else "payouts-lambda@example.com"

        entry = {
            "id": item["id"],
            "timestamp": item["timestamp"],
            "buyer_agent": item["buyer_agent"],
            "contractor_name": item["buyer_agent"],
            "principal_entity": item["principal_entity"],
            "trade_vertical": item["trade_vertical"],
            "service_plan": item["service_plan"],
            "monthly_amount": monthly_float,
            "paypal_sub_id": display_sub_id,
            "kyc_status": kyc_status,
            "kyc_legal_entity": item["kyc_legal_entity"],
            "allocated_did": display_endpoint,
            "tcpa_guard": item["tcpa_guard"],
            "status": status,
            "data_source": "Demo data",
            "operator_name": op_name,
            "operator_email": op_email,
            "operator_split_bps": 8500,
            "operator_monthly_net": round(net_cents / 100, 2),
            "platform_margin_fee": round(margin_cents / 100, 2),
        }
        if anti_tamper:
            entry["anti_tamper_hash"] = anti_tamper
        result.append(entry)
    return result

def get_fleet_stats(db_path: Optional[Path] = None, profile: str = "default") -> Dict[str, Any]:
    """Computes real-time fleet aggregates and KPIs from the persistent SQLite database or AP2 dataset."""
    ledger_items = get_fleet_ledger(db_path=db_path, profile=profile)

    total_mrr = sum(item["monthly_amount"] for item in ledger_items if item["status"] in ["ACTIVE", "ACTIVE_STREAMING"])
    active_lines = sum(1 for item in ledger_items if item["status"] in ["ACTIVE", "ACTIVE_STREAMING"])
    total_subscribers = len(ledger_items)
    annualized_gmv = round(total_mrr * 12, 2)
    # One verified mandate settles each active subscription; no multipliers
    mandates_cleared = active_lines

    # Group by capability / trade vertical
    trade_counts: Dict[str, Dict[str, Any]] = {}
    for item in ledger_items:
        trade = item["trade_vertical"]
        if trade not in trade_counts:
            trade_counts[trade] = {
                "trade": trade,
                "active_agents": 0,
                "monthly_settlement": 0.0,
                "annualized_gmv": 0.0,
                "mandates_cleared": 0,
            }
        if item["status"] in ["ACTIVE", "ACTIVE_STREAMING"]:
            trade_counts[trade]["active_agents"] += 1
            trade_counts[trade]["monthly_settlement"] += item["monthly_amount"]
            trade_counts[trade]["mandates_cleared"] += 1

    for t in trade_counts.values():
        t["monthly_settlement"] = round(t["monthly_settlement"], 2)
        t["annualized_gmv"] = round(t["monthly_settlement"] * 12, 2)

    pending_count = total_subscribers - active_lines
    if pending_count > 0:
        compliance_guard = f"{active_lines}/{total_subscribers} subscriptions active, {pending_count} pending"
    else:
        compliance_guard = f"{active_lines}/{total_subscribers} subscriptions active"

    return {
        "total_mrr": round(total_mrr, 2),
        "active_lines": active_lines,
        "total_subscribers": total_subscribers,
        "annualized_gmv": annualized_gmv,
        "mandates_cleared": mandates_cleared,
        "compliance_guard": compliance_guard,
        "carrier_resporg": "MCP over HTTPS (JSON-RPC 2.0)",
        "trade_breakdown": list(trade_counts.values()),
    }


# MOCK(M-009): hardcoded scheduler events
def get_fleet_schedule(db_path: Optional[Path] = None, profile: str = "ap2") -> Dict[str, Any]:
    """Returns resources and realistic timeline events for Bryntum Dispatch Scheduler in AP2 mode."""
    ledger_items = get_fleet_ledger(db_path=db_path, profile="ap2")
    resources = []
    for idx, item in enumerate(ledger_items):
        node_id = f"node-{idx + 1}"
        resources.append({
            "id": node_id,
            "name": item["buyer_agent"],
            "entity": item["kyc_legal_entity"],
            "trade": item["trade_vertical"],
            "did": item["allocated_did"],
            "status": item["status"],
        })

    events = [
        {
            "id": "evt-ap2-01",
            "resourceId": "node-1",
            "name": "Mandate Ingestion: Demo Buyer • High-Throughput Batch Worker",
            "startDate": "2026-10-02 08:30",
            "endDate": "2026-10-02 09:45",
            "eventColor": "orange",
            "iconCls": "b-fa b-fa-clock",
            "depositStatus": "AWAITING DEPOSIT / MANDATE",
            "paypalTxn": "TXN-AP2-9021",
        },
        {
            "id": "evt-ap2-02",
            "resourceId": "node-2",
            "name": "Mandate Renewal: Apex Enterprise • Dedicated AI Service Gateway",
            "startDate": "2026-10-02 10:00",
            "endDate": "2026-10-02 11:15",
            "eventColor": "blue",
            "iconCls": "b-fa b-fa-key",
            "depositStatus": "RENEWAL CONFIRMED - ED25519",
            "paypalTxn": "I-BW452NX993L2",
        },
        {
            "id": "evt-ap2-03",
            "resourceId": "node-3",
            "name": "SLA Verification: Sentinel Code • Enterprise Cluster Node",
            "startDate": "2026-10-02 11:30",
            "endDate": "2026-10-02 12:45",
            "eventColor": "purple",
            "iconCls": "b-fa b-fa-shield-check",
            "depositStatus": "SLA VERIFIED (99.99%)",
            "paypalTxn": "I-SC994ZZ331A8",
        },
        {
            "id": "evt-ap2-04",
            "resourceId": "node-4",
            "name": "Key Rotation: Vanguard Machine • Dedicated AI Service Gateway",
            "startDate": "2026-10-02 13:00",
            "endDate": "2026-10-02 14:15",
            "eventColor": "blue",
            "iconCls": "b-fa b-fa-sync",
            "depositStatus": "RFC 8032 RE-VERIFIED",
            "paypalTxn": "I-VG551PP882B4",
        },
        {
            "id": "evt-ap2-05",
            "resourceId": "node-5",
            "name": "Quota Refresh: Cortex Labs • High-Throughput Batch Worker",
            "startDate": "2026-10-02 14:30",
            "endDate": "2026-10-02 15:45",
            "eventColor": "cyan",
            "iconCls": "b-fa b-fa-microchip",
            "depositStatus": "125 OPS QUOTA PROVISIONED",
            "paypalTxn": "I-CX119CC447T1",
        },
        {
            "id": "evt-ap2-06",
            "resourceId": "node-6",
            "name": "Cluster Health Audit: Hyperion • Enterprise Cluster Node",
            "startDate": "2026-10-02 16:00",
            "endDate": "2026-10-02 17:15",
            "eventColor": "purple",
            "iconCls": "b-fa b-fa-server",
            "depositStatus": "HARDWARE ENCLAVE BOUND",
            "paypalTxn": "I-HY882GG990W3",
        },
        {
            "id": "evt-ap2-07",
            "resourceId": "node-7",
            "name": "Mandate Settlement: Vector Semantic • High-Throughput Batch Worker",
            "startDate": "2026-10-02 09:15",
            "endDate": "2026-10-02 10:30",
            "eventColor": "cyan",
            "iconCls": "b-fa b-fa-file-invoice",
            "depositStatus": "QBO #6300 SYNCED",
            "paypalTxn": "I-VT771MM220K1",
        },
        {
            "id": "evt-ap2-08",
            "resourceId": "node-8",
            "name": "Gateway Latency Audit: DeepFlow • Dedicated AI Service Gateway",
            "startDate": "2026-10-02 10:45",
            "endDate": "2026-10-02 12:00",
            "eventColor": "blue",
            "iconCls": "b-fa b-fa-bolt",
            "depositStatus": "SUB-350MS LATENCY PASS",
            "paypalTxn": "I-DF449EE881V9",
        },
        {
            "id": "evt-ap2-09",
            "resourceId": "node-9",
            "name": "Failover Simulation: Meridian Cloud • Enterprise Cluster Node",
            "startDate": "2026-10-02 13:30",
            "endDate": "2026-10-02 14:45",
            "eventColor": "purple",
            "iconCls": "b-fa b-fa-network-wired",
            "depositStatus": "MULTI-REGION DRIFT 0MS",
            "paypalTxn": "I-MR662SS331B2",
        },
        {
            "id": "evt-ap2-10",
            "resourceId": "node-10",
            "name": "Mandate Renewal: Cyberdyne • Dedicated AI Service Gateway",
            "startDate": "2026-10-02 15:00",
            "endDate": "2026-10-02 16:15",
            "eventColor": "blue",
            "iconCls": "b-fa b-fa-key",
            "depositStatus": "VAULT MIT ACTIVE",
            "paypalTxn": "I-CD551AA994M7",
        },
        {
            "id": "evt-ap2-11",
            "resourceId": "node-11",
            "name": "Batch Worker Scaling: OmniModel • High-Throughput Batch Worker",
            "startDate": "2026-10-02 08:00",
            "endDate": "2026-10-02 09:15",
            "eventColor": "cyan",
            "iconCls": "b-fa b-fa-microchip",
            "depositStatus": "BATCH ENCLAVE ACTIVE",
            "paypalTxn": "I-OM882JJ115X4",
        },
        {
            "id": "evt-ap2-12",
            "resourceId": "node-12",
            "name": "Gateway Cert Renewal: Example Inference • Dedicated AI Service Gateway",
            "startDate": "2026-10-02 11:15",
            "endDate": "2026-10-02 12:30",
            "eventColor": "blue",
            "iconCls": "b-fa b-fa-lock",
            "depositStatus": "TLS 1.3 CERT BOUND",
            "paypalTxn": "I-PR331DD772Z8",
        },
        {
            "id": "evt-ap2-13",
            "resourceId": "node-13",
            "name": "Auto-Debit Settlement: QuantScale • High-Throughput Batch Worker",
            "startDate": "2026-10-02 14:00",
            "endDate": "2026-10-02 15:15",
            "eventColor": "cyan",
            "iconCls": "b-fa b-fa-dollar-sign",
            "depositStatus": "SETTLED ($49.99)",
            "paypalTxn": "I-QS224RR661K3",
        },
        {
            "id": "evt-ap2-14",
            "resourceId": "node-14",
            "name": "Mandate Health Check: Apex Reasoning • Dedicated AI Service Gateway",
            "startDate": "2026-10-02 16:30",
            "endDate": "2026-10-02 17:45",
            "eventColor": "blue",
            "iconCls": "b-fa b-fa-check-double",
            "depositStatus": "HEALTHY (0 ERRORS)",
            "paypalTxn": "I-AR118CC559W2",
        },
    ]

    slots = list_dispatch_slots(db_path=db_path)
    for s in slots:
        events.append({
            "id": f"slot-{s.get('slot_id', 'dynamic')}",
            "resourceId": "node-1",
            "name": f"Takeoff: {s.get('project_scope', 'Compute Node')} ({s.get('territory_zone', 'Cluster')})",
            "startDate": s.get("slot_start_iso", "2026-10-02 14:00"),
            "endDate": s.get("slot_end_iso", "2026-10-02 15:15"),
            "eventColor": "blue",
            "iconCls": "b-fa b-fa-calendar-check",
            "depositStatus": f"DEPOSIT VERIFIED ({s.get('deposit_payment_id', 'PAY-DEP-9921')})",
            "paypalTxn": s.get("deposit_payment_id", "PAY-DEP-9921"),
        })

    return {
        "resources": resources,
        "events": events,
    }


# --- Dict / Set Mapping Proxies for Seamless Backward Compatibility ---

class SubscriptionsDictProxy(MutableMapping):
    """Dictionary-like proxy backing _COMPLETED_SUBSCRIPTIONS with persistent SQLite storage."""

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path

    def __getitem__(self, key: str) -> Dict[str, Any]:
        item = get_subscription(key, self._db_path)
        if item is None:
            raise KeyError(key)
        return item

    def __setitem__(self, key: str, value: Dict[str, Any]) -> None:
        if isinstance(value, dict):
            sub_id = value.get("subscription_id")
            if not sub_id:
                value["subscription_id"] = key
                sub_id = key
            save_subscription(value, self._db_path)
            if key != sub_id:
                save_subscription_alias(key, sub_id, self._db_path)

    def __delitem__(self, key: str) -> None:
        if not delete_subscription(key, self._db_path):
            raise KeyError(key)

    def items(self) -> List[Tuple[str, Dict[str, Any]]]:
        res = []
        for s in list_subscriptions(db_path=self._db_path):
            sub_id = s["subscription_id"]
            res.append((sub_id, get_subscription(sub_id, self._db_path)))
        conn = get_connection(self._db_path)
        try:
            cur = conn.cursor()
            cur.execute("SELECT alias_key, subscription_id FROM subscription_aliases")
            for r in cur.fetchall():
                sub = get_subscription(r["subscription_id"], self._db_path)
                if sub:
                    res.append((r["alias_key"], sub))
        finally:
            conn.close()
        return res

    def values(self) -> List[Dict[str, Any]]:
        return [s for _, s in self.items()]

    def __iter__(self) -> Iterator[str]:
        for k, _ in self.items():
            yield k

    def __len__(self) -> int:
        return len(self.items())

    def __contains__(self, key: Any) -> bool:
        return get_subscription(str(key), self._db_path) is not None

    def get(self, key: str, default: Any = None) -> Any:
        item = get_subscription(key, self._db_path)
        return item if item is not None else default

    def clear(self) -> None:
        clear_subscriptions(self._db_path)


class ActiveContractorSubscriptionsProxy(MutableMapping):
    """Dictionary-like proxy mapping contractor emails to active subscription IDs with persistent SQLite storage."""

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path

    def __getitem__(self, email: str) -> str:
        if not email:
            raise KeyError(email)
        norm = email.strip().lower()
        conn = get_connection(self._db_path)
        try:
            cur = conn.cursor()
            cur.execute("SELECT subscription_id FROM active_contractor_subscriptions WHERE contractor_email = ?", (norm,))
            row = cur.fetchone()
            if row:
                return row["subscription_id"]
            cur.execute("SELECT subscription_id FROM subscriptions WHERE contractor_email = ? AND status = 'ACTIVE' ORDER BY rowid DESC LIMIT 1", (norm,))
            row = cur.fetchone()
            if row:
                return row["subscription_id"]
            raise KeyError(email)
        finally:
            conn.close()

    def __setitem__(self, email: str, subscription_id: str) -> None:
        if not email or not subscription_id:
            return
        norm = email.strip().lower()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        conn = get_connection(self._db_path)
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO active_contractor_subscriptions (contractor_email, subscription_id, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(contractor_email) DO UPDATE SET
                        subscription_id = excluded.subscription_id,
                        updated_at = excluded.updated_at
                    """,
                    (norm, subscription_id.strip(), now_iso),
                )
        finally:
            conn.close()

    def __delitem__(self, email: str) -> None:
        if not email:
            raise KeyError(email)
        norm = email.strip().lower()
        conn = get_connection(self._db_path)
        try:
            with conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM active_contractor_subscriptions WHERE contractor_email = ?", (norm,))
                if cur.rowcount == 0:
                    raise KeyError(email)
        finally:
            conn.close()

    def __iter__(self) -> Iterator[str]:
        conn = get_connection(self._db_path)
        try:
            cur = conn.cursor()
            cur.execute("SELECT contractor_email FROM active_contractor_subscriptions")
            for r in cur.fetchall():
                yield r["contractor_email"]
        finally:
            conn.close()

    def __len__(self) -> int:
        conn = get_connection(self._db_path)
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) as count FROM active_contractor_subscriptions")
            return cur.fetchone()["count"]
        finally:
            conn.close()

    def __contains__(self, email: Any) -> bool:
        if not email:
            return False
        norm = str(email).strip().lower()
        conn = get_connection(self._db_path)
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM active_contractor_subscriptions WHERE contractor_email = ?", (norm,))
            if cur.fetchone() is not None:
                return True
            cur.execute("SELECT 1 FROM subscriptions WHERE contractor_email = ? AND status = 'ACTIVE' LIMIT 1", (norm,))
            return cur.fetchone() is not None
        finally:
            conn.close()

    def get(self, email: str, default: Any = None) -> Any:
        try:
            return self[email]
        except KeyError:
            return default

    def pop(self, email: str, default: Any = None) -> Any:
        try:
            val = self[email]
            del self[email]
            return val
        except KeyError:
            return default

    def clear(self) -> None:
        conn = get_connection(self._db_path)
        try:
            with conn:
                conn.execute("DELETE FROM active_contractor_subscriptions")
        finally:
            conn.close()


class AuthorizedMandatesProxy(MutableMapping):
    """Dictionary-like proxy backing _AUTHORIZED_MANDATES with persistent SQLite storage."""

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path

    def __getitem__(self, key: str) -> Dict[str, Any]:
        item = get_mandate(key, self._db_path)
        if item is None:
            raise KeyError(key)
        return item

    def __setitem__(self, key: str, value: Dict[str, Any]) -> None:
        save_mandate(key, value, self._db_path)

    def __delitem__(self, key: str) -> None:
        if not delete_mandate(key, self._db_path):
            raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        conn = get_connection(self._db_path)
        try:
            cur = conn.cursor()
            cur.execute("SELECT lookup_key FROM authorized_mandates")
            for r in cur.fetchall():
                yield r["lookup_key"]
        finally:
            conn.close()

    def __len__(self) -> int:
        conn = get_connection(self._db_path)
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) as count FROM authorized_mandates")
            return cur.fetchone()["count"]
        finally:
            conn.close()

    def __contains__(self, key: Any) -> bool:
        return get_mandate(str(key), self._db_path) is not None

    def get(self, key: str, default: Any = None) -> Any:
        item = get_mandate(key, self._db_path)
        return item if item is not None else default

    def clear(self) -> None:
        clear_mandates(self._db_path)


class ProcessedWebhooksProxy(MutableSet):
    """Set-like proxy backing _PROCESSED_WEBHOOK_IDS with persistent SQLite storage."""

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path

    def __contains__(self, event_id: Any) -> bool:
        return is_webhook_processed(str(event_id), self._db_path)

    def add(self, event_id: str) -> None:
        record_processed_webhook(event_id, db_path=self._db_path)

    def discard(self, event_id: str) -> None:
        conn = get_connection(self._db_path)
        try:
            with conn:
                conn.execute("DELETE FROM processed_webhooks WHERE event_id = ?", (str(event_id).strip(),))
        finally:
            conn.close()

    def __iter__(self) -> Iterator[str]:
        conn = get_connection(self._db_path)
        try:
            cur = conn.cursor()
            cur.execute("SELECT event_id FROM processed_webhooks")
            for r in cur.fetchall():
                yield r["event_id"]
        finally:
            conn.close()

    def __len__(self) -> int:
        conn = get_connection(self._db_path)
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) as count FROM processed_webhooks")
            return cur.fetchone()["count"]
        finally:
            conn.close()

    def clear(self) -> None:
        clear_processed_webhooks(self._db_path)


class BuyerKeysProxy(MutableMapping):
    """Dictionary-like proxy backing REGISTERED_BUYER_KEYS with persistent SQLite storage."""

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path

    def __getitem__(self, kid: str) -> str:
        key = get_buyer_key(kid, self._db_path)
        if key is None:
            raise KeyError(kid)
        return key

    def __setitem__(self, kid: str, public_key_hex: str) -> None:
        register_buyer_key(kid, public_key_hex, allow_overwrite=True, db_path=self._db_path)

    def __delitem__(self, kid: str) -> None:
        conn = get_connection(self._db_path)
        try:
            with conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM buyer_keys WHERE kid = ?", (kid.strip(),))
                if cur.rowcount == 0:
                    raise KeyError(kid)
        finally:
            conn.close()

    def __iter__(self) -> Iterator[str]:
        for k in list_buyer_keys(self._db_path).keys():
            yield k

    def __len__(self) -> int:
        return len(list_buyer_keys(self._db_path))

    def __contains__(self, kid: Any) -> bool:
        return get_buyer_key(str(kid), self._db_path) is not None

    def get(self, kid: str, default: Any = None) -> Any:
        key = get_buyer_key(kid, self._db_path)
        return key if key is not None else default

    def items(self) -> List[Tuple[str, str]]:
        return list(list_buyer_keys(self._db_path).items())

    def clear(self) -> None:
        conn = get_connection(self._db_path)
        try:
            with conn:
                conn.execute("DELETE FROM buyer_keys")
        finally:
            conn.close()


# Initialize database automatically upon module import
init_db()
