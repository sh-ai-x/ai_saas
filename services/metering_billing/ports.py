from __future__ import annotations

from typing import Protocol

from services.billing.ports import *  # noqa: F401,F403

from .runtime import CreditCommit, CreditReservation


class CreditReservationPort(Protocol):
    """Provider-neutral port consumed by run-service and agent-worker."""

    def reserve(
        self,
        tenant_id: str,
        account_id: str,
        run_id: str,
        units: int,
        *,
        idempotency_key: str,
    ) -> CreditReservation:
        ...

    def release(self, reservation_id: str, *, idempotency_key: str) -> CreditReservation:
        ...

    def commit(self, reservation_id: str, used_units: int, *, idempotency_key: str) -> CreditCommit:
        ...
