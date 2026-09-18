"""Run-service failures."""


class RunError(ValueError):
    """Base class for expected run boundary failures."""


class RunNotFound(RunError):
    pass


class TenantMismatch(RunError):
    pass


class IdempotencyConflict(RunError):
    pass


class InvalidTransition(RunError):
    pass
