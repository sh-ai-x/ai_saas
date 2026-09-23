from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = ROOT / "scripts/migration-preflight.mjs"
RELEASE = ROOT / "scripts/migration-release.mjs"


def cloud_env() -> dict[str, str]:
    values = os.environ.copy()
    values.update(
        {
            "APP_ENV": "staging",
            "NEON_BRANCH": "stage2",
            "DATABASE_URL": "postgresql://runtime:secret@ep-stage-pooler.aws.neon.tech/neondb?sslmode=require",
            "DATABASE_URL_UNPOOLED": "postgresql://migrator:secret@ep-stage.aws.neon.tech/neondb?sslmode=require",
        }
    )
    for key in ("ALLOW_NON_NEON_DATABASE", "CONFIRM_PRODUCTION_PREFLIGHT", "CONFIRM_PRODUCTION_DB"):
        values.pop(key, None)
    return values


def run_node(script: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", str(script), *args],
        cwd=ROOT,
        env=env or cloud_env(),
        text=True,
        capture_output=True,
        timeout=30,
    )


class MigrationVerificationContractTests(unittest.TestCase):
    def test_static_preflight_accepts_named_staging_branch_without_printing_credentials(self):
        result = run_node(PREFLIGHT, "--target", "staging", "--static-only", "--json")
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        document = json.loads(result.stdout)
        self.assertTrue(document["ok"])
        self.assertEqual(document["branch"], "stage2")
        self.assertNotIn("postgresql://", result.stdout)
        self.assertNotIn("secret", result.stdout)

    def test_preflight_rejects_local_database_for_cloud_target(self):
        env = cloud_env()
        env["DATABASE_URL"] = "postgresql://runtime:secret@localhost/neondb?sslmode=require"
        env["DATABASE_URL_UNPOOLED"] = "postgresql://migrator:secret@localhost/neondb?sslmode=require"
        result = run_node(PREFLIGHT, "--target", "staging", "--static-only", "--json", env=env)
        self.assertNotEqual(result.returncode, 0)
        document = json.loads(result.stdout)
        self.assertFalse(document["ok"])

    def test_production_apply_requires_confirmation_and_ci(self):
        env = cloud_env()
        env.update({"APP_ENV": "production", "NEON_BRANCH": "production"})
        result = run_node(RELEASE, "--target", "production", "--apply", "--static-only", env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CONFIRM_PRODUCTION_DB=production", result.stderr)
        self.assertNotIn("drizzle-kit", result.stderr)

    def test_release_loads_an_explicit_env_file_for_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env.stage"
            env_file.write_text(
                "\n".join(
                    [
                        "APP_ENV=staging",
                        "NEON_BRANCH=stage2",
                        "DATABASE_URL=postgresql://runtime:file-secret@ep-stage-pooler.aws.neon.tech/neondb?sslmode=require",
                        "DATABASE_URL_UNPOOLED=postgresql://migrator:file-secret@ep-stage.aws.neon.tech/neondb?sslmode=require",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            env = os.environ.copy()
            for key in ("APP_ENV", "NEON_BRANCH", "DATABASE_URL", "DATABASE_URL_UNPOOLED"):
                env.pop(key, None)
            result = run_node(RELEASE, "--target", "staging", "--plan", "--static-only", "--from-file", str(env_file), env=env)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertIn("PLAN PASS", result.stdout)
        self.assertNotIn("file-secret", result.stdout)

    def test_destructive_migration_is_blocked_before_database_access(self):
        with tempfile.TemporaryDirectory() as directory:
            migration_dir = Path(directory)
            (migration_dir / "meta").mkdir()
            (migration_dir / "meta" / "_journal.json").write_text(
                json.dumps({"version": "7", "dialect": "postgresql", "entries": [{"idx": 0, "when": 1, "tag": "0000_drop"}]}),
                encoding="utf-8",
            )
            (migration_dir / "0000_drop.sql").write_text("DROP TABLE users;\n", encoding="utf-8")
            result = run_node(PREFLIGHT, "--target", "staging", "--static-only", "--migration-dir", str(migration_dir), "--json")
        self.assertNotEqual(result.returncode, 0)
        document = json.loads(result.stdout)
        self.assertTrue(any(check["name"] == "destructive-migrations" and not check["ok"] for check in document["checks"]))


if __name__ == "__main__":
    unittest.main()
