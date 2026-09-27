from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERIFY_SCRIPT = ROOT / "scripts" / "verify-docker-env.sh"
LOCAL_COMPOSE = ROOT / "docker" / "local" / "compose.yaml"
NEON_COMPOSE = ROOT / "docker" / "neon" / "compose.yaml"
PROD_COMPOSE = ROOT / "docker" / "prod" / "compose.yaml"


class VerifyDockerEnvStaticContractTests(unittest.TestCase):
    """Asserts the bash verifier exists, is executable, and references
    every category the user named (DB, Toss, JEV, OpenAI, Google OAuth).
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.script_text = VERIFY_SCRIPT.read_text(encoding="utf-8")

    def test_script_exists_and_is_executable(self) -> None:
        self.assertTrue(VERIFY_SCRIPT.exists(), f"missing {VERIFY_SCRIPT}")
        mode = VERIFY_SCRIPT.stat().st_mode
        self.assertTrue(mode & stat.S_IXUSR, "verify-docker-env.sh must be user-executable")

    def test_references_all_required_categories(self) -> None:
        for needle in ("DB", "TOSS", "JEV", "OPENAI", "GOOGLE_OAUTH"):
            with self.subTest(category=needle):
                self.assertIn(needle, self.script_text)

    def test_uses_docker_inspect_for_env_dump(self) -> None:
        self.assertIn("docker inspect", self.script_text)
        self.assertIn("Config.Env", self.script_text)

    def test_tolerates_empty_payment_keys_when_provider_is_mock(self) -> None:
        # `docker:local` overrides TOSS_* keys to empty with PAYMENT_PROVIDER=mock.
        # The verifier must downgrade that combination from FAIL to WARN.
        self.assertIn("PAYMENT_PROVIDER", self.script_text)
        self.assertIn("mock", self.script_text)
        self.assertIn("WARN", self.script_text)

    def test_exits_nonzero_on_fail(self) -> None:
        # Mirror the binary contract: any FAIL row forces exit 1.
        self.assertIn('exit 1', self.script_text)

    def test_local_compose_force_mocks_toss_and_openai(self) -> None:
        """If the local compose ever stops insulating TOSS_* / LEMONSQUEEZY_*
        keys, the verifier will start erroring on `docker:local`. Lock the
        override down with a regression test.
        """
        text = LOCAL_COMPOSE.read_text(encoding="utf-8")
        self.assertIn('PAYMENT_PROVIDER: mock', text)
        self.assertIn('TOSS_CLIENT_KEY: ""', text)
        self.assertIn('TOSS_SECRET_KEY: ""', text)
        self.assertIn('LEMONSQUEEZY_API_KEY: ""', text)


class _FakeDocker:
    """Stand-in for the `docker` binary. Returns canned `inspect` output
    keyed off compose project + service. Lets us drive the verifier
    end-to-end without a Docker daemon.
    """

    def __init__(self) -> None:
        self.env_per_service: dict[tuple[str, str], dict[str, str]] = {}

    def set_env(self, project: str, service: str, env: dict[str, str]) -> None:
        self.env_per_service[(project, service)] = dict(env)

    def render(self) -> str:
        # Bash shim for the `docker` binary.
        # - `docker compose …` → exec the sibling `compose` shim.
        # - `docker inspect … <container>` → look up env from JSON.
        # Anything else is a no-op so the verifier can probe service
        # membership without us mocking every docker subcommand.
        return textwrap.dedent(
            r"""
            set -eu
            if [[ "$1" == "compose" ]]; then
              shift
              exec "$(dirname "$0")/compose" "$@"
            fi
            if [[ "$1" == "inspect" ]]; then
              shift
              container=""
              for a in "$@"; do
                if [[ "$a" == *-*-1 ]]; then
                  container="$a"
                  break
                fi
              done
              service=""
              case "$container" in
                *-postgres-1)    service="postgres" ;;
                *-web-migrate-1) service="web-migrate" ;;
                *-foundation-1)  service="foundation" ;;
                *-web-1)         service="web" ;;
              esac
              project="${container%-${service}-1}"
              [[ -n "$service" ]] || exit 0
              exec python3 - "$project" "$service" <<'PY'
            import json, os, sys
            project, service = sys.argv[1], sys.argv[2]
            env_file = os.environ["FAKE_DOCKER_ENV"]
            with open(env_file, encoding="utf-8") as f:
                all_env = json.load(f)
            env_map = all_env.get(f"{project}|{service}", {})
            for k, v in env_map.items():
                print(f"{k}={v}")
            PY
            fi
            exit 0
            """
        ).strip()


class VerifyDockerEnvRuntimeTests(unittest.TestCase):
    """End-to-end: drive verify-docker-env.sh with a fake `docker` on PATH
    and confirm exit codes + table output match the expected classification.
    """

    def setUp(self) -> None:
        if not VERIFY_SCRIPT.exists():
            self.skipTest(f"{VERIFY_SCRIPT} not present (run from repo root)")
        self.tmp = tempfile.mkdtemp(prefix="verify-docker-env-test-")
        self.bin_dir = Path(self.tmp) / "bin"
        self.bin_dir.mkdir()
        self.env_file = Path(self.tmp) / "canned-env.json"
        self.compose_project = "ai-saas-test"
        self.fake = _FakeDocker()

        docker_shim = self.bin_dir / "docker"
        docker_shim.write_text(self.fake.render(), encoding="utf-8")
        docker_shim.chmod(0o755)
        # `docker compose --project-name X ps --services` — return foundation+web
        compose_shim = self.bin_dir / "compose"
        compose_shim.write_text(
            "#!/usr/bin/env bash\necho foundation\necho web\n", encoding="utf-8"
        )
        compose_shim.chmod(0o755)
        # Re-exec `docker compose …` via the compose shim itself.
        compose_shim.write_text(
            textwrap.dedent(
                r"""
                #!/usr/bin/env bash
                if [[ "$1" == "compose" ]]; then
                  shift
                fi
                if [[ "$1" == "--project-name" ]]; then
                  shift 2
                fi
                if [[ "$1" == "ps" && "$2" == "--services" ]]; then
                  echo foundation
                  echo web
                  exit 0
                fi
                if [[ "$1" == "ps" ]]; then
                  echo "Name   State   Ports"
                  echo "${FAKE_PROJECT}-foundation-1 running"
                  echo "${FAKE_PROJECT}-web-1 running"
                  exit 0
                fi
                exit 0
                """
            ).strip(),
            encoding="utf-8",
        )
        compose_shim.chmod(0o755)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_verifier(self, project: str, service_envs: dict[str, dict[str, str]]) -> subprocess.CompletedProcess:
        # Convert service envs into the JSON file the fake docker reads.
        import json
        payload = {f"{project}|{svc}": env for svc, env in service_envs.items()}
        self.env_file.write_text(json.dumps(payload), encoding="utf-8")

        env = os.environ.copy()
        env["PATH"] = f"{self.bin_dir}:{env['PATH']}"
        env["FAKE_DOCKER_ENV"] = str(self.env_file)
        env["FAKE_PROJECT"] = project
        return subprocess.run(
            ["bash", str(VERIFY_SCRIPT), project, str(self.env_file)],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    def test_neon_profile_with_toss_provider_passes(self) -> None:
        result = self._run_verifier(
            self.compose_project,
            {
                "foundation": {
                    "DATABASE_URL": "postgresql://x@y/z",
                    "TOSS_CLIENT_KEY": "test_ck_abc",
                    "TOSS_SECRET_KEY": "test_sk_abc",
                    "TOSS_WEBHOOK_SECRET": "whsec_abc",
                    "OPENAI_API_KEY": "sk-openai",
                },
                "web": {
                    "DATABASE_URL": "postgresql://x@y/z",
                    "TOSS_CLIENT_KEY": "test_ck_abc",
                    "TOSS_SECRET_KEY": "test_sk_abc",
                    "TOSS_WEBHOOK_SECRET": "whsec_abc",
                    "OPENAI_API_KEY": "sk-openai",
                    "JEV_API_KEY": "apikey_jev",
                    "GOOGLE_CLIENT_ID": "id.apps.googleusercontent.com",
                    "GOOGLE_CLIENT_SECRET": "GOCSPX-abc",
                    "NEXT_PUBLIC_GOOGLE_AUTH_ENABLED": "true",
                    "BETTER_AUTH_SECRET": "secret123",
                },
            },
        )
        self.assertEqual(
            result.returncode,
            0,
            f"expected pass (rc=0); stderr=\n{result.stderr}\nstdout=\n{result.stdout}",
        )
        # Spot-check that the categories appeared with PASS rows.
        for needle in ("DB", "TOSS", "JEV", "OPENAI", "GOOGLE_OAUTH"):
            with self.subTest(category=needle):
                self.assertIn(needle, result.stdout)

    def test_local_profile_with_mock_provider_warns_on_empty_toss(self) -> None:
        # docker/local/compose.yaml hardcodes `PAYMENT_PROVIDER: mock` and
        # empty TOSS_* keys. The verifier must downgrade those TOSS_*
        # empties to WARN.
        result = self._run_verifier(
            self.compose_project,
            {
                "foundation": {
                    "PAYMENT_PROVIDER": "mock",
                    "DATABASE_URL": "postgresql://x@y/z",
                    "TOSS_CLIENT_KEY": "",
                    "TOSS_SECRET_KEY": "",
                    "TOSS_WEBHOOK_SECRET": "",
                    "OPENAI_API_KEY": "sk-openai",
                    "MOCK_PAYMENTS_ENABLED": "true",
                },
                "web": {
                    "PAYMENT_PROVIDER": "mock",
                    "DATABASE_URL": "postgresql://x@y/z",
                    "TOSS_CLIENT_KEY": "",
                    "TOSS_SECRET_KEY": "",
                    "TOSS_WEBHOOK_SECRET": "",
                    "NEXT_PUBLIC_GOOGLE_AUTH_ENABLED": "true",
                },
            },
        )
        # Empty TOSS_* under mock provider must downgrade to WARN, not FAIL.
        self.assertIn("WARN", result.stdout, f"stdout=\n{result.stdout}")
        self.assertIn("TOSS", result.stdout)
        # And those WARN rows must reference TOSS_CLIENT_KEY / TOSS_SECRET_KEY /
        # TOSS_WEBHOOK_SECRET (at least one — sample).
        self.assertRegex(result.stdout, r"TOSS_(CLIENT|SECRET|WEBHOOK)_KEY\s+WARN")


if __name__ == "__main__":
    unittest.main()
