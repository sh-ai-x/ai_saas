"""Small composition-root adapters for protected HTTP routes."""

from __future__ import annotations

from typing import Any, Mapping

from .boundary import BetterAuthSession, RequestContext, TenantBoundary


class ProtectedRouteChecks:
    """Resolve Better Auth server results before entering a route use case."""

    def __init__(self, boundary: TenantBoundary) -> None:
        self._boundary = boundary

    def authenticated(
        self, session: BetterAuthSession | Mapping[str, Any] | None
    ) -> RequestContext:
        return self._boundary.authenticate(session)

    def tenant(
        self,
        session: BetterAuthSession | Mapping[str, Any] | None,
        tenant_id: str,
    ) -> RequestContext:
        context = self.authenticated(session)
        self._boundary.require_tenant(context, tenant_id)
        return context

    def admin(
        self,
        session: BetterAuthSession | Mapping[str, Any] | None,
        tenant_id: str,
        permission: str,
    ) -> RequestContext:
        context = self.authenticated(session)
        self._boundary.require_admin(context, tenant_id, permission)
        return context


def require_authenticated(
    boundary: TenantBoundary, session: BetterAuthSession | Mapping[str, Any] | None
) -> RequestContext:
    return ProtectedRouteChecks(boundary).authenticated(session)


def require_tenant_access(
    boundary: TenantBoundary,
    session: BetterAuthSession | Mapping[str, Any] | None,
    tenant_id: str,
) -> RequestContext:
    return ProtectedRouteChecks(boundary).tenant(session, tenant_id)


def require_admin_access(
    boundary: TenantBoundary,
    session: BetterAuthSession | Mapping[str, Any] | None,
    tenant_id: str,
    permission: str,
) -> RequestContext:
    return ProtectedRouteChecks(boundary).admin(session, tenant_id, permission)
