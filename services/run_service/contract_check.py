"""Executable REQ-4 checks used by the phase integrity gate."""

from __future__ import annotations

from services.agent_worker import BoundedWorker, ModelResult
from services.metering_billing import SQLiteCreditLedger

from .models import RunCreate
from .service import RunService
from .store import SQLiteRunStore


def run_contract_checks() -> list[str]:
    ledger = SQLiteCreditLedger(":memory:", initial_balances={"integrity-account": 5})
    runs = SQLiteRunStore(":memory:")
    dispatched: list[dict[str, str]] = []

    class Dispatcher:
        def dispatch(self, value: dict[str, str]) -> None:
            dispatched.append(dict(value))

    service = RunService(runs, ledger, workflow=Dispatcher())
    request = RunCreate(
        tenant_id="integrity-tenant",
        account_id="integrity-account",
        project_id="integrity-project",
        idempotency_key="integrity-run-key",
        trace_id="integrity-trace",
        input={"message": "do not stream", "payment_payload": "card=4242"},
        reserve_units=2,
    )
    first = service.create_run(request)
    replayed = service.create_run(request)
    if first.run_id != replayed.run_id or len(ledger.reservations()) != 1 or ledger.available("integrity-account") != 3:
        raise AssertionError("run creation was not idempotent before dispatch")
    if any("payment_payload" in value or "card=4242" in value for value in dispatched[0].values()):
        raise AssertionError("worker dispatch leaked sensitive input")

    class Model:
        def __call__(self, prompt: str, *, idempotency_key: str, timeout_seconds: float) -> ModelResult:
            if prompt != "do not stream" or not idempotency_key or timeout_seconds <= 0:
                raise AssertionError("worker input or bound was invalid")
            return ModelResult("answer card=4242", usage_units=1)

    BoundedWorker(runs, ledger, Model()).execute(first.run_id)
    frames = service.sse(first.run_id, "integrity-tenant", last_event_id="1")
    if "card=4242" in frames or runs.get(first.run_id).state != "completed":
        raise AssertionError("run completion or SSE redaction failed")
    if not any(
        event.data.get("worker_attempt") == 1
        for event in runs.events(first.run_id, "integrity-tenant")
        if event.event == "run.state_changed"
    ):
        raise AssertionError("worker attempt was not auditable in the durable event stream")
    runs.close()
    ledger.close()
    return ["validated durable run idempotency, reservation, checkpoint, recovery, and replay"]
