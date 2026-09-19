import assert from "node:assert/strict";
import { after, before, describe, it } from "node:test";
import { NextRequest } from "next/server";
import { getTableName } from "drizzle-orm";

import { GET as getAuthCatchAll } from "@/app/api/auth/[...all]/route";
import { GET as getSession } from "@/app/api/auth/session/route";
import { POST as localSignIn } from "@/app/api/auth/local/sign-in/route";
import { POST as localSignOut } from "@/app/api/auth/local/sign-out/route";
import { schema } from "@/db";
import { requireAdmin } from "@/lib/admin-guard";
import { localDemoSession, localSessionCookie } from "@/lib/auth/local-session";

const originalEnv = {
  appEnv: process.env.APP_ENV,
  allowLocalAdmin: process.env.ALLOW_LOCAL_ADMIN,
  databaseUrl: process.env.DATABASE_URL,
  betterAuthSecret: process.env.BETTER_AUTH_SECRET,
  betterAuthUrl: process.env.BETTER_AUTH_URL,
  googleClientId: process.env.GOOGLE_CLIENT_ID,
  googleClientSecret: process.env.GOOGLE_CLIENT_SECRET,
};

function setLocalEnv() {
  process.env.APP_ENV = "test";
  process.env.ALLOW_LOCAL_ADMIN = "true";
  delete process.env.DATABASE_URL;
  delete process.env.BETTER_AUTH_SECRET;
  delete process.env.BETTER_AUTH_URL;
  delete process.env.GOOGLE_CLIENT_ID;
  delete process.env.GOOGLE_CLIENT_SECRET;
}

function restoreEnv() {
  for (const [key, value] of Object.entries({
    APP_ENV: originalEnv.appEnv,
    ALLOW_LOCAL_ADMIN: originalEnv.allowLocalAdmin,
    DATABASE_URL: originalEnv.databaseUrl,
    BETTER_AUTH_SECRET: originalEnv.betterAuthSecret,
    BETTER_AUTH_URL: originalEnv.betterAuthUrl,
    GOOGLE_CLIENT_ID: originalEnv.googleClientId,
    GOOGLE_CLIENT_SECRET: originalEnv.googleClientSecret,
  })) {
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
}

describe("Google auth and session contracts", () => {
  before(setLocalEnv);
  after(restoreEnv);

  it("exports the Better Auth identity tables and keeps the local profile credential-free", () => {
    assert.equal(getTableName(schema.users), "app_user");
    assert.equal(getTableName(schema.sessions), "session");
    assert.equal(getTableName(schema.accounts), "account");
    assert.equal(getTableName(schema.verifications), "verification");
  });

  it("creates a local demo session with an httpOnly cookie and exposes a safe projection", async () => {
    const signIn = await localSignIn();
    assert.equal(signIn.status, 200);
    const setCookie = signIn.headers.get("set-cookie") ?? "";
    assert.match(setCookie, new RegExp(`${localSessionCookie}=${localDemoSession.session.id}`));
    assert.match(setCookie, /HttpOnly/i);

    const session = await getSession(new NextRequest("http://127.0.0.1:3012/api/auth/session", {
      headers: { cookie: `${localSessionCookie}=${localDemoSession.session.id}` },
    }));
    assert.equal(session.status, 200);
    const body = await session.json() as { session: Record<string, unknown> };
    assert.equal((body.session.user as Record<string, unknown>).email, "demo@example.test");
    assert.equal("accessToken" in body.session, false);
    assert.equal("refreshToken" in body.session, false);
  });

  it("returns a safe not-configured response instead of starting OAuth locally", async () => {
    const response = await getAuthCatchAll(new NextRequest("http://127.0.0.1:3012/api/auth/sign-in/social"));
    assert.equal(response.status, 503);
    assert.equal((await response.json()).error, "auth_not_configured");
  });

  it("revokes the local cookie and never accepts local fallback in production", async () => {
    const signedOut = await localSignOut();
    assert.equal(signedOut.status, 200);
    assert.match(signedOut.headers.get("set-cookie") ?? "", /Expires=Thu, 01 Jan 1970/i);

    process.env.APP_ENV = "production";
    delete process.env.ALLOW_LOCAL_ADMIN;
    const session = await getSession(new NextRequest("http://127.0.0.1:3012/api/auth/session", {
      headers: { cookie: `${localSessionCookie}=${localDemoSession.session.id}` },
    }));
    assert.equal(session.status, 503);
    await assert.rejects(
      () => requireAdmin(new NextRequest("http://127.0.0.1:3012/api/admin")),
      /Google auth is not configured|authorization required/,
    );
    setLocalEnv();
  });
});
