from __future__ import annotations

import subprocess
import json
import socket
import threading
import tempfile
import unittest
from pathlib import Path

from agent_platform import KernelStore
from agent_platform.storage import IdempotencyConflict, TenantScopeError
from project_packs.proposal_to_verified_change import ProposalToVerifiedChangePack, RepositoryIndex
from services.agent_orchestrator import ProposalVerifiedWorkflow
from services.control_api.repository_catalog import LocalRepositoryCatalog
from services.control_api import ControlApiConfig, build_runtime
from services.control_api.http import ControlRequestHandler
from services.delivery_gateway import ReviewArtifactStore


class LocalProposalPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)
        self.repo = self.base / "repo"
        (self.repo / "src").mkdir(parents=True)
        (self.repo / "src" / "app.py").write_text("return_value = 'safe'\n", encoding="utf-8")
        self._git("init", "-q")
        self._git("add", ".")
        self._git("-c", "user.email=test@example.invalid", "-c", "user.name=test", "commit", "-qm", "initial")
        self.catalog = LocalRepositoryCatalog([str(self.base)], scope_database=str(self.base / "scopes.sqlite"))
        record = self.catalog.list_repositories()[0]
        self.record = record
        self.snapshot = {**record.__dict__, "commit": record.head_commit}
        self.read_scope = self.catalog.authorize_read("tenant-a", repository_id=record.repository_id)
        self.store_path = self.base / "proposal.sqlite"
        self.store = KernelStore(str(self.store_path))
        self.workflow = ProposalVerifiedWorkflow(
            self.store,
            ProposalToVerifiedChangePack(RepositoryIndex(self.repo, allowlisted_paths=("src",))),
            artifact_store=ReviewArtifactStore(self.base / "artifacts"),
        )
        self.proposal = "runtime: python\nREQ-1: update the app\nsrc/app.py:1"

    def tearDown(self) -> None:
        self.store.close()
        self.catalog.close()
        self.temp_dir.cleanup()

    def _git(self, *args: str) -> None:
        subprocess.run(["git", "-C", str(self.repo), *args], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _workflow(self) -> ProposalVerifiedWorkflow:
        return self.workflow.for_repository(str(self.repo))

    def test_create_list_reopen_and_restart_preserve_review_outputs(self) -> None:
        outcome = self._workflow().run(
            tenant_id="tenant-a",
            proposal=self.proposal,
            mode="plan_only",
            idempotency_key="proposal-1",
            repository_id=self.record.repository_id,
            repository_snapshot=self.snapshot,
        )
        self.assertEqual(outcome.run.state, "plan_only")
        proposal_id = outcome.proposal["proposal_id"]
        self.assertEqual(self.store.list_proposals("tenant-a", self.record.repository_id)[0]["proposal_id"], proposal_id)
        self.assertEqual(outcome.proposal["branch"], self.record.branch)
        self.assertEqual(outcome.proposal["commit"], self.record.head_commit)
        self.assertEqual(outcome.proposal["requirements"][0]["requirement_id"], "REQ-1")
        self.assertEqual(outcome.proposal["evidence"][0]["path"], "src/app.py")
        self.assertIsNotNone(outcome.proposal["plan"])
        self.assertTrue(outcome.proposal["artifacts"])
        self.store.close()

        reopened = KernelStore(str(self.store_path))
        view = reopened.proposal_view(proposal_id, "tenant-a", current_repository=self.snapshot)
        self.assertEqual(view["run"]["state"], "plan_only")
        self.assertEqual(view["evidence"][0]["content_hash"], outcome.proposal["evidence"][0]["content_hash"])
        self.assertEqual(view["plan"]["plan_id"], outcome.proposal["plan"]["plan_id"])
        reopened.close()
        self.store = KernelStore(str(self.store_path))

    def test_commit_drift_marks_evidence_stale_and_blocks_verified_claim(self) -> None:
        waiting = self._workflow().run(
            tenant_id="tenant-a",
            proposal=self.proposal,
            mode="verify",
            idempotency_key="proposal-drift",
            repository_id=self.record.repository_id,
            repository_snapshot=self.snapshot,
        )
        proposal_id = waiting.proposal["proposal_id"]
        self.repo.joinpath("src/app.py").write_text("return_value = 'changed'\n", encoding="utf-8")
        self._git("add", "src/app.py")
        self._git("-c", "user.email=test@example.invalid", "-c", "user.name=test", "commit", "-qm", "changed")
        current = self.catalog.get(self.record.repository_id)
        current_snapshot = {**current.__dict__, "commit": current.head_commit}

        view = self._workflow().refresh_proposal(proposal_id, "tenant-a", current_snapshot)
        self.assertTrue(view["stale_evidence"])
        self.assertTrue(view["evidence"][0]["stale"])
        self.assertEqual(view["report"], None)
        self.assertNotEqual(view["run"]["state"], "verified")

    def test_tenant_isolation_and_idempotent_replay_are_durable(self) -> None:
        first = self.store.create_proposal(
            tenant_id="tenant-a",
            repository=self.snapshot,
            proposal=self.proposal,
            mode="plan_only",
            idempotency_key="same-key",
        )
        replay = self.store.create_proposal(
            tenant_id="tenant-a",
            repository=self.snapshot,
            proposal=self.proposal,
            mode="plan_only",
            idempotency_key="same-key",
        )
        self.assertEqual(first["proposal_id"], replay["proposal_id"])
        with self.assertRaises(IdempotencyConflict):
            self.store.create_proposal(
                tenant_id="tenant-a",
                repository=self.snapshot,
                proposal="different",
                mode="plan_only",
                idempotency_key="same-key",
            )
        with self.assertRaises(TenantScopeError):
            self.store.proposal_view(first["proposal_id"], "tenant-b")
        self.assertEqual(self.store.list_proposals("tenant-b", self.record.repository_id), ())


class LocalProposalApiContractTests(unittest.TestCase):
    def test_create_list_open_and_restart_are_repository_and_tenant_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repo = base / "repo"
            repo.mkdir()
            (repo / "src").mkdir()
            (repo / "src" / "app.py").write_text("value = 1\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.email=test@example.invalid", "-c", "user.name=test", "commit", "-qm", "initial"], check=True)
            config = ControlApiConfig(database=str(base / "state.sqlite"), repository_root=str(base), allow_insecure_local=True)
            runtime = build_runtime(config)
            repository = runtime.catalog.list_repositories()[0]

            status, repositories = self._request(runtime, "GET", "/v1/repositories", "tenant-a")
            self.assertEqual(status, 200)
            self.assertEqual(repositories["repositories"][0]["repository"]["repository_id"], repository.repository_id)

            status, authorized = self._request(
                runtime,
                "POST",
                "/v1/repositories/authorize",
                "tenant-a",
                {"permission": "read_analysis", "repository_id": repository.repository_id},
            )
            self.assertEqual(status, 200)
            read_scope = authorized["scope"]["scope_id"]
            proposal_body = {
                "proposal": "runtime: python\nREQ-1: update\nsrc/app.py:1",
                "mode": "plan_only",
                "idempotency_key": "api-proposal-1",
                "read_scope_id": read_scope,
            }
            status, created = self._request(runtime, "POST", f"/v1/repositories/{repository.repository_id}/proposals", "tenant-a", proposal_body)
            self.assertEqual(status, 201)
            proposal_id = created["proposal"]["proposal_id"]

            status, listed = self._request(runtime, "GET", f"/v1/repositories/{repository.repository_id}/proposals", "tenant-a")
            self.assertEqual(status, 200)
            self.assertEqual(listed["proposals"][0]["proposal_id"], proposal_id)
            status, opened = self._request(runtime, "GET", f"/v1/repositories/{repository.repository_id}/proposals/{proposal_id}", "tenant-a")
            self.assertEqual(status, 200)
            self.assertEqual(opened["proposal"]["run"]["state"], "plan_only")
            status, write_authorized = self._request(
                runtime,
                "POST",
                "/v1/repositories/authorize",
                "tenant-a",
                {"permission": "write_patch", "repository_id": repository.repository_id, "read_scope_id": read_scope},
            )
            self.assertEqual(status, 200)
            write_scope = write_authorized["scope"]["scope_id"]
            status, waiting = self._request(
                runtime,
                "POST",
                f"/v1/repositories/{repository.repository_id}/proposals/{proposal_id}/resume",
                "tenant-a",
                {"write_scope_id": write_scope},
            )
            self.assertEqual(status, 200)
            self.assertEqual(waiting["run"]["state"], "waiting_approval")
            status, verified = self._request(
                runtime,
                "POST",
                f"/v1/repositories/{repository.repository_id}/proposals/{proposal_id}/resume",
                "tenant-a",
                {"write_scope_id": write_scope, "approval": waiting["approval"]},
            )
            self.assertEqual(status, 200)
            self.assertEqual(verified["run"]["state"], "verified")
            runtime.catalog.close()
            runtime.store.close()

            restarted = build_runtime(config)
            status, reopened = self._request(restarted, "GET", f"/v1/repositories/{repository.repository_id}/proposals/{proposal_id}", "tenant-a")
            self.assertEqual(status, 200)
            self.assertEqual(reopened["proposal"]["proposal_id"], proposal_id)
            status, denied = self._request(restarted, "GET", f"/v1/repositories/{repository.repository_id}/proposals/{proposal_id}", "tenant-b")
            self.assertEqual(status, 403)
            self.assertIn("error", denied)
            restarted.catalog.close()
            restarted.store.close()

    @staticmethod
    def _request(runtime, method: str, path: str, tenant: str, body: dict | None = None) -> tuple[int, dict]:
        payload = b"" if body is None else json.dumps(body).encode()
        request = (
            f"{method} {path} HTTP/1.0\r\n"
            "Host: local\r\n"
            f"X-Tenant-ID: {tenant}\r\n"
            f"Content-Length: {len(payload)}\r\n"
            "Connection: close\r\n\r\n"
        ).encode() + payload
        left, right = socket.socketpair()
        right.settimeout(2)
        right.sendall(request)
        right.shutdown(socket.SHUT_WR)

        class LocalServer:
            pass

        Handler = type("Handler", (ControlRequestHandler,), {"runtime": runtime})
        try:
            worker = threading.Thread(target=Handler, args=(left, ("local", 0), LocalServer))
            worker.start()
            response = b""
            while b"\r\n\r\n" not in response:
                response += right.recv(16_384)
            header, body_bytes = response.split(b"\r\n\r\n", 1)
            content_length = int(next(line.split(b":", 1)[1] for line in header.splitlines() if line.lower().startswith(b"content-length:")))
            while len(body_bytes) < content_length:
                body_bytes += right.recv(16_384)
            worker.join(timeout=2)
            response = header + b"\r\n\r\n" + body_bytes
        finally:
            left.close()
            right.close()
        head, encoded = response.split(b"\r\n\r\n", 1)
        status = int(head.splitlines()[0].split()[1])
        return status, json.loads(encoded)


if __name__ == "__main__":
    unittest.main()
