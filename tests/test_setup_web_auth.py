from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "setup-web-auth.py"


class SetupWebAuthTests(unittest.TestCase):
    def run_setup(self, root: Path, *arguments: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        command = [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(root),
            "--env-file",
            "apps/web/.env.local",
            "--neon-env-file",
            ".env.local",
            *arguments,
        ]
        return subprocess.run(command, text=True, capture_output=True, env=env)

    def test_imports_neon_values_reuses_secret_and_preserves_google_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "apps/web/.env.local"
            target.parent.mkdir(parents=True)
            target.write_text(
                "# Google values\nGOOGLE_CLIENT_ID=client.apps.googleusercontent.com\n"
                "GOOGLE_CLIENT_SECRET=google-secret\nBETTER_AUTH_SECRET=stable-secret\n"
                "UNRELATED=value\n",
                encoding="utf-8",
            )
            (root / ".env.local").write_text(
                "DATABASE_URL=postgresql://user:password@ep.example.neon.tech/db?sslmode=require\n"
                "DATABASE_URL_UNPOOLED=postgresql://user:password@ep.example.neon.tech/db\n",
                encoding="utf-8",
            )

            result = self.run_setup(root)

            self.assertEqual(result.returncode, 0, result.stderr)
            content = target.read_text(encoding="utf-8")
            self.assertIn("DATABASE_URL=postgresql://user:password@ep.example.neon.tech/db?sslmode=require", content)
            self.assertIn("BETTER_AUTH_SECRET=stable-secret", content)
            self.assertIn("GOOGLE_CLIENT_SECRET=google-secret", content)
            self.assertIn("UNRELATED=value", content)
            self.assertIn("APP_ENV=staging", content)
            self.assertIn("NEXT_PUBLIC_GOOGLE_AUTH_ENABLED=true", content)
            self.assertNotIn("google-secret", result.stdout)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)

    def test_generates_secret_and_runs_neon_link_and_drizzle_migration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "apps/web/.env.local"
            target.parent.mkdir(parents=True)
            target.write_text(
                "GOOGLE_CLIENT_ID=client.apps.googleusercontent.com\nGOOGLE_CLIENT_SECRET=google-secret\n",
                encoding="utf-8",
            )
            fake_bin = root / "bin"
            fake_bin.mkdir()
            log = root / "commands.log"
            fake_neon = fake_bin / "neon"
            fake_neon.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' \"$*\" >> '{log}'\n"
                "printf '%s\\n' 'DATABASE_URL=postgresql://linked:secret@ep.example.neon.tech/db?sslmode=require' > .env.local\n"
                "exit 0\n",
                encoding="utf-8",
            )
            fake_pnpm = fake_bin / "pnpm"
            fake_pnpm.write_text(
                "#!/bin/sh\n"
                f"printf 'pnpm %s\\n' \"$*\" >> '{log}'\n"
                "exit 0\n",
                encoding="utf-8",
            )
            fake_neon.chmod(0o755)
            fake_pnpm.chmod(0o755)
            test_env = os.environ.copy()
            test_env["PATH"] = f"{fake_bin}{os.pathsep}{test_env['PATH']}"

            result = self.run_setup(
                root,
                "--link-neon",
                "--neon-project-id",
                "test-project",
                "--migrate",
                env=test_env,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            content = target.read_text(encoding="utf-8")
            self.assertIn("DATABASE_URL=postgresql://linked:secret@ep.example.neon.tech/db?sslmode=require", content)
            self.assertRegex(content, r"BETTER_AUTH_SECRET=.+")
            self.assertNotIn("DATABASE_URL=", result.stdout)
            command_log = log.read_text(encoding="utf-8")
            self.assertIn("link --project-id test-project --branch production -y", command_log)
            self.assertIn("pnpm --filter ai-saas-foundation-web db:migrate", command_log)

    def test_fails_before_writing_when_database_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "apps/web/.env.local"
            target.parent.mkdir(parents=True)
            original = "GOOGLE_CLIENT_ID=client\nGOOGLE_CLIENT_SECRET=secret\n"
            target.write_text(original, encoding="utf-8")

            result = self.run_setup(root)

            self.assertEqual(result.returncode, 2)
            self.assertIn("DATABASE_URL", result.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
