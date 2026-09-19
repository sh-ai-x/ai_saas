import dotenv from "dotenv";
import { defineConfig } from "drizzle-kit";

// Keep local secrets in .env.local while allowing CI/deploy environments to
// provide process-level variables. Existing process variables always win.
dotenv.config({ path: ".env.local" });
dotenv.config({ path: ".env" });

export default defineConfig({
  schema: "./db/schema/index.ts",
  out: "./drizzle",
  dialect: "postgresql",
  dbCredentials: {
    url: process.env.DATABASE_URL ?? "postgresql://placeholder:placeholder@localhost/placeholder",
  },
  strict: true,
  verbose: true,
});
