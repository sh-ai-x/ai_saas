"""Kernel-facing replaceable ports."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence

from .contracts import EvidenceReference, Plan, Requirement


class ProjectPackPort(Protocol):
    def parse(self, proposal: str) -> tuple[Requirement, ...]: ...

    def evidence(self, proposal: str) -> tuple[EvidenceReference, ...]: ...

    def plan(self, requirements: Sequence[Requirement], evidence: Sequence[EvidenceReference], mode: str) -> Plan: ...


class StructuredModelPort(Protocol):
    provider_id: str

    def generate(
        self,
        prompt: str,
        *,
        context: Mapping[str, Any],
        schema: str,
        idempotency_key: str,
    ) -> Any: ...


class TracePort(Protocol):
    def record(self, name: str, attributes: Mapping[str, Any]) -> None: ...


class SandboxPort(Protocol):
    def apply(self, plan: Any, *, approval: Any, retry: bool = False) -> Any: ...

    def test(self, plan: Any) -> Any: ...


class DeliveryPort(Protocol):
    def sign(self, **kwargs: Any) -> Any: ...

    def validate(self, request: Any) -> bool: ...
