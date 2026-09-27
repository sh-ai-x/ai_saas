from __future__ import annotations

import re
import stat
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCAL_SCRIPT = ROOT / "scripts" / "docker-local.sh"
NEON_SCRIPT = ROOT / "scripts" / "docker-neon.sh"


class DockerLocalPinnedWebPortTests(unittest.TestCase):
    """`pnpm docker:local` must pin WEB_PORT=3100 across every worktree.

    The slot-allocation block in the old script (`3100 + slot*10`) leaks
    stale ports into env-file URLs (BETTER_AUTH_URL, TOSS_SUCCESS_URL,
    WEB_PUBLIC_URL) that all default to localhost:3100. Pinning forces
    the canonical port.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.script = LOCAL_SCRIPT.read_text(encoding="utf-8")

    def test_script_is_executable(self) -> None:
        self.assertTrue(LOCAL_SCRIPT.exists())
        self.assertTrue(LOCAL_SCRIPT.stat().st_mode & stat.S_IXUSR)

    def test_web_port_is_pinned_to_3100(self) -> None:
        # Look for any assignment of the form `selected_web_port=3100`
        # (no arithmetic, no slot-derived value).
        self.assertRegex(self.script, r"(?m)^\s*selected_web_port\s*=\s*3100\s*$")

    def test_no_slot_arithmetic_for_web_port(self) -> None:
        # The old loop produced lines like `candidate_web_port=$((3100 + candidate_slot * 10))`.
        self.assertNotRegex(
            self.script,
            r"3100\s*\+\s*candidate_slot\s*\*\s*10",
        )

    def test_better_auth_url_uses_pinned_web_port(self) -> None:
        # The BETTER_AUTH_URL default still expands to localhost:${WEB_PORT}.
        self.assertRegex(self.script, r'BETTER_AUTH_URL="\$\{BETTER_AUTH_URL:-http://localhost:\$\{WEB_PORT\}\}"')

    def test_verifier_invoked_after_up(self) -> None:
        # The post-up verifier call must be wired at the bottom.
        self.assertIn('verify-docker-env.sh', self.script)


class DockerNeonPinnedWebPortTests(unittest.TestCase):
    """`pnpm docker:neon` must pin WEB_PORT=3200 across every worktree."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.script = NEON_SCRIPT.read_text(encoding="utf-8")

    def test_script_is_executable(self) -> None:
        self.assertTrue(NEON_SCRIPT.exists())
        self.assertTrue(NEON_SCRIPT.stat().st_mode & stat.S_IXUSR)

    def test_web_port_is_pinned_to_3200(self) -> None:
        self.assertRegex(self.script, r"(?m)^\s*selected_web_port\s*=\s*3200\s*$")

    def test_no_slot_arithmetic_for_web_port(self) -> None:
        self.assertNotRegex(
            self.script,
            r"3200\s*\+\s*candidate_slot\s*\*\s*10",
        )

    def test_better_auth_url_uses_pinned_web_port(self) -> None:
        self.assertRegex(self.script, r'BETTER_AUTH_URL="\$\{BETTER_AUTH_URL:-http://localhost:\$\{WEB_PORT\}\}"')

    def test_verifier_invoked_after_up(self) -> None:
        self.assertIn('verify-docker-env.sh', self.script)

    def test_foundation_port_still_dynamic(self) -> None:
        # Foundation stays on slot allocation so concurrent worktrees don't collide.
        self.assertRegex(self.script, r"8280\s*\+\s*candidate_slot\s*\*\s*10")


if __name__ == "__main__":
    unittest.main()
