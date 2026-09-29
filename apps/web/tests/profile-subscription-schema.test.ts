import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const migrationPath = resolve(__dirname, "../drizzle/0007_profile_subscription_lifecycle.sql");
const journalPath = resolve(__dirname, "../drizzle/meta/_journal.json");

describe("subscription lifecycle migration contract", () => {
  const migration = readFileSync(migrationPath, "utf8");
  const journal = JSON.parse(readFileSync(journalPath, "utf8")) as { entries: Array<{ tag: string }> };

  it("is registered and additive", () => {
    expect(journal.entries.some((entry) => entry.tag === "0007_profile_subscription_lifecycle")).toBe(true);
    expect(migration).toContain("CREATE TABLE IF NOT EXISTS \"subscription_transitions\"");
    expect(migration).toContain("CREATE TABLE IF NOT EXISTS \"token_usage_periods\"");
    expect(migration).toContain("CREATE TABLE IF NOT EXISTS \"token_usage_entries\"");
    expect(migration).not.toMatch(/DROP\s+(?:TABLE|COLUMN|INDEX)/i);
  });

  it("fails before the open-subscription uniqueness index if legacy duplicates exist", () => {
    expect(migration).toContain("RAISE EXCEPTION 'cannot enforce one open subscription per tenant/user while duplicate rows exist'");
    expect(migration).toContain("subscriptions_one_open_per_user_idx");
    expect(migration).toContain("payment_orders_toss_customer_key_idx");
  });

  it("preserves existing custom token quotas while filling missing catalog defaults", () => {
    expect(migration).toContain("COALESCE(\"quotas\"->'monthlyInputTokens'");
    expect(migration).toContain("COALESCE(\"quotas\"->'monthlyOutputTokens'");
    expect(migration).toContain("COALESCE(\"quotas\"->'monthlyTokens'");
  });
});
