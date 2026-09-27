from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS_SCRIPT = ROOT / "scripts" / "drizzle-status.mjs"
DOCTOR_SCRIPT = ROOT / "scripts" / "drizzle-doctor.mjs"
PACKAGE = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))


def run(cmd: list[str], cwd: Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, check=False)


class DrizzleStatusContractTests(unittest.TestCase):
    """`pnpm db:status` wraps `node scripts/drizzle-status.mjs`. The
    script is file-only: it reads the journal + SQL files and reports
    manifest consistency, recent migrations, and any orphan files.
    """

    def test_script_exists_and_is_runnable(self) -> None:
        result = run(["node", str(STATUS_SCRIPT)])
        self.assertEqual(result.returncode, 0, f"stdout={result.stdout}\nstderr={result.stderr}")
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertGreaterEqual(payload["totalMigrations"], 1)
        self.assertEqual(payload["firstMigration"], "0000_loud_salo")

    def test_pnpm_db_status_wires_to_the_script(self) -> None:
        scripts = PACKAGE.get("scripts", {})
        self.assertEqual(scripts.get("db:status"), f"node {STATUS_SCRIPT.relative_to(ROOT)}")

    def test_detects_orphan_sql_file(self) -> None:
        # Write an orphan file in a tempdir scratch and re-run from a
        # sandbox copy of the migration directory. Cheaper than mutating
        # the real one.
        import shutil
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            scratch = Path(tmp) / "drizzle"
            shutil.copytree(ROOT / "apps" / "web" / "drizzle", scratch)
            (scratch / "9999_orphan.sql").write_text("select 1;\n", encoding="utf-8")
            result = run(["node", str(STATUS_SCRIPT), "--migration-dir", str(scratch)])
            self.assertNotEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertIn("9999_orphan", payload["orphanSqlFiles"])

    def test_recent_migrations_are_present(self) -> None:
        result = run(["node", str(STATUS_SCRIPT)])
        payload = json.loads(result.stdout)
        tags = [m["tag"] for m in payload["recentMigrations"]]
        self.assertEqual(tags[0], payload["lastMigration"])


class DrizzleDoctorContractTests(unittest.TestCase):
    """`pnpm db:doctor[:stage|:prod]` wraps `node scripts/drizzle-doctor.mjs`.
    The doctor combines the status check + destructive-statement scan +
    pooler-host check + (best-effort) preflight.
    """

    def test_bare_invocation_runs_in_offline_mode(self) -> None:
        # `pnpm db:doctor` runs without a target; the script does file
        # checks only and skips env/preflight. JSON target field is "".
        result = run(
            [
                "node", str(DOCTOR_SCRIPT),
                "--migration-dir", str(ROOT / "apps" / "web" / "drizzle"),
            ],
        )
        self.assertEqual(result.returncode, 0, f"stdout={result.stdout}\nstderr={result.stderr}")
        payload = json.loads(result.stdout)
        self.assertEqual(payload["target"], "")
        self.assertTrue(payload["ok"])
        # Summary line still prints on stderr for terminal UX.
        self.assertRegex(result.stderr, r"drizzle-doctor: PASS")

    def test_rejects_unknown_target(self) -> None:
        result = run(["node", str(DOCTOR_SCRIPT), "bogus"])
        self.assertEqual(result.returncode, 2)
        self.assertIn("staging or production", result.stderr)

    def test_pnpm_db_doctor_wires(self) -> None:
        scripts = PACKAGE.get("scripts", {})
        self.assertEqual(scripts.get("db:doctor"), f"node {DOCTOR_SCRIPT.relative_to(ROOT)}")
        self.assertEqual(scripts.get("db:doctor:stage"), f"node {DOCTOR_SCRIPT.relative_to(ROOT)} staging")
        self.assertEqual(scripts.get("db:doctor:prod"), f"node {DOCTOR_SCRIPT.relative_to(ROOT)} production")

    def test_doctor_runs_offline_with_minimal_env(self) -> None:
        # Pass the real migration dir via --migration-dir so the script
        # does not depend on cwd. No env-file means WARN for connectivity
        # checks; the script itself must still complete with PASS/FAIL.
        result = subprocess.run(
            [
                "node", str(DOCTOR_SCRIPT), "staging",
                "--migration-dir", str(ROOT / "apps" / "web" / "drizzle"),
                "--from-file", "/nonexistent/.env.staging",
            ],
            capture_output=True, text=True, cwd=ROOT, check=False,
        )
        # Doctor exits 0 (with warnings) or 1 (real failure). Both acceptable.
        self.assertIn(result.returncode, (0, 1))
        # stdout is the canonical JSON contract.
        payload = json.loads(result.stdout)
        self.assertEqual(payload["target"], "staging")
        # Summary line goes to stderr for terminal convenience.
        self.assertRegex(result.stderr, r"drizzle-doctor: (PASS|FAIL)")

    def test_detects_pooler_in_direct_url(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env.staging"
            env_file.write_text(
                'DATABASE_URL="postgresql://x@y/db"\n'
                'DATABASE_URL_UNPOOLED="postgresql://x@-pooler.region.aws.neon.tech/db"\n',
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    "node", str(DOCTOR_SCRIPT), "staging",
                    "--migration-dir", str(ROOT / "apps" / "web" / "drizzle"),
                    "--from-file", str(env_file),
                ],
                capture_output=True, text=True, cwd=ROOT, check=False,
            )
            payload = json.loads(result.stdout)
            direct_check = next((f for f in payload["findings"] if f["check"] == "direct-url"), None)
            self.assertIsNotNone(direct_check)
            self.assertEqual(direct_check["status"], "FAIL")


