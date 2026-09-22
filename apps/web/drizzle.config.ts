import dotenv from "dotenv";
import { defineConfig } from "drizzle-kit";

// Keep local secrets in .env.local while allowing CI/deploy environments to
// provide process-level variables. Existing process variables always win.
dotenv.config({ path: ".env.local" });
dotenv.config({ path: ".env" });

// Neon recommends a direct connection for schema migrations. Runtime traffic
// may use the pooled DATABASE_URL, while CI and the Compose migrator provide
// DATABASE_URL_UNPOOLED for Drizzle.
const migrationDatabaseUrl =
  process.env.DATABASE_URL_UNPOOLED?.trim() ||
  process.env.DATABASE_URL?.trim() ||
  "postgresql://placeholder:placeholder@localhost/placeholder";

export default defineConfig({
  schema: "./db/schema/index.ts",
  out: "./drizzle",
  dialect: "postgresql",
  dbCredentials: {
    url: migrationDatabaseUrl,
  },
  strict: true,
  verbose: true,
});
