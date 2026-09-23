"""Dependency-light control plane with local repository authorization."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from email.parser import BytesParser
from email.policy import default as email_default_policy
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import parse_qs, urlsplit

from agent_platform import KernelStore
from agent_platform.contracts import ApprovalToken
from agent_platform.storage import IdempotencyConflict, StaleProposalError, TenantScopeError
from project_packs.proposal_to_verified_change import ProposalToVerifiedChangePack, RepositoryIndex
from services.agent_orchestrator import (
    FakeStructuredModel,
    ProposalVerifiedWorkflow,
    build_langgraph_runtime,
    build_openai_proposal_adapter,
)
from services.delivery_gateway import ReviewArtifactStore
from services.observability import LangSmithClientAdapter, RedactedTraceAdapter

from .auth import AuthenticationError, TenantAuthenticator
from .repository_catalog import (
    READ_ANALYSIS,
    WRITE_PATCH,
    LocalRepositoryCatalog,
    RepositoryCatalogError,
    parse_repository_roots,
)


@dataclass(frozen=True)
class ControlApiConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    database: str = ":memory:"
    repository_root: str = "."
    repository_roots: tuple[str, ...] = ()
    repository_scope_database: str | None = None
    token_secret: str | None = None
    allow_insecure_local: bool = True
    max_body_bytes: int = 1_048_576


@dataclass(frozen=True)
class ControlRuntime:
    workflow: ProposalVerifiedWorkflow
    store: KernelStore
    authenticator: TenantAuthenticator
    config: ControlApiConfig
    catalog: LocalRepositoryCatalog | None = None


def build_runtime(config: ControlApiConfig | None = None, *, environment: Mapping[str, str] | None = None) -> ControlRuntime:
    config = config or config_from_env()
    values = {**os.environ, **(environment or {})}
    if config.database != ":memory:":
        Path(config.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    store = KernelStore(config.database)
    repository = RepositoryIndex(Path(config.repository_root))
    pack = ProposalToVerifiedChangePack(repository)
    langsmith_client = LangSmithClientAdapter.from_env(
        project=values.get("LANGSMITH_PROJECT", "proposal-to-verified-change"),
        environment=values,
    )
    provider_mode = values.get("AGENT_PROVIDER_MODE", "fake").strip().lower()
    if provider_mode in {"langchain", "openai"}:
        model = build_openai_proposal_adapter(
            model_name=values.get("OPENAI_MODEL") or None,
            api_key=values.get("OPENAI_API_KEY") or None,
        )
    else:
        model = FakeStructuredModel()
    artifact_dir = values.get("AGENT_ARTIFACT_DIR", "").strip()
    workflow = ProposalVerifiedWorkflow(
        store,
        pack,
        model=model,
        tracer=RedactedTraceAdapter(client=langsmith_client, console_url=values.get("LANGSMITH_CONSOLE_URL", "https://smith.langchain.com")),
        graph_runtime=build_langgraph_runtime(),
        artifact_store=ReviewArtifactStore(artifact_dir) if artifact_dir else None,
    )
    configured_import_root = values.get("LOCAL_REPOSITORY_IMPORT_ROOT", "").strip()
    if configured_import_root:
        import_root = Path(configured_import_root).expanduser()
    elif config.database != ":memory:":
        import_root = Path(config.database).expanduser().resolve().parent / "imported-repositories"
    else:
        import_root = Path("/tmp/ai-saas-imported-repositories")
    import_root.mkdir(parents=True, exist_ok=True)
    root_values: tuple[str, ...] | str = config.repository_roots
    if not root_values:
        root_values = values.get("LOCAL_REPOSITORY_ROOTS", "")
    if not root_values and config.repository_root and config.repository_root != ".":
        root_values = (config.repository_root,)
    configured_roots = tuple(parse_repository_roots(root_values)) if isinstance(root_values, str) else tuple(root_values)
    canonical_import_root = import_root.resolve(strict=True)
    configured_canonical_roots = tuple(Path(root).resolve(strict=True) for root in configured_roots)
    if not any(canonical_import_root == root or canonical_import_root.is_relative_to(root) for root in configured_canonical_roots):
        configured_roots = (*configured_roots, str(import_root))
    scope_database = config.repository_scope_database or config.database
    catalog = LocalRepositoryCatalog(configured_roots, scope_database=scope_database, import_root=import_root)
    secret = config.token_secret.encode() if config.token_secret else None
    return ControlRuntime(workflow, store, TenantAuthenticator(secret, config.allow_insecure_local), config, catalog)


def config_from_env() -> ControlApiConfig:
    profile = os.getenv("AGENT_PROFILE", "local-lite")
    secret = os.getenv("CONTROL_API_TOKEN_SECRET")
    return ControlApiConfig(
        host=os.getenv("CONTROL_API_HOST", "127.0.0.1"),
        port=int(os.getenv("CONTROL_API_PORT", "8000")),
        database=os.getenv("AGENT_STATE_DB", ":memory:"),
        repository_root=os.getenv("AGENT_REPOSITORY_ROOT", "."),
        repository_roots=parse_repository_roots(os.getenv("LOCAL_REPOSITORY_ROOTS", "")),
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
    server_version = "ProposalVerifiedControl/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        try:
            self._get()
        except _RequestFinished:
            return
        except RepositoryCatalogError as exc:
            self._catalog_error(exc)
        except StaleProposalError:
            self._send_error(HTTPStatus.CONFLICT, "stale evidence; re-analysis is required")
        except IdempotencyConflict:
            self._send_error(HTTPStatus.CONFLICT, "idempotency key conflicts with an existing request")
        except TenantScopeError:
            self._send_error(HTTPStatus.NOT_FOUND, "run not found")

    def _get(self) -> None:
        path = urlsplit(self.path).path.rstrip("/") or "/"
        if path == "/healthz":
            self._send(HTTPStatus.OK, {"status": "ok", "profile": "local-lite"})
            return
        tenant_id = self._authenticated_tenant()
        if path == "/v1/capabilities":
            self._send(
                HTTPStatus.OK,
                {
                    "profile": "local-lite",
                    "modes": ["plan_only", "verify"],
                    "approval_required_for": ["patch", "deliver"],
                    "repository_scopes": [READ_ANALYSIS, WRITE_PATCH],
                },
            )
            return
        if path in {"/v1/repositories", "/v1/change-assurance/repositories"}:
            if self.runtime.catalog is None:
                raise RepositoryCatalogError("repository_catalog_unconfigured")
            self._repositories(tenant_id)
            return
        repository_id, suffix = self._repository_route(path)
        if repository_id and suffix == "":
            if self.runtime.catalog is None:
                raise RepositoryCatalogError("repository_catalog_unconfigured")
            record = self.runtime.catalog.get(repository_id)
            self._send(HTTPStatus.OK, {"repository": self.runtime.catalog.public_record(record), "authorization": self.runtime.catalog.authorization_state(tenant_id, repository_id)})
            return
        proposal_repository_id, proposal_id, proposal_suffix = self._proposal_route(path)
        if proposal_repository_id:
            self._proposal_get(tenant_id, proposal_repository_id, proposal_id, proposal_suffix)
            return
        run_id, suffix = self._run_route(path)
        if run_id and suffix in {"", "events", "report"}:
            try:
                run = self.runtime.store.get_run(run_id, tenant_id)
                if suffix == "events":
                    self._send(HTTPStatus.OK, {"events": self.runtime.store.events(run_id, tenant_id)})
                elif suffix == "report":
                    self._send(HTTPStatus.OK, {"run": _run_json(run), "report": self.runtime.store.report(run_id, tenant_id)})
                else:
                    proposal = None
                    if run.proposal_id and self.runtime.catalog is not None and run.repository_id:
                        record = self.runtime.catalog.get(run.repository_id)
                        proposal = self.runtime.workflow.for_repository(record.canonical_path).refresh_proposal(run.proposal_id, tenant_id, asdict(record))
                    self._send(HTTPStatus.OK, {"run": _run_json(run), "checkpoint": self.runtime.store.checkpoint(run_id, tenant_id), "report": self.runtime.store.report(run_id, tenant_id), "proposal": proposal})
            except TenantScopeError:
                self._send_error(HTTPStatus.NOT_FOUND, "run not found")
            return
        self._send_error(HTTPStatus.NOT_FOUND, "route not found")

    def _repositories(self, tenant_id: str) -> None:
        query = parse_qs(urlsplit(self.path).query)
        raw_path = query.get("path", [None])[0]
        raw_name = query.get("name", [None])[0]
        if raw_path and raw_name:
            raise RepositoryCatalogError("repository_query_ambiguous")
        if raw_path:
            records = (self.runtime.catalog.resolve(raw_path),)
        elif raw_name:
            records = self.runtime.catalog.list_repositories(name=raw_name)
        else:
            records = self.runtime.catalog.list_repositories()
        self._send(
            HTTPStatus.OK,
            {
                "repositories": [
                    {
                        "repository": self.runtime.catalog.public_record(record),
                        "authorization": self.runtime.catalog.authorization_state(tenant_id, record.repository_id),
                    }
                    for record in records
                ]
            },
        )

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        try:
            self._post()
        except _RequestFinished:
            return
        except RepositoryCatalogError as exc:
            self._catalog_error(exc)
        except StaleProposalError:
            self._send_error(HTTPStatus.CONFLICT, "stale evidence; re-analysis is required")
        except IdempotencyConflict:
            self._send_error(HTTPStatus.CONFLICT, "idempotency key conflicts with an existing request")
        except TenantScopeError:
            self._send_error(HTTPStatus.NOT_FOUND, "run not found")
        except (KeyError, TypeError, ValueError) as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))

    def _post(self) -> None:
        path = urlsplit(self.path).path.rstrip("/")
        tenant_id = self._authenticated_tenant()
        if path in {"/v1/repositories/import", "/v1/change-assurance/repositories/import"}:
            name, files = self._read_repository_import()
            self._import_repository(tenant_id, name, files)
            return
        body = self._read_json()
        if path in {"/v1/repositories/authorize", "/v1/change-assurance/repositories/authorize"}:
            if self.runtime.catalog is None:
                raise RepositoryCatalogError("repository_catalog_unconfigured")
            self._authorize_repository(tenant_id, body)
            return
        proposal_repository_id, proposal_id, proposal_suffix = self._proposal_route(path)
        if proposal_repository_id:
            self._proposal_post(tenant_id, proposal_repository_id, proposal_id, proposal_suffix, body)
            return
        if path in {"/v1/runs", "/v1/change-assurance/runs"}:
            repository_id = self._authorize_analysis_request(tenant_id, body)
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
                snapshot = None
                workflow = self.runtime.workflow
                if repository_id and self.runtime.catalog is not None:
                    record = self.runtime.catalog.get(repository_id)
                    snapshot = asdict(record)
                    workflow = workflow.for_repository(record.canonical_path)
                outcome = workflow.run(tenant_id=tenant_id, proposal=proposal, mode=mode, idempotency_key=idempotency_key, quota_limit=body.get("quota_limit"), repository_id=repository_id, repository_snapshot=snapshot)
                self._send(HTTPStatus.OK, outcome_json(outcome))
            except IdempotencyConflict:
                self._send_error(HTTPStatus.CONFLICT, "idempotency key conflicts with an existing request")
            except (TypeError, ValueError) as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        run_id, suffix = self._run_route(path)
        if run_id and suffix == "resume":
            run = self.runtime.store.get_run(run_id, tenant_id)
            bound_repository_id = run.result.get("repository_id") if isinstance(run.result, Mapping) else None
            requested_repository_id = body.get("repository_id")
            if bound_repository_id and requested_repository_id and requested_repository_id != bound_repository_id:
                raise RepositoryCatalogError("repository_identity_mismatch")
            repository_id = self._authorize_write_request(tenant_id, body, bound_repository_id if isinstance(bound_repository_id, str) else None)
            approval = _approval_from_json(body.get("approval"))
            proposal = body.get("proposal")
            if not isinstance(proposal, str):
                self._send_error(HTTPStatus.BAD_REQUEST, "proposal is required to resume")
                return
            workflow = self.runtime.workflow
            snapshot = None
            if repository_id and self.runtime.catalog is not None:
                record = self.runtime.catalog.get(repository_id)
                snapshot = asdict(record)
                workflow = workflow.for_repository(record.canonical_path)
            outcome = workflow.run(tenant_id=tenant_id, proposal=proposal, mode="verify", idempotency_key=run.idempotency_key, approval=approval, run_id=run_id, repository_id=repository_id, repository_snapshot=snapshot, proposal_id=run.proposal_id)
            self._send(HTTPStatus.OK, outcome_json(outcome))
            return
        self._send_error(HTTPStatus.NOT_FOUND, "route not found")

    def _authorize_repository(self, tenant_id: str, body: Mapping[str, Any]) -> None:
        permission = body.get("permission", body.get("scope"))
        repository_id = body.get("repository_id")
        raw_path = body.get("path")
        if permission == READ_ANALYSIS:
            scope = self.runtime.catalog.authorize_read(tenant_id, repository_id=repository_id, path=raw_path)
        elif permission == WRITE_PATCH:
            read_scope_id = body.get("read_scope_id")
            if not isinstance(read_scope_id, str):
                raise RepositoryCatalogError("read_scope_required")
            scope = self.runtime.catalog.authorize_write(tenant_id, repository_id=repository_id, path=raw_path, read_scope_id=read_scope_id)
        else:
            raise RepositoryCatalogError("scope_invalid")
        record = self.runtime.catalog.get(scope.repository_id)
        self.runtime.store.register_repository(tenant_id, asdict(record))
        self._send(HTTPStatus.OK, {"repository": self.runtime.catalog.public_record(record), "scope": asdict(scope), "authorization": self.runtime.catalog.authorization_state(tenant_id, scope.repository_id)})

    def _import_repository(self, tenant_id: str, name: str, files: Sequence[tuple[str, bytes]]) -> None:
        if self.runtime.catalog is None:
            raise RepositoryCatalogError("repository_catalog_unconfigured")
        record = self.runtime.catalog.import_snapshot(name, files)
        self.runtime.store.register_repository(tenant_id, asdict(record))
        self._send(
            HTTPStatus.CREATED,
            {
                "repository": self.runtime.catalog.public_record(record),
                "authorization": self.runtime.catalog.authorization_state(tenant_id, record.repository_id),
            },
        )

    def _authorize_analysis_request(self, tenant_id: str, body: Mapping[str, Any]) -> str | None:
        repository_id = body.get("repository_id")
        if not repository_id:
            return None
        if self.runtime.catalog is None:
            raise RepositoryCatalogError("repository_catalog_unconfigured")
        if not isinstance(repository_id, str):
            raise RepositoryCatalogError("repository_identity_required")
        scope_id = body.get("read_scope_id")
        if not isinstance(scope_id, str):
            raise RepositoryCatalogError("read_scope_required")
        self.runtime.catalog.require_read(tenant_id, repository_id, scope_id)
        return repository_id

    def _authorize_write_request(self, tenant_id: str, body: Mapping[str, Any], bound_repository_id: str | None = None) -> str | None:
        repository_id = body.get("repository_id") or bound_repository_id
        if not repository_id:
            return None
        if self.runtime.catalog is None:
            raise RepositoryCatalogError("repository_catalog_unconfigured")
        if not isinstance(repository_id, str):
            raise RepositoryCatalogError("repository_identity_required")
        scope_id = body.get("write_scope_id")
        if not isinstance(scope_id, str):
            raise RepositoryCatalogError("write_scope_required")
        self.runtime.catalog.require_write(tenant_id, repository_id, scope_id)
        return repository_id

    def _proposal_get(self, tenant_id: str, repository_id: str, proposal_id: str | None, suffix: str) -> None:
        if self.runtime.catalog is None:
            raise RepositoryCatalogError("repository_catalog_unconfigured")
        record = self.runtime.catalog.get(repository_id)
        self._require_read_scope(tenant_id, repository_id)
        if proposal_id is None:
            workflow = self.runtime.workflow.for_repository(record.canonical_path)
            for item in self.runtime.store.list_proposals(tenant_id, repository_id):
                workflow.refresh_proposal(item["proposal_id"], tenant_id, asdict(record))
            self._send(HTTPStatus.OK, {"repository": self.runtime.catalog.public_record(record), "proposals": list(self.runtime.store.list_proposals(tenant_id, repository_id))})
            return
        if suffix:
            raise RepositoryCatalogError("proposal_route_invalid")
        view = self.runtime.workflow.for_repository(record.canonical_path).refresh_proposal(proposal_id, tenant_id, asdict(record))
        if view["repository_id"] != repository_id:
            raise RepositoryCatalogError("repository_identity_mismatch")
        self._send(HTTPStatus.OK, {"repository": self.runtime.catalog.public_record(record), "proposal": view})

    def _proposal_post(self, tenant_id: str, repository_id: str, proposal_id: str | None, suffix: str, body: Mapping[str, Any]) -> None:
        if self.runtime.catalog is None:
            raise RepositoryCatalogError("repository_catalog_unconfigured")
        record = self.runtime.catalog.get(repository_id)
        snapshot = asdict(record)
        if proposal_id is None and suffix == "":
            self._require_read_scope(tenant_id, repository_id, body.get("read_scope_id"))
            proposal = body.get("proposal")
            idempotency_key = body.get("idempotency_key")
            mode = str(body.get("mode", "plan_only"))
            if not isinstance(proposal, str) or not isinstance(idempotency_key, str):
                raise ValueError("proposal and idempotency_key are required")
            workflow = self.runtime.workflow.for_repository(record.canonical_path)
            outcome = workflow.run(
                tenant_id=tenant_id,
                proposal=proposal,
                mode=mode,
                idempotency_key=idempotency_key,
                quota_limit=body.get("quota_limit"),
                repository_id=repository_id,
                repository_snapshot=snapshot,
            )
            self._send(HTTPStatus.CREATED, outcome_json(outcome))
            return
        if not proposal_id or suffix not in {"resume", "reanalyze"}:
            raise RepositoryCatalogError("proposal_route_invalid")
        view = self.runtime.workflow.for_repository(record.canonical_path).refresh_proposal(proposal_id, tenant_id, snapshot)
        if view["repository_id"] != repository_id:
            raise RepositoryCatalogError("repository_identity_mismatch")
        stored_run = view.get("run") or {}
        if suffix == "resume":
            self._require_write_scope(tenant_id, repository_id, body.get("write_scope_id"))
            proposal = body.get("proposal") or self.runtime.store.proposal_input(proposal_id, tenant_id)
            approval = _approval_from_json(body["approval"]) if body.get("approval") is not None else None
            if not isinstance(proposal, str):
                raise ValueError("proposal is required to resume")
            workflow = self.runtime.workflow.for_repository(record.canonical_path)
            resume_run_id = str(stored_run["run_id"])
            resume_key = str(stored_run["idempotency_key"])
            if stored_run.get("ledger_state", stored_run.get("state")) == "plan_only":
                resume_run_id = None
                resume_key = str(body.get("idempotency_key") or f"{resume_key}:verify")
            outcome = workflow.run(
                tenant_id=tenant_id,
                proposal=proposal,
                mode="verify",
                idempotency_key=resume_key,
                approval=approval,
                run_id=resume_run_id,
                repository_id=repository_id,
                repository_snapshot=snapshot,
                proposal_id=proposal_id,
            )
            self._send(HTTPStatus.OK, outcome_json(outcome))
            return
        self._require_read_scope(tenant_id, repository_id, body.get("read_scope_id"))
        proposal = body.get("proposal") or self.runtime.store.proposal_input(proposal_id, tenant_id)
        idempotency_key = body.get("idempotency_key")
        if not isinstance(proposal, str) or not isinstance(idempotency_key, str):
            raise ValueError("proposal and idempotency_key are required for re-analysis")
        workflow = self.runtime.workflow.for_repository(record.canonical_path)
        outcome = workflow.run(
            tenant_id=tenant_id,
            proposal=proposal,
            mode=str(body.get("mode", "plan_only")),
            idempotency_key=idempotency_key,
            repository_id=repository_id,
            repository_snapshot=snapshot,
            proposal_id=proposal_id,
        )
        self._send(HTTPStatus.CREATED, outcome_json(outcome))

    def _require_read_scope(self, tenant_id: str, repository_id: str, scope_id: str | None = None) -> None:
        if self.runtime.catalog is None:
            raise RepositoryCatalogError("repository_catalog_unconfigured")
        if isinstance(scope_id, str) and scope_id:
            self.runtime.catalog.require_read(tenant_id, repository_id, scope_id)
            return
        if not self.runtime.catalog.authorization_state(tenant_id, repository_id).get(READ_ANALYSIS):
            raise RepositoryCatalogError("read_scope_required")

    def _require_write_scope(self, tenant_id: str, repository_id: str, scope_id: str | None) -> None:
        if self.runtime.catalog is None:
            raise RepositoryCatalogError("repository_catalog_unconfigured")
        if not isinstance(scope_id, str) or not scope_id:
            raise RepositoryCatalogError("write_scope_required")
        self.runtime.catalog.require_write(tenant_id, repository_id, scope_id)

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

    def _read_repository_import(self) -> tuple[str, tuple[tuple[str, bytes], ...]]:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("multipart/form-data"):
            self._send_error(HTTPStatus.BAD_REQUEST, "repository import must use multipart/form-data")
            raise _RequestFinished
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_error(HTTPStatus.BAD_REQUEST, "invalid content length")
            raise _RequestFinished
        max_bytes = 25 * 1024 * 1024
        if length <= 0 or length > max_bytes:
            self._send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "repository import is empty or too large")
            raise _RequestFinished
        raw = self.rfile.read(length)
        message = BytesParser(policy=email_default_policy).parsebytes(
            b"MIME-Version: 1.0\r\nContent-Type: " + content_type.encode("utf-8") + b"\r\n\r\n" + raw
        )
        if not message.is_multipart():
            self._send_error(HTTPStatus.BAD_REQUEST, "invalid repository import payload")
            raise _RequestFinished
        fields: dict[str, list[str]] = {}
        files: list[tuple[str | None, bytes]] = []
        for part in message.iter_parts():
            field_name = part.get_param("name", header="content-disposition")
            if not isinstance(field_name, str):
                continue
            payload = part.get_payload(decode=True) or b""
            filename = part.get_filename()
            if filename is not None:
                files.append((filename, payload))
            else:
                fields.setdefault(field_name, []).append(payload.decode("utf-8"))
        try:
            name = fields["repository_name"][0]
            manifest = json.loads(fields["manifest"][0])
        except (KeyError, IndexError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("repository import requires repository_name and manifest") from exc
        if not isinstance(manifest, list) or len(manifest) != len(files):
            raise ValueError("repository import manifest does not match uploaded files")
        normalized: list[tuple[str, bytes]] = []
        for item, (_, payload) in zip(manifest, files):
            if not isinstance(item, Mapping) or not isinstance(item.get("path"), str):
                raise ValueError("repository import manifest contains an invalid path")
            normalized.append((item["path"], payload))
        return name, tuple(normalized)

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

    def _catalog_error(self, exc: RepositoryCatalogError) -> None:
        status = HTTPStatus.FORBIDDEN if exc.code.startswith("scope_") or exc.code in {"tenant_invalid", "repository_identity_mismatch", "write_scope_missing_read_parent", "read_scope_required", "write_scope_required"} else HTTPStatus.BAD_REQUEST
        self._send_error(status, exc.code)

    @staticmethod
    def _repository_route(path: str) -> tuple[str | None, str]:
        parts = [part for part in path.split("/") if part]
        for prefix in (("v1", "repositories"), ("v1", "change-assurance", "repositories")):
            if parts[: len(prefix)] != list(prefix) or len(parts) < len(prefix) + 1:
                continue
            if len(parts) == len(prefix) + 1:
                return parts[-1], ""
        return None, ""

    @staticmethod
    def _run_route(path: str) -> tuple[str | None, str]:
        parts = [part for part in path.split("/") if part]
        if len(parts) >= 3 and parts[:2] == ["v1", "runs"]:
            if len(parts) == 3:
                return parts[2], ""
            if len(parts) == 4:
                return parts[2], parts[3]
        if len(parts) >= 4 and parts[:3] == ["v1", "change-assurance", "runs"]:
            if len(parts) == 4:
                return parts[3], ""
            if len(parts) == 5:
                return parts[3], parts[4]
        return None, ""

    @staticmethod
    def _proposal_route(path: str) -> tuple[str | None, str | None, str]:
        parts = [part for part in path.split("/") if part]
        prefixes = (("v1", "repositories"), ("v1", "change-assurance", "repositories"))
        for prefix in prefixes:
            if parts[: len(prefix)] != list(prefix):
                continue
            offset = len(prefix)
            if len(parts) == offset + 2 and parts[offset + 1] == "proposals":
                return parts[offset], None, ""
            if len(parts) == offset + 3 and parts[offset + 1] == "proposals":
                return parts[offset], parts[offset + 2], ""
            if len(parts) == offset + 4 and parts[offset + 1] == "proposals" and parts[offset + 3] in {"resume", "reanalyze"}:
                return parts[offset], parts[offset + 2], parts[offset + 3]
        return None, None, ""


class _RequestFinished(Exception):
    pass


def _approval_from_json(value: Any) -> ApprovalToken:
    if not isinstance(value, Mapping):
        raise ValueError("approval token is required")
    return ApprovalToken(
        str(value["token_id"]),
        str(value["run_id"]),
        str(value["tenant_id"]),
        tuple(str(item) for item in value["scopes"]),
        str(value["issued_at"]),
        str(value["expires_at"]),
        bool(value.get("consumed", False)),
        value.get("repository_id"),
        value.get("branch"),
        value.get("commit"),
        value.get("plan_digest"),
        value.get("proposal_id"),
    )


def _run_json(run: Any) -> dict[str, Any]:
    return asdict(run)


def outcome_json(outcome: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"run": _run_json(outcome.run), "requirements": [asdict(item) for item in outcome.requirements], "evidence": [asdict(item) for item in outcome.evidence], "plan": asdict(outcome.plan) if outcome.plan else None, "report": outcome.report}
    if outcome.approval:
        payload["approval"] = asdict(outcome.approval)
    if getattr(outcome, "proposal", None) is not None:
        payload["proposal"] = outcome.proposal
    return payload


def serve(config: ControlApiConfig | None = None) -> None:
    runtime = build_runtime(config)
    server = create_server(runtime)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        if runtime.catalog is not None:
            runtime.catalog.close()
        runtime.store.close()


if __name__ == "__main__":
    serve()
