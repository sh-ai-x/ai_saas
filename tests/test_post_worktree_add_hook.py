from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "post-worktree-add.sh"
SETTINGS = ROOT / ".claude" / "settings.json"


class PostWorktreeAddHookStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = HOOK.read_text(encoding="utf-8")
        cls.settings_text = SETTINGS.read_text(encoding="utf-8")

    def test_hook_exists_and_is_executable(self) -> None:
        self.assertTrue(HOOK.exists())
        self.assertTrue(HOOK.stat().st_mode & stat.S_IXUSR)

    def test_hook_matches_git_worktree_add(self) -> None:
        # Bash extended-regex uses `\<` and `[[:space:]]` to match word-boundary
        # whitespace. Match a representative slice.
        self.assertRegex(self.text, r"git.*worktree.*add")

    def test_hook_copies_env_local_and_env_stage(self) -> None:
        # The script must reference both files and the cp primitive.
        for needle in (".env.local", ".env.stage", "cp -p"):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.text)

    def test_hook_is_self_contained_no_devkit_source(self) -> None:
        # Must not source dev-kit's hook-preamble.sh; that file lives in
        # the plugin cache and would break if dev-kit changes its layout.
        self.assertNotIn("hook-preamble.sh", self.text)

    def test_hook_is_idempotent_skips_existing_target(self) -> None:
        self.assertIn('[[ -f "$dst" ]]', self.text)
        self.assertIn("continue", self.text)

    def test_hook_is_advisory_always_exits_zero(self) -> None:
        # No `exit 2`, no `deny`. An advisory hook must never block.
        self.assertNotIn("exit 2", self.text)
        self.assertNotIn("deny", self.text)

    def test_settings_wires_posttooluse_bash(self) -> None:
        # Parse settings.json and confirm the wiring is present.
        settings = json.loads(self.settings_text)
        post = settings.get("hooks", {}).get("PostToolUse", [])
        self.assertTrue(post, "PostToolUse hooks missing from .claude/settings.json")
        bash_matcher = next((m for m in post if m.get("matcher") == "Bash"), None)
        self.assertIsNotNone(bash_matcher, "no Bash matcher wired in PostToolUse")
        commands = [h.get("command", "") for h in bash_matcher.get("hooks", [])]
        self.assertTrue(
            any("post-worktree-add.sh" in cmd for cmd in commands),
            f"post-worktree-add.sh not wired; saw commands={commands!r}",
        )

    def test_settings_wiring_does_not_depend_on_devkit(self) -> None:
        # Self-contained: no ${CLAUDE_PLUGIN_ROOT} (dev-kit) reference.
        self.assertNotIn("CLAUDE_PLUGIN_ROOT", self.settings_text)


class PostWorktreeAddHookRuntimeTests(unittest.TestCase):
    """Drive the hook end-to-end with a real `git worktree add` invocation
    and confirm the env files land in the new worktree.
    """

    def setUp(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git not installed")
        if shutil.which("jq") is None:
            self.skipTest("jq not installed")

        self.tmp = tempfile.mkdtemp(prefix="hook-runtime-test-")
        self.repo = Path(self.tmp) / "src"
        self.repo.mkdir()
        self.target_worktree = Path(self.tmp) / "wt"

        # Build a minimal git repo with a `.env.local` and `.env.stage` at the
        # root (gitignored so the worktree won't get them automatically).
        run = subprocess.run
        for cmd in (
            ["git", "-C", str(self.repo), "init", "-q", "-b", "main"],
            ["git", "-C", str(self.repo), "config", "user.email", "test@example.com"],
            ["git", "-C", str(self.repo), "config", "user.name", "test"],
            ["git", "-C", str(self.repo), "commit", "--allow-empty", "-q", "-m", "init"],
        ):
            run(cmd, check=True, capture_output=True)

        (self.repo / ".gitignore").write_text(".env.*\n", encoding="utf-8")
        (self.repo / ".env.local").write_text("FOO=local\n", encoding="utf-8")
        (self.repo / ".env.stage").write_text("BAR=stage\n", encoding="utf-8")
        # Sanity: the env files are gitignored.
        run(["git", "-C", str(self.repo), "add", ".gitignore"], check=True, capture_output=True)
        run(["git", "-C", str(self.repo), "commit", "-q", "-m", "gitignore"], check=True, capture_output=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _feed_hook(self, command: str, cwd: str) -> subprocess.CompletedProcess:
        payload = json.dumps({"tool_input": {"command": command, "cwd": cwd}})
        return subprocess.run(
            ["bash", str(HOOK)],
            input=payload,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_env_files_copied_into_new_worktree(self) -> None:
        # Cut a real worktree.
        subprocess.run(
            ["git", "-C", str(self.repo), "worktree", "add", "-b", "feat/test", str(self.target_worktree), "main"],
            check=True,
            capture_output=True,
        )
        # Confirm the worktree does NOT have the env files yet (gitignored).
        self.assertFalse((self.target_worktree / ".env.local").exists())
        self.assertFalse((self.target_worktree / ".env.stage").exists())

        # Fire the hook with a payload that mirrors Claude Code's.
        result = self._feed_hook(
            f"git worktree add -b feat/test {self.target_worktree} main",
            cwd=str(self.repo),
        )
        self.assertEqual(
            result.returncode, 0,
            f"hook exited {result.returncode}; stderr={result.stderr}",
        )

        # The hook only does post-create bookkeeping. We pre-created the
        # worktree, so the files should land after the hook runs.
        self.assertTrue(
            (self.target_worktree / ".env.local").exists(),
            "hook did not copy .env.local into the new worktree",
        )
        self.assertTrue(
            (self.target_worktree / ".env.stage").exists(),
            "hook did not copy .env.stage into the new worktree",
        )
        # Content must match the source.
        self.assertEqual((self.target_worktree / ".env.local").read_text(), "FOO=local\n")
        self.assertEqual((self.target_worktree / ".env.stage").read_text(), "BAR=stage\n")

    def test_hook_noops_on_unrelated_bash_command(self) -> None:
        result = self._feed_hook("ls -la", cwd=str(self.repo))
        self.assertEqual(result.returncode, 0)
        # No copy happened; the target worktree (if any) is untouched.


if __name__ == "__main__":
    unittest.main()
