"""Composition root for the disposable, local foundation runtime.

The production design has logical service boundaries, but the portfolio
profile deliberately runs them in one process with SQLite-backed stores.  This
module is the only place where the local adapters are wired together; domain
modules remain provider- and transport-neutral.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from services.admin_operations import (
    AdminOperations,
    AuditLog,
    InMemoryEntitlements,
)
from services.agent_worker import BoundedWorker, ModelResult
from services.billing import BillingService, SQLiteBillingStore
from services.billing.registry import build_registry_from_environment
from services.identity_tenant import (
    AuthorizationDenied,
    BetterAuthSession,
    GoogleIdentity,
    GoogleOAuthCallback,
    GoogleOAuthCallbackValidator,
    OAuthTransactionStore,
    Role,
    TenantBoundary,
)
from services.identity_tenant.google_provider import GoogleOAuthProvider
from services.metering_billing import (
    QuotaPolicy,
    SQLiteCreditLedger,
    SQLiteQuotaCounter,
)
from services.run_service import RunCreate, RunService, SQLiteRunStore
from services.control_api import ControlApiConfig, build_runtime

from .config import FoundationConfig
from services.agent_worker import build_agent_model


DEMO_USER_ID = "demo-user"
DEMO_TENANT_ID = "demo-tenant"
DEMO_ACCOUNT_ID = "demo-account"
DEMO_PROJECT_ID = "demo-project"
DEMO_SESSION_ID = "demo-session"


class LocalAdminCreditLedger:
    """Map admin user ids to the shared durable run-credit accounts."""

    def __init__(self, ledger: SQLiteCreditLedger, accounts: Mapping[str, str]) -> None:
        self._ledger = ledger
        self._accounts = dict(accounts)

    def _account(self, user_id: str) -> str:
        return self._accounts.get(user_id, user_id)

    def current_balance(self, user_id: str) -> int:
        return self._ledger.available(self._account(user_id))

    def adjust_credits(self, user_id: str, amount: int, *, reason: str) -> int:
        return self._ledger.adjust(
            self._account(user_id),
            amount,
            idempotency_key=f"admin-{user_id}-{uuid.uuid4().hex}",
            reason=reason,
        )


class LocalEchoModel:
    """Deterministic local model substitute; it never calls an external API."""

    def __call__(self, prompt: str, *, idempotency_key: str, timeout_seconds: float) -> ModelResult:
        message = prompt.strip() or "(empty message)"
        return ModelResult(output=f"Local echo: {message}", usage_units=1)


class LocalRuntime:
    """Own local stores and use cases for the HTTP composition root."""

    def __init__(self, config: FoundationConfig, values: Mapping[str, str]) -> None:
        state_path = values.get("LOCAL_STATE_DB", "/tmp/ai-saas-foundation.sqlite3").strip()
        if state_path != ":memory:":
            Path(state_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self.state_path = state_path
        self.config = config
        self.values = dict(values)
        initial_credits = int(values.get("LOCAL_INITIAL_CREDITS", "100"))
        if initial_credits < 0:
            raise ValueError("LOCAL_INITIAL_CREDITS must be non-negative")

        self.run_store = SQLiteRunStore(state_path)
        self.credit_ledger = SQLiteCreditLedger(
            state_path,
            initial_balances={DEMO_ACCOUNT_ID: initial_credits},
        )
        self.quota = SQLiteQuotaCounter(
            state_path,
            policy=QuotaPolicy(
                max_runs=config.quota_max_runs,
                max_units=config.quota_max_units,
                period_seconds=config.quota_period_seconds,
            ),
        )
        self.dispatches: list[Mapping[str, object]] = []
        from services.run_service.workflow import InngestDispatcher

        self.dispatcher = InngestDispatcher(self.dispatches.append)
        self.run_service = RunService(
            self.run_store,
            self.credit_ledger,
            workflow=self.dispatcher,
            quota=self.quota,
        )
        self.worker = BoundedWorker(
            self.run_store,
            self.credit_ledger,
            build_agent_model(
                provider=config.agent_provider,
                model=config.agent_model,
                api_key=values.get("AGENT_API_KEY", ""),
                base_url=config.agent_base_url,
                max_output_tokens=config.agent_max_output_tokens,
            ),
        )

        self.billing_store = SQLiteBillingStore(state_path)
        self.billing_registry = build_registry_from_environment(values)
        self.billing = BillingService(
            store=self.billing_store,
            providers=self.billing_registry,
            active_provider=config.payment_provider,
        )

        proposal_state_path = values.get("PROPOSAL_STATE_DB", "").strip()
        if not proposal_state_path:
            proposal_state_path = ":memory:" if state_path == ":memory:" else str(Path(state_path).with_name("proposal.sqlite3"))
        if proposal_state_path != ":memory:":
            Path(proposal_state_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self.proposal_control = build_runtime(
            ControlApiConfig(
                database=proposal_state_path,
                repository_root=values.get("AGENT_REPOSITORY_ROOT", ".").strip() or ".",
                allow_insecure_local=True,
            ),
            environment=values,
        )

        self.identity = TenantBoundary()
        self.identity.add_user(DEMO_USER_ID, "demo@example.test", display_name="Local Demo")
        self.identity.add_user("demo-member", "member@example.test", display_name="Local Member")
        self.identity.add_tenant(DEMO_TENANT_ID, "Local Demo Tenant")
        self.identity.add_membership(DEMO_USER_ID, DEMO_TENANT_ID, Role.OWNER)
        self.identity.add_membership("demo-member", DEMO_TENANT_ID, Role.MEMBER)
        self.oauth_transactions = OAuthTransactionStore()
        self.oauth = GoogleOAuthCallbackValidator(
            self.oauth_transactions,
            allowed_redirect_uris={
                values.get("GOOGLE_REDIRECT_URI", "").strip()
                or f"{config.app_base_url.rstrip('/')}/auth/callback"
            },
        )
        self.google_provider = (
            GoogleOAuthProvider(
                client_id=values.get("GOOGLE_CLIENT_ID", ""),
                client_secret=values.get("GOOGLE_CLIENT_SECRET", ""),
                redirect_uri=values.get("GOOGLE_REDIRECT_URI", ""),
            )
            if config.auth_provider == "google"
            else None
        )
        self.admin_audit = AuditLog()
        self.admin_entitlements = InMemoryEntitlements({DEMO_USER_ID: "free", "demo-member": "free"})
        self.admin_credits = LocalAdminCreditLedger(
            self.credit_ledger,
            {DEMO_USER_ID: DEMO_ACCOUNT_ID, "demo-member": "demo-member-account"},
        )
        self.admin = AdminOperations(
            self.identity,
            self.admin_entitlements,
            self.admin_credits,
            self.admin_audit,
        )
        self.session = BetterAuthSession(
            session_id=DEMO_SESSION_ID,
            user_id=DEMO_USER_ID,
            active_tenant_id=DEMO_TENANT_ID,
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )

    def close(self) -> None:
        self.proposal_control.catalog.close()
        for store in (self.run_store, self.credit_ledger, self.quota, self.billing_store, self.proposal_control.store):
            store.close()

    def proposal_capabilities(self) -> dict[str, object]:
        workflow = self.proposal_control.workflow
        return {
            "contract_version": "v1",
            "profile": "local-lite",
            "modes": ["plan_only", "verify"],
            "provider": workflow.model.provider_id,
            "langchain_enabled": workflow.model.provider_id == "langchain",
            "langgraph_enabled": workflow.graph_runtime is not None,
            "langsmith_enabled": bool(getattr(workflow.tracer, "_client", None)),
            "langsmith_project": self.values.get("LANGSMITH_PROJECT", "proposal-to-verified-change"),
            "langsmith_console_url": self.values.get("LANGSMITH_CONSOLE_URL", "https://smith.langchain.com"),
            "repository_roots": [root.canonical_path for root in self.proposal_control.catalog.roots],
            "repository_scopes": ["read_analysis", "write_patch"],
            "approval_required_for": ["patch", "deliver"],
        }

    def authenticate_demo(self, tenant_id: str | None = None) -> None:
        if tenant_id is None or tenant_id == DEMO_TENANT_ID:
            return
        if self.session.active_tenant_id != tenant_id:
            raise AuthorizationDenied("tenant access denied")
        context = self.identity.authenticate(self.session)
        self.identity.require_tenant(context, tenant_id)

    def create_run(self, payload: Mapping[str, Any]) -> Mapping[str, object]:
        tenant_id = str(payload.get("tenant_id") or DEMO_TENANT_ID)
        self.authenticate_demo(tenant_id)
        raw_input = payload.get("input")
        request = RunCreate(
            tenant_id=tenant_id,
            account_id=str(payload.get("account_id") or DEMO_ACCOUNT_ID),
            project_id=str(payload.get("project_id") or DEMO_PROJECT_ID),
            idempotency_key=str(payload["idempotency_key"]),
            trace_id=str(payload["trace_id"]),
            input=raw_input if isinstance(raw_input, Mapping) else {},
            reserve_units=int(payload.get("reserve_units", 1)),
            max_steps=int(payload.get("max_steps", 1)),
            max_model_calls=int(payload.get("max_model_calls", 1)),
            max_runtime_seconds=float(payload.get("max_runtime_seconds", 30)),
        )
        run = self.run_service.create_run(request)
        if run.state == "queued":
            run = self.worker.execute(run.run_id)
        return self.run_payload(run)

    def run_payload(self, run: Any) -> dict[str, object]:
        result = dict(run.result)
        checkpoint = self.run_store.checkpoint(run.run_id)
        if "output" not in result and checkpoint is not None and checkpoint.state.get("last_output"):
            result["output"] = checkpoint.state["last_output"]
        return {
            "contract_version": "v1",
            "run_id": run.run_id,
            "tenant_id": run.tenant_id,
            "project_id": run.project_id,
            "state": run.state,
            "sequence": run.sequence,
            "trace_id": run.trace_id,
            "reservation_id": run.reservation_id,
            "result": result,
        }

    def auth_payload(self) -> dict[str, object]:
        return {
            "contract_version": "v1",
            "user_id": self.session.user_id,
            "session_id": self.session.session_id,
            "tenant_id": self.session.active_tenant_id,
            "expires_at": self.session.expires_at.isoformat(),
            "provider": self.config.auth_provider,
        }

    def start_google(self) -> dict[str, object]:
        state = f"local-state-{uuid.uuid4().hex}"
        redirect_uri = (
            self.config.values.get("GOOGLE_REDIRECT_URI")
            or f"{self.config.app_base_url.rstrip('/')}/auth/callback"
        )
        self.oauth_transactions.begin(
            state,
            redirect_uri,
            datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        if self.google_provider is not None:
            authorization = self.google_provider.authorization_url(state)
            return {
                "provider": "google",
                "mode": "authorization-code",
                "state": state,
                "redirect_uri": authorization.redirect_uri,
                "authorization_url": authorization.authorization_url,
            }
        return {
            "provider": "google",
            "mode": "local-mock",
            "state": state,
            "redirect_uri": redirect_uri,
            "authorization_url": f"https://accounts.google.com/o/oauth2/v2/auth?state={state}",
        }

    def complete_google(self, payload: Mapping[str, Any]) -> dict[str, object]:
        redirect_uri = str(
            payload.get("redirect_uri")
            or self.config.values.get("GOOGLE_REDIRECT_URI")
            or f"{self.config.app_base_url.rstrip('/')}/auth/callback"
        )
        callback = GoogleOAuthCallback(
            state=str(payload.get("state") or ""),
            code=str(payload.get("code") or ""),
            redirect_uri=redirect_uri,
        )
        if self.google_provider is None:
            identity = self.oauth.validate_and_exchange(
                callback,
                lambda _code, _redirect: GoogleIdentity(
                    provider_subject="local-google-subject",
                    email="demo@example.test",
                    email_verified=True,
                    display_name="Local Demo",
                ),
            )
            user_id = DEMO_USER_ID
            tenant_id = DEMO_TENANT_ID
        else:
            identity = self.oauth.validate_and_exchange(callback, self.google_provider.exchange_code)
            user_id = self.identity.link_google_identity(identity)
            tenant_id = f"tenant-{user_id}"
            try:
                has_membership = bool(self.identity.memberships_for_tenant(tenant_id))
            except AuthorizationDenied:
                has_membership = False
            if not has_membership:
                self.identity.add_tenant(tenant_id, f"{identity.display_name or identity.email}'s workspace")
                self.identity.add_membership(user_id, tenant_id, Role.OWNER)
        self.session = BetterAuthSession(
            session_id=DEMO_SESSION_ID if self.google_provider is None else f"session-{uuid.uuid4().hex}",
            user_id=user_id,
            active_tenant_id=tenant_id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        return {**self.auth_payload(), "email": identity.email, "display_name": identity.display_name}
