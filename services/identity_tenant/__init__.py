"""Identity, session, tenant, and RBAC boundary for the modular monolith."""

from .boundary import (
    AccountCollision,
    AuthenticationRequired,
    AuthorizationDenied,
    BetterAuthSession,
    GoogleIdentity,
    GoogleOAuthCallback,
    GoogleOAuthCallbackValidator,
    OAuthCallbackError,
    OAuthTransactionStore,
    RequestContext,
    Role,
    TenantBoundary,
)
from .routes import ProtectedRouteChecks, require_admin_access, require_authenticated, require_tenant_access

__all__ = [
    "AccountCollision",
    "AuthenticationRequired",
    "AuthorizationDenied",
    "BetterAuthSession",
    "GoogleIdentity",
    "GoogleOAuthCallback",
    "GoogleOAuthCallbackValidator",
    "OAuthCallbackError",
    "OAuthTransactionStore",
    "RequestContext",
    "Role",
    "TenantBoundary",
    "ProtectedRouteChecks",
    "require_admin_access",
    "require_authenticated",
    "require_tenant_access",
]
