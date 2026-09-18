from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from foundation.config import validate_profile
from services.agent_worker import BoundedWorker, FargateSpotBoundary, ModelResult
from services.metering_billing import QuotaExceeded, QuotaPolicy, SQLiteCreditLedger, SQLiteQuotaCounter
from services.observability import InMemorySpanExporter, SampledTracer
from services.run_service import RunCreate, RunService, SQLiteRunStore


def free_values() -> dict[str, str]:
    return {
        "APP_ENV": "local",
        "DEPLOYMENT_PROFILE": "free-portfolio",
        "APP_BASE_URL": "http://localhost:8080",
        "DATABASE_URL": "postgresql://foundation@localhost:5432/foundation",
        "APP_SECRET_KEY": "x" * 64,
        "CONTRACT_VERSION": "v1",
        "PAYMENT_PROVIDER": "mock",
        "MOCK_PAYMENTS_ENABLED": "true",
        "WORKFLOW_PROVIDER": "local",
        "PAID_INFRASTRUCTURE": "false",
        "AWS_WORKER_ENABLED": "false",
        "RUN_QUOTA_MAX_RUNS": "2",
        "RUN_QUOTA_MAX_UNITS": "4",
        "RUN_QUOTA_PERIOD_SECONDS": "86400",
        "OTEL_ENABLED": "true",
        "OTEL_SAMPLE_RATE": "0.1",
        "OTEL_EXPORTER": "memory",
    }


class QuotaAndPauseTests(unittest.TestCase):
    def test_counter_is_idempotent_and_pauses_without_reserving_credits(self) -> None:
        now = [1_700_000_000.0]
        quota = SQLiteQuotaCounter(
            ":memory:",
            policy=QuotaPolicy(max_runs=1, max_units=2, period_seconds=86400),
            clock=lambda: now[0],
        )
        ledger = SQLiteCreditLedger(":memory:", initial_balances={"account-1": 10})
        runs = SQLiteRunStore(":memory:")
        service = RunService(runs, ledger, quota=quota)
        request = RunCreate(
            tenant_id="tenant-1",
            account_id="account-1",
            project_id="project-1",
            idempotency_key="quota-key-1",
            trace_id="trace-quota-1",
            input={"message": "hello"},
            reserve_units=2,
        )
        first = service.create_run(request)
        second_request = RunCreate(
            **{**request.__dict__, "idempotency_key": "quota-key-2", "trace_id": "trace-quota-2"}
        )
        second = service.create_run(second_request)

        self.assertEqual(first.state, "queued")
        self.assertEqual(second.state, "quota_paused")
        self.assertEqual(ledger.available("account-1"), 8)
        self.assertEqual(quota.snapshot("tenant-1").run_count, 1)
        self.assertEqual(quota.snapshot("tenant-1").unit_count, 2)
        with self.assertRaises(QuotaExceeded):
            quota.reserve("tenant-1", "run-third", 1)

        now[0] += 86400
        resumed = service.create_run(second_request)
        self.assertEqual(resumed.state, "queued")
        self.assertEqual(ledger.available("account-1"), 6)

        runs.close()
        ledger.close()

    def test_profile_exposes_explicit_cost_and_telemetry_limits(self) -> None:
        config = validate_profile(free_values())
        self.assertEqual(config.quota_max_runs, 2)
        self.assertEqual(config.quota_max_units, 4)
        self.assertEqual(config.otel_sample_rate, 0.1)
        self.assertNotIn("APP_SECRET_KEY", config.values)


class ObservabilityTests(unittest.TestCase):
    def test_sampling_redacts_prompts_payment_data_and_secrets(self) -> None:
        exporter = InMemorySpanExporter()
        tracer = SampledTracer(sample_rate=1.0, exporter=exporter, random_value=lambda: 0.0)
        with tracer.start_span(
            "run.execute",
            {
                "run_id": "run-1",
                "prompt": "do not export this prompt",
                "payment_payload": "payment-fixture",
                "authorization": "auth-fixture",
            },
        ) as span:
            span.set_attribute("output", "safe result")

        self.assertEqual(len(exporter.spans), 1)
        encoded = json.dumps(exporter.spans[0], sort_keys=True)
        self.assertNotIn("do not export this prompt", encoded)
        self.assertNotIn("payment-fixture", encoded)
        self.assertNotIn("auth-fixture", encoded)
        self.assertIn("REDACTED", encoded)

    def test_zero_sample_rate_does_not_export(self) -> None:
        exporter = InMemorySpanExporter()
        tracer = SampledTracer(sample_rate=0.0, exporter=exporter, random_value=lambda: 0.0)
        with tracer.start_span("run.execute", {"run_id": "run-1"}):
            pass
        self.assertEqual(exporter.spans, ())

    def test_worker_emits_sampled_call_span_without_request_content(self) -> None:
        exporter = InMemorySpanExporter()
        tracer = SampledTracer(sample_rate=1.0, exporter=exporter, random_value=lambda: 0.0)
        ledger = SQLiteCreditLedger(":memory:", initial_balances={"account-otel": 2})
        runs = SQLiteRunStore(":memory:")
        run = RunService(runs, ledger).create_run(
            RunCreate(
                tenant_id="tenant-otel",
                account_id="account-otel",
                project_id="project-otel",
                idempotency_key="otel-request-1",
                trace_id="otel-trace-1",
                input={"message": "private request body"},
            )
        )

        def model(_prompt: str, *, idempotency_key: str, timeout_seconds: float) -> ModelResult:
            del idempotency_key, timeout_seconds
            return ModelResult("safe output")

        BoundedWorker(runs, ledger, model, tracer=tracer).execute(run.run_id)
        encoded = json.dumps(exporter.spans, sort_keys=True)
        self.assertIn("agent.model_call", encoded)
        self.assertNotIn("private request body", encoded)
        runs.close()
        ledger.close()


class AwsRunTaskContractTests(unittest.TestCase):
    def test_run_task_request_is_spot_arm_public_egress_without_inbound_route(self) -> None:
        boundary = FargateSpotBoundary(
            cluster_arn="arn:aws:ecs:us-east-1:000000000000:cluster/foundation",
            task_definition="foundation-worker:1",
            subnet_id="subnet-public-1",
            security_group_id="sg-worker-no-ingress",
        )
        request = boundary.run_task_request("run-1", "tenant-1", "trace-1")
        self.assertEqual(request["capacityProviderStrategy"], [{"capacityProvider": "FARGATE_SPOT", "weight": 1}])
        self.assertEqual(request["networkConfiguration"]["awsvpcConfiguration"]["assignPublicIp"], "ENABLED")
        self.assertEqual(request["overrides"]["containerOverrides"][0]["name"], "agent-worker")
        self.assertNotIn("portMappings", request["overrides"]["containerOverrides"][0])


class EvidenceCaptureTests(unittest.TestCase):
    def test_evaluator_capture_is_redacted_and_covers_required_scenarios(self) -> None:
        from evaluators.capture import capture_evidence

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "evidence.json"
            result = capture_evidence(output)
            document = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(result, document)
        self.assertEqual(document["schema_version"], "v1")
        self.assertTrue(all(item["status"] == "passed" for item in document["scenarios"]))
        self.assertEqual(
            {item["id"] for item in document["scenarios"]},
            {"auth", "admin", "payment-replay", "ledger-concurrency", "run-recovery", "profile-boundaries"},
        )
        self.assertNotIn("prompt", json.dumps(document).lower())


if __name__ == "__main__":
    unittest.main()
