"""Bounded catalog and authorization boundary for mounted local Git roots."""

from __future__ import annotations

import hashlib
import os
import re
import selectors
import sqlite3
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence


READ_ANALYSIS = "read_analysis"
WRITE_PATCH = "write_patch"
SUPPORTED_SCOPES = frozenset({READ_ANALYSIS, WRITE_PATCH})
MAX_DISCOVERY_DEPTH = 8
MAX_REPOSITORIES = 128
MAX_DISCOVERY_DIRECTORIES = 4096
MAX_GIT_OUTPUT = 4096
GIT_TIMEOUT_SECONDS = 2.0
_TENANT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class RepositoryCatalogError(ValueError, PermissionError):
    """Stable safe error raised for catalog and scope failures."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class RepositoryRoot:
    root_id: str
    canonical_path: str


@dataclass(frozen=True)
class RepositoryRecord:
    repository_id: str
    root_id: str
    canonical_path: str
    name: str
    branch: str
    head_commit: str
    dirty: bool
    capabilities: tuple[str, ...]


@dataclass(frozen=True)
class RepositoryScope:
    scope_id: str
    tenant_id: str
    repository_id: str
    permission: str
    issued_at: str
    expires_at: str
    parent_scope_id: str | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _path_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _stable_id(prefix: str, value: str, length: int = 24) -> str:
    return f"{prefix}-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:length]}"


def _validate_tenant(tenant_id: str) -> str:
    if not isinstance(tenant_id, str) or not _TENANT_PATTERN.fullmatch(tenant_id):
        raise RepositoryCatalogError("tenant_invalid")
    return tenant_id


def parse_repository_roots(value: str | Sequence[str] | None) -> tuple[Path, ...]:
    """Parse explicit local roots without interpreting URLs or shell syntax."""

    if value is None:
        return ()
    if isinstance(value, str):
        raw_items = re.split(r"[,\n]+", value)
    else:
        raw_items = list(value)
    roots: list[Path] = []
    for raw in raw_items:
        item = str(raw).strip()
        if not item:
            continue
        if "://" in item or item.startswith("git@") or item.startswith("-"):
            raise RepositoryCatalogError("repository_remote_unsupported")
        candidate = Path(item).expanduser()
        if not candidate.is_absolute():
            raise RepositoryCatalogError("repository_root_not_absolute")
        try:
            canonical = candidate.resolve(strict=True)
        except OSError as exc:
            raise RepositoryCatalogError("repository_root_unavailable") from exc
        if not canonical.is_dir():
            raise RepositoryCatalogError("repository_root_not_directory")
        if canonical not in roots:
            roots.append(canonical)
    for index, left in enumerate(roots):
        for right in roots[index + 1 :]:
            if _path_inside(left, right) or _path_inside(right, left):
                raise RepositoryCatalogError("repository_root_ambiguous")
    return tuple(roots)


class RepositoryAuthorizationStore:
    """Persist opaque read and write scopes with tenant/repository bindings."""

    def __init__(self, database: str = ":memory:") -> None:
        self._db = sqlite3.connect(database, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS repository_scopes (
                scope_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                repository_id TEXT NOT NULL,
                permission TEXT NOT NULL,
                parent_scope_id TEXT,
                issued_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def issue_read(self, tenant_id: str, repository_id: str, *, ttl_seconds: int = 1800) -> RepositoryScope:
        return self._issue(tenant_id, repository_id, READ_ANALYSIS, None, ttl_seconds)

    def issue_write(
        self,
        tenant_id: str,
        repository_id: str,
        *,
        read_scope_id: str,
        ttl_seconds: int = 1800,
    ) -> RepositoryScope:
        read_scope = self.require(read_scope_id, tenant_id, repository_id, READ_ANALYSIS)
        issued = _utc_now()
        if issued <= datetime.fromisoformat(read_scope.issued_at):
            raise RepositoryCatalogError("write_scope_not_later")
        return self._issue(tenant_id, repository_id, WRITE_PATCH, read_scope.scope_id, ttl_seconds, issued=issued)

    def require(self, scope_id: str, tenant_id: str, repository_id: str, permission: str) -> RepositoryScope:
        _validate_tenant(tenant_id)
        if permission not in SUPPORTED_SCOPES or not isinstance(scope_id, str) or not scope_id:
            raise RepositoryCatalogError("scope_invalid")
        row = self._db.execute("SELECT * FROM repository_scopes WHERE scope_id = ?", (scope_id,)).fetchone()
        if row is None or bool(row["revoked"]):
            raise RepositoryCatalogError("scope_invalid")
        if row["tenant_id"] != tenant_id or row["repository_id"] != repository_id or row["permission"] != permission:
            raise RepositoryCatalogError("scope_mismatch")
        try:
            expired = datetime.fromisoformat(row["expires_at"]) <= _utc_now()
        except ValueError:
            expired = True
        if expired:
            raise RepositoryCatalogError("scope_expired")
        return self._scope(row)

    def state(self, tenant_id: str, repository_id: str) -> dict[str, bool]:
        _validate_tenant(tenant_id)
        result = {READ_ANALYSIS: False, WRITE_PATCH: False}
        rows = self._db.execute(
            "SELECT permission, expires_at, revoked FROM repository_scopes WHERE tenant_id = ? AND repository_id = ?",
            (tenant_id, repository_id),
        ).fetchall()
        for row in rows:
            if not bool(row["revoked"]):
                try:
                    active = datetime.fromisoformat(row["expires_at"]) > _utc_now()
                except ValueError:
                    active = False
                result[row["permission"]] = result.get(row["permission"], False) or active
        return result

    def _issue(
        self,
        tenant_id: str,
        repository_id: str,
        permission: str,
        parent_scope_id: str | None,
        ttl_seconds: int,
        *,
        issued: datetime | None = None,
    ) -> RepositoryScope:
        _validate_tenant(tenant_id)
        if permission not in SUPPORTED_SCOPES or not isinstance(repository_id, str) or not repository_id:
            raise RepositoryCatalogError("scope_invalid")
        if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool) or not 1 <= ttl_seconds <= 3600:
            raise RepositoryCatalogError("scope_ttl_invalid")
        issued = issued or _utc_now()
        scope = RepositoryScope(
            scope_id=f"scope-{uuid.uuid4().hex}",
            tenant_id=tenant_id,
            repository_id=repository_id,
            permission=permission,
            issued_at=_timestamp(issued),
            expires_at=_timestamp(issued + timedelta(seconds=ttl_seconds)),
            parent_scope_id=parent_scope_id,
        )
        self._db.execute(
            "INSERT INTO repository_scopes VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
            (scope.scope_id, scope.tenant_id, scope.repository_id, scope.permission, scope.parent_scope_id, scope.issued_at, scope.expires_at),
        )
        self._db.commit()
        return scope

    @staticmethod
    def _scope(row: sqlite3.Row) -> RepositoryScope:
        return RepositoryScope(row["scope_id"], row["tenant_id"], row["repository_id"], row["permission"], row["issued_at"], row["expires_at"], row["parent_scope_id"])


class LocalRepositoryCatalog:
    """Discover only Git roots below explicitly configured local directories."""

    def __init__(
        self,
        roots: str | Sequence[str] | None,
        *,
        scope_database: str = ":memory:",
        max_depth: int = MAX_DISCOVERY_DEPTH,
        max_repositories: int = MAX_REPOSITORIES,
    ) -> None:
        if not isinstance(max_depth, int) or not 0 <= max_depth <= MAX_DISCOVERY_DEPTH:
            raise RepositoryCatalogError("discovery_limit_invalid")
        if not isinstance(max_repositories, int) or not 1 <= max_repositories <= MAX_REPOSITORIES:
            raise RepositoryCatalogError("discovery_limit_invalid")
        self._root_aliases = self._configured_root_aliases(roots)
        canonical_roots = parse_repository_roots(roots)
        self.roots = tuple(RepositoryRoot(_stable_id("root", str(path), 16), str(path)) for path in canonical_roots)
        self._root_paths = tuple(Path(root.canonical_path) for root in self.roots)
        self.max_depth = max_depth
        self.max_repositories = max_repositories
        self.scopes = RepositoryAuthorizationStore(scope_database)

    def close(self) -> None:
        self.scopes.close()

    def list_repositories(self) -> tuple[RepositoryRecord, ...]:
        records: dict[str, RepositoryRecord] = {}
        for root in self._root_paths:
            for candidate in self._walk(root):
                record = self._record(candidate, root)
                if record.repository_id in records and records[record.repository_id] != record:
                    raise RepositoryCatalogError("repository_root_ambiguous")
                records[record.repository_id] = record
                if len(records) > self.max_repositories:
                    raise RepositoryCatalogError("repository_discovery_limit")
        return tuple(records[key] for key in sorted(records))

    def get(self, repository_id: str) -> RepositoryRecord:
        for record in self.list_repositories():
            if record.repository_id == repository_id:
                return record
        raise RepositoryCatalogError("repository_not_found")

    def resolve(self, raw_path: str) -> RepositoryRecord:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise RepositoryCatalogError("repository_path_required")
        if "://" in raw_path or raw_path.startswith("git@"):
            raise RepositoryCatalogError("repository_remote_unsupported")
        candidate_path = Path(raw_path).expanduser()
        if not candidate_path.is_absolute():
            raise RepositoryCatalogError("repository_path_invalid")
        lexical = Path(os.path.abspath(candidate_path))
        lexical_root_match = any(
            _path_inside(lexical, root) or _path_inside(lexical, alias)
            for root, alias in zip(self._root_paths, self._root_aliases)
        )
        if not lexical_root_match:
            raise RepositoryCatalogError("repository_path_outside_root")
        try:
            canonical = lexical.resolve(strict=True)
        except OSError as exc:
            raise RepositoryCatalogError("repository_path_not_found") from exc
        matching_roots = [root for root in self._root_paths if _path_inside(canonical, root)]
        if not matching_roots:
            if lexical_root_match and (lexical.is_symlink() or self._has_symlink_component(lexical)):
                raise RepositoryCatalogError("repository_symlink_escape")
            raise RepositoryCatalogError("repository_path_outside_root")
        if len(matching_roots) != 1:
            raise RepositoryCatalogError("repository_root_ambiguous")
        if not canonical.is_dir():
            raise RepositoryCatalogError("repository_path_not_directory")
        markers = self._git_ancestors(canonical, matching_roots[0])
        if not markers:
            raise RepositoryCatalogError("repository_not_git")
        if len(markers) > 1:
            raise RepositoryCatalogError("repository_root_ambiguous")
        return self._record(markers[0], matching_roots[0])

    def authorize_read(self, tenant_id: str, *, repository_id: str | None = None, path: str | None = None) -> RepositoryScope:
        record = self._select(repository_id, path)
        return self.scopes.issue_read(_validate_tenant(tenant_id), record.repository_id)

    def authorize_write(
        self,
        tenant_id: str,
        *,
        read_scope_id: str,
        repository_id: str | None = None,
        path: str | None = None,
    ) -> RepositoryScope:
        record = self._select(repository_id, path)
        return self.scopes.issue_write(_validate_tenant(tenant_id), record.repository_id, read_scope_id=read_scope_id)

    def require_read(self, tenant_id: str, repository_id: str, scope_id: str) -> RepositoryScope:
        self.get(repository_id)
        return self.scopes.require(scope_id, tenant_id, repository_id, READ_ANALYSIS)

    def require_write(self, tenant_id: str, repository_id: str, scope_id: str) -> RepositoryScope:
        self.get(repository_id)
        scope = self.scopes.require(scope_id, tenant_id, repository_id, WRITE_PATCH)
        if not scope.parent_scope_id:
            raise RepositoryCatalogError("write_scope_missing_read_parent")
        self.scopes.require(scope.parent_scope_id, tenant_id, repository_id, READ_ANALYSIS)
        return scope

    def authorization_state(self, tenant_id: str, repository_id: str) -> dict[str, bool]:
        self.get(repository_id)
        return self.scopes.state(tenant_id, repository_id)

    def public_record(self, record: RepositoryRecord) -> dict[str, object]:
        return asdict(record)

    def _select(self, repository_id: str | None, path: str | None) -> RepositoryRecord:
        if repository_id and path:
            resolved = self.resolve(path)
            if resolved.repository_id != repository_id:
                raise RepositoryCatalogError("repository_identity_mismatch")
            return resolved
        if repository_id:
            return self.get(repository_id)
        if path:
            return self.resolve(path)
        raise RepositoryCatalogError("repository_identity_required")

    def _walk(self, root: Path) -> Iterable[Path]:
        queue: list[tuple[Path, int]] = [(root, 0)]
        visited = 0
        while queue:
            current, depth = queue.pop(0)
            visited += 1
            if visited > MAX_DISCOVERY_DIRECTORIES:
                raise RepositoryCatalogError("repository_discovery_limit")
            marker = current / ".git"
            if marker.is_symlink():
                continue
            if marker.is_dir() or marker.is_file():
                yield current
                continue
            if depth >= self.max_depth:
                continue
            try:
                entries = sorted(os.scandir(current), key=lambda entry: entry.name)
            except OSError:
                continue
            for entry in entries:
                if entry.name.startswith("."):
                    continue
                try:
                    if entry.is_dir(follow_symlinks=False):
                        queue.append((Path(entry.path), depth + 1))
                except OSError:
                    continue

    def _git_ancestors(self, candidate: Path, root: Path) -> list[Path]:
        result: list[Path] = []
        current = candidate
        while _path_inside(current, root):
            marker = current / ".git"
            if marker.is_symlink():
                raise RepositoryCatalogError("repository_symlink_escape")
            if marker.is_dir() or marker.is_file():
                result.append(current)
            if current == root:
                break
            current = current.parent
        return result

    def _record(self, repository_path: Path, root: Path) -> RepositoryRecord:
        canonical = repository_path.resolve(strict=True)
        if not _path_inside(canonical, root):
            raise RepositoryCatalogError("repository_symlink_escape")
        top_level, branch, head, dirty = self._git_metadata(canonical)
        if top_level != canonical:
            raise RepositoryCatalogError("repository_root_ambiguous")
        return RepositoryRecord(
            repository_id=_stable_id("repo", str(canonical)),
            root_id=_stable_id("root", str(root), 16),
            canonical_path=str(canonical),
            name=canonical.name,
            branch=branch,
            head_commit=head,
            dirty=dirty,
            capabilities=(READ_ANALYSIS, WRITE_PATCH),
        )

    @staticmethod
    def _has_symlink_component(path: Path) -> bool:
        current = Path(path.anchor)
        for part in path.parts[1:]:
            current /= part
            if current.is_symlink():
                return True
        return False

    @staticmethod
    def _configured_root_aliases(value: str | Sequence[str] | None) -> tuple[Path, ...]:
        if value is None:
            return ()
        raw_items = re.split(r"[,\n]+", value) if isinstance(value, str) else list(value)
        aliases: list[Path] = []
        for raw in raw_items:
            item = str(raw).strip()
            if item:
                candidate = Path(item).expanduser()
                if candidate.is_absolute() and candidate.absolute() not in aliases:
                    aliases.append(candidate.absolute())
        return tuple(aliases)

    @staticmethod
    def _git_metadata(repository_path: Path) -> tuple[Path, str, str, bool]:
        top_level_text = LocalRepositoryCatalog._git(repository_path, "rev-parse", "--show-toplevel")
        try:
            top_level = Path(top_level_text).resolve(strict=True)
        except OSError as exc:
            raise RepositoryCatalogError("repository_metadata_unavailable") from exc
        branch = LocalRepositoryCatalog._git(repository_path, "rev-parse", "--abbrev-ref", "HEAD") or "HEAD"
        head = LocalRepositoryCatalog._git(repository_path, "rev-parse", "HEAD")
        status = LocalRepositoryCatalog._git(repository_path, "status", "--porcelain=v1", "--untracked-files=normal")
        return top_level, branch, head, bool(status)

    @staticmethod
    def _git(repository_path: Path, *arguments: str) -> str:
        allowed = {
            ("rev-parse", "--show-toplevel"),
            ("rev-parse", "--abbrev-ref", "HEAD"),
            ("rev-parse", "HEAD"),
            ("status", "--porcelain=v1", "--untracked-files=normal"),
        }
        if arguments not in allowed:
            raise RepositoryCatalogError("git_operation_not_allowed")
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_OPTIONAL_LOCKS": "0",
            "LC_ALL": "C",
        }
        process: subprocess.Popen[bytes] | None = None
        selector: selectors.BaseSelector | None = None
        try:
            process = subprocess.Popen(
                ["git", "--no-pager", "-C", str(repository_path), *arguments],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=environment,
            )
            assert process.stdout is not None
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)
            output = bytearray()
            deadline = time.monotonic() + GIT_TIMEOUT_SECONDS
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(arguments, GIT_TIMEOUT_SECONDS)
                if not selector.select(remaining):
                    raise subprocess.TimeoutExpired(arguments, GIT_TIMEOUT_SECONDS)
                chunk = os.read(process.stdout.fileno(), min(4096, MAX_GIT_OUTPUT + 1 - len(output)))
                if not chunk:
                    break
                output.extend(chunk)
                if len(output) > MAX_GIT_OUTPUT:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                    process.wait()
                    raise RepositoryCatalogError("repository_metadata_too_large")
            return_code = process.wait(timeout=max(0.01, deadline - time.monotonic()))
        except (OSError, subprocess.TimeoutExpired) as exc:
            if process is not None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                process.wait()
            raise RepositoryCatalogError("repository_metadata_unavailable") from exc
        finally:
            if selector is not None:
                selector.close()
            if process is not None and process.stdout is not None:
                process.stdout.close()
        if return_code != 0:
            raise RepositoryCatalogError("repository_not_git")
        return bytes(output).decode("utf-8", errors="replace").strip()
