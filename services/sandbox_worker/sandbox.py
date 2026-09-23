"""Bounded local execution workers for approved repository changes.

The deterministic worker never executes a repository command.  The process
worker may execute only commands already present in a typed plan, inside a
temporary checkout created from the approved commit and with a scrubbed
environment.
"""

from __future__ import annotations

import difflib
import hashlib
import os
import re
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Mapping

from agent_platform.contracts import ApprovalToken, Plan


class SandboxFailure(RuntimeError):
    """A readable, fail-closed execution failure."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class SandboxPolicy:
    allowlisted_paths: tuple[str, ...] = ("agent_platform", "services", "project_packs", "tests")
    allowed_commands: tuple[str, ...] = ("python3 -m pytest", "python3 -m compileall")
    network_enabled: bool = False
    max_seconds: int = 60
    max_memory_mb: int = 512
    max_commands: int = 8
    max_output_bytes: int = 32_768
    max_files: int = 2_048
    max_archive_bytes: int = 64 * 1024 * 1024


@dataclass(frozen=True)
class CommandResult:
    command: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    allowed: bool = True


@dataclass(frozen=True)
class SimulationResult:
    success: bool
    action: str
    detail: str
    workspace_path: str | None = None
    base_commit: str | None = None
    changed_files: tuple[str, ...] = ()
    diff_artifact: Mapping[str, Any] | None = None
    command_results: tuple[Mapping[str, Any], ...] = ()
    error_code: str | None = None


def _safe_relative(path: str) -> str:
    normalized = Path(path).as_posix()
    parts = Path(normalized).parts
    if normalized.startswith("/") or any(part in {"", ".", ".."} for part in parts):
        raise SandboxFailure("unsafe_archive_path", path)
    return normalized


def _path_allowed(path: str, allowlisted_paths: tuple[str, ...]) -> bool:
    return any(path == prefix or path.startswith(prefix + "/") for prefix in allowlisted_paths)


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class IsolatedRepositoryWorkspace:
    """Create a disposable tree from a local Git commit without touching it."""

    def __init__(self, source_root: str | Path, approved_snapshot: Mapping[str, Any], policy: SandboxPolicy) -> None:
        self.source_root = Path(source_root).resolve(strict=True)
        self.approved_snapshot = dict(approved_snapshot)
        self.policy = policy
        self.root: Path | None = None
        self.base_commit = str(approved_snapshot.get("commit", approved_snapshot.get("head_commit", "")))
        self.baseline: dict[str, bytes] = {}

    def create(self) -> "IsolatedRepositoryWorkspace":
        self._validate_source()
        archive = self._git_archive()
        if len(archive) > self.policy.max_archive_bytes:
            raise SandboxFailure("workspace_limit_exceeded", "approved repository archive is too large")
        self.root = Path(tempfile.mkdtemp(prefix="local-lite-workspace-"))
        try:
            self._extract(archive)
            self.baseline = self._manifest()
            return self
        except SandboxFailure:
            self.dispose()
            raise
        except Exception as exc:
            self.dispose()
            raise SandboxFailure("workspace_create_failed", "approved commit could not be safely extracted") from exc

    def dispose(self) -> None:
        if self.root is not None:
            shutil.rmtree(self.root, ignore_errors=True)
            self.root = None

    def _validate_source(self) -> None:
        if not re.fullmatch(r"[0-9a-fA-F]{40}", self.base_commit):
            raise SandboxFailure("approved_commit_invalid", "approval must contain a full commit SHA")
        branch, commit, dirty = self.source_state()
        expected_branch = self.approved_snapshot.get("branch")
        expected_commit = self.approved_snapshot.get("commit", self.approved_snapshot.get("head_commit"))
        expected_dirty = bool(self.approved_snapshot.get("dirty", False))
        if expected_branch and branch != expected_branch:
            raise SandboxFailure("stale_commit", "repository branch changed after approval")
        if expected_commit and commit != expected_commit:
            raise SandboxFailure("stale_commit", "repository commit changed after approval")
        if dirty != expected_dirty:
            raise SandboxFailure("stale_commit", "repository dirty state changed after approval")
        if commit != self.base_commit:
            raise SandboxFailure("stale_commit", "approved commit is not the current checkout")
        self._git_value("cat-file", "-e", f"{self.base_commit}^{{commit}}")

    def source_state(self) -> tuple[str, str, bool]:
        return (
            self._git_value("rev-parse", "--abbrev-ref", "HEAD"),
            self._git_value("rev-parse", "HEAD"),
            bool(self._git_value("status", "--porcelain=v1", "--untracked-files=normal")),
        )

    def source_unchanged(self) -> bool:
        branch, commit, dirty = self.source_state()
        expected_branch = self.approved_snapshot.get("branch")
        expected_commit = self.approved_snapshot.get("commit", self.approved_snapshot.get("head_commit"))
        return branch == (expected_branch or branch) and commit == (expected_commit or commit) and dirty == bool(self.approved_snapshot.get("dirty", False))

    def _git_value(self, *arguments: str) -> str:
        environment = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C", "LANG": "C"}
        try:
            completed = subprocess.run(["git", "-C", str(self.source_root), *arguments], capture_output=True, text=True, env=environment, timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SandboxFailure("repository_inspection_failed", "bounded Git inspection failed") from exc
        if completed.returncode != 0:
            raise SandboxFailure("repository_inspection_failed", completed.stderr[:512] or "Git inspection failed")
        return completed.stdout.strip()

    def _git_archive(self) -> bytes:
        environment = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C", "LANG": "C"}
        try:
            completed = subprocess.run(["git", "-C", str(self.source_root), "archive", "--format=tar", self.base_commit], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment, timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SandboxFailure("workspace_create_failed", "could not archive the approved commit") from exc
        if completed.returncode != 0:
            raise SandboxFailure("workspace_create_failed", completed.stderr.decode(errors="replace")[:512] or "could not archive the approved commit")
        return completed.stdout

    def _extract(self, archive: bytes) -> None:
        if self.root is None:
            raise SandboxFailure("workspace_create_failed", "workspace is not allocated")
        total = 0
        files = 0
        with tarfile.open(fileobj=BytesIO(archive), mode="r:") as stream:
            for member in stream:
                if member.isdir():
                    continue
                path = _safe_relative(member.name)
                if member.issym() or member.islnk() or not member.isfile():
                    raise SandboxFailure("unsafe_archive_entry", path)
                if len(Path(path).parts) > 16:
                    raise SandboxFailure("workspace_limit_exceeded", "archive path depth exceeded")
                files += 1
                if files > self.policy.max_files:
                    raise SandboxFailure("workspace_limit_exceeded", "archive file count exceeded")
                total += member.size
                if total > self.policy.max_archive_bytes:
                    raise SandboxFailure("workspace_limit_exceeded", "archive content exceeded limit")
                target = self.root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                source = stream.extractfile(member)
                if source is None:
                    raise SandboxFailure("workspace_create_failed", f"archive entry has no content: {path}")
                target.write_bytes(source.read(self.policy.max_archive_bytes + 1))

    def _manifest(self) -> dict[str, bytes]:
        if self.root is None:
            return {}
        manifest: dict[str, bytes] = {}
        total = 0
        for candidate in sorted(self.root.rglob("*")):
            if candidate.is_symlink() or not candidate.is_file():
                continue
            relative = candidate.relative_to(self.root).as_posix()
            if len(manifest) >= self.policy.max_files:
                raise SandboxFailure("workspace_limit_exceeded", "workspace file count exceeded")
            data = candidate.read_bytes()
            total += len(data)
            if total > self.policy.max_archive_bytes:
                raise SandboxFailure("workspace_limit_exceeded", "workspace content exceeded limit")
            manifest[relative] = data
        return manifest

    def diff(self) -> Mapping[str, Any]:
        if not self.source_unchanged():
            raise SandboxFailure("source_changed", "source checkout changed during isolated execution")
        current = self._manifest()
        changed: list[dict[str, Any]] = []
        for path in sorted(set(self.baseline) | set(current)):
            before = self.baseline.get(path)
            after = current.get(path)
            if before == after:
                continue
            if not _path_allowed(path, self.policy.allowlisted_paths):
                raise SandboxFailure("path_not_allowlisted", path)
            status = "added" if before is None else "deleted" if after is None else "modified"
            changed.append({"path": path, "status": status, "before_hash": _digest(before) if before is not None else None, "after_hash": _digest(after) if after is not None else None, "patch": _unified_patch(path, before, after)})
        return {
            "schema_version": "1.0",
            "kind": "repository_diff",
            "base_commit": self.base_commit,
            "changed_files": [item["path"] for item in changed],
            "files": changed,
            "source_unchanged": True,
        }


def _unified_patch(path: str, before: bytes | None, after: bytes | None) -> str:
    def lines(value: bytes | None) -> list[str]:
        if value is None:
            return []
        try:
            return value.decode("utf-8").splitlines(keepends=True)
        except UnicodeDecodeError:
            return [f"[binary content: {_digest(value)}]\n"]

    return "".join(difflib.unified_diff(lines(before), lines(after), fromfile=f"a/{path}", tofile=f"b/{path}"))


class IsolatedRepositorySandbox:
    """Deterministic offline executor backed by an approved commit archive."""

    def __init__(self, source_root: str | Path, approved_snapshot: Mapping[str, Any], policy: SandboxPolicy | None = None, *, patcher: Callable[[Path, Plan], None] | None = None) -> None:
        self.source_root = Path(source_root)
        self.approved_snapshot = dict(approved_snapshot)
        self.policy = policy or SandboxPolicy()
        self.patcher = patcher
        self.workspace: IsolatedRepositoryWorkspace | None = None
        self.patch_calls = 0
        self.test_calls = 0
        self._last_diff: Mapping[str, Any] | None = None

    def apply(self, plan: Plan, *, approval: ApprovalToken | None, retry: bool = False, source_root: str | Path | None = None, approved_snapshot: Mapping[str, Any] | None = None) -> SimulationResult:
        if approval is None or "patch" not in approval.scopes:
            return SimulationResult(False, "patch", "valid patch approval is required", error_code="approval_required")
        if any(not _path_allowed(evidence.path, self.policy.allowlisted_paths) for step in plan.steps for evidence in step.evidence):
            return SimulationResult(False, "patch", "path is not allowlisted", error_code="path_not_allowlisted")
        if retry and self.workspace is not None:
            self.workspace.dispose()
            self.workspace = None
        if self.workspace is None:
            if source_root is not None:
                self.source_root = Path(source_root)
            if approved_snapshot is not None:
                self.approved_snapshot = dict(approved_snapshot)
            try:
                self.workspace = IsolatedRepositoryWorkspace(self.source_root, self.approved_snapshot, self.policy).create()
            except SandboxFailure as exc:
                return SimulationResult(False, "patch", str(exc), error_code=exc.code)
        self.patch_calls += 1
        try:
            if self.patcher is not None:
                self.patcher(self.workspace.root, plan)
            self._last_diff = self.workspace.diff()
            changed = tuple(self._last_diff["changed_files"])
            return SimulationResult(True, "patch", "approved patch applied in disposable workspace", str(self.workspace.root), self.workspace.base_commit, changed, self._last_diff)
        except Exception as exc:
            code = exc.code if isinstance(exc, SandboxFailure) else "patch_failed"
            return SimulationResult(False, "patch", str(exc), str(self.workspace.root), self.workspace.base_commit, error_code=code)

    def test(self, plan: Plan) -> SimulationResult:
        self.test_calls += 1
        if self.workspace is None or self._last_diff is None:
            return SimulationResult(False, "test", "isolated workspace is not ready", error_code="workspace_missing")
        try:
            unchanged = self.workspace.source_unchanged()
        except SandboxFailure as exc:
            return SimulationResult(False, "test", str(exc), str(self.workspace.root), self.workspace.base_commit, tuple(self._last_diff["changed_files"]), self._last_diff, error_code=exc.code)
        if not unchanged:
            return SimulationResult(False, "test", "source checkout changed during isolated execution", str(self.workspace.root), self.workspace.base_commit, tuple(self._last_diff["changed_files"]), self._last_diff, error_code="source_changed")
        if not plan.valid_references or not plan.steps:
            return SimulationResult(False, "test", "plan has no valid executable evidence", error_code="invalid_evidence")
        commands = tuple(command for step in plan.steps for command in step.commands)
        if commands:
            return SimulationResult(False, "test", "deterministic mode rejects undeclared process execution", str(self.workspace.root), self.workspace.base_commit, tuple(self._last_diff["changed_files"]), self._last_diff, error_code="deterministic_command_rejected")
        result = {"command": "deterministic:evidence-validation", "exit_code": 0, "stdout": "evidence and diff validation passed", "stderr": "", "duration_seconds": 0.0, "offline": True}
        return SimulationResult(True, "test", "deterministic offline verification passed", str(self.workspace.root), self.workspace.base_commit, tuple(self._last_diff["changed_files"]), self._last_diff, (result,))

    def close(self) -> None:
        if self.workspace is not None:
            self.workspace.dispose()
            self.workspace = None


class ProcessSandbox(IsolatedRepositorySandbox):
    """Execute only typed, allowlisted plan commands in the isolated tree."""

    def test(self, plan: Plan) -> SimulationResult:
        self.test_calls += 1
        if self.workspace is None or self._last_diff is None:
            return SimulationResult(False, "test", "isolated workspace is not ready", error_code="workspace_missing")
        try:
            unchanged = self.workspace.source_unchanged()
        except SandboxFailure as exc:
            return SimulationResult(False, "test", str(exc), str(self.workspace.root), self.workspace.base_commit, tuple(self._last_diff["changed_files"]), self._last_diff, error_code=exc.code)
        if not unchanged:
            return SimulationResult(False, "test", "source checkout changed during isolated execution", str(self.workspace.root), self.workspace.base_commit, tuple(self._last_diff["changed_files"]), self._last_diff, error_code="source_changed")
        if not plan.valid_references or not plan.steps:
            return SimulationResult(False, "test", "plan has no valid executable evidence", error_code="invalid_evidence")
        commands = tuple(command for step in plan.steps for command in step.commands)
        if not commands:
            return SimulationResult(False, "test", "process mode requires declared verification commands", str(self.workspace.root), self.workspace.base_commit, tuple(self._last_diff["changed_files"]), self._last_diff, error_code="verification_commands_missing")
        if len(commands) > self.policy.max_commands:
            return SimulationResult(False, "test", "verification command budget exceeded", str(self.workspace.root), self.workspace.base_commit, tuple(self._last_diff["changed_files"]), self._last_diff, error_code="verification_budget_exceeded")
        results: list[Mapping[str, Any]] = []
        safe_environment = {"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"), "HOME": str(self.workspace.root), "LANG": "C", "LC_ALL": "C", "CI": "1", "PYTHONNOUSERSITE": "1"}
        for command in commands:
            if not isinstance(command, str) or not _command_allowed(command, self.policy):
                return SimulationResult(False, "test", f"verification command is not allowlisted: {command}", str(self.workspace.root), self.workspace.base_commit, tuple(self._last_diff["changed_files"]), self._last_diff, tuple(results), "command_not_allowlisted")
            try:
                argv = shlex.split(command)
            except ValueError:
                return SimulationResult(False, "test", "verification command cannot be parsed", str(self.workspace.root), self.workspace.base_commit, tuple(self._last_diff["changed_files"]), self._last_diff, tuple(results), "command_invalid")
            started = time.monotonic()
            try:
                completed = subprocess.run(argv, cwd=self.workspace.root, env=safe_environment, shell=False, capture_output=True, text=True, timeout=self.policy.max_seconds, check=False)
                stdout = completed.stdout[: self.policy.max_output_bytes]
                stderr = completed.stderr[: self.policy.max_output_bytes]
                command_result = {"command": command, "exit_code": completed.returncode, "stdout": stdout, "stderr": stderr, "duration_seconds": round(time.monotonic() - started, 6), "offline": not self.policy.network_enabled}
            except subprocess.TimeoutExpired as exc:
                command_result = {"command": command, "exit_code": 124, "stdout": str(exc.stdout or "")[: self.policy.max_output_bytes], "stderr": str(exc.stderr or "")[: self.policy.max_output_bytes], "duration_seconds": round(time.monotonic() - started, 6), "timeout": True, "offline": not self.policy.network_enabled}
            except OSError as exc:
                command_result = {"command": command, "exit_code": 127, "stdout": "", "stderr": str(exc)[: self.policy.max_output_bytes], "duration_seconds": round(time.monotonic() - started, 6), "offline": not self.policy.network_enabled}
            results.append(command_result)
            if command_result["exit_code"] != 0:
                return SimulationResult(False, "test", f"verification command failed: {command}", str(self.workspace.root), self.workspace.base_commit, tuple(self._last_diff["changed_files"]), self._last_diff, tuple(results), "verification_command_failed")
        return SimulationResult(True, "test", "bounded verification commands passed", str(self.workspace.root), self.workspace.base_commit, tuple(self._last_diff["changed_files"]), self._last_diff, tuple(results))


def _command_allowed(command: str, policy: SandboxPolicy) -> bool:
    if not command or len(command) > 512 or any(char in command for char in ";&|><`$\x00"):
        return False
    try:
        normalized = " ".join(shlex.split(command))
    except ValueError:
        return False
    return any(normalized == allowed or normalized.startswith(allowed + " ") for allowed in policy.allowed_commands)


class DeterministicSandbox:
    """Compatibility worker used by the existing no-filesystem tests."""

    def __init__(self, policy: SandboxPolicy | None = None, *, fail_first_patch: bool = False) -> None:
        self.policy = policy or SandboxPolicy()
        self.fail_first_patch = fail_first_patch
        self.patch_calls = 0
        self.test_calls = 0

    def apply(self, plan: Plan, *, approval: ApprovalToken | None, retry: bool = False, **_: Any) -> SimulationResult:
        if approval is None or "patch" not in approval.scopes:
            return SimulationResult(False, "patch", "valid patch approval is required", error_code="approval_required")
        if any(not _path_allowed(evidence.path, self.policy.allowlisted_paths) for step in plan.steps for evidence in step.evidence):
            return SimulationResult(False, "patch", "path is not allowlisted", error_code="path_not_allowlisted")
        self.patch_calls += 1
        if self.fail_first_patch and self.patch_calls == 1 and not retry:
            return SimulationResult(False, "patch", "deterministic transient patch failure", error_code="patch_failed")
        return SimulationResult(True, "patch", "patch simulation applied; no filesystem mutation", changed_files=())

    def test(self, plan: Plan, **_: Any) -> SimulationResult:
        self.test_calls += 1
        if not plan.valid_references or not plan.steps:
            return SimulationResult(False, "test", "plan has no valid executable evidence", error_code="invalid_evidence")
        result = {"command": "deterministic:evidence-validation", "exit_code": 0, "stdout": "deterministic test simulation passed", "stderr": "", "duration_seconds": 0.0, "offline": True}
        return SimulationResult(True, "test", "deterministic test simulation passed", command_results=(result,))
