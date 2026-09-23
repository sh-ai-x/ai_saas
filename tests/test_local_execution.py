from __future__ import annotations

import dataclasses
import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path

from agent_platform import KernelStore
from agent_platform.contracts import ApprovalToken, EvidenceReference, Plan, PlanStep, Requirement
from agent_platform.storage import InvalidApproval
from project_packs.proposal_to_verified_change import ProposalToVerifiedChangePack, RepositoryIndex
from services.agent_orchestrator import ProposalVerifiedWorkflow
from services.control_api.repository_catalog import LocalRepositoryCatalog
from services.delivery_gateway import ReviewArtifactStore
from services.sandbox_worker import IsolatedRepositorySandbox, ProcessSandbox, SandboxPolicy


class FakeTracer:
    def __init__(self) -> None:
        self.finished: list[tuple[str, dict, str | None]] = []
        self.events: list[tuple[str, dict]] = []

    def start_run(self, name: str, attributes: dict) -> str:
        self.events.append((name, attributes))
        return "trace-root-1"

    def record(self, name: str, attributes: dict) -> None:
        self.events.append((name, attributes))

    def finish_run(self, run_id: str, *, outputs: dict | None = None, error: str | None = None) -> None:
        self.finished.append((run_id, outputs or {}, error))


class LocalExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)
        self.repo = self.base / "repo"
        (self.repo / "src").mkdir(parents=True)
        (self.repo / "src" / "app.py").write_text("value = 1\n", encoding="utf-8")
        self._git("init", "-q")
        self._git("add", ".")
        self._git("-c", "user.email=test@example.invalid", "-c", "user.name=test", "commit", "-qm", "initial")
        self.catalog = LocalRepositoryCatalog([str(self.base)])
        self.record = self.catalog.list_repositories()[0]
        self.snapshot = {**dataclasses.asdict(self.record), "commit": self.record.head_commit}
        self.store = KernelStore(":memory:")
        self.tracer = FakeTracer()
        self.changed = False

    def tearDown(self) -> None:
        self.store.close()
        self.catalog.close()
        self.temp_dir.cleanup()

    def _git(self, *args: str) -> None:
        subprocess.run(["git", "-C", str(self.repo), *args], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _workflow(self, *, patcher=None) -> ProposalVerifiedWorkflow:
        return ProposalVerifiedWorkflow(
            self.store,
            ProposalToVerifiedChangePack(RepositoryIndex(self.repo, allowlisted_paths=("src",))),
            tracer=self.tracer,
            artifact_store=ReviewArtifactStore(self.base / "artifacts"),
            patcher=patcher,
        )

    def test_approved_run_is_isolated_and_returns_typed_review_package(self) -> None:
        before_commit = subprocess.check_output(["git", "-C", str(self.repo), "rev-parse", "HEAD"], text=True).strip()
        before_status = subprocess.check_output(["git", "-C", str(self.repo), "status", "--porcelain=v1"], text=True)

        def patcher(root: Path, _plan: Plan) -> None:
            self.changed = True
            (root / "src" / "app.py").write_text("value = 2\n", encoding="utf-8")

        workflow = self._workflow(patcher=patcher)
        proposal = "runtime: python\nREQ-1: update app\nsrc/app.py:1"
        waiting = workflow.run(tenant_id="tenant-a", proposal=proposal, mode="verify", idempotency_key="isolated-1", repository_id=self.record.repository_id, repository_snapshot=self.snapshot)
        self.assertEqual(waiting.run.state, "waiting_approval")
        self.assertEqual(waiting.approval.repository_id, self.record.repository_id)
        self.assertEqual(waiting.approval.branch, self.record.branch)
        self.assertEqual(waiting.approval.commit, self.record.head_commit)
        self.assertRegex(waiting.approval.plan_digest or "", r"^[0-9a-f]{64}$")

        verified = workflow.run(tenant_id="tenant-a", proposal=proposal, mode="verify", idempotency_key="isolated-1", approval=waiting.approval, repository_id=self.record.repository_id, repository_snapshot=self.snapshot, proposal_id=waiting.proposal["proposal_id"])
        self.assertEqual(verified.run.state, "verified")
        self.assertTrue(self.changed)
        self.assertEqual(subprocess.check_output(["git", "-C", str(self.repo), "rev-parse", "HEAD"], text=True).strip(), before_commit)
        self.assertEqual(subprocess.check_output(["git", "-C", str(self.repo), "status", "--porcelain=v1"], text=True), before_status)
        kinds = {item["kind"] for item in verified.proposal["artifacts"]}
        self.assertTrue({"diff", "test", "verification"}.issubset(kinds))
        diff = next(item for item in verified.proposal["artifacts"] if item["kind"] == "diff")
        self.assertEqual(diff["metadata"]["schema_version"], "1.0")
        self.assertEqual(diff["metadata"]["changed_files"], ["src/app.py"])
        self.assertEqual(verified.report["verification_status"], "verified")
        self.assertEqual(verified.report["changed_files"], ["src/app.py"])
        self.assertEqual(verified.proposal["trace"]["trace_id"], "trace-root-1")
        self.assertEqual(len(self.tracer.finished), 2)
        self.assertEqual(self.tracer.finished[-1][0], "trace-root-1")
        self.assertEqual(self.tracer.finished[-1][2], None)
        self.assertEqual(self.tracer.finished[-1][1]["state"], "verified")

    def test_tampered_approval_and_commit_drift_fail_before_patch(self) -> None:
        calls = 0

        def patcher(_root: Path, _plan: Plan) -> None:
            nonlocal calls
            calls += 1

        workflow = self._workflow(patcher=patcher)
        proposal = "runtime: python\nREQ-1: update app\nsrc/app.py:1"
        waiting = workflow.run(tenant_id="tenant-a", proposal=proposal, mode="verify", idempotency_key="approval-1", repository_id=self.record.repository_id, repository_snapshot=self.snapshot)
        with self.assertRaises(InvalidApproval):
            self.store.consume_approval(waiting.approval.token_id, run_id=waiting.run.run_id, tenant_id="tenant-b", scope="patch", current_repository=self.snapshot, plan_digest=waiting.approval.plan_digest)
        self.assertEqual(calls, 0)

        self.store.close()
        self.store = KernelStore(":memory:")
        workflow = self._workflow(patcher=patcher)
        waiting = workflow.run(tenant_id="tenant-a", proposal=proposal, mode="verify", idempotency_key="approval-2", repository_id=self.record.repository_id, repository_snapshot=self.snapshot)
        self.repo.joinpath("src/app.py").write_text("value = 9\n", encoding="utf-8")
        self._git("add", "src/app.py")
        self._git("-c", "user.email=test@example.invalid", "-c", "user.name=test", "commit", "-qm", "drift")
        drifted = workflow.run(tenant_id="tenant-a", proposal=proposal, mode="verify", idempotency_key="approval-2", approval=waiting.approval, repository_id=self.record.repository_id, repository_snapshot=self.snapshot, proposal_id=waiting.proposal["proposal_id"])
        self.assertNotEqual(drifted.run.state, "verified")
        self.assertIn("stale", (drifted.run.error or "").lower())
        self.assertEqual(calls, 0)

    def test_patch_failure_is_terminal_and_reported(self) -> None:
        def failing_patcher(_root: Path, _plan: Plan) -> None:
            raise RuntimeError("patch fixture failed")

        workflow = self._workflow(patcher=failing_patcher)
        proposal = "runtime: python\nREQ-1: update app\nsrc/app.py:1"
        waiting = workflow.run(tenant_id="tenant-a", proposal=proposal, mode="verify", idempotency_key="patch-failure", repository_id=self.record.repository_id, repository_snapshot=self.snapshot)
        failed = workflow.run(tenant_id="tenant-a", proposal=proposal, mode="verify", idempotency_key="patch-failure", approval=waiting.approval, repository_id=self.record.repository_id, repository_snapshot=self.snapshot, proposal_id=waiting.proposal["proposal_id"])
        self.assertEqual(failed.run.state, "failed")
        self.assertIn("patch fixture failed", failed.run.error or "")
        self.assertEqual(failed.proposal["report"]["verification_status"], "failed")


class SandboxPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "repo"
        (self.root / "src").mkdir(parents=True)
        (self.root / "src" / "app.py").write_text("value = 1\n", encoding="utf-8")
        for args in (("init", "-q"), ("add", "."), ("-c", "user.email=x@y", "-c", "user.name=x", "commit", "-qm", "initial")):
            subprocess.run(["git", "-C", str(self.root), *args], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.commit = subprocess.check_output(["git", "-C", str(self.root), "rev-parse", "HEAD"], text=True).strip()
        branch = subprocess.check_output(["git", "-C", str(self.root), "branch", "--show-current"], text=True).strip() or "HEAD"
        self.snapshot = {"repository_id": "repo-1", "branch": branch, "commit": self.commit, "dirty": False}
        evidence = EvidenceReference("REQ-1", "src/app.py", 1, 1, hashlib.sha256(b"value = 1").hexdigest())
        self.plan = Plan("plan-1", (Requirement("REQ-1", "change", "change"),), (PlanStep("step-1", "change", "change", (evidence,), commands=("python3 -m compileall",)),), "python", "verify")
        self.approval = ApprovalToken("token", "run", "tenant-a", ("patch",), "now", "later")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_process_mode_runs_only_declared_bounded_command_with_clean_environment(self) -> None:
        sandbox = ProcessSandbox(self.root, self.snapshot, SandboxPolicy(allowlisted_paths=("src",), allowed_commands=("python3 -m compileall",), max_seconds=5))
        applied = sandbox.apply(self.plan, approval=self.approval)
        self.assertTrue(applied.success)
        tested = sandbox.test(self.plan)
        self.assertTrue(tested.success)
        self.assertEqual(tested.command_results[0]["exit_code"], 0)
        sandbox.close()

        forbidden_plan = dataclasses.replace(self.plan, steps=(dataclasses.replace(self.plan.steps[0], commands=("python3 -m unittest",)),))
        sandbox = ProcessSandbox(self.root, self.snapshot, SandboxPolicy(allowlisted_paths=("src",), allowed_commands=("python3 -m compileall",)))
        self.assertTrue(sandbox.apply(forbidden_plan, approval=self.approval).success)
        forbidden = sandbox.test(forbidden_plan)
        self.assertFalse(forbidden.success)
        self.assertEqual(forbidden.error_code, "command_not_allowlisted")
        sandbox.close()

    def test_deterministic_workspace_does_not_execute_process_commands(self) -> None:
        sandbox = IsolatedRepositorySandbox(self.root, self.snapshot, SandboxPolicy(allowlisted_paths=("src",)))
        self.assertTrue(sandbox.apply(dataclasses.replace(self.plan, steps=(dataclasses.replace(self.plan.steps[0], commands=()),)), approval=self.approval).success)
        result = sandbox.test(dataclasses.replace(self.plan, steps=(dataclasses.replace(self.plan.steps[0], commands=("python3 -m compileall",)),)))
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "deterministic_command_rejected")
        sandbox.close()


if __name__ == "__main__":
    unittest.main()
