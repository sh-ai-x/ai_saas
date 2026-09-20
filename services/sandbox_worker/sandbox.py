"""No-shell sandbox simulation for the Local Lite profile."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

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


@dataclass(frozen=True)
class ProcessResult:
    success: bool
    action: str
    detail: str
    duration_ms: int
    stdout: str = ""
    stderr: str = ""


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


class BoundedSubprocessSandbox:
    """Run only declared verification commands in a disposable copy.

    This is the Local Lite execution boundary. It is deliberately not called
    a production isolation boundary: a production deployment should place the
    same protocol behind a dedicated worker VM/container policy. No shell,
    inherited credentials, or model-generated command is accepted here.
    """

    def __init__(self, workspace: str | Path, policy: SandboxPolicy | None = None) -> None:
        self.workspace = Path(workspace).resolve()
        self.policy = policy or SandboxPolicy()

    def apply(self, plan: Plan, *, approval: ApprovalToken | None, retry: bool = False) -> ProcessResult:
        del retry
        if approval is None or "patch" not in approval.scopes:
            return ProcessResult(False, "patch", "valid patch approval is required", 0)
        error = self._validate_plan_paths(plan)
        if error:
            return ProcessResult(False, "patch", error, 0)
        # The current Project Pack emits reviewable plan steps, not arbitrary
        # source edits. Keep the actual workspace immutable until a future
        # patch adapter provides a signed, typed diff.
        return ProcessResult(True, "patch", "verified plan accepted; workspace was not mutated", 0)

    def test(self, plan: Plan) -> ProcessResult:
        error = self._validate_plan_paths(plan)
        if error:
            return ProcessResult(False, "test", error, 0)
        commands = tuple(command for step in plan.steps for command in step.commands)
        if not commands:
            roots = sorted({Path(evidence.path).parts[0] for step in plan.steps for evidence in step.evidence})
            commands = (f"python3 -m compileall -q {' '.join(roots)}",) if roots else ("python3 -m compileall -q .",)
        with tempfile.TemporaryDirectory(prefix="proposal-verified-sandbox-") as temp_dir:
            sandbox_root = Path(temp_dir)
            self._copy_allowlisted_files(sandbox_root)
            for command in commands:
                result = self._run(command, sandbox_root)
                if not result.success:
                    return result
        return ProcessResult(True, "test", "all declared verification commands passed", 0)

    def _run(self, command: str, cwd: Path) -> ProcessResult:
        try:
            args = shlex.split(command)
        except ValueError:
            return ProcessResult(False, "test", "command is not valid shell-free syntax", 0)
        if not args or not self._is_allowed(args):
            return ProcessResult(False, "test", "command is not allowlisted", 0)
        started = time.monotonic()
        env = {"PATH": os.getenv("PATH", "/usr/bin:/bin"), "PYTHONNOUSERSITE": "1", "NO_PROXY": "*", "HOME": str(cwd)}
        try:
            completed = subprocess.run(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=self.policy.max_seconds, check=False, shell=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return ProcessResult(False, "test", "sandbox process failed or timed out", int((time.monotonic() - started) * 1000), stderr=type(exc).__name__)
        duration = int((time.monotonic() - started) * 1000)
        stdout = completed.stdout[-4096:]
        stderr = completed.stderr[-4096:]
        return ProcessResult(completed.returncode == 0, "test", "command passed" if completed.returncode == 0 else "command failed", duration, stdout, stderr)

    def _is_allowed(self, args: list[str]) -> bool:
        return any(args[: len(expected)] == expected for prefix in self.policy.allowed_commands for expected in (shlex.split(prefix),))

    def _validate_plan_paths(self, plan: Plan) -> str | None:
        for step in plan.steps:
            for evidence in step.evidence:
                normalized = Path(evidence.path).as_posix()
                if not any(normalized == prefix or normalized.startswith(prefix + "/") for prefix in self.policy.allowlisted_paths):
                    return "path is not allowlisted"
        return None

    def _copy_allowlisted_files(self, destination: Path) -> None:
        for prefix in self.policy.allowlisted_paths:
            source = self.workspace / prefix
            if not source.exists():
                continue
            target = destination / prefix
            if source.is_dir():
                shutil.copytree(source, target, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
