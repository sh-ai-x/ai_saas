"""Small local control facade; no web server is required for tests."""

from .service import LocalControlService

__all__ = ["LocalControlService"]
