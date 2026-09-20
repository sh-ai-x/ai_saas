from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest import skipUnless

from agent_platform.contracts import ApprovalToken, EvidenceReference, Plan, PlanStep, Requirement
from services.agent_orchestrator import LangChainStructuredModelAdapter, build_langgraph_runtime
from services.control_api.auth import AuthenticationError, TenantAuthenticator
from services.control_api.http import ControlApiConfig, ControlRuntime, create_server
from services.delivery_gateway import ReviewArtifactStore
from services.observability import LangSmithClientAdapter, RedactedTraceAdapter
from services.sandbox_worker import BoundedSubprocessSandbox, SandboxPolicy

from agent_platform import KernelStore
from project_packs.proposal_to_verified_change import ProposalToVerifiedChangePack, RepositoryIndex
from services.agent_orchestrator import FakeStructuredModel, ProposalVerifiedWorkflow


class RuntimeBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        (root / "src").mkdir()
        (root / "src" / "app.py").write_text("def change():\n    return 'safe'\n", encoding="utf-8")
        self.store = KernelStore(":memory:")
        self.workflow = ProposalVerifiedWorkflow(self.store, ProposalToVerifiedChangePack(RepositoryIndex(root, allowlisted_paths=("src",))))

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def test_signed_tenant_token_is_scoped_and_tamper_proof(self) -> None:
        auth = TenantAuthenticator(b"test-secret-012345")
        token = auth.issue("tenant-a", now=100)
        self.assertEqual(auth.authenticate(token, "tenant-a", now=101), "tenant-a")
        with self.assertRaises(AuthenticationError):
            auth.authenticate(token[:-1] + "0", "tenant-a", now=101)
        with self.assertRaises(AuthenticationError):
            auth.authenticate(token, "tenant-b", now=101)

    def test_langchain_adapter_accepts_typed_runnable_and_estimates_missing_usage(self) -> None:
        class Runnable:
            def invoke(self, value):
                self.value = value
                return {"data": {"summary": "ok", "requirement_ids": ["REQ-1"], "claims": []}}

        runnable = Runnable()
        adapter = LangChainStructuredModelAdapter(runnable)
        result = adapter.generate("a bounded prompt", context={"requirement_ids": ["REQ-1"]}, schema="v1", idempotency_key="call-1")
        self.assertEqual(result.data["requirement_ids"], ["REQ-1"])
        self.assertTrue(result.estimated)
        self.assertEqual(runnable.value["idempotency_key"], "call-1")

    @skipUnless(__import__("importlib.util").util.find_spec("langgraph"), "optional LangGraph package is not installed")
    def test_real_langgraph_interrupts_before_patch_and_keeps_thread_state(self) -> None:
        runtime = build_langgraph_runtime()
        self.assertIsNotNone(runtime)
        result = runtime.invoke({"run_id": "run-1", "tenant_id": "tenant-a"}, thread_id="run-1")
        self.assertEqual(result["last_node"], "human_approval")
        self.assertEqual(runtime.backend, "langgraph")

    def test_langsmith_adapter_receives_only_redacted_attributes(self) -> None:
        class Client:
            def __init__(self):
                self.calls = []

            def create_run(self, **kwargs):
                self.calls.append(kwargs)

        client = Client()
        tracer = RedactedTraceAdapter(client=LangSmithClientAdapter(client))
        tracer.record("run.event", {"token": "secret-value", "nested": {"api_key": "another-secret"}, "safe": "ok"})
        self.assertEqual(len(client.calls), 1)
        encoded = json.dumps(client.calls[0], sort_keys=True)
        self.assertNotIn("secret-value", encoded)
        self.assertNotIn("another-secret", encoded)

    def test_http_api_runs_plan_only_and_replays_sse_events(self) -> None:
        runtime = ControlRuntime(self.workflow, self.store, TenantAuthenticator(None, True), ControlApiConfig(host="127.0.0.1", port=0, repository_root=self.temp_dir.name))
        server = create_server(runtime)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            connection = HTTPConnection(host, port)
            proposal = "runtime: python\nREQ-1: inspect source\nsrc/app.py:1-2"
            body = json.dumps({"tenant_id": "tenant-a", "proposal": proposal, "mode": "plan_only", "idempotency_key": "http-1"})
            connection.request("POST", "/v1/runs", body, {"Content-Type": "application/json", "X-Tenant-ID": "tenant-a"})
            response = connection.getresponse()
            payload = json.loads(response.read())
            self.assertEqual(response.status, 200)
            run_id = payload["run"]["run_id"]
            connection.request("GET", f"/v1/runs/{run_id}/events", headers={"X-Tenant-ID": "tenant-a", "Accept": "text/event-stream"})
            response = connection.getresponse()
            events = response.read().decode()
            self.assertEqual(response.status, 200)
            self.assertIn("event: run.queued", events)
            self.assertIn("event: run.state_changed", events)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_subprocess_sandbox_runs_only_allowlisted_commands_in_copy(self) -> None:
        root = Path(self.temp_dir.name)
        plan = Plan("p", (Requirement("REQ-1", "compile", "compile"),), (PlanStep("s", "compile", "compile", (EvidenceReference("REQ-1", "src/app.py", 1, 2, "a"),)),), "python", "verify")
        sandbox = BoundedSubprocessSandbox(root, SandboxPolicy(allowlisted_paths=("src",), allowed_commands=("python3 -m compileall",), max_seconds=5))
        approval = ApprovalToken("a", "r", "t", ("patch",), "2026-01-01T00:00:00+00:00", "2099-01-01T00:00:00+00:00")
        self.assertTrue(sandbox.apply(plan, approval=approval).success)
        result = sandbox.test(plan)
        self.assertTrue(result.success, result.stderr)
        self.assertFalse((root / "src" / "__pycache__").exists())

    def test_artifact_store_is_atomic_and_redacted(self) -> None:
        store = ReviewArtifactStore(Path(self.temp_dir.name) / "artifacts")
        artifact = store.write("run-1", {"report": {"status": "plan_only"}, "secret": "do-not-store"})
        content = Path(artifact.path).read_text(encoding="utf-8")
        self.assertEqual(len(artifact.digest), 64)
        self.assertNotIn("do-not-store", content)
        self.assertEqual(Path(artifact.path).stat().st_mode & 0o777, 0o600)

    def test_workflow_persists_a_redacted_review_artifact_before_terminal_state(self) -> None:
        artifact_store = ReviewArtifactStore(Path(self.temp_dir.name) / "workflow-artifacts")
        workflow = ProposalVerifiedWorkflow(self.store, ProposalToVerifiedChangePack(RepositoryIndex(Path(self.temp_dir.name), allowlisted_paths=("src",))), artifact_store=artifact_store)
        outcome = workflow.run(tenant_id="tenant-a", proposal="runtime: python\nREQ-1: inspect\nsrc/app.py:1-2", mode="plan_only", idempotency_key="artifact-run")
        self.assertEqual(outcome.run.state, "plan_only")
        persisted = [event for event in self.store.events(outcome.run.run_id, "tenant-a") if event["event"] == "artifact.persisted"]
        self.assertEqual(len(persisted), 1)
        self.assertTrue(Path(persisted[0]["payload"]["path"]).exists())


if __name__ == "__main__":
    unittest.main()
