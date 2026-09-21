"""Dependency-light HTTP control plane for the bounded workflow.

The API is intentionally standard-library based. Nginx can terminate TLS and
proxy SSE, while this process remains the authoritative owner of tenant scope,
idempotency, approvals, and run state.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from agent_platform import KernelStore
from agent_platform.contracts import ApprovalToken
from agent_platform.storage import IdempotencyConflict, TenantScopeError
from project_packs import ProposalToVerifiedChangePack, RepositoryIndex, resolve_project_pack
from services.agent_orchestrator import FakeStructuredModel, ProposalVerifiedWorkflow, build_langgraph_runtime, build_openai_proposal_adapter
from services.delivery_gateway import ReviewArtifactStore
from services.observability import LangSmithClientAdapter, RedactedTraceAdapter
from services.sandbox_worker import BoundedSubprocessSandbox

from .auth import AuthenticationError, TenantAuthenticator


@dataclass(frozen=True)
class ControlApiConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    database: str = ":memory:"
    repository_root: str = "."
    token_secret: str | None = None
    allow_insecure_local: bool = True
    max_body_bytes: int = 1_048_576


@dataclass(frozen=True)
class ControlRuntime:
    workflow: ProposalVerifiedWorkflow
    store: KernelStore
    authenticator: TenantAuthenticator
    config: ControlApiConfig


def build_runtime(config: ControlApiConfig | None = None) -> ControlRuntime:
    config = config or config_from_env()
    if config.database != ":memory:":
        Path(config.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    store = KernelStore(config.database)
    repository = RepositoryIndex(Path(config.repository_root))
    pack = resolve_project_pack()(repository)
    langsmith_client = LangSmithClientAdapter.from_env()
    model = build_openai_proposal_adapter() if os.getenv("AGENT_PROVIDER_MODE", "fake") == "langchain" else FakeStructuredModel()
    sandbox = BoundedSubprocessSandbox(config.repository_root) if os.getenv("AGENT_SANDBOX_MODE", "deterministic") == "process" else None
    artifact_store = ReviewArtifactStore(os.getenv("AGENT_ARTIFACT_DIR", ".local/artifacts"))
    workflow = ProposalVerifiedWorkflow(store, pack, model=model, sandbox=sandbox, tracer=RedactedTraceAdapter(client=langsmith_client), graph_runtime=build_langgraph_runtime(), artifact_store=artifact_store)
    secret = config.token_secret.encode() if config.token_secret else None
    return ControlRuntime(workflow, store, TenantAuthenticator(secret, config.allow_insecure_local), config)


def config_from_env() -> ControlApiConfig:
    profile = os.getenv("AGENT_PROFILE", "local-lite")
    secret = os.getenv("CONTROL_API_TOKEN_SECRET")
    return ControlApiConfig(
        host=os.getenv("CONTROL_API_HOST", "127.0.0.1"),
        port=int(os.getenv("CONTROL_API_PORT", "8000")),
        database=os.getenv("AGENT_STATE_DB", ":memory:"),
        repository_root=os.getenv("AGENT_REPOSITORY_ROOT", "."),
        token_secret=secret,
        allow_insecure_local=profile == "local-lite" and not bool(secret),
        max_body_bytes=int(os.getenv("CONTROL_API_MAX_BODY_BYTES", "1048576")),
    )


def create_server(runtime: ControlRuntime) -> ThreadingHTTPServer:
    class RuntimeServer(ThreadingHTTPServer):
        control_runtime = runtime

        daemon_threads = True
        allow_reuse_address = True

    class Handler(ControlRequestHandler):
        pass

    Handler.runtime = runtime
    return RuntimeServer((runtime.config.host, runtime.config.port), Handler)


class ControlRequestHandler(BaseHTTPRequestHandler):
    runtime: ControlRuntime
    server_version = "ProposalVerifiedControl/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        # Do not write request bodies, bearer tokens, proposals, or source data.
        return

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        try:
            path = urlsplit(self.path).path.rstrip("/") or "/"
            if path == "/healthz":
                self._send(HTTPStatus.OK, {"status": "ok", "profile": "local-lite"})
                return
            if path == "/v1/capabilities":
                self._authenticated_tenant()
                self._send(HTTPStatus.OK, {"profile": "local-lite", "modes": ["plan_only", "verify"], "approval_required_for": ["patch", "deliver"], "sse_replay": True})
                return
            run_id, suffix = self._run_route(path)
            if run_id and suffix in {"", "events", "report"}:
                tenant_id = self._authenticated_tenant()
                try:
                    run = self.runtime.store.get_run(run_id, tenant_id)
                    if suffix == "events":
                        self._send_events(self.runtime.store.events(run_id, tenant_id))
                    elif suffix == "report":
                        self._send(HTTPStatus.OK, {"run": _run_json(run), "report": self.runtime.store.report(run_id, tenant_id)})
                    else:
                        self._send(HTTPStatus.OK, {"run": _run_json(run), "checkpoint": self.runtime.store.checkpoint(run_id, tenant_id), "report": self.runtime.store.report(run_id, tenant_id)})
                except TenantScopeError:
                    self._send_error(HTTPStatus.NOT_FOUND, "run not found")
                return
            self._send_error(HTTPStatus.NOT_FOUND, "route not found")
        except _RequestFinished:
            return

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        try:
            path = urlsplit(self.path).path.rstrip("/")
            tenant_id = self._authenticated_tenant()
            body = self._read_json()
            if path == "/v1/runs":
                proposal = body.get("proposal")
                mode = body.get("mode", "plan_only")
                idempotency_key = body.get("idempotency_key")
                if body.get("tenant_id") and body["tenant_id"] != tenant_id:
                    self._send_error(HTTPStatus.FORBIDDEN, "tenant mismatch")
                    return
                if not isinstance(proposal, str) or not isinstance(idempotency_key, str):
                    self._send_error(HTTPStatus.BAD_REQUEST, "proposal and idempotency_key are required")
                    return
                try:
                    outcome = self.runtime.workflow.run(tenant_id=tenant_id, proposal=proposal, mode=mode, idempotency_key=idempotency_key, quota_limit=body.get("quota_limit"))
                    self._send(HTTPStatus.OK, _outcome_json(outcome))
                except IdempotencyConflict:
                    self._send_error(HTTPStatus.CONFLICT, "idempotency key conflicts with an existing request")
                except (TypeError, ValueError) as exc:
                    self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
                return

            run_id, suffix = self._run_route(path)
            if run_id and suffix == "resume":
                try:
                    run = self.runtime.store.get_run(run_id, tenant_id)
                    approval = _approval_from_json(body.get("approval"))
                    proposal = body.get("proposal")
                    if not isinstance(proposal, str):
                        self._send_error(HTTPStatus.BAD_REQUEST, "proposal is required to resume")
                        return
                    outcome = self.runtime.workflow.run(tenant_id=tenant_id, proposal=proposal, mode=run.mode, idempotency_key=run.idempotency_key, approval=approval, run_id=run_id)
                    self._send(HTTPStatus.OK, _outcome_json(outcome))
                except TenantScopeError:
                    self._send_error(HTTPStatus.NOT_FOUND, "run not found")
                except (KeyError, TypeError, ValueError) as exc:
                    self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
                return
            self._send_error(HTTPStatus.NOT_FOUND, "route not found")
        except _RequestFinished:
            return

    def _authenticated_tenant(self) -> str:
        try:
            return self.runtime.authenticator.authenticate(self.headers.get("Authorization"), self.headers.get("X-Tenant-ID"))
        except AuthenticationError as exc:
            self._send_error(HTTPStatus.UNAUTHORIZED, str(exc))
            raise _RequestFinished

    def _read_json(self) -> Mapping[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_error(HTTPStatus.BAD_REQUEST, "invalid content length")
            raise _RequestFinished
        if length <= 0 or length > self.runtime.config.max_body_bytes:
            self._send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request body is empty or too large")
            raise _RequestFinished
        try:
            value = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_error(HTTPStatus.BAD_REQUEST, "request body must be valid JSON")
            raise _RequestFinished
        if not isinstance(value, Mapping):
            self._send_error(HTTPStatus.BAD_REQUEST, "request body must be an object")
            raise _RequestFinished
        return value

    def _send_events(self, events: tuple[dict[str, Any], ...]) -> None:
        wants_sse = "text/event-stream" in self.headers.get("Accept", "")
        if not wants_sse:
            self._send(HTTPStatus.OK, {"events": events})
            return
        payload = "".join(f"id: {event['event_id']}\nevent: {event['event']}\ndata: {json.dumps(event, sort_keys=True)}\n\n" for event in events).encode()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send(self, status: HTTPStatus, payload: Mapping[str, Any]) -> None:
        encoded = json.dumps(payload, sort_keys=True, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_error(self, status: HTTPStatus, message: str) -> None:
        self._send(status, {"error": message})

    def _run_route(self, path: str) -> tuple[str | None, str]:
        parts = [part for part in path.split("/") if part]
        if len(parts) < 3 or parts[:2] != ["v1", "runs"]:
            return None, ""
        if len(parts) == 3:
            return parts[2], ""
        if len(parts) == 4:
            return parts[2], parts[3]
        return None, ""


class _RequestFinished(Exception):
    pass


def _approval_from_json(value: Any) -> ApprovalToken:
    if not isinstance(value, Mapping):
        raise ValueError("approval token is required")
    return ApprovalToken(str(value["token_id"]), str(value["run_id"]), str(value["tenant_id"]), tuple(str(item) for item in value["scopes"]), str(value["issued_at"]), str(value["expires_at"]), bool(value.get("consumed", False)))


def _run_json(run: Any) -> dict[str, Any]:
    return asdict(run)


def _outcome_json(outcome: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"run": _run_json(outcome.run), "requirements": [asdict(item) for item in outcome.requirements], "evidence": [asdict(item) for item in outcome.evidence], "plan": asdict(outcome.plan) if outcome.plan else None, "report": outcome.report}
    if outcome.approval:
        payload["approval"] = asdict(outcome.approval)
    return payload


def serve(config: ControlApiConfig | None = None) -> None:
    runtime = build_runtime(config)
    server = create_server(runtime)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        runtime.store.close()


if __name__ == "__main__":
    serve()
