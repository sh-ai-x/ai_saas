"""Bounded, restart-safe worker execution."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

from services.metering_billing.ports import CreditReservationPort
from services.run_service.models import Run
from services.run_service.store import SQLiteRunStore


class WorkerInterrupted(RuntimeError):
    """The worker stopped before its checkpoint; retry is expected."""


class ApprovalRequired(RuntimeError):
    """A high-impact operation must pause until the user approves it."""


@dataclass(frozen=True)
class ModelResult:
    output: str
    usage_units: int = 1
    done: bool = True
    approval_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.output, str):
            raise ValueError("model output must be text")
        if not isinstance(self.usage_units, int) or isinstance(self.usage_units, bool) or self.usage_units < 0:
            raise ValueError("usage_units must be a non-negative integer")


class ModelCallable(Protocol):
    def __call__(self, prompt: str, *, idempotency_key: str, timeout_seconds: float) -> ModelResult:
        ...


class Tracer(Protocol):
    def start_span(self, name: str, attributes: Mapping[str, Any] | None = None):
        ...


class BoundedWorker:
    """Executes one run with explicit step, call, and wall-clock limits."""

    def __init__(
        self,
        runs: SQLiteRunStore,
        credits: CreditReservationPort,
        model: ModelCallable,
        *,
        after_model: Callable[[str, int, ModelResult], None] | None = None,
        after_commit: Callable[[str, int], None] | None = None,
        tracer: Tracer | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._runs = runs
        self._credits = credits
        self._model = model
        self._after_model = after_model
        self._after_commit = after_commit
        self._tracer = tracer
        self._clock = clock

    def execute(self, run_id: str) -> Run:
        run = self._runs.claim(run_id)
        if run.state in {"completed", "failed", "cancelled", "waiting_approval", "quota_paused"}:
            return run
        if not run.reservation_id:
            return self._runs.fail(run_id, "missing credit reservation")
        checkpoint = self._runs.checkpoint(run_id)
        step = checkpoint.step if checkpoint else 0
        used_units = checkpoint.usage_units if checkpoint else 0
        if checkpoint is not None and checkpoint.state.get("done") is True:
            if checkpoint.state.get("token_emitted") is not True:
                self._runs.append_token(run_id, str(checkpoint.state.get("last_output", "")))
            self._credits.commit(run.reservation_id, used_units, idempotency_key=f"run-commit:{run_id}")
            return self._runs.complete(run_id, usage_units=used_units)
        deadline = self._clock() + run.max_runtime_seconds
        model_calls = 0
        while step < run.max_steps and model_calls < run.max_model_calls:
            current = self._runs.get(run_id)
            if current.cancel_requested:
                self._settle_or_release(run.reservation_id, used_units, run_id)
                return self._runs.transition(run_id, "cancelled", payload={"reason": "user_cancelled"})
            if self._clock() >= deadline:
                self._settle_or_release(run.reservation_id, used_units, run_id)
                return self._runs.fail(run_id, "workflow timeout")

            inflight_key = (
                checkpoint.inflight_key
                if checkpoint is not None and checkpoint.step == step and checkpoint.inflight_key
                else f"{run_id}:model:{step}"
            )
            self._runs.save_checkpoint(
                run_id,
                step=step,
                state={"step": step},
                inflight_key=inflight_key,
                approval_id=None,
                usage_units=used_units,
            )
            prompt = self._prompt(run)
            if self._tracer is None:
                result = self._model(
                    prompt,
                    idempotency_key=inflight_key,
                    timeout_seconds=max(0.01, deadline - self._clock()),
                )
            else:
                with self._tracer.start_span(
                    "agent.model_call",
                    {
                        "run_id": run.run_id,
                        "tenant_id": run.tenant_id,
                        "trace_id": run.trace_id,
                        "step": step,
                    },
                ) as span:
                    result = self._model(
                        prompt,
                        idempotency_key=inflight_key,
                        timeout_seconds=max(0.01, deadline - self._clock()),
                    )
                    span.set_attribute("usage_units", result.usage_units)
            model_calls += 1
            if self._after_model is not None:
                self._after_model(run_id, step, result)

            used_units += result.usage_units
            next_step = step + 1
            self._runs.save_checkpoint(
                run_id,
                step=next_step,
                state={"step": next_step, "last_output": result.output, "done": result.done, "token_emitted": False},
                inflight_key=None,
                approval_id=result.approval_id,
                usage_units=used_units,
            )
            if result.approval_id:
                self._runs.append_token(run_id, "[approval required]")
                return self._runs.transition(run_id, "waiting_approval", payload={"approval_id": result.approval_id})
            self._runs.append_token(run_id, result.output)
            checkpoint = self._runs.checkpoint(run_id)
            step = next_step
            if result.done:
                try:
                    self._credits.commit(
                        run.reservation_id,
                        used_units,
                        idempotency_key=f"run-commit:{run_id}",
                    )
                except ValueError:
                    self._settle_or_release(run.reservation_id, 0, run_id)
                    return self._runs.fail(run_id, "actual usage exceeded reservation")
                if self._after_commit is not None:
                    self._after_commit(run_id, used_units)
                return self._runs.complete(run_id, usage_units=used_units)

        self._settle_or_release(run.reservation_id, used_units, run_id)
        return self._runs.fail(run_id, "workflow step or model-call limit exceeded")

    def _settle_or_release(self, reservation_id: str, used_units: int, run_id: str) -> None:
        if used_units:
            try:
                self._credits.commit(reservation_id, used_units, idempotency_key=f"run-commit:{run_id}")
                return
            except ValueError:
                # The reservation is too small for actual usage; never turn a
                # bounded failure into a negative balance.
                pass
        self._credits.release(reservation_id, idempotency_key=f"run-release:{run_id}")

    @staticmethod
    def _prompt(run: Run) -> str:
        value = run.input.get("message", run.input.get("prompt", ""))
        return value if isinstance(value, str) else str(value)
