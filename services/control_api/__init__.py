"""Small local control facade; no web server is required for tests."""

from .service import LocalControlService
from .http import ControlApiConfig, ControlRuntime, build_runtime, create_server, outcome_json
from .repository_catalog import (
    READ_ANALYSIS,
    WRITE_PATCH,
    LocalRepositoryCatalog,
    RepositoryAuthorizationStore,
    RepositoryCatalogError,
    RepositoryRecord,
    RepositoryScope,
)

__all__ = [
    "ControlApiConfig",
    "ControlRuntime",
    "LocalControlService",
    "LocalRepositoryCatalog",
    "READ_ANALYSIS",
    "RepositoryAuthorizationStore",
    "RepositoryCatalogError",
    "RepositoryRecord",
    "RepositoryScope",
    "WRITE_PATCH",
    "build_runtime",
    "create_server",
    "outcome_json",
]
