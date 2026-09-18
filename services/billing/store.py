"""SQLite persistence with an atomic inbox/effects/ledger transaction."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from .errors import InsufficientCredits, OrderConflict, UnknownOrder
from .models import AuditRecord, CreateOrder, Entitlement, InboxRecord, NormalizedEvent, Order, ProcessingResult


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SQLiteBillingStore:
    """Durable store; one connection and a write lock make local SQLite safe."""

    def __init__(self, database: str) -> None:
        self._connection = sqlite3.connect(database, check_same_thread=False, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    def _create_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS billing_orders (
                order_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, account_id TEXT NOT NULL,
                plan_id TEXT NOT NULL, amount_minor INTEGER NOT NULL, currency TEXT NOT NULL,
                credit_grant INTEGER NOT NULL, idempotency_key TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL, provider TEXT, provider_reference TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS provider_inbox (
                provider TEXT NOT NULL, provider_event_id TEXT NOT NULL, idempotency_key TEXT NOT NULL,
                raw_body BLOB NOT NULL, headers_json TEXT NOT NULL, normalized_json TEXT NOT NULL,
                status TEXT NOT NULL, applied INTEGER NOT NULL DEFAULT 0, received_at TEXT NOT NULL,
                PRIMARY KEY (provider, provider_event_id), UNIQUE (provider, idempotency_key)
            );
            CREATE TABLE IF NOT EXISTS entitlements (
                account_id TEXT PRIMARY KEY, plan TEXT NOT NULL, version INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS credit_accounts (
                account_id TEXT PRIMARY KEY, balance INTEGER NOT NULL DEFAULT 0 CHECK (balance >= 0)
            );
            CREATE TABLE IF NOT EXISTS credit_ledger (
                entry_id TEXT PRIMARY KEY, account_id TEXT NOT NULL, amount INTEGER NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE, reason TEXT NOT NULL, balance_after INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS billing_audit (
                event_id TEXT PRIMARY KEY, action TEXT NOT NULL, target_id TEXT NOT NULL,
                before_json TEXT NOT NULL, after_json TEXT NOT NULL, occurred_at TEXT NOT NULL
            );
            """
        )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def create_pending_order(self, order: CreateOrder, *, provider: str) -> Order:
        with self._transaction():
            existing = self._connection.execute(
                "SELECT * FROM billing_orders WHERE idempotency_key = ?", (order.idempotency_key,)
            ).fetchone()
            if existing:
                if existing["order_id"] != order.order_id:
                    raise OrderConflict("order idempotency key is already used")
                return self._to_order(existing)
            now = _now()
            self._connection.execute(
                "INSERT INTO billing_orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, NULL, ?, ?)",
                (order.order_id, order.tenant_id, order.account_id, order.plan_id, order.amount_minor,
                 order.currency, order.credit_grant, order.idempotency_key, provider, now, now),
            )
            return self._to_order(self._connection.execute("SELECT * FROM billing_orders WHERE order_id = ?", (order.order_id,)).fetchone())

    def attach_checkout(self, order_id: str, provider: str, provider_reference: str) -> Order:
        with self._transaction():
            self._connection.execute(
                "UPDATE billing_orders SET provider = ?, provider_reference = ?, updated_at = ? WHERE order_id = ?",
                (provider, provider_reference, _now(), order_id),
            )
            return self._to_order(self._connection.execute("SELECT * FROM billing_orders WHERE order_id = ?", (order_id,)).fetchone())

    def order(self, order_id: str) -> Order:
        row = self._connection.execute("SELECT * FROM billing_orders WHERE order_id = ?", (order_id,)).fetchone()
        if row is None:
            raise UnknownOrder(order_id)
        return self._to_order(row)

    def process_event(self, event: NormalizedEvent, raw_body: bytes, headers: dict[str, str]) -> ProcessingResult:
        with self._transaction():
            duplicate = self._connection.execute(
                "SELECT applied, status FROM provider_inbox WHERE provider = ? AND (provider_event_id = ? OR idempotency_key = ?)",
                (event.provider, event.provider_event_id, event.idempotency_key),
            ).fetchone()
            if duplicate is not None:
                return ProcessingResult(event.provider, event.provider_event_id, False, duplicate["status"])
            order_row = self._connection.execute("SELECT * FROM billing_orders WHERE order_id = ?", (event.order_id,)).fetchone()
            if order_row is None:
                raise UnknownOrder(event.order_id)
            if event.amount_minor is not None and event.amount_minor != order_row["amount_minor"]:
                raise OrderConflict("provider amount does not match the pending order")
            self._connection.execute(
                "INSERT INTO provider_inbox VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)",
                (event.provider, event.provider_event_id, event.idempotency_key, raw_body,
                 json.dumps(headers, sort_keys=True), json.dumps(event.as_dict(), sort_keys=True), "received", _now()),
            )
            before = self._to_order(order_row)
            applied = False
            if event.status == "succeeded" and before.status in {"pending", "unknown"}:
                self._connection.execute(
                    "UPDATE billing_orders SET status = 'succeeded', updated_at = ? WHERE order_id = ? AND status IN ('pending', 'unknown')",
                    (_now(), event.order_id),
                )
                self._connection.execute(
                    "INSERT INTO entitlements(account_id, plan, version) VALUES (?, ?, 1) "
                    "ON CONFLICT(account_id) DO UPDATE SET plan = excluded.plan, version = entitlements.version + 1",
                    (before.account_id, before.plan_id),
                )
                self._connection.execute(
                    "INSERT OR IGNORE INTO credit_accounts(account_id, balance) VALUES (?, 0)", (before.account_id,)
                )
                ledger_key = f"{event.provider}:{event.idempotency_key}:grant"
                cursor = self._connection.execute(
                    "INSERT OR IGNORE INTO credit_ledger VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (uuid.uuid4().hex, before.account_id, before.credit_grant, ledger_key,
                     f"payment {event.order_id}", 0, _now()),
                )
                if cursor.rowcount:
                    updated = self._connection.execute(
                        "UPDATE credit_accounts SET balance = balance + ? "
                        "WHERE account_id = ? AND balance + ? >= 0",
                        (before.credit_grant, before.account_id, before.credit_grant),
                    )
                    if updated.rowcount != 1:
                        raise InsufficientCredits(before.account_id)
                    new_balance = self._connection.execute(
                        "SELECT balance FROM credit_accounts WHERE account_id = ?", (before.account_id,)
                    ).fetchone()["balance"]
                    self._connection.execute(
                        "UPDATE credit_ledger SET balance_after = ? WHERE entry_id = (SELECT entry_id FROM credit_ledger WHERE idempotency_key = ?)",
                        (new_balance, ledger_key),
                    )
                after = self._to_order(self._connection.execute("SELECT * FROM billing_orders WHERE order_id = ?", (event.order_id,)).fetchone())
                self._audit("billing.payment.succeeded", before.account_id, {"status": before.status}, {"status": after.status, "credits": before.credit_grant})
                applied = True
            elif event.status == "refunded" and before.status == "succeeded":
                self._connection.execute(
                    "UPDATE billing_orders SET status = 'refunded', updated_at = ? WHERE order_id = ? AND status = 'succeeded'",
                    (_now(), event.order_id),
                )
                self._connection.execute(
                    "INSERT INTO entitlements(account_id, plan, version) VALUES (?, 'free', 1) "
                    "ON CONFLICT(account_id) DO UPDATE SET plan = 'free', version = entitlements.version + 1",
                    (before.account_id,),
                )
                self._connection.execute(
                    "INSERT OR IGNORE INTO credit_accounts(account_id, balance) VALUES (?, 0)", (before.account_id,)
                )
                ledger_key = f"{event.provider}:{event.idempotency_key}:refund"
                cursor = self._connection.execute(
                    "INSERT OR IGNORE INTO credit_ledger VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (uuid.uuid4().hex, before.account_id, -before.credit_grant, ledger_key,
                     f"refund {event.order_id}", 0, _now()),
                )
                if cursor.rowcount:
                    updated = self._connection.execute(
                        "UPDATE credit_accounts SET balance = balance - ? "
                        "WHERE account_id = ? AND balance - ? >= 0",
                        (before.credit_grant, before.account_id, before.credit_grant),
                    )
                    if updated.rowcount != 1:
                        raise InsufficientCredits(before.account_id)
                    new_balance = self._connection.execute(
                        "SELECT balance FROM credit_accounts WHERE account_id = ?", (before.account_id,)
                    ).fetchone()["balance"]
                    self._connection.execute(
                        "UPDATE credit_ledger SET balance_after = ? WHERE entry_id = (SELECT entry_id FROM credit_ledger WHERE idempotency_key = ?)",
                        (new_balance, ledger_key),
                    )
                after = self._to_order(self._connection.execute("SELECT * FROM billing_orders WHERE order_id = ?", (event.order_id,)).fetchone())
                self._audit("billing.payment.refunded", before.account_id, {"status": before.status, "plan": before.plan_id}, {"status": after.status, "plan": "free", "credits": -before.credit_grant})
                applied = True
            else:
                self._connection.execute(
                    "UPDATE billing_orders SET status = ?, updated_at = ? WHERE order_id = ? AND status = 'pending'",
                    (event.status, _now(), event.order_id),
                )
            self._connection.execute(
                "UPDATE provider_inbox SET status = ?, applied = 1 WHERE provider = ? AND provider_event_id = ?",
                (event.status, event.provider, event.provider_event_id),
            )
            return ProcessingResult(event.provider, event.provider_event_id, applied, event.status)

    def balance(self, account_id: str) -> int:
        row = self._connection.execute("SELECT balance FROM credit_accounts WHERE account_id = ?", (account_id,)).fetchone()
        return 0 if row is None else int(row["balance"])

    def entitlement(self, account_id: str) -> Entitlement:
        row = self._connection.execute("SELECT * FROM entitlements WHERE account_id = ?", (account_id,)).fetchone()
        if row is None:
            return Entitlement(account_id, "free", 0)
        return Entitlement(account_id, row["plan"], row["version"])

    def inbox(self) -> tuple[InboxRecord, ...]:
        rows = self._connection.execute("SELECT * FROM provider_inbox ORDER BY received_at").fetchall()
        return tuple(InboxRecord(row["provider"], row["provider_event_id"], row["idempotency_key"], row["status"], bool(row["applied"])) for row in rows)

    def audit_events(self) -> tuple[AuditRecord, ...]:
        rows = self._connection.execute("SELECT * FROM billing_audit ORDER BY occurred_at").fetchall()
        return tuple(AuditRecord(row["event_id"], row["action"], row["target_id"], json.loads(row["before_json"]), json.loads(row["after_json"])) for row in rows)

    def _audit(self, action: str, target_id: str, before: dict[str, object], after: dict[str, object]) -> None:
        self._connection.execute(
            "INSERT INTO billing_audit VALUES (?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, action, target_id, json.dumps(before, sort_keys=True), json.dumps(after, sort_keys=True), _now()),
        )

    def _transaction(self):
        return _Transaction(self._connection, self._lock)

    @staticmethod
    def _to_order(row: sqlite3.Row) -> Order:
        return Order(row["order_id"], row["tenant_id"], row["account_id"], row["plan_id"], row["amount_minor"], row["currency"], row["credit_grant"], row["idempotency_key"], row["status"], row["provider"], row["provider_reference"])


class _Transaction:
    def __init__(self, connection: sqlite3.Connection, lock: threading.RLock) -> None:
        self._connection = connection
        self._lock = lock

    def __enter__(self) -> "_Transaction":
        self._lock.acquire()
        self._connection.execute("BEGIN IMMEDIATE")
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        try:
            self._connection.execute("ROLLBACK" if exc_type else "COMMIT")
        finally:
            self._lock.release()
