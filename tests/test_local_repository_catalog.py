from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from services.control_api.repository_catalog import (
    READ_ANALYSIS,
    WRITE_PATCH,
    LocalRepositoryCatalog,
    RepositoryCatalogError,
)


class LocalRepositoryCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)
        self.root = self.base / "mounted"
        self.repo = self.root / "demo-repository"
        self.repo.mkdir(parents=True)
        self._git("init", "-q")
        (self.repo / "README.md").write_text("private source text\n", encoding="utf-8")
        self._git("add", "README.md")
        self._git("-c", "user.email=test@example.invalid", "-c", "user.name=test", "commit", "-qm", "initial")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _git(self, *arguments: str) -> None:
        subprocess.run(["git", "-C", str(self.repo), *arguments], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def test_discovery_returns_metadata_only_and_detects_dirty_state(self) -> None:
        catalog = LocalRepositoryCatalog([str(self.root)])
        record = catalog.list_repositories()[0]
        self.assertEqual(record.name, "demo-repository")
        self.assertIn(record.branch, {"main", "master"})
        self.assertRegex(record.head_commit, r"^[0-9a-f]{40}$")
        self.assertFalse(record.dirty)
        self.assertNotIn("private source text", repr(record))
        (self.repo / "README.md").write_text("changed\n", encoding="utf-8")
        self.assertTrue(catalog.get(record.repository_id).dirty)
        catalog.close()

    def test_outside_non_git_remote_and_symlink_paths_have_stable_errors(self) -> None:
        catalog = LocalRepositoryCatalog([str(self.root)])
        cases = ((self.base / "outside", "repository_path_outside_root"), (self.root / "plain", "repository_not_git"), ("https://example.invalid/repo", "repository_remote_unsupported"))
        (self.base / "outside").mkdir()
        (self.root / "plain").mkdir()
        for path, code in cases:
            with self.subTest(path=path):
                with self.assertRaises(RepositoryCatalogError) as raised:
                    catalog.resolve(str(path))
                self.assertEqual(raised.exception.code, code)
        outside_repo = self.base / "outside-repository"
        outside_repo.mkdir()
        subprocess.run(["git", "-C", str(outside_repo), "init", "-q"], check=True)
        (self.root / "escape").symlink_to(outside_repo, target_is_directory=True)
        with self.assertRaises(RepositoryCatalogError) as raised:
            catalog.resolve(str(self.root / "escape"))
        self.assertEqual(raised.exception.code, "repository_symlink_escape")
        catalog.close()

    def test_read_and_write_scopes_are_distinct_and_tenant_bound(self) -> None:
        catalog = LocalRepositoryCatalog([str(self.root)])
        record = catalog.list_repositories()[0]
        read = catalog.authorize_read("tenant-a", repository_id=record.repository_id)
        self.assertEqual(read.permission, READ_ANALYSIS)
        with self.assertRaises(RepositoryCatalogError) as raised:
            catalog.require_read("tenant-b", record.repository_id, read.scope_id)
        self.assertEqual(raised.exception.code, "scope_mismatch")
        with self.assertRaises(RepositoryCatalogError) as raised:
            catalog.require_write("tenant-a", record.repository_id, read.scope_id)
        self.assertEqual(raised.exception.code, "scope_mismatch")
        write = catalog.authorize_write("tenant-a", repository_id=record.repository_id, read_scope_id=read.scope_id)
        self.assertEqual(write.permission, WRITE_PATCH)
        self.assertNotEqual(write.scope_id, read.scope_id)
        catalog.require_write("tenant-a", record.repository_id, write.scope_id)
        self.assertEqual(catalog.authorization_state("tenant-a", record.repository_id), {READ_ANALYSIS: True, WRITE_PATCH: True})
        catalog.close()

    def test_overlapping_configured_roots_are_rejected(self) -> None:
        with self.assertRaises(RepositoryCatalogError) as raised:
            LocalRepositoryCatalog([str(self.root), str(self.repo)])
        self.assertEqual(raised.exception.code, "repository_root_ambiguous")


if __name__ == "__main__":
    unittest.main()
