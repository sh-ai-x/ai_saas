from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from services.agent_worker import (
    BoundedInngestWorkflow,
    BoundedWorker,
    FargateSpotBoundary,
    ModelResult,
    WorkerInterrupted,
)
from services.metering_billing import SQLiteCreditLedger
from services.run_service import (
    IdempotencyConflict,
    InngestDispatcher,
    RunCreate,
    RunService,
    SQLiteRunStore,
)


class RecordingWorkflow:
    def __init__(self) -> None:
        self.requests: list[dict[str, str]] = []

    def dispatch(self, request: dict[str, str]) -> None:
        self.requests.append(request)


class IdempotentModel:
    def __init__(self, *, approval_once: bool = False) -> None:
        self.calls: list[str] = []
        self.results: dict[str, ModelResult] = {}
        self.approval_once = approval_once

    def __call__(self, prompt: str, *, idempotency_key: str, timeout_seconds: float) -> ModelResult:
        del prompt, timeout_seconds
        self.calls.append(idempotency_key)
        if idempotency_key not in self.results:
            if self.approval_once:
                self.approval_once = False
                self.results[idempotency_key] = ModelResult(
                    output="safe approval request", usage_units=1, approval_id="approval-1"
                )
            else:
                self.results[idempotency_key] = ModelResult(output="safe answer", usage_units=1)
        return self.results[idempotency_key]


class RunWorkerStreamingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = SQLiteCreditLedger(":memory:", initial_balances={"account-1": 10})
        self.runs = SQLiteRunStore(":memory:")
        self.workflow = RecordingWorkflow()
        self.service = RunService(self.runs, self.ledger, workflow=self.workflow)

    def tearDown(self) -> None:
        self.runs.close()
        self.ledger.close()

    def request(self, **overrides: object) -> RunCreate:
        values: dict[str, object] = {
            "tenant_id": "tenant-1",
            "account_id": "account-1",
            "project_id": "project-1",
            "idempotency_key": "request-key-1",
            "trace_id": "trace-id-1",
            "input": {"message": "hello", "payment_payload": "card=4242"},
            "reserve_units": 4,
        }
        values.update(overrides)
        return RunCreate(**values)  # type: ignore[arg-type]

    def test_creation_is_idempotent_and_reserves_before_dispatch(self) -> None:
        first = self.service.create_run(self.request())
        second = self.service.create_run(self.request())

        self.assertEqual(first.run_id, second.run_id)
        self.assertEqual(self.ledger.available("account-1"), 6)
        self.assertEqual(len(self.ledger.reservations()), 1)
        self.assertEqual(len(self.workflow.requests), 1)
        self.assertEqual(first.state, "queued")

        with self.assertRaises(IdempotencyConflict):
            self.service.create_run(self.request(input={"message": "changed"}))

    def test_worker_checkpoint_recovery_reuses_model_key_and_does_not_double_spend(self) -> None:
        run = self.service.create_run(self.request(reserve_units=3))
        model = IdempotentModel()
        interrupted = {"value": True}

        def interrupt_after_model(_run_id: str, _step: int, _result: ModelResult) -> None:
            if interrupted["value"]:
                interrupted["value"] = False
                raise WorkerInterrupted("spot interruption")

        worker = BoundedWorker(self.runs, self.ledger, model, after_model=interrupt_after_model)
        with self.assertRaises(WorkerInterrupted):
            worker.execute(run.run_id)

        self.assertEqual(self.runs.get(run.run_id).state, "running")
        checkpoint = self.runs.checkpoint(run.run_id)
        self.assertIsNotNone(checkpoint)
        self.assertTrue(checkpoint.inflight_key)

        worker.execute(run.run_id)
        completed = self.runs.get(run.run_id)
        self.assertEqual(completed.state, "completed")
        self.assertEqual(model.calls, [model.calls[0], model.calls[0]])
        self.assertEqual(self.ledger.available("account-1"), 9)
        self.assertEqual(len(self.ledger.commits()), 1)

    def test_recovery_after_commit_before_terminal_state_is_idempotent(self) -> None:
        run = self.service.create_run(self.request(reserve_units=3))
        model = IdempotentModel()
        interrupted = {"value": True}

        def interrupt_after_commit(_run_id: str, _used_units: int) -> None:
            if interrupted["value"]:
                interrupted["value"] = False
                raise WorkerInterrupted("interrupted after metering commit")

        worker = BoundedWorker(self.runs, self.ledger, model, after_commit=interrupt_after_commit)
        with self.assertRaises(WorkerInterrupted):
            worker.execute(run.run_id)
        worker.execute(run.run_id)
        self.assertEqual(self.runs.get(run.run_id).state, "completed")
        self.assertEqual(len(model.calls), 1)
        self.assertEqual(len(self.ledger.commits()), 1)

    def test_interrupted_worker_recovers_from_reopened_durable_stores(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_path = str(Path(directory) / "runs.sqlite3")
            ledger_path = str(Path(directory) / "credits.sqlite3")
            ledger = SQLiteCreditLedger(ledger_path, initial_balances={"account-1": 4})
            runs = SQLiteRunStore(run_path)
            request = self.request(idempotency_key="durable-key", reserve_units=2)
            run = RunService(runs, ledger).create_run(request)
            model = IdempotentModel()
            interrupted = {"value": True}

            def interrupt(_run_id: str, _step: int, _result: ModelResult) -> None:
                if interrupted["value"]:
                    interrupted["value"] = False
                    raise WorkerInterrupted("spot interruption")

            with self.assertRaises(WorkerInterrupted):
                BoundedWorker(runs, ledger, model, after_model=interrupt).execute(run.run_id)
            runs.close()
            ledger.close()

            reopened_ledger = SQLiteCreditLedger(ledger_path, initial_balances={"account-1": 4})
            reopened_runs = SQLiteRunStore(run_path)
            BoundedWorker(reopened_runs, reopened_ledger, model).execute(run.run_id)
            self.assertEqual(reopened_runs.get(run.run_id).state, "completed")
            self.assertEqual(reopened_ledger.available("account-1"), 3)
            reopened_runs.close()
            reopened_ledger.close()

    def test_approval_and_cancellation_are_explicit_terminal_or_paused_states(self) -> None:
        run = self.service.create_run(self.request(reserve_units=2))
        model = IdempotentModel(approval_once=True)
        worker = BoundedWorker(self.runs, self.ledger, model)
        worker.execute(run.run_id)
        self.assertEqual(self.runs.get(run.run_id).state, "waiting_approval")
        self.assertEqual(self.runs.checkpoint(run.run_id).approval_id, "approval-1")  # type: ignore[union-attr]

        self.service.approve(run.run_id, "tenant-1")
        worker.execute(run.run_id)
        self.assertEqual(self.runs.get(run.run_id).state, "completed")

        cancelled = self.service.create_run(self.request(idempotency_key="request-key-2", reserve_units=2))
        self.service.cancel(cancelled.run_id, "tenant-1")
        self.assertEqual(self.runs.get(cancelled.run_id).state, "cancelled")
        self.assertEqual(self.ledger.available("account-1"), 9)

    def test_sse_replays_persisted_events_after_last_id_and_redacts_sensitive_values(self) -> None:
        run = self.service.create_run(self.request())
        model = IdempotentModel()
        BoundedWorker(self.runs, self.ledger, model).execute(run.run_id)

        replay = self.service.replay(run.run_id, "tenant-1", last_event_id="1")
        self.assertTrue(replay)
        self.assertTrue(all(event.sequence > 1 for event in replay))
        frames = self.service.sse(run.run_id, "tenant-1", last_event_id="1")
        self.assertIn("id:", frames)
        self.assertIn("data:", frames)
        self.assertNotIn("card=4242", frames)
        for event in replay:
            json.loads(event.data_json)

    def test_fargate_spot_boundary_is_worker_only_and_has_no_inbound_route(self) -> None:
        boundary = FargateSpotBoundary(
            cluster_arn="arn:aws:ecs:local:000000000000:cluster/foundation",
            task_definition="foundation-worker:1",
            subnet_id="subnet-local",
            security_group_id="sg-local",
        )
        request = boundary.task_request("run-1", "tenant-1")
        self.assertEqual(request["capacity_provider"], "FARGATE_SPOT")
        self.assertEqual(request["architecture"], "arm64")
        self.assertEqual(request["inbound_rules"], "none")
        self.assertNotIn("url", request)

    def test_inngest_dispatch_is_bounded_and_contains_no_prompt(self) -> None:
        sent: list[dict[str, object]] = []
        dispatcher = InngestDispatcher(sent.append, max_steps=2, max_model_calls=2, max_runtime_seconds=30)
        dispatcher.dispatch(
            {
                "run_id": "run-1",
                "tenant_id": "tenant-1",
                "trace_id": "trace-1",
                "reservation_id": "reservation-1",
                "idempotency_key": "request-key-1",
            }
        )
        self.assertEqual(sent[0]["name"], "run.requested")
        self.assertEqual(sent[0]["limits"], {"max_steps": 2, "max_model_calls": 2, "max_runtime_seconds": 30})
        self.assertNotIn("input", sent[0])
        with self.assertRaises(ValueError):
            dispatcher.dispatch({"run_id": "run-1"})

        run = self.service.create_run(self.request())
        worker_event = {"name": "run.requested", "data": self.service.request_payload(run)}
        result = BoundedInngestWorkflow(BoundedWorker(self.runs, self.ledger, IdempotentModel())).handle(worker_event)
        self.assertEqual(result.state, "completed")


if __name__ == "__main__":
    unittest.main()
