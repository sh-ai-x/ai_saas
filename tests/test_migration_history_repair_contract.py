from pathlib import Path
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts" / "migration-history-repair.mjs"


class MigrationHistoryRepairContractTests(unittest.TestCase):
    def test_repair_accepts_only_staging_or_production_targets(self):
        source = SCRIPT.read_text()
        # Both targets must be accepted; anything else is rejected.
        self.assertIn('["staging", "production"]', source)
        self.assertIn("--target staging or --target production", source)

    def test_staging_repair_requires_staging_environment_and_confirmations(self):
        source = SCRIPT.read_text()
        self.assertIn("APP_ENV must be staging", source)
        self.assertIn("NEON_BRANCH must be a non-production branch", source)
        self.assertIn('CONFIRM_STAGING_DB !== "staging"', source)
        self.assertIn('CONFIRM_HISTORY_REPAIR !== "stage2"', source)

    def test_production_repair_requires_production_environment_and_extra_gates(self):
        source = SCRIPT.read_text()
        self.assertIn("APP_ENV must be production", source)
        self.assertIn("NEON_BRANCH must be production", source)
        self.assertIn('CONFIRM_PRODUCTION_DB !== "production"', source)
        self.assertIn('CONFIRM_HISTORY_REPAIR !== "production"', source)
        # Production apply is gated to GitHub Actions — no local apply.
        self.assertIn("production apply is allowed only from GitHub Actions", source)

    def test_cleanup_legacy_is_staging_only(self):
        source = SCRIPT.read_text()
        self.assertIn("--cleanup-legacy is limited to --target staging", source)
        self.assertIn('CONFIRM_LEGACY_CLEANUP !== "stage2"', source)

    def test_repair_archives_history_before_normalizing_it(self):
        source = SCRIPT.read_text()
        self.assertIn("__drizzle_migrations_repair_backup", source)
        self.assertIn("original_rows", source)
        self.assertIn("original_faq_rows", source)
        self.assertIn("tx.json(state.history)", source)
        self.assertIn("lock table drizzle.__drizzle_migrations", source)

    def test_repair_preserves_legacy_faq_rows_before_canonical_english_updates(self):
        source = SCRIPT.read_text()
        self.assertIn("legacy-${row.id}", source)
        self.assertIn("faqConflicts", source)

    def test_repair_is_idempotent_after_canonical_history_is_restored(self):
        source = SCRIPT.read_text()
        self.assertIn("already current; no repair needed", source)

    def test_legacy_cleanup_is_explicitly_scoped_and_confirmed(self):
        source = SCRIPT.read_text()
        self.assertIn("--cleanup-legacy", source)
        self.assertIn('CONFIRM_LEGACY_CLEANUP !== "stage2"', source)
        self.assertIn('const LEGACY_FAQ_IDS = ["guides", "workspace", "support"]', source)
        self.assertIn("legacy_faq_rows", source)

    def test_repair_keeps_the_known_vector_lineage_out_of_canonical_history(self):
        source = SCRIPT.read_text()
        self.assertIn('"ca15976228b72e97c66f7e326b076479605e079e46f056cf099f6c30eabdb27f"', source)
        self.assertIn("delete from drizzle.__drizzle_migrations where id >", source)


if __name__ == "__main__":
    unittest.main()
