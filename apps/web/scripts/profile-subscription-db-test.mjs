import { spawnSync } from "node:child_process";

import dotenv from "dotenv";

// Keep the command short while allowing the URL to live in an ignored file.
// A shell-provided value always wins because dotenv does not override existing
// environment variables by default.
dotenv.config({ path: ".env.test.local" });
dotenv.config({ path: ".env.local" });

const databaseUrl = process.env.PROFILE_SUBSCRIPTION_DATABASE_URL?.trim();
if (!databaseUrl) {
  console.error("PROFILE_SUBSCRIPTION_DATABASE_URL is required for db:test.");
  console.error("Add it to apps/web/.env.test.local or export it for a dedicated Neon test database.");
  process.exit(1);
}

const result = spawnSync(
  "pnpm",
  ["exec", "jest", "--config", "jest.config.mjs", "--runInBand", "tests/profile-subscription.database.test.ts"],
  {
    cwd: process.cwd(),
    env: { ...process.env, APP_ENV: "test" },
    stdio: "inherit",
  },
);

if (result.error) {
  console.error(result.error.message);
  process.exit(1);
}

process.exit(result.status ?? 1);
