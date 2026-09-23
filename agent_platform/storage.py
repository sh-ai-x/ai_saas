"""SQLite persistence boundary for product runs and repository proposals.

The product run ledger remains the lifecycle authority.  Proposal tables are
the durable review projection linked to that ledger; optional graph and
LangSmith integrations never decide state.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from .contracts import ApprovalToken, ReleaseReport, RunLifecycle, UsageRecord
from .redaction import redact


class TenantScopeError(PermissionError):
    pass


class IdempotencyConflict(ValueError):
    pass


class InvalidApproval(PermissionError):
    pass


class StaleProposalError(PermissionError):
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

_MAX_PROPOSAL_CHARS = 32_000
_MAX_JSON_CHARS = 256_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bounded_text(value: Any, limit: int = _MAX_JSON_CHARS) -> str:
    text = str(value)
    return text if len(text) <= limit else text[:limit] + "\n[TRUNCATED]"


def _safe_json(value: Any, *, limit: int = _MAX_JSON_CHARS) -> str:
    encoded = json.dumps(redact(value), sort_keys=True, default=str)
    return _bounded_text(encoded, limit)


def _request_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_safe_json(value).encode()).hexdigest()


def _snapshot(snapshot: Mapping[str, Any] | None) -> dict[str, Any]:
    source = snapshot or {}
    commit = source.get("commit", source.get("head_commit"))
    return {
        "repository_id": source.get("repository_id"),
        "canonical_path": source.get("canonical_path"),
        "name": source.get("name"),
        "branch": source.get("branch"),
        "commit": commit,
        "dirty": bool(source.get("dirty", False)),
        "capabilities": tuple(str(item) for item in source.get("capabilities", ()) or ()),
    }


def _snapshot_changed(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return any(
        left.get(key) != right.get(key)
        for key in ("repository_id", "branch", "commit")
        if left.get(key) is not None and right.get(key) is not None
    )


class KernelStore:
    """The product run ledger and its repository-scoped review projection."""

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
                proposal_id TEXT,
                repository_id TEXT,
                branch TEXT,
                commit_sha TEXT,
                repository_dirty INTEGER NOT NULL DEFAULT 0,
                trace_id TEXT,
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
                consumed INTEGER NOT NULL DEFAULT 0,
                proposal_id TEXT,
                repository_id TEXT,
                branch TEXT,
                commit_sha TEXT,
                plan_digest TEXT
            );
            CREATE TABLE IF NOT EXISTS release_reports (
                run_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                report_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS repositories (
                tenant_id TEXT NOT NULL,
                repository_id TEXT NOT NULL,
                root_id TEXT,
                canonical_path TEXT NOT NULL,
                name TEXT NOT NULL,
                branch TEXT NOT NULL,
                commit_sha TEXT NOT NULL,
                dirty INTEGER NOT NULL,
                capabilities_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(tenant_id, repository_id)
            );
            CREATE TABLE IF NOT EXISTS proposals (
                proposal_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                repository_id TEXT NOT NULL,
                branch TEXT NOT NULL,
                commit_sha TEXT NOT NULL,
                repository_dirty INTEGER NOT NULL,
                idempotency_key TEXT NOT NULL,
                request_hash TEXT NOT NULL,
                proposal_text TEXT NOT NULL,
                proposal_digest TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'created',
                stale_evidence INTEGER NOT NULL DEFAULT 0,
                stale_reason TEXT,
                latest_run_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(tenant_id, repository_id, idempotency_key)
            );
            CREATE TABLE IF NOT EXISTS proposal_runs (
                run_id TEXT PRIMARY KEY,
                proposal_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                repository_id TEXT NOT NULL,
                branch TEXT NOT NULL,
                commit_sha TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                requirements_json TEXT NOT NULL DEFAULT '[]',
                plan_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS evidence_snapshots (
                evidence_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                proposal_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                requirement_id TEXT NOT NULL,
                path TEXT NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                content_hash TEXT NOT NULL,
                symbol TEXT,
                authorized INTEGER NOT NULL,
                valid INTEGER NOT NULL,
                stale INTEGER NOT NULL DEFAULT 0,
                stale_reason TEXT,
                checked_commit TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS plans (
                plan_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                proposal_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                plan_json TEXT NOT NULL,
                plan_digest TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS proposal_approvals (
                token_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                proposal_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                repository_id TEXT NOT NULL,
                branch TEXT NOT NULL,
                commit_sha TEXT NOT NULL,
                plan_digest TEXT NOT NULL,
                scopes_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS verification_reports (
                run_id TEXT PRIMARY KEY,
                proposal_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                report_json TEXT NOT NULL,
                status TEXT NOT NULL,
                stale INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS proposal_artifacts (
                artifact_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                proposal_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                path TEXT,
                digest TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS trace_correlations (
                run_id TEXT PRIMARY KEY,
                proposal_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                trace_id TEXT,
                provider TEXT NOT NULL,
                project TEXT,
                console_url TEXT,
                export_status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        self._ensure_legacy_columns()

    def _ensure_legacy_columns(self) -> None:
        """Keep previously-created local SQLite files readable after upgrade."""

        columns = {
            "product_runs": {
                "proposal_id": "TEXT",
                "repository_id": "TEXT",
                "branch": "TEXT",
                "commit_sha": "TEXT",
                "repository_dirty": "INTEGER NOT NULL DEFAULT 0",
                "trace_id": "TEXT",
            },
            "approvals": {
                "proposal_id": "TEXT",
                "repository_id": "TEXT",
                "branch": "TEXT",
                "commit_sha": "TEXT",
                "plan_digest": "TEXT",
            },
        }
        for table, table_columns in columns.items():
            existing = {row["name"] for row in self._db.execute(f"PRAGMA table_info({table})").fetchall()}
            for name, definition in table_columns.items():
                if name not in existing:
                    self._db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    def close(self) -> None:
        self._db.close()

    # Product run ledger -------------------------------------------------

    def create_run(
        self,
        *,
        run_id: str,
        tenant_id: str,
        idempotency_key: str,
        mode: str,
        payload: Mapping[str, Any],
        proposal_id: str | None = None,
        repository_snapshot: Mapping[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> RunLifecycle:
        snapshot = _snapshot(repository_snapshot)
        request_payload = {**dict(payload), "repository_snapshot": snapshot}
        request_hash = _request_hash(request_payload)
        with self._transaction():
            if proposal_id:
                proposal = self._owned_proposal(proposal_id, tenant_id)
                if snapshot["repository_id"] and snapshot["repository_id"] != proposal["repository_id"]:
                    raise TenantScopeError("proposal repository does not match the requested repository")
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
                """
                INSERT INTO product_runs(
                    run_id, tenant_id, idempotency_key, request_hash, mode, state,
                    sequence, error, approval_id, result_json, created_at, updated_at,
                    proposal_id, repository_id, branch, commit_sha, repository_dirty, trace_id
                ) VALUES (?, ?, ?, ?, ?, 'queued', 1, NULL, NULL, '{}', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    tenant_id,
                    idempotency_key,
                    request_hash,
                    mode,
                    now,
                    now,
                    proposal_id,
                    snapshot["repository_id"],
                    snapshot["branch"],
                    snapshot["commit"],
                    int(snapshot["dirty"]),
                    trace_id,
                ),
            )
            self._append_event_locked(run_id, tenant_id, 1, "run.queued", {"mode": mode, **snapshot})
            if proposal_id:
                self._db.execute(
                    """
                    INSERT OR REPLACE INTO proposal_runs(
                        run_id, proposal_id, tenant_id, repository_id, branch, commit_sha,
                        idempotency_key, requirements_json, plan_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, '[]', NULL, ?, ?)
                    """,
                    (
                        run_id,
                        proposal_id,
                        tenant_id,
                        snapshot["repository_id"],
                        snapshot["branch"] or "",
                        snapshot["commit"] or "",
                        idempotency_key,
                        now,
                        now,
                    ),
                )
                self._db.execute("UPDATE proposals SET latest_run_id = ?, updated_at = ? WHERE proposal_id = ? AND tenant_id = ?", (run_id, now, proposal_id, tenant_id))
            return self._run(self._db.execute("SELECT * FROM product_runs WHERE run_id = ?", (run_id,)).fetchone())

    def get_run(self, run_id: str, tenant_id: str) -> RunLifecycle:
        row = self._db.execute("SELECT * FROM product_runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None or row["tenant_id"] != tenant_id:
            raise TenantScopeError("run is not visible to this tenant")
        return self._run(row)

    def transition(
        self,
        run_id: str,
        tenant_id: str,
        state: str,
        *,
        payload: Mapping[str, Any] | None = None,
        error: str | None = None,
    ) -> RunLifecycle:
        with self._transaction():
            row = self._owned_row(run_id, tenant_id)
            if state not in _ALLOWED[row["state"]]:
                raise ValueError(f"{row['state']} -> {state} is not allowed")
            sequence = int(row["sequence"]) + 1
            safe_payload = dict(redact(payload or {}))
            event_payload = {"state": state, **safe_payload}
            self._append_event_locked(run_id, tenant_id, sequence, "run.state_changed", event_payload)
            existing_result = json.loads(row["result_json"] or "{}")
            existing_result.update(safe_payload)
            self._db.execute(
                """
                UPDATE product_runs
                SET state = ?, sequence = ?, error = ?, approval_id = COALESCE(?, approval_id),
                    result_json = ?, updated_at = ?
                WHERE run_id = ?
                """,
                (
                    state,
                    sequence,
                    error,
                    (payload or {}).get("approval_id"),
                    _safe_json(existing_result),
                    _now(),
                    run_id,
                ),
            )
            if row["proposal_id"]:
                self._db.execute("UPDATE proposals SET state = ?, updated_at = ? WHERE proposal_id = ? AND tenant_id = ?", (state, _now(), row["proposal_id"], tenant_id))
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
                """
                INSERT INTO graph_checkpoints(run_id, tenant_id, node, state_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET node=excluded.node, state_json=excluded.state_json, updated_at=excluded.updated_at
                """,
                (run_id, tenant_id, node, _safe_json(safe), _now()),
            )

    def checkpoint(self, run_id: str, tenant_id: str) -> dict[str, Any] | None:
        self.get_run(run_id, tenant_id)
        row = self._db.execute("SELECT * FROM graph_checkpoints WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        return {"run_id": run_id, "tenant_id": tenant_id, "node": row["node"], "state": json.loads(row["state_json"])}

    def record_usage(self, usage: UsageRecord, tenant_id: str | None = None) -> None:
        self._owned_row(usage.run_id, tenant_id or self._tenant_for_run(usage.run_id))
        encoded = _safe_json(usage.__dict__)
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

    # Proposal records ---------------------------------------------------

    def register_repository(self, tenant_id: str, repository: Mapping[str, Any]) -> dict[str, Any]:
        snapshot = _snapshot(repository)
        if not snapshot["repository_id"]:
            raise ValueError("repository_id is required")
        now = _now()
        self._db.execute(
            """
            INSERT INTO repositories(
                tenant_id, repository_id, root_id, canonical_path, name, branch,
                commit_sha, dirty, capabilities_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tenant_id, repository_id) DO UPDATE SET
                root_id=excluded.root_id, canonical_path=excluded.canonical_path,
                name=excluded.name, branch=excluded.branch, commit_sha=excluded.commit_sha,
                dirty=excluded.dirty, capabilities_json=excluded.capabilities_json,
                updated_at=excluded.updated_at
            """,
            (
                tenant_id,
                snapshot["repository_id"],
                repository.get("root_id"),
                snapshot["canonical_path"] or "",
                snapshot["name"] or "",
                snapshot["branch"] or "",
                snapshot["commit"] or "",
                int(snapshot["dirty"]),
                _safe_json(list(snapshot["capabilities"])),
                now,
                now,
            ),
        )
        return self.repository(tenant_id, str(snapshot["repository_id"]))

    def repository(self, tenant_id: str, repository_id: str) -> dict[str, Any]:
        row = self._db.execute("SELECT * FROM repositories WHERE tenant_id = ? AND repository_id = ?", (tenant_id, repository_id)).fetchone()
        if row is None:
            raise TenantScopeError("repository is not visible to this tenant")
        return {
            "tenant_id": row["tenant_id"],
            "repository_id": row["repository_id"],
            "root_id": row["root_id"],
            "canonical_path": row["canonical_path"],
            "name": row["name"],
            "branch": row["branch"],
            "commit": row["commit_sha"],
            "head_commit": row["commit_sha"],
            "dirty": bool(row["dirty"]),
            "capabilities": tuple(json.loads(row["capabilities_json"] or "[]")),
            "updated_at": row["updated_at"],
        }

    def create_proposal(
        self,
        *,
        tenant_id: str,
        repository: Mapping[str, Any],
        proposal: str,
        mode: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        if not isinstance(proposal, str) or not proposal.strip():
            raise ValueError("proposal must be non-empty")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ValueError("idempotency_key must be non-empty")
        snapshot = _snapshot(repository)
        repository_id = snapshot["repository_id"]
        if not repository_id or not snapshot["branch"] or not snapshot["commit"]:
            raise ValueError("repository snapshot is incomplete")
        self.register_repository(tenant_id, repository)
        safe_proposal = _bounded_text(redact(proposal), _MAX_PROPOSAL_CHARS)
        request_hash = _request_hash({"proposal": safe_proposal, "mode": mode, "repository": snapshot})
        existing = self._db.execute(
            "SELECT * FROM proposals WHERE tenant_id = ? AND repository_id = ? AND idempotency_key = ?",
            (tenant_id, repository_id, idempotency_key),
        ).fetchone()
        if existing:
            if existing["request_hash"] != request_hash:
                raise IdempotencyConflict("idempotency key was reused with different input")
            return self._proposal_row(existing)
        now = _now()
        proposal_id = f"proposal-{uuid.uuid4().hex}"
        self._db.execute(
            """
            INSERT INTO proposals(
                proposal_id, tenant_id, repository_id, branch, commit_sha, repository_dirty,
                idempotency_key, request_hash, proposal_text, proposal_digest, state,
                stale_evidence, stale_reason, latest_run_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'created', 0, NULL, NULL, ?, ?)
            """,
            (
                proposal_id,
                tenant_id,
                repository_id,
                snapshot["branch"],
                snapshot["commit"],
                int(snapshot["dirty"]),
                idempotency_key,
                request_hash,
                safe_proposal,
                hashlib.sha256(safe_proposal.encode()).hexdigest(),
                now,
                now,
            ),
        )
        return self._proposal_row(self._db.execute("SELECT * FROM proposals WHERE proposal_id = ?", (proposal_id,)).fetchone())

    def proposal_input(self, proposal_id: str, tenant_id: str) -> str:
        row = self._owned_proposal(proposal_id, tenant_id)
        return str(row["proposal_text"])

    def list_proposals(self, tenant_id: str, repository_id: str) -> tuple[dict[str, Any], ...]:
        rows = self._db.execute(
            "SELECT * FROM proposals WHERE tenant_id = ? AND repository_id = ? ORDER BY updated_at DESC, proposal_id DESC",
            (tenant_id, repository_id),
        ).fetchall()
        return tuple(self._proposal_summary(row) for row in rows)

    def proposal_view(
        self,
        proposal_id: str,
        tenant_id: str,
        *,
        current_repository: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        row = self._owned_proposal(proposal_id, tenant_id)
        if current_repository is not None:
            self.revalidate_proposal(proposal_id, tenant_id, current_repository)
            row = self._owned_proposal(proposal_id, tenant_id)
        latest_run_id = row["latest_run_id"]
        result: dict[str, Any] = {
            "proposal_id": row["proposal_id"],
            "tenant_id": row["tenant_id"],
            "repository_id": row["repository_id"],
            "branch": row["branch"],
            "commit": row["commit_sha"],
            "repository_dirty": bool(row["repository_dirty"]),
            "idempotency_key": row["idempotency_key"],
            "proposal_digest": row["proposal_digest"],
            "state": row["state"],
            "stale_evidence": bool(row["stale_evidence"]),
            "stale_reason": row["stale_reason"],
            "latest_run_id": latest_run_id,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "run": None,
            "requirements": [],
            "evidence": [],
            "plan": None,
            "approval": None,
            "report": None,
            "artifacts": [],
            "trace": None,
        }
        if not latest_run_id:
            return result
        run = self.get_run(str(latest_run_id), tenant_id)
        run_json = self._run_json(run)
        if bool(row["stale_evidence"]):
            run_json["ledger_state"] = run.state
            run_json["state"] = "stale"
            run_json["verification_blocked"] = True
        result["run"] = run_json
        run_row = self._db.execute("SELECT * FROM proposal_runs WHERE run_id = ? AND tenant_id = ?", (latest_run_id, tenant_id)).fetchone()
        if run_row:
            result["requirements"] = json.loads(run_row["requirements_json"] or "[]")
            result["plan"] = json.loads(run_row["plan_json"]) if run_row["plan_json"] else None
        evidence_rows = self._db.execute("SELECT * FROM evidence_snapshots WHERE run_id = ? AND tenant_id = ? ORDER BY evidence_id", (latest_run_id, tenant_id)).fetchall()
        result["evidence"] = [self._evidence_json(item) for item in evidence_rows]
        approval = self._db.execute("SELECT * FROM proposal_approvals WHERE run_id = ? AND tenant_id = ? ORDER BY created_at DESC LIMIT 1", (latest_run_id, tenant_id)).fetchone()
        if approval:
            result["approval"] = self._approval_json(approval)
        report = self._db.execute("SELECT report_json, status, stale FROM verification_reports WHERE run_id = ? AND tenant_id = ?", (latest_run_id, tenant_id)).fetchone()
        if report:
            report_value = json.loads(report["report_json"])
            report_value["status"] = "stale" if bool(report["stale"]) else report["status"]
            report_value["verification_blocked"] = bool(report["stale"])
            result["report"] = report_value
        else:
            result["report"] = self.report(latest_run_id, tenant_id)
        artifacts = self._db.execute("SELECT * FROM proposal_artifacts WHERE run_id = ? AND tenant_id = ? ORDER BY created_at, artifact_id", (latest_run_id, tenant_id)).fetchall()
        result["artifacts"] = [self._artifact_json(item) for item in artifacts]
        trace = self._db.execute("SELECT * FROM trace_correlations WHERE run_id = ? AND tenant_id = ?", (latest_run_id, tenant_id)).fetchone()
        if trace:
            result["trace"] = self._trace_json(trace)
        return result

    def revalidate_proposal(self, proposal_id: str, tenant_id: str, current_repository: Mapping[str, Any], *, evidence: Iterable[Mapping[str, Any]] | None = None) -> bool:
        row = self._owned_proposal(proposal_id, tenant_id)
        current = _snapshot(current_repository)
        if current["repository_id"] != row["repository_id"]:
            raise TenantScopeError("repository identity mismatch")
        changed = _snapshot_changed({"repository_id": row["repository_id"], "branch": row["branch"], "commit": row["commit_sha"]}, current)
        latest_run_id = row["latest_run_id"]
        if latest_run_id:
            if changed:
                self._db.execute(
                    "UPDATE evidence_snapshots SET stale = 1, stale_reason = ? WHERE run_id = ? AND tenant_id = ?",
                    ("repository commit or branch changed; re-analysis required", latest_run_id, tenant_id),
                )
                self._db.execute("UPDATE verification_reports SET stale = 1, updated_at = ? WHERE run_id = ? AND tenant_id = ?", (_now(), latest_run_id, tenant_id))
            elif not changed and evidence is not None:
                for item in evidence:
                    evidence_id = item.get("evidence_id")
                    path = item.get("path")
                    content_hash = item.get("content_hash")
                    if evidence_id:
                        self._db.execute(
                            "UPDATE evidence_snapshots SET stale = ?, stale_reason = ?, valid = ?, authorized = ? WHERE evidence_id = ? AND tenant_id = ?",
                            (
                                int(not bool(item.get("valid", False)) or not bool(item.get("authorized", False)) or content_hash is None),
                                "evidence hash no longer matches the repository" if not item.get("valid", False) else None,
                                int(bool(item.get("valid", False))),
                                int(bool(item.get("authorized", False))),
                                evidence_id,
                                tenant_id,
                            ),
                        )
                    elif path:
                        self._db.execute(
                            "UPDATE evidence_snapshots SET stale = 1, stale_reason = ? WHERE run_id = ? AND path = ? AND tenant_id = ?",
                            ("evidence hash no longer matches the repository", latest_run_id, path, tenant_id),
                        )
        stale = changed or self._db.execute("SELECT 1 FROM evidence_snapshots WHERE run_id = ? AND tenant_id = ? AND stale = 1 LIMIT 1", (latest_run_id, tenant_id)).fetchone() is not None if latest_run_id else False
        self._db.execute(
            "UPDATE proposals SET stale_evidence = ?, stale_reason = ?, state = CASE WHEN ? = 1 THEN 'stale' ELSE state END, updated_at = ? WHERE proposal_id = ? AND tenant_id = ?",
            (int(stale), "repository commit or branch changed; re-analysis required" if changed else ("evidence hash no longer matches the repository" if stale else None), int(stale), _now(), proposal_id, tenant_id),
        )
        if latest_run_id:
            run = self.get_run(latest_run_id, tenant_id)
            if stale:
                safe_result = dict(run.result)
                safe_result.update({"stale_evidence": True, "verification_blocked": True, "stale_reason": "repository commit or branch changed; re-analysis required" if changed else "evidence hash no longer matches the repository"})
                self._db.execute("UPDATE product_runs SET result_json = ?, updated_at = ? WHERE run_id = ? AND tenant_id = ?", (_safe_json(safe_result), _now(), latest_run_id, tenant_id))
        return stale

    # Reviewable output records ----------------------------------------

    def issue_approval(
        self,
        *,
        run_id: str,
        tenant_id: str,
        scopes: tuple[str, ...],
        expires_at: str,
        plan_digest: str | None = None,
    ) -> ApprovalToken:
        row = self._owned_row(run_id, tenant_id)
        plan = self._db.execute("SELECT plan_digest FROM plans WHERE run_id = ? AND tenant_id = ?", (run_id, tenant_id)).fetchone()
        bound_plan_digest = plan_digest or (str(plan["plan_digest"]) if plan is not None else None)
        if row["repository_id"] and not bound_plan_digest:
            raise InvalidApproval("local repository approvals must bind a plan digest")
        token = ApprovalToken(
            f"approval-{uuid.uuid4().hex}",
            run_id,
            tenant_id,
            scopes,
            _now(),
            expires_at,
            False,
            row["repository_id"],
            row["branch"],
            row["commit_sha"],
            bound_plan_digest,
            row["proposal_id"],
        )
        self._db.execute(
            "INSERT INTO approvals(token_id, run_id, tenant_id, scopes_json, issued_at, expires_at, consumed, proposal_id, repository_id, branch, commit_sha, plan_digest) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)",
            (token.token_id, run_id, tenant_id, json.dumps(scopes), token.issued_at, expires_at, row["proposal_id"], row["repository_id"], row["branch"], row["commit_sha"], bound_plan_digest),
        )
        if row["proposal_id"]:
            now = _now()
            self._db.execute(
                "INSERT INTO proposal_approvals(token_id, run_id, proposal_id, tenant_id, repository_id, branch, commit_sha, plan_digest, scopes_json, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'issued', ?, ?)",
                (token.token_id, run_id, row["proposal_id"], tenant_id, row["repository_id"], row["branch"], row["commit_sha"], bound_plan_digest or "", json.dumps(scopes), now, now),
            )
        return token

    def approval_for_run(self, run_id: str, tenant_id: str) -> ApprovalToken | None:
        self._owned_row(run_id, tenant_id)
        row = self._db.execute("SELECT * FROM approvals WHERE run_id = ? AND tenant_id = ? ORDER BY issued_at DESC LIMIT 1", (run_id, tenant_id)).fetchone()
        if row is None:
            return None
        return ApprovalToken(row["token_id"], row["run_id"], row["tenant_id"], tuple(json.loads(row["scopes_json"])), row["issued_at"], row["expires_at"], bool(row["consumed"]), row["repository_id"], row["branch"], row["commit_sha"], row["plan_digest"], row["proposal_id"])

    def consume_approval(self, token_id: str, *, run_id: str, tenant_id: str, scope: str, current_repository: Mapping[str, Any] | None = None, plan_digest: str | None = None) -> ApprovalToken:
        with self._transaction():
            row = self._db.execute("SELECT * FROM approvals WHERE token_id = ?", (token_id,)).fetchone()
            if row is None or row["run_id"] != run_id or row["tenant_id"] != tenant_id or bool(row["consumed"]):
                raise InvalidApproval("approval token is invalid or already consumed")
            if scope not in json.loads(row["scopes_json"]):
                raise InvalidApproval("approval token does not grant the requested scope")
            if datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc):
                raise InvalidApproval("approval token is expired")
            if row["repository_id"] and current_repository is None:
                raise InvalidApproval("approval repository binding is required")
            if row["repository_id"] and current_repository is not None:
                bound = {"repository_id": row["repository_id"], "branch": row["branch"], "commit": row["commit_sha"]}
                current = _snapshot(current_repository)
                if _snapshot_changed(bound, current) or not all(bound.get(key) for key in ("repository_id", "branch", "commit")):
                    raise InvalidApproval("approval is stale for the current repository commit")
            if row["plan_digest"] and (not plan_digest or plan_digest != row["plan_digest"]):
                raise InvalidApproval("approval is bound to a different plan")
            if plan_digest and not row["plan_digest"]:
                raise InvalidApproval("approval is missing its plan binding")
            self._db.execute("UPDATE approvals SET consumed = 1 WHERE token_id = ?", (token_id,))
            self._db.execute("UPDATE proposal_approvals SET status = 'consumed', updated_at = ? WHERE token_id = ? AND tenant_id = ?", (_now(), token_id, tenant_id))
            return ApprovalToken(row["token_id"], row["run_id"], row["tenant_id"], tuple(json.loads(row["scopes_json"])), row["issued_at"], row["expires_at"], True, row["repository_id"], row["branch"], row["commit_sha"], row["plan_digest"], row["proposal_id"])

    def save_report(self, report: ReleaseReport, tenant_id: str, *, stale: bool = False) -> None:
        self.get_run(report.run_id, tenant_id)
        payload = {
            "run_id": report.run_id,
            "status": report.status,
            "terminal_state_consistent": report.terminal_state_consistent,
            "metrics": {key: value.__dict__ for key, value in report.metrics.items()},
            "persisted": True,
            "verification_status": report.verification_status,
            "changed_files": list(report.changed_files),
            "test_results": list(report.test_results),
            "artifact_ids": list(report.artifact_ids),
            "trace_id": report.trace_id,
            "reason": report.reason,
        }
        encoded = _safe_json(payload)
        self._db.execute("INSERT OR REPLACE INTO release_reports VALUES (?, ?, ?, ?)", (report.run_id, tenant_id, encoded, _now()))
        run = self._db.execute("SELECT proposal_id FROM product_runs WHERE run_id = ? AND tenant_id = ?", (report.run_id, tenant_id)).fetchone()
        if run and run["proposal_id"]:
            self._db.execute(
                "INSERT OR REPLACE INTO verification_reports(run_id, proposal_id, tenant_id, report_json, status, stale, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM verification_reports WHERE run_id = ?), ?), ?)",
                (report.run_id, run["proposal_id"], tenant_id, encoded, report.status, int(stale), report.run_id, _now(), _now()),
            )

    def report(self, run_id: str, tenant_id: str) -> Mapping[str, Any] | None:
        self.get_run(run_id, tenant_id)
        row = self._db.execute("SELECT report_json FROM release_reports WHERE run_id = ?", (run_id,)).fetchone()
        return None if row is None else json.loads(row["report_json"])

    def save_proposal_outputs(
        self,
        *,
        proposal_id: str,
        run_id: str,
        tenant_id: str,
        requirements: Iterable[Mapping[str, Any]],
        evidence: Iterable[Mapping[str, Any]],
        plan: Mapping[str, Any] | None,
        report: Mapping[str, Any] | None,
        repository_snapshot: Mapping[str, Any],
    ) -> None:
        proposal = self._owned_proposal(proposal_id, tenant_id)
        if proposal["latest_run_id"] != run_id:
            raise TenantScopeError("proposal run is not current")
        snapshot = _snapshot(repository_snapshot)
        req_json = _safe_json(list(requirements))
        plan_json = _safe_json(plan) if plan is not None else None
        now = _now()
        self._db.execute("UPDATE proposal_runs SET requirements_json = ?, plan_json = ?, updated_at = ? WHERE run_id = ? AND tenant_id = ?", (req_json, plan_json, now, run_id, tenant_id))
        self._db.execute("DELETE FROM evidence_snapshots WHERE run_id = ? AND tenant_id = ?", (run_id, tenant_id))
        for index, item in enumerate(evidence):
            item = dict(item)
            self._db.execute(
                "INSERT INTO evidence_snapshots(evidence_id, run_id, proposal_id, tenant_id, requirement_id, path, start_line, end_line, content_hash, symbol, authorized, valid, stale, stale_reason, checked_commit) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?)",
                (
                    f"{run_id}:evidence:{index}",
                    run_id,
                    proposal_id,
                    tenant_id,
                    item.get("requirement_id", ""),
                    item.get("path", ""),
                    int(item.get("start_line", 1)),
                    int(item.get("end_line", 1)),
                    item.get("content_hash", ""),
                    item.get("symbol"),
                    int(bool(item.get("authorized", False))),
                    int(bool(item.get("valid", False))),
                    snapshot["commit"] or "",
                ),
            )
        if plan is not None:
            plan_id = str(plan.get("plan_id", f"plan-{run_id}"))
            plan_digest = hashlib.sha256(_safe_json(plan).encode()).hexdigest()
            self._db.execute(
                "INSERT OR REPLACE INTO plans(plan_id, run_id, proposal_id, tenant_id, plan_json, plan_digest, created_at) VALUES (?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM plans WHERE plan_id = ?), ?))",
                (plan_id, run_id, proposal_id, tenant_id, plan_json or "{}", plan_digest, plan_id, now),
            )
        if report is not None:
            encoded_report = _safe_json(report)
            self._db.execute(
                "INSERT OR REPLACE INTO verification_reports(run_id, proposal_id, tenant_id, report_json, status, stale, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 0, COALESCE((SELECT created_at FROM verification_reports WHERE run_id = ?), ?), ?)",
                (run_id, proposal_id, tenant_id, encoded_report, str(report.get("status", "unknown")), run_id, now, now),
            )
        self._db.execute(
            "UPDATE proposals SET stale_evidence = 0, stale_reason = NULL, updated_at = ? WHERE proposal_id = ? AND tenant_id = ?",
            (now, proposal_id, tenant_id),
        )

    def record_artifact(self, *, artifact_id: str, run_id: str, tenant_id: str, kind: str, digest: str, path: str | None = None, metadata: Mapping[str, Any] | None = None) -> None:
        row = self._owned_row(run_id, tenant_id)
        if not row["proposal_id"]:
            return
        self._db.execute(
            "INSERT OR REPLACE INTO proposal_artifacts(artifact_id, run_id, proposal_id, tenant_id, kind, path, digest, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (artifact_id, run_id, row["proposal_id"], tenant_id, kind, path, digest, _safe_json(metadata or {}), _now()),
        )

    def save_trace(self, *, run_id: str, tenant_id: str, trace_id: str | None, provider: str, project: str | None = None, console_url: str | None = None, export_status: str = "observational") -> None:
        row = self._owned_row(run_id, tenant_id)
        if not row["proposal_id"]:
            return
        self._db.execute(
            "INSERT OR REPLACE INTO trace_correlations(run_id, proposal_id, tenant_id, trace_id, provider, project, console_url, export_status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM trace_correlations WHERE run_id = ?), ?), ?)",
            (run_id, row["proposal_id"], tenant_id, trace_id, provider, project, console_url, export_status, run_id, _now(), _now()),
        )
        self._db.execute("UPDATE product_runs SET trace_id = ?, updated_at = ? WHERE run_id = ? AND tenant_id = ?", (trace_id, _now(), run_id, tenant_id))

    # Internal helpers --------------------------------------------------

    def _owned_row(self, run_id: str, tenant_id: str) -> sqlite3.Row:
        row = self._db.execute("SELECT * FROM product_runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None or row["tenant_id"] != tenant_id:
            raise TenantScopeError("run is not visible to this tenant")
        return row

    def _owned_proposal(self, proposal_id: str, tenant_id: str) -> sqlite3.Row:
        row = self._db.execute("SELECT * FROM proposals WHERE proposal_id = ?", (proposal_id,)).fetchone()
        if row is None or row["tenant_id"] != tenant_id:
            raise TenantScopeError("proposal is not visible to this tenant")
        return row

    def _tenant_for_run(self, run_id: str) -> str:
        row = self._db.execute("SELECT tenant_id FROM product_runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise TenantScopeError("run is not visible")
        return str(row["tenant_id"])

    def _append_event_locked(self, run_id: str, tenant_id: str, sequence: int, event: str, payload: Mapping[str, Any]) -> None:
        self._db.execute("INSERT INTO product_events VALUES (?, ?, ?, ?, ?, ?, ?)", (f"event-{uuid.uuid4().hex}", run_id, tenant_id, sequence, event, _safe_json(payload), _now()))

    @staticmethod
    def _run(row: sqlite3.Row) -> RunLifecycle:
        keys = set(row.keys())
        result = json.loads(row["result_json"] or "{}")
        return RunLifecycle(
            row["run_id"],
            row["tenant_id"],
            row["idempotency_key"],
            row["state"],
            row["mode"],
            int(row["sequence"]),
            row["error"],
            row["approval_id"],
            result,
            row["proposal_id"] if "proposal_id" in keys else None,
            row["repository_id"] if "repository_id" in keys else None,
            row["branch"] if "branch" in keys else None,
            row["commit_sha"] if "commit_sha" in keys else None,
            row["trace_id"] if "trace_id" in keys else None,
        )

    @staticmethod
    def _run_json(run: RunLifecycle) -> dict[str, Any]:
        return {
            "run_id": run.run_id,
            "tenant_id": run.tenant_id,
            "idempotency_key": run.idempotency_key,
            "state": run.state,
            "mode": run.mode,
            "sequence": run.sequence,
            "error": run.error,
            "approval_id": run.approval_id,
            "result": dict(run.result),
            "proposal_id": run.proposal_id,
            "repository_id": run.repository_id,
            "branch": run.branch,
            "commit": run.commit,
            "trace_id": run.trace_id,
        }

    @staticmethod
    def _proposal_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "proposal_id": row["proposal_id"],
            "tenant_id": row["tenant_id"],
            "repository_id": row["repository_id"],
            "branch": row["branch"],
            "commit": row["commit_sha"],
            "repository_dirty": bool(row["repository_dirty"]),
            "idempotency_key": row["idempotency_key"],
            "proposal_digest": row["proposal_digest"],
            "state": row["state"],
            "stale_evidence": bool(row["stale_evidence"]),
            "stale_reason": row["stale_reason"],
            "latest_run_id": row["latest_run_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _proposal_summary(row: sqlite3.Row) -> dict[str, Any]:
        return KernelStore._proposal_row(row)

    @staticmethod
    def _evidence_json(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "evidence_id": row["evidence_id"],
            "requirement_id": row["requirement_id"],
            "path": row["path"],
            "start_line": row["start_line"],
            "end_line": row["end_line"],
            "content_hash": row["content_hash"],
            "symbol": row["symbol"],
            "authorized": bool(row["authorized"]),
            "valid": bool(row["valid"]),
            "stale": bool(row["stale"]),
            "stale_reason": row["stale_reason"],
            "checked_commit": row["checked_commit"],
        }

    @staticmethod
    def _approval_json(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "token_id": row["token_id"],
            "run_id": row["run_id"],
            "proposal_id": row["proposal_id"],
            "tenant_id": row["tenant_id"],
            "repository_id": row["repository_id"],
            "branch": row["branch"],
            "commit": row["commit_sha"],
            "plan_digest": row["plan_digest"],
            "scopes": json.loads(row["scopes_json"]),
            "consumed": row["status"] == "consumed",
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _artifact_json(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "artifact_id": row["artifact_id"],
            "kind": row["kind"],
            "path": row["path"],
            "digest": row["digest"],
            "metadata": json.loads(row["metadata_json"] or "{}"),
            "created_at": row["created_at"],
        }

    @staticmethod
    def _trace_json(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "trace_id": row["trace_id"],
            "provider": row["provider"],
            "project": row["project"],
            "console_url": row["console_url"],
            "export_status": row["export_status"],
            "observational": True,
            "updated_at": row["updated_at"],
        }

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
