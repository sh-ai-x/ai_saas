from __future__ import annotations

import stat
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PORTS_LIB = ROOT / "scripts" / "lib" / "ports.sh"
LOCAL_SCRIPT = ROOT / "scripts" / "docker-local.sh"
NEON_SCRIPT = ROOT / "scripts" / "docker-neon.sh"


class PortsLibStaticContractTests(unittest.TestCase):
    """`scripts/lib/ports.sh` is the single source of truth for every
    host + container port used by `pnpm docker:local` and `pnpm docker:neon`.
    Lock the registry values down so future drift in scripts/composes
    fails the test instead of silently shipping.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.lib_text = PORTS_LIB.read_text(encoding="utf-8")

    def test_lib_exists_and_is_readable(self) -> None:
        self.assertTrue(PORTS_LIB.exists(), f"missing {PORTS_LIB}")

    def test_container_ports_are_stable_per_adr_0002(self) -> None:
        # Container ports stay stable across every worktree + profile
        # (ADR-0002 "Decision": "Compose service ports remain stable").
        self.assertRegex(self.lib_text, r"(?m)^readonly DOCKER_WEB_CONTAINER_PORT=3000$")
        self.assertRegex(self.lib_text, r"(?m)^readonly DOCKER_FOUNDATION_CONTAINER_PORT=8080$")
        self.assertRegex(self.lib_text, r"(?m)^readonly DOCKER_POSTGRES_CONTAINER_PORT=5432$")

    def test_local_web_host_port_is_pinned_to_3100(self) -> None:
        self.assertRegex(self.lib_text, r"(?m)^readonly DOCKER_LOCAL_WEB_HOST_PORT=3100$")

    def test_stage_web_host_port_is_pinned_to_3200(self) -> None:
        self.assertRegex(self.lib_text, r"(?m)^readonly DOCKER_STAGE_WEB_HOST_PORT=3200$")

    def test_foundation_slot_base_matches_adr_0002(self) -> None:
        # The original ADR-0002 table documents 8180 (local) + 8280 (stage).
        self.assertRegex(self.lib_text, r"(?m)^readonly DOCKER_LOCAL_FOUNDATION_PORT_BASE=8180$")
        self.assertRegex(self.lib_text, r"(?m)^readonly DOCKER_STAGE_FOUNDATION_PORT_BASE=8280$")
        self.assertRegex(self.lib_text, r"(?m)^readonly DOCKER_LOCAL_POSTGRES_PORT_BASE=55433$")

    def test_lib_references_adr_0002(self) -> None:
        # Documentation reference; the next person editing ports should
        # read the ADR first.
        self.assertIn("0002-worktree-port-and-database-isolation", self.lib_text)


class DockerLocalPinnedWebPortTests(unittest.TestCase):
    """`pnpm docker:local` must source the port registry and pin WEB to
    the local host port from the lib.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.script = LOCAL_SCRIPT.read_text(encoding="utf-8")

    def test_script_is_executable(self) -> None:
        self.assertTrue(LOCAL_SCRIPT.exists())
        self.assertTrue(LOCAL_SCRIPT.stat().st_mode & stat.S_IXUSR)

    def test_sources_port_registry_lib(self) -> None:
        self.assertRegex(
            self.script,
            r"source\s+\"?\$repo_root/scripts/lib/ports\.sh\"?",
        )

    def test_web_port_uses_lib_constant(self) -> None:
        self.assertRegex(
            self.script,
            r'(?m)^\s*selected_web_port="\$DOCKER_LOCAL_WEB_HOST_PORT"\s*$',
        )

    def test_no_literal_slot_arithmetic_for_web_port(self) -> None:
        self.assertNotRegex(self.script, r"3100\s*\+\s*candidate_slot\s*\*\s*10")

    def test_better_auth_url_uses_pinned_web_port(self) -> None:
        self.assertRegex(
            self.script,
            r'BETTER_AUTH_URL="\$\{BETTER_AUTH_URL:-http://localhost:\$\{WEB_PORT\}\}"',
        )

    def test_container_port_lookup_uses_lib(self) -> None:
        self.assertIn("$DOCKER_FOUNDATION_CONTAINER_PORT", self.script)
        self.assertIn("$DOCKER_POSTGRES_CONTAINER_PORT", self.script)

    def test_verifier_invoked_after_up(self) -> None:
        self.assertIn("verify-docker-env.sh", self.script)


class DockerNeonPinnedWebPortTests(unittest.TestCase):
    """`pnpm docker:neon` mirrors the local profile: WEB pinned via the
    lib, foundation + slot derived from the lib, container ports sourced
    from the lib.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.script = NEON_SCRIPT.read_text(encoding="utf-8")

    def test_script_is_executable(self) -> None:
        self.assertTrue(NEON_SCRIPT.exists())
        self.assertTrue(NEON_SCRIPT.stat().st_mode & stat.S_IXUSR)

    def test_sources_port_registry_lib(self) -> None:
        self.assertRegex(
            self.script,
            r"source\s+\"?\$repo_root/scripts/lib/ports\.sh\"?",
        )

    def test_web_port_uses_lib_constant(self) -> None:
        self.assertRegex(
            self.script,
            r'(?m)^\s*selected_web_port="\$DOCKER_STAGE_WEB_HOST_PORT"\s*$',
        )

    def test_no_literal_slot_arithmetic_for_web_port(self) -> None:
        self.assertNotRegex(self.script, r"3200\s*\+\s*candidate_slot\s*\*\s*10")

    def test_foundation_slot_still_dynamic_via_lib(self) -> None:
        # Foundation stays on slot allocation so concurrent worktrees don't collide.
        self.assertIn("DOCKER_STAGE_FOUNDATION_PORT_BASE", self.script)

    def test_better_auth_url_uses_pinned_web_port(self) -> None:
        self.assertRegex(
            self.script,
            r'BETTER_AUTH_URL="\$\{BETTER_AUTH_URL:-http://localhost:\$\{WEB_PORT\}\}"',
        )

    def test_container_port_lookup_uses_lib(self) -> None:
        self.assertIn("$DOCKER_FOUNDATION_CONTAINER_PORT", self.script)

    def test_verifier_invoked_after_up(self) -> None:
        self.assertIn("verify-docker-env.sh", self.script)


if __name__ == "__main__":
    unittest.main()
