"""Small SQLite-backed store for review checkpoints and immutable results."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Mapping


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReviewArtifactStore:
    def __init__(self, database: str = ":memory:") -> None:
        self._db = sqlite3.connect(database, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS proposal_reviews (
                review_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                status TEXT NOT NULL,
                payload TEXT NOT NULL,
                checkpoint TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS proposal_review_decisions (
                decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
                review_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                decision TEXT NOT NULL,
                reason TEXT NOT NULL,
                reviewer TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def put(self, review_id: str, tenant_id: str, payload: Mapping[str, Any], *, status: str, checkpoint: Mapping[str, Any]) -> None:
        encoded = json.dumps(dict(payload), sort_keys=True, default=str)
        state = json.dumps(dict(checkpoint), sort_keys=True, default=str)
        now = _now()
        self._db.execute(
            """INSERT INTO proposal_reviews(review_id, tenant_id, status, payload, checkpoint, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(review_id) DO UPDATE SET status=excluded.status, payload=excluded.payload,
               checkpoint=excluded.checkpoint, updated_at=excluded.updated_at""",
            (review_id, tenant_id, status, encoded, state, now, now),
        )
        self._db.commit()

    def get(self, review_id: str, tenant_id: str) -> dict[str, Any]:
        row = self._db.execute("SELECT * FROM proposal_reviews WHERE review_id = ? AND tenant_id = ?", (review_id, tenant_id)).fetchone()
        if row is None:
            raise KeyError("review not found")
        return {
            "review_id": row["review_id"], "tenant_id": row["tenant_id"], "status": row["status"],
            "payload": json.loads(row["payload"]), "checkpoint": json.loads(row["checkpoint"]),
            "created_at": row["created_at"], "updated_at": row["updated_at"],
            "decisions": self.decisions(review_id, tenant_id),
        }

    def decide(self, review_id: str, tenant_id: str, *, decision: str, reason: str, reviewer: str) -> dict[str, Any]:
        if decision not in {"ready", "revise", "blocked"}:
            raise ValueError("decision must be ready, revise, or blocked")
        current = self.get(review_id, tenant_id)
        now = _now()
        self._db.execute(
            "INSERT INTO proposal_review_decisions(review_id, tenant_id, decision, reason, reviewer, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (review_id, tenant_id, decision, reason[:1_000], reviewer[:128], now),
        )
        payload = dict(current["payload"])
        payload["human_decision"] = {"decision": decision, "reason": reason[:1_000], "reviewer": reviewer[:128], "created_at": now}
        self._db.execute("UPDATE proposal_reviews SET status = ?, payload = ?, updated_at = ? WHERE review_id = ? AND tenant_id = ?", (decision, json.dumps(payload, sort_keys=True), now, review_id, tenant_id))
        self._db.commit()
        return self.get(review_id, tenant_id)

    def decisions(self, review_id: str, tenant_id: str) -> list[dict[str, str]]:
        rows = self._db.execute("SELECT decision, reason, reviewer, created_at FROM proposal_review_decisions WHERE review_id = ? AND tenant_id = ? ORDER BY decision_id", (review_id, tenant_id)).fetchall()
        return [{"decision": row["decision"], "reason": row["reason"], "reviewer": row["reviewer"], "created_at": row["created_at"]} for row in rows]
