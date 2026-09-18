"""Durable credit reservations used by agent runs.

Reservations are held separately from the spendable balance.  Every mutation
is keyed and transactional, so retrying a workflow cannot reserve or commit
the same credits twice.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

from services.billing.errors import InsufficientCredits


class ReservationConflict(ValueError):
    """An idempotency key was reused for a different reservation."""


@dataclass(frozen=True)
class CreditReservation:
    reservation_id: str
    tenant_id: str
    account_id: str
    run_id: str
    units: int
    idempotency_key: str
    status: str


@dataclass(frozen=True)
class CreditCommit:
    reservation_id: str
    account_id: str
    used_units: int
    idempotency_key: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SQLiteCreditLedger:
    """SQLite implementation of the metering-billing reservation port."""

    def __init__(self, database: str, *, initial_balances: Mapping[str, int] | None = None) -> None:
        self._connection = sqlite3.connect(database, check_same_thread=False, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS credit_accounts (
                account_id TEXT PRIMARY KEY,
                balance INTEGER NOT NULL CHECK (balance >= 0)
            );
            CREATE TABLE IF NOT EXISTS run_credit_reservations (
                reservation_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                units INTEGER NOT NULL CHECK (units > 0),
                idempotency_key TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL CHECK (status IN ('reserved', 'committed', 'released')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS run_credit_ledger (
                entry_id TEXT PRIMARY KEY,
                reservation_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                amount INTEGER NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        for account_id, balance in (initial_balances or {}).items():
            if not isinstance(balance, int) or isinstance(balance, bool) or balance < 0:
                raise ValueError("initial credit balances must be non-negative integers")
            self._connection.execute(
                "INSERT INTO credit_accounts(account_id, balance) VALUES (?, ?) "
                "ON CONFLICT(account_id) DO NOTHING",
                (account_id, balance),
            )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def reserve(
        self,
        tenant_id: str,
        account_id: str,
        run_id: str,
        units: int,
        *,
        idempotency_key: str,
    ) -> CreditReservation:
        if not all(isinstance(value, str) and value.strip() for value in (tenant_id, account_id, run_id, idempotency_key)):
            raise ValueError("reservation identity fields must be non-empty")
        if not isinstance(units, int) or isinstance(units, bool) or units <= 0:
            raise ValueError("reservation units must be a positive integer")
        with self._transaction():
            existing = self._connection.execute(
                "SELECT * FROM run_credit_reservations WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if existing is not None:
                if tuple(existing[key] for key in ("tenant_id", "account_id", "run_id", "units")) != (
                    tenant_id,
                    account_id,
                    run_id,
                    units,
                ):
                    raise ReservationConflict("reservation idempotency key is already used")
                return self._reservation(existing)

            account = self._connection.execute(
                "SELECT balance FROM credit_accounts WHERE account_id = ?", (account_id,)
            ).fetchone()
            if account is None:
                raise InsufficientCredits(account_id)
            held = self._connection.execute(
                "SELECT COALESCE(SUM(units), 0) AS units FROM run_credit_reservations "
                "WHERE account_id = ? AND status = 'reserved'",
                (account_id,),
            ).fetchone()["units"]
            if int(account["balance"]) - int(held) < units:
                raise InsufficientCredits(account_id)
            now = _now()
            reservation_id = f"reservation-{uuid.uuid4().hex}"
            self._connection.execute(
                "INSERT INTO run_credit_reservations VALUES (?, ?, ?, ?, ?, ?, 'reserved', ?, ?)",
                (reservation_id, tenant_id, account_id, run_id, units, idempotency_key, now, now),
            )
            return self._reservation(
                self._connection.execute(
                    "SELECT * FROM run_credit_reservations WHERE reservation_id = ?", (reservation_id,)
                ).fetchone()
            )

    def release(self, reservation_id: str, *, idempotency_key: str) -> CreditReservation:
        with self._transaction():
            row = self._connection.execute(
                "SELECT * FROM run_credit_reservations WHERE reservation_id = ?", (reservation_id,)
            ).fetchone()
            if row is None:
                raise KeyError(reservation_id)
            if row["status"] == "committed":
                return self._reservation(row)
            if row["status"] == "released":
                return self._reservation(row)
            self._connection.execute(
                "UPDATE run_credit_reservations SET status = 'released', updated_at = ? WHERE reservation_id = ?",
                (_now(), reservation_id),
            )
            return self._reservation(
                self._connection.execute(
                    "SELECT * FROM run_credit_reservations WHERE reservation_id = ?", (reservation_id,)
                ).fetchone()
            )

    def commit(self, reservation_id: str, used_units: int, *, idempotency_key: str) -> CreditCommit:
        if not isinstance(used_units, int) or isinstance(used_units, bool) or used_units < 0:
            raise ValueError("used units must be a non-negative integer")
        with self._transaction():
            row = self._connection.execute(
                "SELECT * FROM run_credit_reservations WHERE reservation_id = ?", (reservation_id,)
            ).fetchone()
            if row is None:
                raise KeyError(reservation_id)
            existing = self._connection.execute(
                "SELECT * FROM run_credit_ledger WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if existing is not None:
                if existing["reservation_id"] != reservation_id or existing["amount"] != -used_units:
                    raise ReservationConflict("commit idempotency key is already used")
                return CreditCommit(reservation_id, existing["account_id"], used_units, idempotency_key)
            if row["status"] == "released":
                raise ReservationConflict("released reservation cannot be committed")
            if used_units > row["units"]:
                raise ValueError("actual usage exceeds the reserved units")
            if row["status"] == "committed":
                raise ReservationConflict("reservation was committed with another key")
            updated = self._connection.execute(
                "UPDATE credit_accounts SET balance = balance - ? "
                "WHERE account_id = ? AND balance >= ?",
                (used_units, row["account_id"], used_units),
            )
            if updated.rowcount != 1:
                raise InsufficientCredits(row["account_id"])
            self._connection.execute(
                "INSERT INTO run_credit_ledger VALUES (?, ?, ?, ?, ?, ?, ?)",
                (uuid.uuid4().hex, reservation_id, row["account_id"], -used_units, idempotency_key, "run usage", _now()),
            )
            self._connection.execute(
                "UPDATE run_credit_reservations SET status = 'committed', updated_at = ? WHERE reservation_id = ?",
                (_now(), reservation_id),
            )
            return CreditCommit(reservation_id, row["account_id"], used_units, idempotency_key)

    def available(self, account_id: str) -> int:
        account = self._connection.execute(
            "SELECT balance FROM credit_accounts WHERE account_id = ?", (account_id,)
        ).fetchone()
        if account is None:
            return 0
        held = self._connection.execute(
            "SELECT COALESCE(SUM(units), 0) AS units FROM run_credit_reservations "
            "WHERE account_id = ? AND status = 'reserved'",
            (account_id,),
        ).fetchone()["units"]
        return int(account["balance"]) - int(held)

    def reservations(self) -> tuple[CreditReservation, ...]:
        rows = self._connection.execute("SELECT * FROM run_credit_reservations ORDER BY created_at").fetchall()
        return tuple(self._reservation(row) for row in rows)

    def commits(self) -> tuple[CreditCommit, ...]:
        rows = self._connection.execute(
            "SELECT reservation_id, account_id, amount, idempotency_key FROM run_credit_ledger ORDER BY created_at"
        ).fetchall()
        return tuple(CreditCommit(row["reservation_id"], row["account_id"], -int(row["amount"]), row["idempotency_key"]) for row in rows)

    @staticmethod
    def _reservation(row: sqlite3.Row) -> CreditReservation:
        return CreditReservation(
            row["reservation_id"], row["tenant_id"], row["account_id"], row["run_id"],
            int(row["units"]), row["idempotency_key"], row["status"],
        )

    def _transaction(self):
        return _Transaction(self._connection, self._lock)


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
