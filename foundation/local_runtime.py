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
from services.metering_billing import (
    QuotaPolicy,
    SQLiteCreditLedger,
    SQLiteQuotaCounter,
)
from services.run_service import RunCreate, RunService, SQLiteRunStore

from .config import FoundationConfig


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
        self.worker = BoundedWorker(self.run_store, self.credit_ledger, LocalEchoModel())

        self.billing_store = SQLiteBillingStore(state_path)
        self.billing_registry = build_registry_from_environment(values)
        self.billing = BillingService(
            store=self.billing_store,
            providers=self.billing_registry,
            active_provider=config.payment_provider,
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
            allowed_redirect_uris={f"{config.app_base_url.rstrip('/')}/auth/callback"},
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
        for store in (self.run_store, self.credit_ledger, self.quota, self.billing_store):
            store.close()

    def authenticate_demo(self, tenant_id: str | None = None) -> None:
        if tenant_id is not None and tenant_id != DEMO_TENANT_ID:
            raise AuthorizationDenied("tenant access denied")

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
        return {
            "contract_version": "v1",
            "run_id": run.run_id,
            "tenant_id": run.tenant_id,
            "project_id": run.project_id,
            "state": run.state,
            "sequence": run.sequence,
            "trace_id": run.trace_id,
            "reservation_id": run.reservation_id,
            "result": dict(run.result),
        }

    def auth_payload(self) -> dict[str, object]:
        return {
            "contract_version": "v1",
            "user_id": self.session.user_id,
            "session_id": self.session.session_id,
            "tenant_id": self.session.active_tenant_id,
            "expires_at": self.session.expires_at.isoformat(),
            "provider": "local-demo",
        }

    def start_google(self) -> dict[str, object]:
        state = f"local-state-{uuid.uuid4().hex}"
        redirect_uri = f"{self.config.app_base_url.rstrip('/')}/auth/callback"
        self.oauth_transactions.begin(
            state,
            redirect_uri,
            datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        return {
            "provider": "google",
            "mode": "local-mock",
            "state": state,
            "redirect_uri": redirect_uri,
            "authorization_url": f"https://accounts.google.com/o/oauth2/v2/auth?state={state}",
        }

    def complete_google(self, payload: Mapping[str, Any]) -> dict[str, object]:
        redirect_uri = str(payload.get("redirect_uri") or f"{self.config.app_base_url.rstrip('/')}/auth/callback")
        callback = GoogleOAuthCallback(
            state=str(payload.get("state") or ""),
            code=str(payload.get("code") or ""),
            redirect_uri=redirect_uri,
        )
        identity = self.oauth.validate_and_exchange(
            callback,
            lambda _code, _redirect: GoogleIdentity(
                provider_subject="local-google-subject",
                email="demo@example.test",
                email_verified=True,
                display_name="Local Demo",
            ),
        )
        return {**self.auth_payload(), "email": identity.email, "display_name": identity.display_name}
