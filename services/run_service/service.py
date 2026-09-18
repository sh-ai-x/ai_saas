"""Run creation, authorization, reservation, approval, and replay boundary."""

from __future__ import annotations

import uuid
from typing import Mapping

from services.metering_billing.ports import CreditReservationPort
from services.metering_billing.quota import QuotaCounterPort, QuotaExceeded

from .models import Run, RunCreate, RunEvent
from .store import SQLiteRunStore
from .workflow import WorkflowDispatcher


class RunService:
    def __init__(
        self,
        store: SQLiteRunStore,
        credits: CreditReservationPort,
        *,
        workflow: WorkflowDispatcher | None = None,
        quota: QuotaCounterPort | None = None,
    ) -> None:
        self._store = store
        self._credits = credits
        self._workflow = workflow
        self._quota = quota

    def create_run(self, request: RunCreate) -> Run:
        candidate_id = f"run-{uuid.uuid4().hex}"
        run, _created = self._store.create(candidate_id, request)
        quota_admitted = False
        if not _created:
            if run.reservation_id is not None or run.state not in {"queued", "quota_paused"}:
                return self._store.get(run.run_id)
            if run.state == "quota_paused":
                if self._quota is None:
                    return self._store.get(run.run_id)
                try:
                    self._quota.reserve(request.tenant_id, run.run_id, request.reserve_units)
                except QuotaExceeded:
                    return self._store.get(run.run_id)
                run = self._store.transition(
                    run.run_id,
                    "queued",
                    payload={"reason": "quota_window_available"},
                )
                quota_admitted = True
        if self._quota is not None:
            if not quota_admitted:
                try:
                    self._quota.reserve(request.tenant_id, run.run_id, request.reserve_units)
                except QuotaExceeded as exc:
                    return self._store.pause_quota(run.run_id, dimension=exc.dimension, limit=exc.limit)
        try:
            reservation = self._credits.reserve(
                request.tenant_id,
                request.account_id,
                run.run_id,
                request.reserve_units,
                idempotency_key=f"run-reserve:{request.tenant_id}:{request.idempotency_key}",
            )
            run = self._store.attach_reservation(run.run_id, reservation.reservation_id)
            if self._workflow is not None:
                self._workflow.dispatch(
                    {
                        "run_id": run.run_id,
                        "tenant_id": run.tenant_id,
                        "trace_id": run.trace_id,
                        "reservation_id": reservation.reservation_id,
                        "idempotency_key": request.idempotency_key,
                    }
                )
        except Exception:
            if self._quota is not None:
                self._quota.release(run.run_id)
            if run.reservation_id:
                self._credits.release(run.reservation_id, idempotency_key=f"run-release:{run.run_id}")
            self._store.fail(run.run_id, "workflow dispatch failed")
            raise
        return self._store.get(run.run_id)

    def status(self, run_id: str, tenant_id: str) -> Run:
        return self._store.get(run_id, tenant_id)

    def approve(self, run_id: str, tenant_id: str) -> Run:
        return self._store.approve(run_id, tenant_id)

    def cancel(self, run_id: str, tenant_id: str) -> Run:
        run = self._store.mark_cancel_requested(run_id, tenant_id)
        if run.state == "cancelled" and run.reservation_id:
            self._credits.release(run.reservation_id, idempotency_key=f"run-release:{run.run_id}")
        return run

    def replay(self, run_id: str, tenant_id: str, *, last_event_id: str | None = None) -> tuple[RunEvent, ...]:
        after = 0
        if last_event_id:
            try:
                after = int(last_event_id)
            except ValueError:
                after = self._store.sequence_for_event(run_id, last_event_id)
        return self._store.events(run_id, tenant_id, after_sequence=after)

    def sse(self, run_id: str, tenant_id: str, *, last_event_id: str | None = None) -> str:
        events = self.replay(run_id, tenant_id, last_event_id=last_event_id)
        return "".join(
            f"id: {event.event_id}\n"
            f"event: {event.event}\n"
            f"data: {event.data_json}\n\n"
            for event in events
        )

    @staticmethod
    def request_payload(run: Run) -> Mapping[str, str]:
        """Build a safe worker message without copying the prompt/input."""

        return {
            "run_id": run.run_id,
            "tenant_id": run.tenant_id,
            "trace_id": run.trace_id,
            "reservation_id": run.reservation_id or "",
            "idempotency_key": run.idempotency_key,
        }
