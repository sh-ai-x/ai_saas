"""Runnable local HTTP surface for the foundation vertical slice.

The local profile exposes the same logical seams as the production design:
Google session validation, tenant-scoped admin operations, provider-neutral
mock billing, durable runs, and replayable SSE. It uses only stdlib HTTP and
SQLite so a fresh clone can exercise the flow without cloud credentials.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
from dataclasses import asdict
from email.parser import BytesParser
from email.policy import default as email_default_policy
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping, Sequence
from urllib.parse import parse_qs, urlparse

from services.billing.errors import InsufficientCredits
from services.control_api import outcome_json
from services.control_api.repository_catalog import READ_ANALYSIS, WRITE_PATCH, RepositoryCatalogError
from agent_platform.contracts import ApprovalToken
from agent_platform.storage import IdempotencyConflict, TenantScopeError as ProposalTenantScopeError
from services.identity_tenant import AuthorizationDenied, OAuthCallbackError
from services.run_service.errors import RunError, RunNotFound, TenantMismatch

from .config import ConfigError, merged_environment, validate_profile
from .local_runtime import DEMO_ACCOUNT_ID, DEMO_TENANT_ID, LocalRuntime


MAX_BODY_BYTES = 256 * 1024
MAX_REPOSITORY_IMPORT_BYTES = 25 * 1024 * 1024


class LocalServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], runtime: LocalRuntime) -> None:
        super().__init__(address, FoundationHandler)
        self.runtime = runtime


class FoundationHandler(BaseHTTPRequestHandler):
    server_version = "ai-saas-foundation/0.2"

    @property
    def runtime(self) -> LocalRuntime:
        return self.server.runtime  # type: ignore[attr-defined]

    def _json(
        self,
        status: int,
        payload: Mapping[str, object],
        extra_headers: Mapping[str, str] | None = None,
    ) -> None:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _sse(self, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _error(self, status: int, code: str, message: str) -> None:
        self._json(status, {"error": code, "message": message})

    def _raw_body(self) -> bytes:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("invalid content length") from exc
        if length < 0 or length > MAX_BODY_BYTES:
            raise ValueError("request body is too large")
        return self.rfile.read(length)

    @staticmethod
    def _decode_body(raw: bytes) -> dict[str, Any]:
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("request body must be a JSON object") from exc
        if not isinstance(value, dict):
            raise ValueError("request body must be a JSON object")
        return value

    def _body(self) -> dict[str, Any]:
        return self._decode_body(self._raw_body())

    def _tenant(self) -> str:
        supplied = self.headers.get("X-Tenant-Id")
        if supplied:
            return supplied
        return self.runtime.session.active_tenant_id or DEMO_TENANT_ID

    def _request_tenant(self, expected: str | None = None) -> str:
        tenant_id = self._tenant()
        self.runtime.authenticate_demo(tenant_id)
        if expected is not None and expected != tenant_id:
            raise TenantMismatch("tenant access denied")
        return tenant_id

    def _session(self):
        session_id = self.headers.get("X-Session-Id")
        if not session_id:
            cookie = SimpleCookie()
            cookie.load(self.headers.get("Cookie", ""))
            session_id = cookie.get("foundation_session").value if cookie.get("foundation_session") else "demo-session"
        if session_id != self.runtime.session.session_id:
            raise AuthorizationDenied("session access denied")
        return self.runtime.identity.authenticate(self.runtime.session)

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        try:
            self._get()
        except Exception as exc:  # boundary converts expected failures safely
            self._handle_error(exc)

    def _get(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path == "/healthz":
            self._json(
                200,
                {
                    "status": "ok",
                    "contract_version": self.runtime.config.contract_version,
                    "deployment_profile": self.runtime.config.deployment_profile,
                },
            )
            return
        if path == "/v1/contracts":
            self._json(
                200,
                {
                    "contract_version": "v1",
                    "families": ["rest", "sse", "events", "providers"],
                    "provider_policy": "domain consumes normalized events only",
                    "local_runtime": "sqlite + stdlib http + mock provider",
                },
            )
            return
        if path == "/v1/change-assurance/capabilities":
            self._request_tenant()
            self._json(200, self.runtime.proposal_capabilities())
            return
        if path in {"/v1/change-impact/catalog", "/v1/proposal-review/catalog"}:
            self._request_tenant()
            self._json(200, self.runtime.proposal_control.proposal_review.catalog())
            return
        review_id, review_suffix = self._review_route(path)
        if review_id:
            tenant_id = self._request_tenant()
            if review_suffix:
                self._error(404, "not_found", "review route not found")
                return
            self._json(200, self.runtime.proposal_control.proposal_review.detail(review_id, tenant_id))
            return
        if path in {"/v1/repositories", "/v1/change-assurance/repositories"}:
            self._get_repositories(parsed.query)
            return
        proposal_repository_id, proposal_id, proposal_suffix = self._proposal_route(path)
        if proposal_repository_id:
            self._get_proposals(proposal_repository_id, proposal_id, proposal_suffix, parsed.query)
            return
        if path.startswith("/v1/repositories/") or path.startswith("/v1/change-assurance/repositories/"):
            self._get_repository(path)
            return
        if path == "/v1/auth/session":
            self._request_tenant(self.runtime.session.active_tenant_id)
            self._session()
            self._json(200, self.runtime.auth_payload())
            return
        if path == "/v1/agent/providers":
            self._json(
                200,
                {
                    "contract_version": "v1",
                    "provider": self.runtime.config.agent_provider,
                    "model": self.runtime.config.agent_model,
                    "max_output_tokens": self.runtime.config.agent_max_output_tokens,
                    "timeout_seconds": self.runtime.config.agent_timeout_seconds,
                    "configured": self.runtime.config.agent_provider == "local"
                    or bool(self.runtime.values.get("AGENT_API_KEY", "").strip()),
                },
            )
            return
        if path == "/v1/billing/providers":
            self._json(
                200,
                {
                    "contract_version": "v1",
                    "provider": self.runtime.config.payment_provider,
                    "sandbox": self.runtime.config.payment_sandbox,
                    "mock_enabled": self.runtime.config.mock_payments_enabled,
                },
            )
            return
        if path == "/v1/auth/google/start":
            self._json(200, self.runtime.start_google())
            return
        if path == "/v1/admin/users":
            actor = self._session()
            users = self.runtime.admin.search_users(actor, self._tenant())
            self._json(200, {"users": [self._admin_user(user) for user in users]})
            return
        if path.startswith("/v1/runs/"):
            self._get_run(path, parsed.query)
            return
        if path.startswith("/v1/change-assurance/runs/"):
            self._get_proposal_run(path)
            return
        if path.startswith("/v1/billing/orders/"):
            order_id = path.removeprefix("/v1/billing/orders/")
            tenant_id = self._request_tenant()
            order = self.runtime.billing_store.order(order_id)
            if order.tenant_id != tenant_id:
                raise TenantMismatch("tenant access denied")
            self._json(200, self._order(order))
            return
        if path == "/v1/billing/balance":
            self._request_tenant()
            account_id = parse_qs(parsed.query).get("account_id", ["demo-account"])[0]
            if account_id != DEMO_ACCOUNT_ID:
                raise TenantMismatch("account access denied")
            self._json(
                200,
                {
                    "account_id": account_id,
                    "run_credits_available": self.runtime.credit_ledger.available(account_id),
                    "payment_credits": self.runtime.billing_store.balance(account_id),
                    "entitlement": self.runtime.billing_store.entitlement(account_id).plan,
                },
            )
            return
        self._error(404, "not_found", "route not found")

    def _get_run(self, path: str, query: str) -> None:
        parts = path.split("/")
        if len(parts) < 4 or not parts[3]:
            self._error(404, "not_found", "run not found")
            return
        run_id = parts[3]
        tenant_id = self._tenant()
        if len(parts) == 5 and parts[4] == "events":
            last_id = self.headers.get("Last-Event-ID")
            if not last_id:
                last_id = parse_qs(query).get("last_event_id", [None])[0]
            self._sse(self.runtime.run_service.sse(run_id, tenant_id, last_event_id=last_id))
            return
        if len(parts) == 4:
            self._json(200, self.runtime.run_payload(self.runtime.run_service.status(run_id, tenant_id)))
            return
        self._error(404, "not_found", "route not found")

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        try:
            self._post()
        except Exception as exc:  # boundary converts expected failures safely
            self._handle_error(exc)

    def _post(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path == "/v1/auth/google/callback":
            if self.runtime.config.auth_provider != "google" and self.runtime.config.app_env not in {"local", "test"}:
                raise AuthorizationDenied("local Google callback is disabled")
            result = self.runtime.complete_google(self._body())
            self._json(
                200,
                result,
                {"Set-Cookie": f"foundation_session={result['session_id']}; HttpOnly; Path=/; SameSite=Lax"},
            )
            return
        if path.startswith("/v1/billing/webhooks/"):
            provider_id = path.removeprefix("/v1/billing/webhooks/").strip("/")
            raw_body = self._raw_body()
            result = self.runtime.billing.receive_webhook(
                provider_id,
                raw_body,
                {key.lower(): value for key, value in self.headers.items()},
            )
            self._json(
                200,
                {
                    "contract_version": "v1",
                    "provider": result.provider,
                    "provider_event_id": result.provider_event_id,
                    "status": result.status,
                    "applied": result.applied,
                },
            )
            return
        if path == "/v1/billing/toss/confirm":
            if self.runtime.config.payment_provider != "toss":
                raise AuthorizationDenied("Toss payment is not enabled")
            payload = self._body()
            tenant_id = self._request_tenant()
            order_id = str(payload.get("order_id") or "")
            order = self.runtime.billing_store.order(order_id)
            if order.tenant_id != tenant_id:
                raise TenantMismatch("tenant access denied")
            amount_minor = int(payload.get("amount_minor", -1))
            result = self.runtime.billing.confirm_payment(
                order_id=order_id,
                provider_reference=str(payload.get("payment_key") or ""),
                amount_minor=amount_minor,
                idempotency_key=str(payload.get("idempotency_key") or f"confirm-{order_id}"),
            )
            self._json(
                200,
                {
                    "contract_version": "v1",
                    "provider": result.provider,
                    "provider_event_id": result.provider_event_id,
                    "status": result.status,
                    "applied": result.applied,
                },
            )
            return
        if path == "/v1/agent/execute":
            payload = self._body()
            payload = {
                **payload,
                "contract_version": "v1",
                "tenant_id": payload.get("tenant_id") or self._request_tenant(),
                "project_id": payload.get("project_id") or "agent-project",
                "idempotency_key": payload.get("idempotency_key") or f"agent-{uuid_hex()}",
                "trace_id": payload.get("trace_id") or f"agent-trace-{uuid_hex()}",
                "input": payload.get("input") or {"message": payload.get("message", "")},
            }
            request_tenant = self._request_tenant()
            if str(payload["tenant_id"]) != request_tenant:
                raise TenantMismatch("tenant access denied")
            self._json(201, self.runtime.create_run(payload))
            return
        if path in {"/v1/repositories/import", "/v1/change-assurance/repositories/import"}:
            tenant_id = self._request_tenant()
            name, files = self._read_repository_import()
            self._import_repository(tenant_id, name, files)
            return
        if path in {"/v1/repositories/authorize", "/v1/change-assurance/repositories/authorize"}:
            self._authorize_repository(self._body())
            return
        if path in {"/v1/change-impact/documents/from-url", "/v1/proposal-review/documents/from-url"}:
            self._request_tenant()
            payload = self._body()
            url = payload.get("url")
            if not isinstance(url, str) or not url.strip():
                raise ValueError("url is required")
            self._json(200, self.runtime.proposal_control.proposal_review.fetch_document(url))
            return
        if path in {"/v1/change-impact/reviews", "/v1/proposal-review/reviews"}:
            tenant_id = self._request_tenant()
            self._json(201, self.runtime.proposal_control.proposal_review.start(tenant_id, self._body()))
            return
        review_id, review_suffix = self._review_route(path)
        if review_id and review_suffix in {"decision", "resume"}:
            tenant_id = self._request_tenant()
            if review_suffix == "resume":
                self._json(200, self.runtime.proposal_control.proposal_review.resume(review_id, tenant_id))
            else:
                self._json(200, self.runtime.proposal_control.proposal_review.decide(review_id, tenant_id, self._body()))
            return
        proposal_repository_id, proposal_id, proposal_suffix = self._proposal_route(path)
        if proposal_repository_id:
            self._post_proposals(proposal_repository_id, proposal_id, proposal_suffix, self._body())
            return
        if path == "/v1/change-assurance/runs":
            payload = self._body()
            request_tenant = self._request_tenant()
            repository_id = self._require_read_scope(request_tenant, payload)
            payload_tenant = str(payload.get("tenant_id") or request_tenant)
            if payload_tenant != request_tenant:
                raise TenantMismatch("tenant access denied")
            proposal = payload.get("proposal")
            idempotency_key = payload.get("idempotency_key")
            if not isinstance(proposal, str) or not isinstance(idempotency_key, str):
                raise ValueError("proposal and idempotency_key are required")
            outcome = self.runtime.proposal_control.workflow.run(
                tenant_id=request_tenant,
                proposal=proposal,
                mode=str(payload.get("mode") or "plan_only"),
                idempotency_key=idempotency_key,
                quota_limit=payload.get("quota_limit"),
                repository_id=repository_id,
                repository_snapshot=asdict(self.runtime.proposal_control.catalog.get(repository_id)) if repository_id else None,
            )
            self._json(201, outcome_json(outcome))
            return
        if path.startswith("/v1/change-assurance/runs/"):
            self._post_proposal_run(path)
            return
        if path == "/v1/runs":
            payload = self._body()
            if payload.get("contract_version") != "v1":
                raise ValueError("contract_version must be v1")
            request_tenant = self._request_tenant()
            payload_tenant = str(payload.get("tenant_id") or request_tenant)
            if payload_tenant != request_tenant:
                raise TenantMismatch("tenant access denied")
            self._json(201, self.runtime.create_run(payload))
            return
        if path.startswith("/v1/runs/"):
            self._post_run(path)
            return
        if path == "/v1/billing/orders":
            payload = self._body()
            request_tenant = self._request_tenant()
            tenant_id = str(payload.get("tenant_id") or request_tenant)
            if tenant_id != request_tenant:
                raise TenantMismatch("tenant access denied")
            from services.billing import CreateOrder

            request = CreateOrder(
                order_id=str(payload.get("order_id") or f"order-{uuid_hex()}"),
                tenant_id=tenant_id,
                account_id=str(payload.get("account_id") or "demo-account"),
                plan_id=str(payload.get("plan_id") or "pro"),
                amount_minor=int(payload.get("amount_minor", 1000)),
                currency=str(payload.get("currency") or ("KRW" if self.runtime.config.payment_provider == "toss" else "USD")),
                credit_grant=int(payload.get("credit_grant", 10)),
                idempotency_key=str(payload["idempotency_key"]),
            )
            checkout = self.runtime.billing.create_order(request)
            self._json(
                201,
                {
                    "order_id": request.order_id,
                    "provider": checkout.provider,
                    "provider_reference": checkout.provider_reference,
                    "checkout_url": checkout.checkout_url,
                    "test_mode": checkout.test_mode,
                    "checkout_context": dict(checkout.checkout_context),
                },
            )
            return
        if path == "/v1/billing/mock/complete":
            self._complete_mock_payment(self._body())
            return
        if path == "/v1/admin/plan":
            self._admin_mutation("plan.change", self._body())
            return
        if path == "/v1/admin/credits":
            self._admin_mutation("credits.adjust", self._body())
            return
        self._error(404, "not_found", "route not found")

    def _post_run(self, path: str) -> None:
        parts = path.split("/")
        if len(parts) != 5 or parts[4] not in {"approve", "cancel"}:
            self._error(404, "not_found", "route not found")
            return
        run_id = parts[3]
        self.runtime.authenticate_demo(self._tenant())
        run = (
            self.runtime.run_service.approve(run_id, self._tenant())
            if parts[4] == "approve"
            else self.runtime.run_service.cancel(run_id, self._tenant())
        )
        if parts[4] == "approve" and run.state == "running":
            run = self.runtime.worker.execute(run_id)
        self._json(200, self.runtime.run_payload(run))

    def _get_repositories(self, query: str) -> None:
        tenant_id = self._request_tenant()
        parsed_query = parse_qs(query)
        raw_path = parsed_query.get("path", [None])[0]
        raw_name = parsed_query.get("name", [None])[0]
        if raw_path and raw_name:
            raise RepositoryCatalogError("repository_query_ambiguous")
        if raw_path:
            records = (self.runtime.proposal_control.catalog.resolve(raw_path),)
        elif raw_name:
            records = self.runtime.proposal_control.catalog.list_repositories(name=raw_name)
        else:
            records = self.runtime.proposal_control.catalog.list_repositories()
        self._json(
            200,
            {
                "repositories": [
                    {
                        "repository": self.runtime.proposal_control.catalog.public_record(record),
                        "authorization": self.runtime.proposal_control.catalog.authorization_state(tenant_id, record.repository_id),
                    }
                    for record in records
                ]
            },
        )

    def _get_proposals(self, repository_id: str, proposal_id: str | None, suffix: str, query: str) -> None:
        tenant_id = self._request_tenant()
        record = self.runtime.proposal_control.catalog.get(repository_id)
        self._require_repository_read(tenant_id, repository_id, parse_qs(query).get("read_scope_id", [None])[0])
        if proposal_id is None:
            workflow = self.runtime.proposal_control.workflow.for_repository(record.canonical_path)
            for item in self.runtime.proposal_control.store.list_proposals(tenant_id, repository_id):
                workflow.refresh_proposal(item["proposal_id"], tenant_id, asdict(record))
            self._json(
                200,
                {
                    "repository": self.runtime.proposal_control.catalog.public_record(record),
                    "proposals": list(self.runtime.proposal_control.store.list_proposals(tenant_id, repository_id)),
                },
            )
            return
        if suffix:
            self._error(404, "not_found", "proposal route not found")
            return
        view = self.runtime.proposal_control.workflow.for_repository(record.canonical_path).refresh_proposal(proposal_id, tenant_id, asdict(record))
        if view["repository_id"] != repository_id:
            raise RepositoryCatalogError("repository_identity_mismatch")
        self._json(200, {"repository": self.runtime.proposal_control.catalog.public_record(record), "proposal": view})

    def _post_proposals(self, repository_id: str, proposal_id: str | None, suffix: str, payload: Mapping[str, Any]) -> None:
        tenant_id = self._request_tenant()
        record = self.runtime.proposal_control.catalog.get(repository_id)
        snapshot = asdict(record)
        workflow = self.runtime.proposal_control.workflow.for_repository(record.canonical_path)
        if proposal_id is None and not suffix:
            self._require_repository_read(tenant_id, repository_id, payload.get("read_scope_id"))
            proposal = payload.get("proposal")
            idempotency_key = payload.get("idempotency_key")
            if not isinstance(proposal, str) or not isinstance(idempotency_key, str):
                raise ValueError("proposal and idempotency_key are required")
            outcome = workflow.run(
                tenant_id=tenant_id,
                proposal=proposal,
                mode=str(payload.get("mode") or "plan_only"),
                idempotency_key=idempotency_key,
                quota_limit=payload.get("quota_limit"),
                repository_id=repository_id,
                repository_snapshot=snapshot,
            )
            self._json(201, outcome_json(outcome))
            return
        if not proposal_id or suffix not in {"resume", "reanalyze"}:
            raise RepositoryCatalogError("proposal_route_invalid")
        view = workflow.refresh_proposal(proposal_id, tenant_id, snapshot)
        if view["repository_id"] != repository_id:
            raise RepositoryCatalogError("repository_identity_mismatch")
        run = view.get("run") or {}
        if suffix == "resume":
            write_scope_id = payload.get("write_scope_id")
            if not isinstance(write_scope_id, str):
                raise RepositoryCatalogError("write_scope_required")
            self.runtime.proposal_control.catalog.require_write(tenant_id, repository_id, write_scope_id)
            proposal = payload.get("proposal") or self.runtime.proposal_control.store.proposal_input(proposal_id, tenant_id)
            approval = _approval_from_json(payload["approval"]) if payload.get("approval") is not None else None
            resume_run_id = str(run["run_id"])
            resume_key = str(run["idempotency_key"])
            if run.get("ledger_state", run.get("state")) == "plan_only":
                resume_run_id = None
                resume_key = str(payload.get("idempotency_key") or f"{resume_key}:verify")
            outcome = workflow.run(
                tenant_id=tenant_id,
                proposal=str(proposal),
                mode="verify",
                idempotency_key=resume_key,
                approval=approval,
                run_id=resume_run_id,
                repository_id=repository_id,
                repository_snapshot=snapshot,
                proposal_id=proposal_id,
            )
            self._json(200, outcome_json(outcome))
            return
        self._require_repository_read(tenant_id, repository_id, payload.get("read_scope_id"))
        proposal = payload.get("proposal") or self.runtime.proposal_control.store.proposal_input(proposal_id, tenant_id)
        idempotency_key = payload.get("idempotency_key")
        if not isinstance(idempotency_key, str):
            raise ValueError("idempotency_key is required for re-analysis")
        outcome = workflow.run(
            tenant_id=tenant_id,
            proposal=str(proposal),
            mode=str(payload.get("mode") or "plan_only"),
            idempotency_key=idempotency_key,
            repository_id=repository_id,
            repository_snapshot=snapshot,
            proposal_id=proposal_id,
        )
        self._json(201, outcome_json(outcome))

    def _require_repository_read(self, tenant_id: str, repository_id: str, scope_id: str | None) -> None:
        if isinstance(scope_id, str) and scope_id:
            self.runtime.proposal_control.catalog.require_read(tenant_id, repository_id, scope_id)
            return
        if not self.runtime.proposal_control.catalog.authorization_state(tenant_id, repository_id).get(READ_ANALYSIS):
            raise RepositoryCatalogError("read_scope_required")

    def _get_repository(self, path: str) -> None:
        self._request_tenant()
        parts = [part for part in path.split("/") if part]
        repository_id = parts[-1] if parts else ""
        if not repository_id or repository_id == "authorize":
            self._error(404, "not_found", "repository not found")
            return
        record = self.runtime.proposal_control.catalog.get(repository_id)
        self._json(200, {"repository": self.runtime.proposal_control.catalog.public_record(record)})

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

    @staticmethod
    def _review_route(path: str) -> tuple[str | None, str]:
        parts = [part for part in path.split("/") if part]
        for prefix in (("v1", "change-impact", "reviews"), ("v1", "proposal-review", "reviews")):
            if parts[: len(prefix)] != list(prefix) or len(parts) < len(prefix) + 1:
                continue
            if len(parts) == len(prefix) + 1:
                return parts[-1], ""
            if len(parts) == len(prefix) + 2:
                return parts[-2], parts[-1]
        return None, ""

    def _authorize_repository(self, payload: Mapping[str, Any]) -> None:
        tenant_id = self._request_tenant()
        permission = payload.get("permission", payload.get("scope"))
        repository_id = payload.get("repository_id")
        raw_path = payload.get("path")
        if permission == READ_ANALYSIS:
            scope = self.runtime.proposal_control.catalog.authorize_read(tenant_id, repository_id=repository_id, path=raw_path)
        elif permission == WRITE_PATCH:
            read_scope_id = payload.get("read_scope_id")
            if not isinstance(read_scope_id, str):
                raise RepositoryCatalogError("read_scope_required")
            scope = self.runtime.proposal_control.catalog.authorize_write(tenant_id, repository_id=repository_id, path=raw_path, read_scope_id=read_scope_id)
        else:
            raise RepositoryCatalogError("scope_invalid")
        record = self.runtime.proposal_control.catalog.get(scope.repository_id)
        self.runtime.proposal_control.store.register_repository(tenant_id, asdict(record))
        self._json(200, {"repository": self.runtime.proposal_control.catalog.public_record(record), "scope": asdict(scope), "authorization": self.runtime.proposal_control.catalog.authorization_state(tenant_id, scope.repository_id)})

    def _import_repository(self, tenant_id: str, name: str, files: Sequence[tuple[str, bytes]]) -> None:
        record = self.runtime.proposal_control.catalog.import_snapshot(name, files)
        self.runtime.proposal_control.store.register_repository(tenant_id, asdict(record))
        self._json(
            201,
            {
                "repository": self.runtime.proposal_control.catalog.public_record(record),
                "authorization": self.runtime.proposal_control.catalog.authorization_state(tenant_id, record.repository_id),
            },
        )

    def _read_repository_import(self) -> tuple[str, tuple[tuple[str, bytes], ...]]:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("multipart/form-data"):
            raise ValueError("repository import must use multipart/form-data")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid content length") from exc
        if length <= 0 or length > MAX_REPOSITORY_IMPORT_BYTES:
            raise ValueError("repository import is empty or too large")
        raw = self.rfile.read(length)
        message = BytesParser(policy=email_default_policy).parsebytes(
            b"MIME-Version: 1.0\r\nContent-Type: " + content_type.encode("utf-8") + b"\r\n\r\n" + raw
        )
        if not message.is_multipart():
            raise ValueError("invalid repository import payload")
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

    def _require_read_scope(self, tenant_id: str, payload: Mapping[str, Any]) -> str | None:
        repository_id = payload.get("repository_id")
        if not repository_id:
            return None
        if not isinstance(repository_id, str):
            raise RepositoryCatalogError("repository_identity_required")
        scope_id = payload.get("read_scope_id")
        if not isinstance(scope_id, str):
            raise RepositoryCatalogError("read_scope_required")
        self.runtime.proposal_control.catalog.require_read(tenant_id, repository_id, scope_id)
        return repository_id

    def _post_proposal_run(self, path: str) -> None:
        parts = path.split("/")
        if len(parts) != 6 or parts[5] != "resume":
            self._error(404, "not_found", "route not found")
            return
        tenant_id = self._request_tenant()
        run_id = parts[4]
        run = self.runtime.proposal_control.store.get_run(run_id, tenant_id)
        payload = self._body()
        bound_repository_id = run.repository_id or (run.result.get("repository_id") if isinstance(run.result, Mapping) else None)
        repository_id = payload.get("repository_id") or bound_repository_id
        if bound_repository_id and payload.get("repository_id") and payload.get("repository_id") != bound_repository_id:
            raise RepositoryCatalogError("repository_identity_mismatch")
        if repository_id:
            if not isinstance(repository_id, str):
                raise RepositoryCatalogError("repository_identity_required")
            write_scope_id = payload.get("write_scope_id")
            if not isinstance(write_scope_id, str):
                raise RepositoryCatalogError("write_scope_required")
            self.runtime.proposal_control.catalog.require_write(tenant_id, repository_id, write_scope_id)
        proposal = payload.get("proposal")
        if not isinstance(proposal, str):
            raise ValueError("proposal is required to resume")
        snapshot = asdict(self.runtime.proposal_control.catalog.get(repository_id)) if repository_id else None
        workflow = self.runtime.proposal_control.workflow.for_repository(snapshot["canonical_path"]) if snapshot else self.runtime.proposal_control.workflow
        outcome = workflow.run(
            tenant_id=tenant_id,
            proposal=proposal,
            mode=run.mode,
            idempotency_key=run.idempotency_key,
            approval=_approval_from_json(payload.get("approval")),
            run_id=run_id,
            repository_id=repository_id if isinstance(repository_id, str) else None,
            repository_snapshot=snapshot,
            proposal_id=run.proposal_id,
        )
        self._json(200, outcome_json(outcome))

    def _get_proposal_run(self, path: str) -> None:
        parts = path.split("/")
        if len(parts) < 5 or not parts[4]:
            self._error(404, "not_found", "run not found")
            return
        run_id = parts[4]
        tenant_id = self._request_tenant()
        run = self.runtime.proposal_control.store.get_run(run_id, tenant_id)
        if len(parts) == 5:
            self._json(200, {"run": asdict(run), "checkpoint": self.runtime.proposal_control.store.checkpoint(run_id, tenant_id), "report": self.runtime.proposal_control.store.report(run_id, tenant_id)})
            return
        if len(parts) == 6 and parts[5] == "events":
            self._json(200, {"events": self.runtime.proposal_control.store.events(run_id, tenant_id)})
            return
        if len(parts) == 6 and parts[5] == "report":
            self._json(200, {"run": asdict(run), "report": self.runtime.proposal_control.store.report(run_id, tenant_id)})
            return
        self._error(404, "not_found", "route not found")

    def _complete_mock_payment(self, payload: Mapping[str, Any]) -> None:
        if self.runtime.config.payment_provider != "mock":
            raise AuthorizationDenied("mock payment route is disabled")
        request_tenant = self._request_tenant()
        order_id = str(payload.get("order_id") or "")
        order = self.runtime.billing_store.order(order_id)
        if order.tenant_id != request_tenant:
            raise TenantMismatch("tenant access denied")
        event = {
            "event_id": str(payload.get("event_id") or f"mock-event-{order_id}"),
            "event_type": "payment.updated",
            "status": str(payload.get("status") or "succeeded"),
            "order_id": order_id,
            "amount_minor": int(payload.get("amount_minor", order.amount_minor)),
            "idempotency_key": str(payload.get("idempotency_key") or f"mock-event-{order_id}"),
            "test_mode": True,
        }
        raw = json.dumps(event, sort_keys=True, separators=(",", ":")).encode("utf-8")
        secret = self.runtime.values.get("MOCK_WEBHOOK_SECRET", "mock-secret")
        signature = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
        result = self.runtime.billing.receive_webhook("mock", raw, {"x-signature": signature})
        self._json(200, {"provider": result.provider, "event_id": result.provider_event_id, "status": result.status, "applied": result.applied})

    def _admin_mutation(self, action: str, payload: Mapping[str, Any]) -> None:
        actor = self._session()
        request_tenant = self._request_tenant()
        tenant_id = str(payload.get("tenant_id") or request_tenant)
        if tenant_id != request_tenant:
            raise TenantMismatch("tenant access denied")
        target_user_id = str(payload.get("target_user_id") or "")
        reason = str(payload.get("reason") or "")
        correlation_id = str(payload.get("correlation_id") or f"local-{uuid_hex()}")
        idempotency_key = payload.get("idempotency_key")
        if action == "plan.change":
            result = self.runtime.admin.change_plan(
                actor,
                tenant_id,
                target_user_id,
                str(payload.get("plan") or ""),
                reason=reason,
                correlation_id=correlation_id,
                idempotency_key=str(idempotency_key) if idempotency_key else None,
            )
        else:
            raw_amount = payload.get("amount")
            if not isinstance(raw_amount, int) or isinstance(raw_amount, bool):
                raise ValueError("amount must be an integer")
            result = self.runtime.admin.adjust_credits(
                actor,
                tenant_id,
                target_user_id,
                raw_amount,
                reason=reason,
                correlation_id=correlation_id,
                idempotency_key=str(idempotency_key) if idempotency_key else None,
            )
        self._json(200, {"action": result.action, "target_user_id": result.target_user_id, "before": dict(result.before), "after": dict(result.after), "audit_event_id": result.audit_event_id})

    @staticmethod
    def _admin_user(user: Any) -> dict[str, object]:
        return {"user_id": user.user_id, "email": user.email, "status": user.status, "tenant_id": user.tenant_id, "plan": user.plan, "credit_balance": user.credit_balance}

    @staticmethod
    def _order(order: Any) -> dict[str, object]:
        return {"order_id": order.order_id, "tenant_id": order.tenant_id, "account_id": order.account_id, "plan_id": order.plan_id, "amount_minor": order.amount_minor, "currency": order.currency, "credit_grant": order.credit_grant, "status": order.status, "provider": order.provider, "provider_reference": order.provider_reference}

    def _handle_error(self, exc: Exception) -> None:
        if isinstance(exc, (AuthorizationDenied, OAuthCallbackError)):
            status = getattr(exc, "status_code", 403 if isinstance(exc, AuthorizationDenied) else 400)
            self._error(status, "authorization_denied" if status == 403 else "invalid_request", str(exc))
        elif isinstance(exc, InsufficientCredits):
            self._error(402, "insufficient_credits", "credits are unavailable")
        elif isinstance(exc, RunNotFound):
            self._error(404, "run_not_found", "run not found")
        elif isinstance(exc, TenantMismatch):
            self._error(403, "tenant_access_denied", "tenant access denied")
        elif isinstance(exc, (ProposalTenantScopeError, RepositoryCatalogError)):
            code = exc.code if isinstance(exc, RepositoryCatalogError) else "tenant_access_denied"
            status = 403 if isinstance(exc, ProposalTenantScopeError) or code.startswith("scope_") or code in {"tenant_invalid", "repository_identity_mismatch", "write_scope_missing_read_parent", "read_scope_required", "write_scope_required"} else 400
            self._error(status, code, code)
        elif isinstance(exc, IdempotencyConflict):
            self._error(409, "idempotency_conflict", "idempotency key conflicts with an existing request")
        elif isinstance(exc, RunError):
            self._error(409, "run_conflict", str(exc))
        elif isinstance(exc, (KeyError, TypeError, ValueError)):
            self._error(400, "invalid_request", str(exc))
        else:
            self._error(500, "internal_error", "request could not be completed")

    def log_message(self, format: str, *args: object) -> None:
        # Keep logs deterministic and free of request bodies, headers, and secrets.
        print(f"foundation: {format % args}")


def uuid_hex() -> str:
    import uuid

    return uuid.uuid4().hex


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


def _main() -> int:
    parser = argparse.ArgumentParser(description="Start the local foundation HTTP surface")
    parser.add_argument("--env-file", default=None)
    parser.add_argument("--profile", choices=("free-portfolio", "aws-worker"), default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    values = merged_environment(args.env_file)
    try:
        config = validate_profile(values, args.profile)
        runtime = LocalRuntime(config, values)
    except (ConfigError, ValueError) as exc:
        print(str(exc))
        return 2

    server = LocalServer((args.host, args.port), runtime)
    actual_address = server.server_address
    actual_host, actual_port = actual_address[0], actual_address[1]
    host_text = actual_host.decode("ascii") if isinstance(actual_host, bytes) else str(actual_host)
    print(f"foundation listening on http://{host_text}:{actual_port} ({config.deployment_profile})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("foundation stopping")
    finally:
        server.server_close()
        runtime.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
