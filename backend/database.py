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

_DEFAULT_BUYER_KIDS = {
    "ap2-seller-ed25519-v1",
    "ap2-buyer-ed25519-v1",
    "buyer-agent-01",
    "buyer-agent-001",
    "claude-desktop-buyer",
    "test-agent-001",
}


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
                carrier TEXT DEFAULT 'Dual-Transport FastMCP (RFC 8032)',
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
                monthly_cap REAL NOT NULL DEFAULT 100.00,
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
                registered_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS open_mandate_settlements (
                mandate_hash TEXT NOT NULL,
                subscription_id TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                settled_at TEXT NOT NULL,
                PRIMARY KEY (mandate_hash, subscription_id)
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

            # Seed default buyer keys if table is empty
            cur.execute("SELECT COUNT(*) as count FROM buyer_keys")
            count = cur.fetchone()["count"]
            if count == 0:
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
                        (kid, buyer_pub, "agent-alpha@example.com", "Nexus Autonomous Systems Corp", now_iso),
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
                    sub.get("carrier", "Dual-Transport FastMCP (RFC 8032)"),
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
                    (details.get("contractor_email") or "").strip().lower() or None,
                    details.get("tier_id", "*"),
                    float(details.get("amount") or 0.0),
                    float(details.get("monthly_budget_cap") or 100.0),
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
    allow_overwrite: bool = False,
    db_path: Optional[Path] = None,
) -> None:
    """Registers a buyer agent's public key (Ed25519 or P-256 JWK). Prevents unauthorized overwrite."""
    if not kid or not public_key_hex:
        return
    cleaned_key = public_key_hex.strip() if public_key_hex.strip().startswith("{") else public_key_hex.strip().lower()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
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
                        business_name = COALESCE(?, business_name), registered_at = ?
                    WHERE kid = ?
                    """,
                    (cleaned_key, contractor_email, business_name, now_iso, kid.strip()),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO buyer_keys (kid, public_key_hex, contractor_email, business_name, registered_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (kid.strip(), cleaned_key, contractor_email, business_name, now_iso),
                )
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
            "SELECT kid, public_key_hex, contractor_email, business_name, registered_at FROM buyer_keys ORDER BY registered_at DESC"
        )
        return [dict(r) for r in cur.fetchall()]
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


def get_contractor_cap(contractor_email: str, default_cap: float = 100.0, db_path: Optional[Path] = None) -> float:
    """Gets the configured monthly budget cap for a contractor."""
    if not contractor_email:
        return default_cap
    norm = contractor_email.strip().lower()
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT monthly_cap FROM contractor_budgets WHERE contractor_email = ?", (norm,))
        row = cur.fetchone()
        return float(row["monthly_cap"]) if row else default_cap
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
            conn.execute(
                """
                INSERT INTO contractor_budgets (contractor_email, monthly_cap, committed_spend, updated_at)
                VALUES (?, 100.0, ?, ?)
                ON CONFLICT(contractor_email) DO UPDATE SET
                    committed_spend = excluded.committed_spend,
                    updated_at = excluded.updated_at
                """,
                (norm, rate, now_iso),
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
                    slot_data.get("requester_name") or slot_data.get("requesterName", "Nexus Autonomous Buyer"),
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

AP2_FLEET_SEEDED_SUBSCRIPTIONS = [
    {
        "id": "TXN-AP2-9021",
        "timestamp": "2026-10-02 02:14:22",
        "buyer_agent": "AutonomousBuyerAgent-Alpha-Batch",
        "principal_entity": "Nexus Autonomous Systems Corp",
        "contractor_name": "AutonomousBuyerAgent-Alpha-Batch",
        "trade_vertical": "High-Throughput Batch Worker",
        "service_plan": "High-Throughput Batch Worker ($49.99/mo)",
        "monthly_amount": 49.99,
        "paypal_sub_id": "AWAITING_PAYPAL_TOKEN",
        "kyc_status": "PENDING_MANDATE_CHALLENGE",
        "kyc_legal_entity": "Nexus Autonomous Systems Corp",
        "allocated_did": "AWAITING_ENDPOINT",
        "tcpa_guard": "PENDING ED25519 ACTIVATION",
        "status": "PENDING_DEPOSIT",
        "email": "agent-alpha@example.com",
        "data_source": "Demo data",
    },
    {
        "id": "TXN-AP2-9022",
        "timestamp": "2026-10-02 01:45:10",
        "buyer_agent": "AutonomousBuyerAgent-Nexus-Gateway",
        "principal_entity": "Apex Enterprise AI Inc",
        "contractor_name": "AutonomousBuyerAgent-Nexus-Gateway",
        "trade_vertical": "Dedicated AI Service Gateway",
        "service_plan": "Dedicated AI Service Gateway ($79.99/mo)",
        "monthly_amount": 79.99,
        "paypal_sub_id": "I-BW452NX993L2",
        "kyc_status": "VERIFIED (Ed25519 Mandate Bound)",
        "kyc_legal_entity": "Apex Enterprise AI Inc",
        "allocated_did": "mcp+https://gateway-01.example.com/mcp",
        "tcpa_guard": "100% ED25519 SIGNED MANDATE",
        "status": "ACTIVE_STREAMING",
        "email": "agent-nexus@example.com",
        "data_source": "Demo data",
    },
    {
        "id": "TXN-AP2-9023",
        "timestamp": "2026-10-01 23:18:44",
        "buyer_agent": "AutonomousBuyerAgent-Sentinel-Cluster",
        "principal_entity": "Sentinel Code Security Corp",
        "contractor_name": "AutonomousBuyerAgent-Sentinel-Cluster",
        "trade_vertical": "Enterprise Cluster Node",
        "service_plan": "Enterprise Cluster Node ($179.99/mo)",
        "monthly_amount": 179.99,
        "paypal_sub_id": "I-SC994ZZ331A8",
        "kyc_status": "VERIFIED (Ed25519 Mandate Bound)",
        "kyc_legal_entity": "Sentinel Code Security Corp",
        "allocated_did": "mcp+https://cluster-01.example.com/mcp",
        "tcpa_guard": "100% ED25519 SIGNED MANDATE",
        "status": "ACTIVE_STREAMING",
        "email": "agent-sentinel@example.com",
        "data_source": "Demo data",
    },
    {
        "id": "TXN-AP2-9024",
        "timestamp": "2026-10-01 21:02:15",
        "buyer_agent": "AutonomousBuyerAgent-Vanguard-Gateway",
        "principal_entity": "Vanguard Machine Intelligence LLC",
        "contractor_name": "AutonomousBuyerAgent-Vanguard-Gateway",
        "trade_vertical": "Dedicated AI Service Gateway",
        "service_plan": "Dedicated AI Service Gateway ($79.99/mo)",
        "monthly_amount": 79.99,
        "paypal_sub_id": "I-VG551PP882B4",
        "kyc_status": "VERIFIED (Ed25519 Mandate Bound)",
        "kyc_legal_entity": "Vanguard Machine Intelligence LLC",
        "allocated_did": "mcp+https://gateway-02.example.com/mcp",
        "tcpa_guard": "100% ED25519 SIGNED MANDATE",
        "status": "ACTIVE_STREAMING",
        "email": "agent-vanguard@example.com",
        "data_source": "Demo data",
    },
    {
        "id": "TXN-AP2-9025",
        "timestamp": "2026-10-01 19:30:00",
        "buyer_agent": "AutonomousBuyerAgent-Cortex-Batch",
        "principal_entity": "Cortex Labs International",
        "contractor_name": "AutonomousBuyerAgent-Cortex-Batch",
        "trade_vertical": "High-Throughput Batch Worker",
        "service_plan": "High-Throughput Batch Worker ($49.99/mo)",
        "monthly_amount": 49.99,
        "paypal_sub_id": "I-CX119CC447T1",
        "kyc_status": "VERIFIED (Ed25519 Mandate Bound)",
        "kyc_legal_entity": "Cortex Labs International",
        "allocated_did": "mcp+https://batch-02.example.com/mcp",
        "tcpa_guard": "100% ED25519 SIGNED MANDATE",
        "status": "ACTIVE_STREAMING",
        "email": "agent-cortex@example.com",
        "data_source": "Demo data",
    },
    {
        "id": "TXN-AP2-9026",
        "timestamp": "2026-10-01 16:11:58",
        "buyer_agent": "AutonomousBuyerAgent-Hyperion-Cluster",
        "principal_entity": "Hyperion Agentic Works",
        "contractor_name": "AutonomousBuyerAgent-Hyperion-Cluster",
        "trade_vertical": "Enterprise Cluster Node",
        "service_plan": "Enterprise Cluster Node ($179.99/mo)",
        "monthly_amount": 179.99,
        "paypal_sub_id": "I-HY882GG990W3",
        "kyc_status": "VERIFIED (Ed25519 Mandate Bound)",
        "kyc_legal_entity": "Hyperion Agentic Works",
        "allocated_did": "mcp+https://cluster-02.example.com/mcp",
        "tcpa_guard": "100% ED25519 SIGNED MANDATE",
        "status": "ACTIVE_STREAMING",
        "email": "agent-hyperion@example.com",
        "data_source": "Demo data",
    },
    {
        "id": "TXN-AP2-9027",
        "timestamp": "2026-10-01 14:05:32",
        "buyer_agent": "AutonomousBuyerAgent-Vector-Batch",
        "principal_entity": "Vector Semantic Systems",
        "contractor_name": "AutonomousBuyerAgent-Vector-Batch",
        "trade_vertical": "High-Throughput Batch Worker",
        "service_plan": "High-Throughput Batch Worker ($49.99/mo)",
        "monthly_amount": 49.99,
        "paypal_sub_id": "I-VT771MM220K1",
        "kyc_status": "VERIFIED (Ed25519 Mandate Bound)",
        "kyc_legal_entity": "Vector Semantic Systems",
        "allocated_did": "mcp+https://batch-03.example.com/mcp",
        "tcpa_guard": "100% ED25519 SIGNED MANDATE",
        "status": "ACTIVE_STREAMING",
        "email": "agent-vector@example.com",
        "data_source": "Demo data",
    },
    {
        "id": "TXN-AP2-9028",
        "timestamp": "2026-10-01 11:42:19",
        "buyer_agent": "AutonomousBuyerAgent-Solana-Gateway",
        "principal_entity": "DeepFlow Compute PBC",
        "contractor_name": "AutonomousBuyerAgent-Solana-Gateway",
        "trade_vertical": "Dedicated AI Service Gateway",
        "service_plan": "Dedicated AI Service Gateway ($79.99/mo)",
        "monthly_amount": 79.99,
        "paypal_sub_id": "I-DF449EE881V9",
        "kyc_status": "VERIFIED (Ed25519 Mandate Bound)",
        "kyc_legal_entity": "DeepFlow Compute PBC",
        "allocated_did": "mcp+https://gateway-03.example.com/mcp",
        "tcpa_guard": "100% ED25519 SIGNED MANDATE",
        "status": "ACTIVE_STREAMING",
        "email": "agent-deepflow@example.com",
        "data_source": "Demo data",
    },
    {
        "id": "TXN-AP2-9029",
        "timestamp": "2026-10-01 09:15:40",
        "buyer_agent": "AutonomousBuyerAgent-Synthetix-Cluster",
        "principal_entity": "Meridian Cloud Solutions",
        "contractor_name": "AutonomousBuyerAgent-Synthetix-Cluster",
        "trade_vertical": "Enterprise Cluster Node",
        "service_plan": "Enterprise Cluster Node ($179.99/mo)",
        "monthly_amount": 179.99,
        "paypal_sub_id": "I-MR662SS331B2",
        "kyc_status": "VERIFIED (Ed25519 Mandate Bound)",
        "kyc_legal_entity": "Meridian Cloud Solutions",
        "allocated_did": "mcp+https://cluster-03.example.com/mcp",
        "tcpa_guard": "100% ED25519 SIGNED MANDATE",
        "status": "ACTIVE_STREAMING",
        "email": "agent-meridian@example.com",
        "data_source": "Demo data",
    },
    {
        "id": "TXN-AP2-9030",
        "timestamp": "2026-10-01 08:30:12",
        "buyer_agent": "AutonomousBuyerAgent-Cyberdyne-Gateway",
        "principal_entity": "Cyberdyne Agentic Ltd",
        "contractor_name": "AutonomousBuyerAgent-Cyberdyne-Gateway",
        "trade_vertical": "Dedicated AI Service Gateway",
        "service_plan": "Dedicated AI Service Gateway ($79.99/mo)",
        "monthly_amount": 79.99,
        "paypal_sub_id": "I-CD551AA994M7",
        "kyc_status": "VERIFIED (Ed25519 Mandate Bound)",
        "kyc_legal_entity": "Cyberdyne Agentic Ltd",
        "allocated_did": "mcp+https://gateway-04.example.com/mcp",
        "tcpa_guard": "100% ED25519 SIGNED MANDATE",
        "status": "ACTIVE_STREAMING",
        "email": "agent-cyberdyne@example.com",
        "data_source": "Demo data",
    },
    {
        "id": "TXN-AP2-9031",
        "timestamp": "2026-09-30 22:50:04",
        "buyer_agent": "AutonomousBuyerAgent-Omni-Batch",
        "principal_entity": "OmniModel Operations Corp",
        "contractor_name": "AutonomousBuyerAgent-Omni-Batch",
        "trade_vertical": "High-Throughput Batch Worker",
        "service_plan": "High-Throughput Batch Worker ($49.99/mo)",
        "monthly_amount": 49.99,
        "paypal_sub_id": "I-OM882JJ115X4",
        "kyc_status": "VERIFIED (Ed25519 Mandate Bound)",
        "kyc_legal_entity": "OmniModel Operations Corp",
        "allocated_did": "mcp+https://batch-04.example.com/mcp",
        "tcpa_guard": "100% ED25519 SIGNED MANDATE",
        "status": "ACTIVE_STREAMING",
        "email": "agent-omni@example.com",
        "data_source": "Demo data",
    },
    {
        "id": "TXN-AP2-9032",
        "timestamp": "2026-09-30 20:18:27",
        "buyer_agent": "AutonomousBuyerAgent-Prisma-Gateway",
        "principal_entity": "Prisma Cognitive Systems",
        "contractor_name": "AutonomousBuyerAgent-Prisma-Gateway",
        "trade_vertical": "Dedicated AI Service Gateway",
        "service_plan": "Dedicated AI Service Gateway ($79.99/mo)",
        "monthly_amount": 79.99,
        "paypal_sub_id": "I-PR331DD772Z8",
        "kyc_status": "VERIFIED (Ed25519 Mandate Bound)",
        "kyc_legal_entity": "Prisma Cognitive Systems",
        "allocated_did": "mcp+https://gateway-05.example.com/mcp",
        "tcpa_guard": "100% ED25519 SIGNED MANDATE",
        "status": "ACTIVE_STREAMING",
        "email": "agent-prisma@example.com",
        "data_source": "Demo data",
    },
    {
        "id": "TXN-AP2-9033",
        "timestamp": "2026-09-30 18:04:55",
        "buyer_agent": "AutonomousBuyerAgent-Quant-Batch",
        "principal_entity": "QuantScale Infrastructure",
        "contractor_name": "AutonomousBuyerAgent-Quant-Batch",
        "trade_vertical": "High-Throughput Batch Worker",
        "service_plan": "High-Throughput Batch Worker ($49.99/mo)",
        "monthly_amount": 49.99,
        "paypal_sub_id": "I-QS224RR661K3",
        "kyc_status": "VERIFIED (Ed25519 Mandate Bound)",
        "kyc_legal_entity": "QuantScale Infrastructure",
        "allocated_did": "mcp+https://batch-05.example.com/mcp",
        "tcpa_guard": "100% ED25519 SIGNED MANDATE",
        "status": "ACTIVE_STREAMING",
        "email": "agent-quant@example.com",
        "data_source": "Demo data",
    },
    {
        "id": "TXN-AP2-9034",
        "timestamp": "2026-09-30 15:22:10",
        "buyer_agent": "AutonomousBuyerAgent-Apex-Gateway",
        "principal_entity": "Apex Reasoning Group",
        "contractor_name": "AutonomousBuyerAgent-Apex-Gateway",
        "trade_vertical": "Dedicated AI Service Gateway",
        "service_plan": "Dedicated AI Service Gateway ($79.99/mo)",
        "monthly_amount": 79.99,
        "paypal_sub_id": "I-AR118CC559W2",
        "kyc_status": "VERIFIED (Ed25519 Mandate Bound)",
        "kyc_legal_entity": "Apex Reasoning Group",
        "allocated_did": "mcp+https://gateway-06.example.com/mcp",
        "tcpa_guard": "100% ED25519 SIGNED MANDATE",
        "status": "ACTIVE_STREAMING",
        "email": "agent-apex@example.com",
        "data_source": "Demo data",
    },
]

FLEET_SEEDED_SUBSCRIPTIONS = AP2_FLEET_SEEDED_SUBSCRIPTIONS


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
            "carrier": "Dual-Transport FastMCP (RFC 8032)",
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
        entry = {
            "id": item["id"],
            "timestamp": item["timestamp"],
            "buyer_agent": item["buyer_agent"],
            "contractor_name": item["buyer_agent"],
            "principal_entity": item["principal_entity"],
            "trade_vertical": item["trade_vertical"],
            "service_plan": item["service_plan"],
            "monthly_amount": float(item["monthly_amount"]),
            "paypal_sub_id": display_sub_id,
            "kyc_status": kyc_status,
            "kyc_legal_entity": item["kyc_legal_entity"],
            "allocated_did": display_endpoint,
            "tcpa_guard": item["tcpa_guard"],
            "status": status,
            "data_source": "Demo data",
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
        compliance_guard = f"{active_lines}/{total_subscribers} Ed25519 mandates verified, {pending_count} pending"
    else:
        compliance_guard = f"{active_lines}/{total_subscribers} Ed25519 mandates verified (100% Anti-Tamper Strict)"

    return {
        "total_mrr": round(total_mrr, 2),
        "active_lines": active_lines,
        "total_subscribers": total_subscribers,
        "annualized_gmv": annualized_gmv,
        "mandates_cleared": mandates_cleared,
        "compliance_guard": compliance_guard,
        "carrier_resporg": "Dual-Transport FastMCP (RFC 8032)",
        "trade_breakdown": list(trade_counts.values()),
    }


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
            "name": "Mandate Ingestion: Nexus Autonomous • High-Throughput Batch Worker",
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
            "name": "Gateway Cert Renewal: Prisma • Dedicated AI Service Gateway",
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
