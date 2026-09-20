"""Exact Local Lite model-token ceilings and bounded call accounting."""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import BudgetDecision


@dataclass(frozen=True)
class BudgetPolicy:
    mode: str
    phase_limits: tuple[int, int, int]
    total_limit: int
    per_call_input_limit: int = 8_000
    max_primary_calls: int = 5
    max_retries: int = 1

    @classmethod
    def local_lite(cls, mode: str) -> "BudgetPolicy":
        if mode == "plan_only":
            return cls(mode, (2_000, 9_000, 9_000), 20_000)
        if mode == "verify":
            return cls(mode, (20_000, 16_000, 5_000), 41_000)
        raise ValueError("mode must be plan_only or verify")


class TokenBudgetLedger:
    def __init__(self, policy: BudgetPolicy, *, quota_limit: int | None = None) -> None:
        self.policy = policy
        self.quota_limit = quota_limit
        self.total_used = 0
        self.primary_calls = 0
        self.retries = 0
        self.decisions: list[BudgetDecision] = []
        self._phase_used = [0, 0, 0]

    def reserve(
        self,
        *,
        phase: int,
        input_tokens: int,
        output_tokens: int,
        retry: bool = False,
    ) -> BudgetDecision:
        if phase not in range(3):
            raise ValueError("phase must be 0, 1, or 2")
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
