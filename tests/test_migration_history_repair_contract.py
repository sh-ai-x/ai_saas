from pathlib import Path
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts" / "migration-history-repair.mjs"


class MigrationHistoryRepairContractTests(unittest.TestCase):
    def test_repair_is_staging_only_and_requires_explicit_confirmation(self):
        source = SCRIPT.read_text()
        self.assertIn('args.target !== "staging"', source)
        self.assertIn('CONFIRM_STAGING_DB !== "staging"', source)
        self.assertIn('CONFIRM_HISTORY_REPAIR !== "stage2"', source)

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
