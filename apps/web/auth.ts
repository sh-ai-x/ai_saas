import { betterAuth, type BetterAuthOptions } from "better-auth";
import { drizzleAdapter } from "better-auth/adapters/drizzle";
import { admin } from "better-auth/plugins";
import { nextCookies } from "better-auth/next-js";

import { getDb, schema } from "@/db";
import { assertGoogleAuthConfiguration } from "@/lib/auth/config";

let authInstance: ReturnType<typeof betterAuth> | undefined;

export function getAuth() {
  if (authInstance) return authInstance;
  assertGoogleAuthConfiguration();
  const db = getDb();
  if (!db) throw new Error("Google auth requires DATABASE_URL outside local/test mode");

  const options: BetterAuthOptions = {
    baseURL: process.env.BETTER_AUTH_URL,
    secret: process.env.BETTER_AUTH_SECRET,
    database: drizzleAdapter(db, {
      provider: "pg",
      schema: {
        app_user: schema.users,
        session: schema.sessions,
        account: schema.accounts,
        verification: schema.verifications,
      },
    }),
    user: {
      modelName: "app_user",
      additionalFields: {
        role: { type: "string", required: false, input: false },
        banned: { type: "boolean", required: false, input: false },
      },
    },
    session: { modelName: "session", expiresIn: 60 * 60 * 24 * 7, updateAge: 60 * 60 * 24 },
    account: { modelName: "account" },
    socialProviders: {
      google: {
        clientId: process.env.GOOGLE_CLIENT_ID!,
        clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
        accessType: "offline",
        prompt: "select_account",
      },
    },
    plugins: [admin({ defaultRole: "user" }), nextCookies()],
  };

  authInstance = betterAuth(options);
  return authInstance;
}
