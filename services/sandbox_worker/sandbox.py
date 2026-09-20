"""No-shell sandbox simulation for the Local Lite profile."""

from __future__ import annotations

from dataclasses import dataclass

from agent_platform.contracts import ApprovalToken, Plan


@dataclass(frozen=True)
class SandboxPolicy:
    allowlisted_paths: tuple[str, ...] = ("agent_platform", "services", "project_packs", "tests")
    allowed_commands: tuple[str, ...] = ("python3 -m pytest", "python3 -m compileall")
    network_enabled: bool = False
    max_seconds: int = 60
    max_memory_mb: int = 512


@dataclass(frozen=True)
class SimulationResult:
    success: bool
    action: str
    detail: str


class DeterministicSandbox:
    def __init__(self, policy: SandboxPolicy | None = None, *, fail_first_patch: bool = False) -> None:
        self.policy = policy or SandboxPolicy()
        self.fail_first_patch = fail_first_patch
        self.patch_calls = 0
        self.test_calls = 0

    def apply(self, plan: Plan, *, approval: ApprovalToken | None, retry: bool = False) -> SimulationResult:
        if approval is None or "patch" not in approval.scopes:
            return SimulationResult(False, "patch", "valid patch approval is required")
        if any(not any(path == prefix or path.startswith(prefix + "/") for prefix in self.policy.allowlisted_paths) for step in plan.steps for evidence in step.evidence for path in (evidence.path,)):
            return SimulationResult(False, "patch", "path is not allowlisted")
        self.patch_calls += 1
        if self.fail_first_patch and self.patch_calls == 1 and not retry:
            return SimulationResult(False, "patch", "deterministic transient patch failure")
        return SimulationResult(True, "patch", "patch simulation applied; no filesystem mutation")

    def test(self, plan: Plan) -> SimulationResult:
        self.test_calls += 1
        if not plan.valid_references or not plan.steps:
            return SimulationResult(False, "test", "plan has no valid executable evidence")
        return SimulationResult(True, "test", "deterministic test simulation passed")

