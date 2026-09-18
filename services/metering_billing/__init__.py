"""Compatibility and runtime boundary for the logical metering-billing service."""

from services.billing import BillingService, CreateOrder, Entitlement, Order, ProviderRegistry, SQLiteBillingStore
from .ports import CreditReservationPort
from .quota import QuotaCounterPort, QuotaExceeded, QuotaPolicy, QuotaSnapshot, SQLiteQuotaCounter
from .runtime import CreditCommit, CreditReservation, ReservationConflict, SQLiteCreditLedger

__all__ = [
    "BillingService", "CreateOrder", "CreditCommit", "CreditReservation", "CreditReservationPort", "Entitlement", "Order",
    "ProviderRegistry", "QuotaCounterPort", "QuotaExceeded", "QuotaPolicy", "QuotaSnapshot", "ReservationConflict",
    "SQLiteBillingStore", "SQLiteCreditLedger", "SQLiteQuotaCounter",
]
