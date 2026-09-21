"""SQLite kernel store: tenant-scoped ledger, usage, approvals, and reports."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from .contracts import ApprovalToken, ReleaseReport, RunLifecycle, UsageRecord
from .redaction import redact


class TenantScopeError(PermissionError):
    pass


class IdempotencyConflict(ValueError):
    pass


class InvalidApproval(PermissionError):
    pass


_ALLOWED: dict[str, frozenset[str]] = {
    "queued": frozenset({"running", "failed", "rejected"}),
    "running": frozenset({"waiting_approval", "plan_only", "verified", "quota_paused", "budget_exceeded", "failed", "rejected"}),
    "waiting_approval": frozenset({"running", "rejected", "failed"}),
    "plan_only": frozenset(),
    "verified": frozenset(),
    "quota_paused": frozenset(),
    "budget_exceeded": frozenset(),
    "failed": frozenset(),
    "rejected": frozenset(),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class KernelStore:
    """The product run ledger is intentionally separate from graph checkpoints."""

    def __init__(self, database: str = ":memory:") -> None:
        self._db = sqlite3.connect(database, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS product_runs (
                run_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                request_hash TEXT NOT NULL,
                mode TEXT NOT NULL,
                state TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                error TEXT,
                approval_id TEXT,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(tenant_id, idempotency_key)
            );
            CREATE TABLE IF NOT EXISTS product_events (
                event_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                event TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(run_id, sequence)
            );
            CREATE TABLE IF NOT EXISTS graph_checkpoints (
                run_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                node TEXT NOT NULL,
                state_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS model_usage (
                run_id TEXT NOT NULL,
                call_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                PRIMARY KEY(run_id, call_id)
            );
            CREATE TABLE IF NOT EXISTS approvals (
                token_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                scopes_json TEXT NOT NULL,
                issued_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                plan_hash TEXT,
                consumed INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS release_reports (
                run_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                report_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )

    def close(self) -> None:
        self._db.close()

    def create_run(self, *, run_id: str, tenant_id: str, idempotency_key: str, mode: str, payload: Mapping[str, Any]) -> RunLifecycle:
        request_hash = hashlib.sha256(json.dumps(redact(payload), sort_keys=True, default=str).encode()).hexdigest()
        with self._transaction():
            existing = self._db.execute(
                "SELECT * FROM product_runs WHERE tenant_id = ? AND idempotency_key = ?",
                (tenant_id, idempotency_key),
            ).fetchone()
            if existing:
                if existing["request_hash"] != request_hash:
                    raise IdempotencyConflict("idempotency key was reused with different input")
                return self._run(existing)
            now = _now()
            self._db.execute(
                "INSERT INTO product_runs VALUES (?, ?, ?, ?, ?, 'queued', 1, NULL, NULL, '{}', ?, ?)",
                (run_id, tenant_id, idempotency_key, request_hash, mode, now, now),
            )
            self._append_event_locked(run_id, tenant_id, 1, "run.queued", {"mode": mode})
            return self._run(self._db.execute("SELECT * FROM product_runs WHERE run_id = ?", (run_id,)).fetchone())

    def get_run(self, run_id: str, tenant_id: str) -> RunLifecycle:
        row = self._db.execute("SELECT * FROM product_runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None or row["tenant_id"] != tenant_id:
            raise TenantScopeError("run is not visible to this tenant")
        return self._run(row)

    def transition(self, run_id: str, tenant_id: str, state: str, *, payload: Mapping[str, Any] | None = None, error: str | None = None) -> RunLifecycle:
        with self._transaction():
            row = self._owned_row(run_id, tenant_id)
            if state not in _ALLOWED[row["state"]]:
                raise ValueError(f"{row['state']} -> {state} is not allowed")
            sequence = int(row["sequence"]) + 1
            event_payload = {"state": state, **dict(redact(payload or {}))}
            self._append_event_locked(run_id, tenant_id, sequence, "run.state_changed", event_payload)
            self._db.execute(
                "UPDATE product_runs SET state = ?, sequence = ?, error = ?, approval_id = COALESCE(?, approval_id), result_json = ?, updated_at = ? WHERE run_id = ?",
                (state, sequence, error, (payload or {}).get("approval_id"), json.dumps(redact(payload or {}), sort_keys=True), _now(), run_id),
            )
            return self._run(self._db.execute("SELECT * FROM product_runs WHERE run_id = ?", (run_id,)).fetchone())

    def append_event(self, run_id: str, tenant_id: str, event: str, payload: Mapping[str, Any]) -> None:
        with self._transaction():
            row = self._owned_row(run_id, tenant_id)
            sequence = int(row["sequence"]) + 1
            self._append_event_locked(run_id, tenant_id, sequence, event, payload)
            self._db.execute("UPDATE product_runs SET sequence = ?, updated_at = ? WHERE run_id = ?", (sequence, _now(), run_id))

    def events(self, run_id: str, tenant_id: str) -> tuple[dict[str, Any], ...]:
        self.get_run(run_id, tenant_id)
        rows = self._db.execute("SELECT * FROM product_events WHERE run_id = ? ORDER BY sequence", (run_id,)).fetchall()
        return tuple({"event_id": row["event_id"], "sequence": row["sequence"], "event": row["event"], "payload": json.loads(row["payload_json"])} for row in rows)

    def save_checkpoint(self, run_id: str, tenant_id: str, node: str, state: Mapping[str, Any]) -> None:
        safe = redact(state)
        with self._transaction():
            self._owned_row(run_id, tenant_id)
            self._db.execute(
                "INSERT INTO graph_checkpoints VALUES (?, ?, ?, ?, ?) ON CONFLICT(run_id) DO UPDATE SET node=excluded.node, state_json=excluded.state_json, updated_at=excluded.updated_at",
                (run_id, tenant_id, node, json.dumps(safe, sort_keys=True), _now()),
            )

    def checkpoint(self, run_id: str, tenant_id: str) -> dict[str, Any] | None:
        self.get_run(run_id, tenant_id)
        row = self._db.execute("SELECT * FROM graph_checkpoints WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        return {"run_id": run_id, "tenant_id": tenant_id, "node": row["node"], "state": json.loads(row["state_json"])}

    def record_usage(self, usage: UsageRecord, tenant_id: str | None = None) -> None:
        self._owned_row(usage.run_id, tenant_id or self._tenant_for_run(usage.run_id))
        payload = usage.__dict__
        encoded = json.dumps(payload, sort_keys=True)
        try:
            self._db.execute("INSERT INTO model_usage VALUES (?, ?, ?)", (usage.run_id, usage.call_id, encoded))
        except sqlite3.IntegrityError:
            existing = self._db.execute("SELECT payload_json FROM model_usage WHERE run_id = ? AND call_id = ?", (usage.run_id, usage.call_id)).fetchone()
            if existing is None or existing["payload_json"] != encoded:
                raise IdempotencyConflict("usage call id was reused with different usage") from None

    def usage(self, run_id: str, tenant_id: str) -> tuple[UsageRecord, ...]:
        self.get_run(run_id, tenant_id)
        rows = self._db.execute("SELECT payload_json FROM model_usage WHERE run_id = ? ORDER BY call_id", (run_id,)).fetchall()
        return tuple(UsageRecord(**json.loads(row["payload_json"])) for row in rows)

    def issue_approval(self, *, run_id: str, tenant_id: str, scopes: tuple[str, ...], expires_at: str, plan_hash: str | None = None) -> ApprovalToken:
        self._owned_row(run_id, tenant_id)
        token = ApprovalToken(f"approval-{uuid.uuid4().hex}", run_id, tenant_id, scopes, _now(), expires_at, plan_hash)
        self._db.execute(
            "INSERT INTO approvals VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
            (token.token_id, run_id, tenant_id, json.dumps(scopes), token.issued_at, expires_at, plan_hash),
        )
        return token

    def consume_approval(self, token_id: str, *, run_id: str, tenant_id: str, scope: str, plan_hash: str | None = None) -> ApprovalToken:
        with self._transaction():
            row = self._db.execute("SELECT * FROM approvals WHERE token_id = ?", (token_id,)).fetchone()
            if row is None or row["run_id"] != run_id or row["tenant_id"] != tenant_id or bool(row["consumed"]):
                raise InvalidApproval("approval token is invalid or already consumed")
            if scope not in json.loads(row["scopes_json"]):
                raise InvalidApproval("approval token does not grant the requested scope")
            if datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc):
                raise InvalidApproval("approval token is expired")
            bound_plan_hash = row["plan_hash"]
            if bound_plan_hash is not None and plan_hash != bound_plan_hash:
                raise InvalidApproval("approval token is bound to a different plan")
            self._db.execute("UPDATE approvals SET consumed = 1 WHERE token_id = ?", (token_id,))
            return ApprovalToken(
                row["token_id"], row["run_id"], row["tenant_id"],
                tuple(json.loads(row["scopes_json"])), row["issued_at"], row["expires_at"],
                bound_plan_hash, True,
            )

    def save_report(self, report: ReleaseReport, tenant_id: str) -> None:
        self.get_run(report.run_id, tenant_id)
        payload = {"run_id": report.run_id, "status": report.status, "terminal_state_consistent": report.terminal_state_consistent, "metrics": {key: value.__dict__ for key, value in report.metrics.items()}, "persisted": True}
        self._db.execute("INSERT OR REPLACE INTO release_reports VALUES (?, ?, ?, ?)", (report.run_id, tenant_id, json.dumps(payload, sort_keys=True), _now()))

    def report(self, run_id: str, tenant_id: str) -> Mapping[str, Any] | None:
        self.get_run(run_id, tenant_id)
        row = self._db.execute("SELECT report_json FROM release_reports WHERE run_id = ?", (run_id,)).fetchone()
        return None if row is None else json.loads(row["report_json"])

    def _owned_row(self, run_id: str, tenant_id: str) -> sqlite3.Row:
        row = self._db.execute("SELECT * FROM product_runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None or row["tenant_id"] != tenant_id:
            raise TenantScopeError("run is not visible to this tenant")
        return row

    def _tenant_for_run(self, run_id: str) -> str:
        row = self._db.execute("SELECT tenant_id FROM product_runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise TenantScopeError("run is not visible")
        return str(row["tenant_id"])

    def _append_event_locked(self, run_id: str, tenant_id: str, sequence: int, event: str, payload: Mapping[str, Any]) -> None:
        self._db.execute("INSERT INTO product_events VALUES (?, ?, ?, ?, ?, ?, ?)", (f"event-{uuid.uuid4().hex}", run_id, tenant_id, sequence, event, json.dumps(redact(payload), sort_keys=True), _now()))

    @staticmethod
    def _run(row: sqlite3.Row) -> RunLifecycle:
        return RunLifecycle(row["run_id"], row["tenant_id"], row["idempotency_key"], row["state"], row["mode"], int(row["sequence"]), row["error"], row["approval_id"], json.loads(row["result_json"]))

    class _Transaction:
        def __init__(self, owner: "KernelStore") -> None:
            self.owner = owner

        def __enter__(self):
            self.owner._lock.acquire()
            self.owner._db.execute("BEGIN")
            return self.owner._db

        def __exit__(self, exc_type, exc, tb):
            self.owner._db.execute("ROLLBACK" if exc else "COMMIT")
            self.owner._lock.release()

    def _transaction(self) -> "KernelStore._Transaction":
        return self._Transaction(self)
