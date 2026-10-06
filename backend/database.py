"""
Persistent SQLite Database Engine for FieldSmith Pro A2A Commerce.
Survives process restarts across subscriptions, mandates, ledger commitments,
processed webhook event IDs, and registered buyer public keys.
Thread-safe with SQLite WAL mode and busy_timeout=5000ms.
Conforms to SPEC-001 v1.4.1 and Milestone M-032 Criterion 1.
"""

import os
import json
import time
import sqlite3
import datetime
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Set, Iterator
from collections.abc import MutableMapping, MutableSet

from .config import settings, get_db_path

logger = logging.getLogger("a2a_database")

_DEFAULT_BUYER_KIDS = {
    "marcus-buyer-ed25519-v1",
    "fieldsmith-seller-ed25519-v1",
    "buyer-agent-01",
    "marcus-buyer",
    "claude-desktop-buyer",
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
                carrier TEXT DEFAULT 'Telnyx',
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
            """)

            # Seed default buyer keys if table is empty
            cur = conn.cursor()
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
                        (kid, buyer_pub, "marcus@millercustomfloors.com", "Miller Custom Flooring LLC", now_iso),
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
                    sub.get("tier_id", "solo-starter"),
                    float(sub.get("agreed_monthly_rate") or 0.0),
                    sub.get("plan_id"),
                    sub.get("buyer_agent_id"),
                    sub.get("subscriber_country_code", "US"),
                    sub.get("assigned_did"),
                    sub.get("carrier", "Telnyx"),
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
    db_path: Optional[Path] = None,
) -> None:
    """Registers a buyer agent's Ed25519 public key."""
    if not kid or not public_key_hex:
        return
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO buyer_keys (kid, public_key_hex, contractor_email, business_name, registered_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(kid) DO UPDATE SET
                    public_key_hex = excluded.public_key_hex,
                    contractor_email = COALESCE(excluded.contractor_email, buyer_keys.contractor_email),
                    business_name = COALESCE(excluded.business_name, buyer_keys.business_name),
                    registered_at = excluded.registered_at
                """,
                (kid.strip(), public_key_hex.strip().lower(), contractor_email, business_name, now_iso),
            )
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


def list_buyer_keys(db_path: Optional[Path] = None) -> Dict[str, str]:
    """Returns a dictionary of all registered buyer keys (kid -> hex)."""
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT kid, public_key_hex FROM buyer_keys")
        return {r["kid"]: r["public_key_hex"] for r in cur.fetchall()}
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
            conn.execute("DELETE FROM agent_spends")
            conn.execute("DELETE FROM spend_history")
            conn.execute("DELETE FROM processed_webhooks")
    finally:
        conn.close()


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
        register_buyer_key(kid, public_key_hex, db_path=self._db_path)

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