class DrizzleCommandSurfaceTests(unittest.TestCase):
    """Lock down the pnpm command surface so future drift in
    package.json fails the test instead of silently dropping a workflow.
    """

    SCRIPTS = (
        "db:generate",
        "db:migrate",
        "db:status",
        "db:doctor",
        "db:doctor:stage",
        "db:doctor:prod",
        "db:verify:stage",
        "db:verify:prod",
        "db:plan:stage",
        "db:plan:prod",
        "db:migrate:stage",
        "db:migrate:prod",
        "db:repair-history:stage",
        "db:cleanup:legacy:stage",
    )

    def test_every_drizzle_command_is_wired(self) -> None:
        scripts = PACKAGE.get("scripts", {})
        missing = [cmd for cmd in self.SCRIPTS if cmd not in scripts]
        self.assertEqual(missing, [], f"missing pnpm commands: {missing}")

    def test_stage_and_prod_commands_are_separate(self) -> None:
        # Stage and prod release wrappers must NOT share a single
        # pnpm target — the user-confirmed separation between the two
        # environments is part of the contract.
        scripts = PACKAGE.get("scripts", {})
        for prefix in ("db:verify", "db:plan", "db:migrate", "db:doctor"):
            stage = scripts.get(f"{prefix}:stage")
            prod = scripts.get(f"{prefix}:prod")
            self.assertTrue(stage, f"missing {prefix}:stage")
            self.assertTrue(prod, f"missing {prefix}:prod")
            self.assertNotEqual(stage, prod)

    def test_no_legacy_web_db_prefix_remains(self) -> None:
        # After the cleanup, `web:db:*` is gone.
        scripts = PACKAGE.get("scripts", {})
        for key in scripts:
            self.assertFalse(
                key.startswith("web:db:"),
                f"legacy pnpm command still wired: {key}",
            )

    def test_destructive_migration_pattern_is_sane(self) -> None:
        # The doctor flags DROP TABLE / DROP COLUMN / TRUNCATE — verify
        # the regex isn't trivially broken (no `.+` would do).
        text = DOCTOR_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("drop\\s+table", text)
        self.assertIn("drop\\s+column", text)
        self.assertIn("truncate", text)


if __name__ == "__main__":
    unittest.main()
