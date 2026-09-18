"""Durable, fail-closed run admission counters for cost-tier profiles."""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Callable, Protocol


class QuotaExceeded(RuntimeError):
    """A run must pause until the current quota window changes."""

    def __init__(self, dimension: str, limit: int) -> None:
        if dimension not in {"runs", "units"}:
            raise ValueError("unsupported quota dimension")
        self.dimension = dimension
        self.limit = limit
        super().__init__(f"{dimension} quota limit reached ({limit})")


@dataclass(frozen=True)
class QuotaPolicy:
    max_runs: int = 10
    max_units: int = 100
    period_seconds: int = 86400

    def __post_init__(self) -> None:
        for name in ("max_runs", "max_units", "period_seconds"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if self.max_runs > 1_000_000 or self.max_units > 10_000_000 or self.period_seconds > 31_536_000:
            raise ValueError("quota policy exceeds the low-cost safety ceiling")


@dataclass(frozen=True)
class QuotaSnapshot:
    scope_id: str
    period_key: int
    run_count: int
    unit_count: int
    max_runs: int
    max_units: int


class QuotaCounterPort(Protocol):
    def reserve(self, scope_id: str, run_id: str, units: int) -> QuotaSnapshot:
        ...

    def release(self, run_id: str) -> None:
        ...


class SQLiteQuotaCounter:
    """Atomically count admitted runs and requested units per scope/window.

    Admission is keyed by ``run_id``. Retrying the same run is a no-op, while
    a new run that would exceed either limit is rejected before credit
    reservation and can be represented as a durable ``quota_paused`` run.
    """

    def __init__(
        self,
        database: str,
        *,
        policy: QuotaPolicy | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.policy = policy or QuotaPolicy()
        self._clock = clock
        self._connection = sqlite3.connect(database, check_same_thread=False, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS quota_buckets (
                scope_id TEXT NOT NULL,
                period_key INTEGER NOT NULL,
                run_count INTEGER NOT NULL CHECK (run_count >= 0),
                unit_count INTEGER NOT NULL CHECK (unit_count >= 0),
                PRIMARY KEY (scope_id, period_key)
            );
            CREATE TABLE IF NOT EXISTS quota_admissions (
                run_id TEXT PRIMARY KEY,
                scope_id TEXT NOT NULL,
                period_key INTEGER NOT NULL,
                units INTEGER NOT NULL CHECK (units > 0),
                status TEXT NOT NULL CHECK (status IN ('counted', 'released'))
            );
            """
        )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def reserve(self, scope_id: str, run_id: str, units: int) -> QuotaSnapshot:
        if not isinstance(scope_id, str) or not scope_id.strip() or not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("quota scope and run identity must be non-empty")
        if not isinstance(units, int) or isinstance(units, bool) or units <= 0:
            raise ValueError("quota units must be a positive integer")
        period_key = self._period_key()
        with self._transaction():
            existing = self._connection.execute(
                "SELECT * FROM quota_admissions WHERE run_id = ?", (run_id,)
            ).fetchone()
            if existing is not None:
                if (
                    existing["scope_id"], int(existing["period_key"]), int(existing["units"]), existing["status"]
                ) != (scope_id, period_key, units, "counted"):
                    raise ValueError("quota run identity was reused with different admission data")
                return self.snapshot(scope_id)

            bucket = self._bucket(scope_id, period_key)
            if int(bucket["run_count"]) + 1 > self.policy.max_runs:
                raise QuotaExceeded("runs", self.policy.max_runs)
            if int(bucket["unit_count"]) + units > self.policy.max_units:
                raise QuotaExceeded("units", self.policy.max_units)
            self._connection.execute(
                "UPDATE quota_buckets SET run_count = run_count + 1, unit_count = unit_count + ? "
                "WHERE scope_id = ? AND period_key = ?",
                (units, scope_id, period_key),
            )
            self._connection.execute(
                "INSERT INTO quota_admissions(run_id, scope_id, period_key, units, status) "
                "VALUES (?, ?, ?, ?, 'counted')",
                (run_id, scope_id, period_key, units),
            )
            return self.snapshot(scope_id)

    def release(self, run_id: str) -> None:
        """Undo an admission that failed before credit reservation/dispatch."""

        with self._transaction():
            admission = self._connection.execute(
                "SELECT * FROM quota_admissions WHERE run_id = ?", (run_id,)
            ).fetchone()
            if admission is None or admission["status"] == "released":
                return
            self._connection.execute(
                "UPDATE quota_buckets SET run_count = run_count - 1, unit_count = unit_count - ? "
                "WHERE scope_id = ? AND period_key = ?",
                (int(admission["units"]), admission["scope_id"], int(admission["period_key"])),
            )
            self._connection.execute(
                "UPDATE quota_admissions SET status = 'released' WHERE run_id = ?", (run_id,)
            )

    def snapshot(self, scope_id: str) -> QuotaSnapshot:
        period_key = self._period_key()
        bucket = self._bucket(scope_id, period_key)
        return QuotaSnapshot(
            scope_id,
            period_key,
            int(bucket["run_count"]),
            int(bucket["unit_count"]),
            self.policy.max_runs,
            self.policy.max_units,
        )

    def _period_key(self) -> int:
        return int(self._clock() // self.policy.period_seconds)

    def _bucket(self, scope_id: str, period_key: int) -> sqlite3.Row:
        self._connection.execute(
            "INSERT INTO quota_buckets(scope_id, period_key, run_count, unit_count) "
            "VALUES (?, ?, 0, 0) ON CONFLICT(scope_id, period_key) DO NOTHING",
            (scope_id, period_key),
        )
        row = self._connection.execute(
            "SELECT * FROM quota_buckets WHERE scope_id = ? AND period_key = ?",
            (scope_id, period_key),
        ).fetchone()
        if row is None:
            raise RuntimeError("quota bucket was not created")
        return row

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
