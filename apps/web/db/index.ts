import postgres from "postgres";
import { drizzle } from "drizzle-orm/postgres-js";

import * as schema from "./schema";

type AppDb = ReturnType<typeof drizzle<typeof schema>>;

let cachedClient: ReturnType<typeof postgres> | undefined;
let cachedDb: AppDb | null | undefined;

/**
 * Neon is optional for the local profile. Production intentionally fails when
 * the URL is absent instead of silently using the in-memory repository.
 */
export function getDb(): AppDb | null {
  if (cachedDb !== undefined) return cachedDb;
  const url = process.env.DATABASE_URL;
  if (!url) {
    if (process.env.APP_ENV === "production") {
      throw new Error("DATABASE_URL is required in production");
    }
    cachedDb = null;
    return cachedDb;
  }
  cachedClient = postgres(url, { prepare: false, max: 3 });
  cachedDb = drizzle(cachedClient, { schema });
  return cachedDb;
}

export { schema };
