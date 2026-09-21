"""Exact Local Lite model-token ceilings and bounded call accounting."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

from .contracts import BudgetDecision


class BudgetPhase(IntEnum):
    """Named positions for the per-phase token ceilings.

    The tuple-shaped `phase_limits` field used a magic index (0,1,2) which
    obscured which position corresponded to which phase; the enum below
    documents the contract and keeps the per-phase accounting readable.
    """

    INTAKE = 0
    ANALYZE = 1
    DISPATCH = 2


@dataclass(frozen=True)
class BudgetPolicy:
    mode: str
    intake_limit: int
    analyze_limit: int
    dispatch_limit: int
    total_limit: int
    per_call_input_limit: int = 8_000
    max_primary_calls: int = 5
    max_retries: int = 1
    phase_limits: dict[BudgetPhase, int] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "phase_limits",
            {
                BudgetPhase.INTAKE: self.intake_limit,
                BudgetPhase.ANALYZE: self.analyze_limit,
                BudgetPhase.DISPATCH: self.dispatch_limit,
            },
        )

    @classmethod
    def local_lite(cls, mode: str) -> "BudgetPolicy":
        if mode == "plan_only":
            return cls(mode, 2_000, 9_000, 9_000, 20_000)
        if mode == "verify":
            return cls(mode, 20_000, 16_000, 5_000, 41_000)
        raise ValueError("mode must be plan_only or verify")


class TokenBudgetLedger:
    def __init__(self, policy: BudgetPolicy, *, quota_limit: int | None = None) -> None:
        self.policy = policy
        self.quota_limit = quota_limit
        self.total_used = 0
        self.primary_calls = 0
        self.retries = 0
        self.decisions: list[BudgetDecision] = []
        self._phase_used: dict[BudgetPhase, int] = {phase: 0 for phase in BudgetPhase}

    def reserve(
        self,
        *,
        phase: BudgetPhase,
        input_tokens: int,
        output_tokens: int,
        retry: bool = False,
    ) -> BudgetDecision:
        if not isinstance(phase, BudgetPhase):
            raise ValueError("phase must be a BudgetPhase")
        if input_tokens > self.policy.per_call_input_limit:
            return self._decision(False, "budget_exceeded", "per-call input limit exceeded")
        if input_tokens < 0 or output_tokens < 0:
            return self._decision(False, "budget_exceeded", "negative token usage")
        if retry:
            if self.retries >= self.policy.max_retries:
                return self._decision(False, "budget_exceeded", "retry limit exceeded")
        elif self.primary_calls >= self.policy.max_primary_calls:
            return self._decision(False, "budget_exceeded", "primary model-call limit exceeded")
        amount = input_tokens + output_tokens
        if self.quota_limit is not None and self.total_used + amount > self.quota_limit:
            return self._decision(False, "quota_paused", "tenant quota exhausted")
        if self.total_used + amount > self.policy.total_limit:
            return self._decision(False, "budget_exceeded", "total token budget exhausted")
        if self._phase_used[phase] + amount > self.policy.phase_limits[phase]:
            return self._decision(False, "budget_exceeded", "phase token budget exhausted")
        self.total_used += amount
        self._phase_used[phase] += amount
        if retry:
            self.retries += 1
        else:
            self.primary_calls += 1
        return self._decision(True, "allowed", "within Local Lite budget")

    def refund(self, *, phase: BudgetPhase, tokens: int) -> None:
        """Return pre-flight budget back when an actual call consumed less than estimated."""
        if tokens <= 0:
            return
        self.total_used = max(0, self.total_used - tokens)
        self._phase_used[phase] = max(0, self._phase_used[phase] - tokens)

    def record_output(self, *, phase: BudgetPhase, output_tokens: int) -> BudgetDecision:
        """Record the output portion of a model call whose input was already reserved."""
        if output_tokens <= 0:
            return self._decision(True, "allowed", "no output to record")
        if output_tokens > self.policy.per_call_input_limit:
            return self._decision(False, "budget_exceeded", "output token cap exceeded")
        self.total_used += output_tokens
        self._phase_used[phase] += output_tokens
        return self._decision(True, "allowed", "output within budget")

    def _decision(self, allowed: bool, status: str, reason: str) -> BudgetDecision:
        decision = BudgetDecision(
            allowed=allowed,
            status=status,  # type: ignore[arg-type]
            reason=reason,
            total_used=self.total_used,
            total_limit=self.policy.total_limit,
            primary_calls=self.primary_calls,
            retries=self.retries,
        )
        self.decisions.append(decision)
        return decision


def estimate_tokens(text: str) -> int:
    """Stable offline estimate used only when a provider does not report usage."""

    return max(1, (len(text.encode("utf-8")) + 3) // 4)


TokenBudgetContract = BudgetPolicy
