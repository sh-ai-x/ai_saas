"""Errors raised at the billing boundary."""


class BillingError(ValueError):
    """Base class for expected billing boundary failures."""


class InvalidWebhook(BillingError):
    """The raw webhook could not be authenticated or parsed."""


class UnknownProvider(BillingError):
    """No registered provider exists for the requested operation."""


class ProviderConfigurationError(BillingError):
    """The deployment selected an unsafe or ambiguous provider setup."""


class OrderConflict(BillingError):
    """An idempotency key was reused for a different order."""


class UnknownOrder(BillingError):
    """A verified event references no locally-created pending order."""


class InsufficientCredits(BillingError):
    """A guarded debit would make an account balance negative."""

