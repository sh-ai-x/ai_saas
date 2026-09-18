"""Durable run state, event, and checkpoint persistence."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from .errors import IdempotencyConflict, InvalidTransition, RunNotFound, TenantMismatch
from .models import Checkpoint, Run, RunCreate, RunEvent, RunState

_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"running", "failed", "cancelled", "quota_paused"}),
    "running": frozenset({"waiting_approval", "completed", "failed", "cancelled"}),
    "waiting_approval": frozenset({"running", "failed", "cancelled"}),
    "quota_paused": frozenset({"queued", "cancelled"}),
    "failed": frozenset({"queued"}),
    "completed": frozenset(),
    "cancelled": frozenset(),
}


def redact_text(value: str) -> str:
    """Remove common secret/payment shapes before a value enters events."""

    patterns = (
        (r"(?i)(sk-[A-Za-z0-9_-]+)", "[REDACTED_KEY]"),
        (r"(?i)(password|passwd|secret|token|api[_-]?key|card(?:_number)?)[=:][^,;\s}]+", r"\1=[REDACTED]"),
        (r"(?i)card=\d+", "card=[REDACTED]"),
    )
    result = value
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result)
    return result


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact_state(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {key: _redact_state(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_redact_state(child) for child in value]
    return value


class SQLiteRunStore:
    def __init__(self, database: str) -> None:
        self._connection = sqlite3.connect(database, check_same_thread=False, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                trace_id TEXT NOT NULL,
                input_json TEXT NOT NULL,
                request_hash TEXT NOT NULL,
                state TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                reservation_id TEXT,
                cancel_requested INTEGER NOT NULL DEFAULT 0,
                worker_attempt INTEGER NOT NULL DEFAULT 0,
                max_steps INTEGER NOT NULL,
                max_model_calls INTEGER NOT NULL,
                max_runtime_seconds REAL NOT NULL,
                result_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(tenant_id, idempotency_key)
            );
            CREATE TABLE IF NOT EXISTS run_events (
                event_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                event TEXT NOT NULL,
                data_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(run_id, sequence)
            );
            CREATE TABLE IF NOT EXISTS run_checkpoints (
                run_id TEXT PRIMARY KEY,
                step INTEGER NOT NULL,
                state_json TEXT NOT NULL,
                inflight_key TEXT,
                approval_id TEXT,
                usage_units INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def create(self, run_id: str, request: RunCreate) -> tuple[Run, bool]:
        with self._transaction():
            existing = self._connection.execute(
                "SELECT * FROM runs WHERE tenant_id = ? AND idempotency_key = ?",
                (request.tenant_id, request.idempotency_key),
            ).fetchone()
            if existing is not None:
                if existing["request_hash"] != request.fingerprint:
                    raise IdempotencyConflict("run idempotency key was reused with different input")
                return self._to_run(existing), False
            now = _now()
            self._connection.execute(
                "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', 1, NULL, 0, 0, ?, ?, ?, '{}', ?, ?)",
                (
                    run_id,
                    request.tenant_id,
                    request.account_id,
                    request.project_id,
                    request.idempotency_key,
                    request.trace_id,
                    json.dumps(dict(request.input), sort_keys=True, separators=(",", ":")),
                    request.fingerprint,
                    request.max_steps,
                    request.max_model_calls,
                    request.max_runtime_seconds,
                    now,
                    now,
                ),
            )
            self._append_event_locked(
                run_id, request.tenant_id, 1, "run.state_changed",
                {"state": "queued", "trace_id": request.trace_id},
            )
            row = self._connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            return self._to_run(row), True

    def get(self, run_id: str, tenant_id: str | None = None) -> Run:
        row = self._connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise RunNotFound(run_id)
        if tenant_id is not None and row["tenant_id"] != tenant_id:
            raise TenantMismatch(run_id)
        return self._to_run(row)

    def attach_reservation(self, run_id: str, reservation_id: str) -> Run:
        with self._transaction():
            row = self._row_locked(run_id)
            if row["reservation_id"] not in (None, reservation_id):
                raise IdempotencyConflict("run already has a different reservation")
            self._connection.execute(
                "UPDATE runs SET reservation_id = ?, updated_at = ? WHERE run_id = ?",
                (reservation_id, _now(), run_id),
            )
            return self._to_run(self._row_locked(run_id))

    def claim(self, run_id: str) -> Run:
        with self._transaction():
            row = self._row_locked(run_id)
            if row["state"] not in {"queued", "running"}:
                return self._to_run(row)
            self._connection.execute(
                "UPDATE runs SET state = 'running', worker_attempt = worker_attempt + 1, updated_at = ? WHERE run_id = ?",
                (_now(), run_id),
            )
            if row["state"] == "queued":
                self._append_event_locked(
                    run_id, row["tenant_id"], row["sequence"] + 1, "run.state_changed",
                    {
                        "state": "running",
                        "trace_id": row["trace_id"],
                        "worker_attempt": int(row["worker_attempt"]) + 1,
                    },
                )
                self._connection.execute("UPDATE runs SET sequence = sequence + 1 WHERE run_id = ?", (run_id,))
            return self._to_run(self._row_locked(run_id))

    def transition(self, run_id: str, state: RunState, *, payload: Mapping[str, Any] | None = None) -> Run:
        with self._transaction():
            row = self._row_locked(run_id)
            previous = row["state"]
            if state not in _TRANSITIONS[previous]:
                raise InvalidTransition(f"{previous} -> {state} is not allowed")
            sequence = int(row["sequence"]) + 1
            event_payload = {"state": state, "trace_id": row["trace_id"], **dict(payload or {})}
            self._append_event_locked(run_id, row["tenant_id"], sequence, "run.state_changed", event_payload)
            self._connection.execute(
                "UPDATE runs SET state = ?, sequence = ?, updated_at = ? WHERE run_id = ?",
                (state, sequence, _now(), run_id),
            )
            return self._to_run(self._row_locked(run_id))

    def mark_cancel_requested(self, run_id: str, tenant_id: str) -> Run:
        with self._transaction():
            row = self._row_locked(run_id)
            if row["tenant_id"] != tenant_id:
                raise TenantMismatch(run_id)
            if row["state"] in {"completed", "failed", "cancelled"}:
                return self._to_run(row)
            if row["state"] in {"queued", "waiting_approval"}:
                return self._transition_locked(row, "cancelled", {"reason": "user_cancelled"})
            sequence = int(row["sequence"]) + 1
            self._append_event_locked(
                run_id, tenant_id, sequence, "run.state_changed",
                {"state": "running", "trace_id": row["trace_id"], "cancellation_requested": True},
            )
            self._connection.execute(
                "UPDATE runs SET cancel_requested = 1, sequence = ?, updated_at = ? WHERE run_id = ?",
                (sequence, _now(), run_id),
            )
            return self._to_run(self._row_locked(run_id))

    def approve(self, run_id: str, tenant_id: str) -> Run:
        with self._transaction():
            row = self._row_locked(run_id)
            if row["tenant_id"] != tenant_id:
                raise TenantMismatch(run_id)
            return self._transition_locked(row, "running", {"approval": "granted"})

    def fail(self, run_id: str, reason: str) -> Run:
        safe_reason = redact_text(reason)[:160]
        return self.transition(run_id, "failed", payload={"reason": safe_reason})

    def pause_quota(self, run_id: str, *, dimension: str, limit: int) -> Run:
        if dimension not in {"runs", "units"}:
            raise ValueError("unsupported quota dimension")
        return self.transition(
            run_id,
            "quota_paused",
            payload={"reason": "quota_limit", "dimension": dimension, "limit": limit},
        )

    def save_checkpoint(
        self,
        run_id: str,
        *,
        step: int,
        state: Mapping[str, Any],
        inflight_key: str | None,
        approval_id: str | None,
        usage_units: int,
    ) -> Checkpoint:
        safe_state = {key: _redact_state(value) for key, value in state.items()}
        with self._transaction():
            self._row_locked(run_id)
            self._connection.execute(
                "INSERT INTO run_checkpoints VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(run_id) DO UPDATE SET step = excluded.step, state_json = excluded.state_json, "
                "inflight_key = excluded.inflight_key, approval_id = excluded.approval_id, "
                "usage_units = excluded.usage_units, updated_at = excluded.updated_at",
                (run_id, step, json.dumps(safe_state, sort_keys=True), inflight_key, approval_id, usage_units, _now()),
            )
            return Checkpoint(run_id, step, safe_state, inflight_key, approval_id, usage_units)

    def checkpoint(self, run_id: str) -> Checkpoint | None:
        row = self._connection.execute("SELECT * FROM run_checkpoints WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        return Checkpoint(run_id, int(row["step"]), json.loads(row["state_json"]), row["inflight_key"], row["approval_id"], int(row["usage_units"]))

    def append_token(self, run_id: str, text: str) -> RunEvent:
        safe = redact_text(text)
        with self._transaction():
            row = self._row_locked(run_id)
            sequence = int(row["sequence"]) + 1
            event = self._append_event_locked(
                run_id, row["tenant_id"], sequence, "run.token",
                {"text": safe, "trace_id": row["trace_id"]},
            )
            checkpoint = self._connection.execute(
                "SELECT state_json FROM run_checkpoints WHERE run_id = ?", (run_id,)
            ).fetchone()
            if checkpoint is not None:
                state = json.loads(checkpoint["state_json"])
                state["token_emitted"] = True
                self._connection.execute(
                    "UPDATE run_checkpoints SET state_json = ?, updated_at = ? WHERE run_id = ?",
                    (json.dumps(state, sort_keys=True), _now(), run_id),
                )
            self._connection.execute("UPDATE runs SET sequence = ?, updated_at = ? WHERE run_id = ?", (sequence, _now(), run_id))
            return event

    def complete(self, run_id: str, *, usage_units: int) -> Run:
        with self._transaction():
            row = self._row_locked(run_id)
            if row["state"] != "running":
                raise InvalidTransition(f"{row['state']} -> completed is not allowed")
            sequence = int(row["sequence"]) + 1
            self._append_event_locked(
                run_id, row["tenant_id"], sequence, "run.completed",
                {"usage_units": usage_units, "trace_id": row["trace_id"]},
            )
            self._connection.execute(
                "UPDATE runs SET state = 'completed', sequence = ?, result_json = ?, updated_at = ? WHERE run_id = ?",
                (sequence, json.dumps({"usage_units": usage_units}), _now(), run_id),
            )
            return self._to_run(self._row_locked(run_id))

    def events(self, run_id: str, tenant_id: str, *, after_sequence: int = 0) -> tuple[RunEvent, ...]:
        self.get(run_id, tenant_id)
        rows = self._connection.execute(
            "SELECT * FROM run_events WHERE run_id = ? AND sequence > ? ORDER BY sequence",
            (run_id, after_sequence),
        ).fetchall()
        return tuple(RunEvent(row["event_id"], row["run_id"], row["tenant_id"], int(row["sequence"]), row["event"], json.loads(row["data_json"]), row["created_at"]) for row in rows)

    def sequence_for_event(self, run_id: str, event_id: str) -> int:
        row = self._connection.execute("SELECT sequence FROM run_events WHERE run_id = ? AND event_id = ?", (run_id, event_id)).fetchone()
        return 0 if row is None else int(row["sequence"])

    def _transition_locked(self, row: sqlite3.Row, state: RunState, payload: Mapping[str, Any]) -> Run:
        previous = row["state"]
        if state not in _TRANSITIONS[previous]:
            raise InvalidTransition(f"{previous} -> {state} is not allowed")
        sequence = int(row["sequence"]) + 1
        self._append_event_locked(
            row["run_id"], row["tenant_id"], sequence, "run.state_changed",
            {"state": state, "trace_id": row["trace_id"], **dict(payload)},
        )
        self._connection.execute(
            "UPDATE runs SET state = ?, sequence = ?, cancel_requested = 0, updated_at = ? WHERE run_id = ?",
            (state, sequence, _now(), row["run_id"]),
        )
        return self._to_run(self._row_locked(row["run_id"]))

    def _append_event_locked(self, run_id: str, tenant_id: str, sequence: int, event: str, data: Mapping[str, Any]) -> RunEvent:
        event_id = f"event-{uuid.uuid4().hex}"
        created_at = _now()
        self._connection.execute(
            "INSERT INTO run_events VALUES (?, ?, ?, ?, ?, ?, ?)",
            (event_id, run_id, tenant_id, sequence, event, json.dumps(data, sort_keys=True, separators=(",", ":")), created_at),
        )
        return RunEvent(event_id, run_id, tenant_id, sequence, event, dict(data), created_at)

    def _row_locked(self, run_id: str) -> sqlite3.Row:
        row = self._connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise RunNotFound(run_id)
        return row

    @staticmethod
    def _to_run(row: sqlite3.Row) -> Run:
        return Run(
            row["run_id"], row["tenant_id"], row["account_id"], row["project_id"], row["idempotency_key"],
            row["trace_id"], json.loads(row["input_json"]), row["state"], int(row["sequence"]),
            row["reservation_id"], bool(row["cancel_requested"]), int(row["worker_attempt"]),
            int(row["max_steps"]), int(row["max_model_calls"]), float(row["max_runtime_seconds"]),
            json.loads(row["result_json"]),
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
