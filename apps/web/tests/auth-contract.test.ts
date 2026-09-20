import { NextRequest } from "next/server";
import { getTableName } from "drizzle-orm";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { GET as getAuthCatchAll } from "@/app/api/auth/[...all]/route";
import { GET as getFoundation } from "@/app/api/foundation/[...path]/route";
import { GET as getSession } from "@/app/api/auth/session/route";
import { POST as localSignIn } from "@/app/api/auth/local/sign-in/route";
import { POST as localSignOut } from "@/app/api/auth/local/sign-out/route";
import { schema } from "@/db";
import { GoogleLoginForm } from "@/components/auth/google-login-form";
import { requireAdmin } from "@/lib/admin-guard";
import { localDemoSession, localMemberSession, localSessionCookie } from "@/lib/auth/local-session";

const originalEnv = {
  appEnv: process.env.APP_ENV,
  databaseUrl: process.env.DATABASE_URL,
  betterAuthSecret: process.env.BETTER_AUTH_SECRET,
  betterAuthUrl: process.env.BETTER_AUTH_URL,
  googleClientId: process.env.GOOGLE_CLIENT_ID,
  googleClientSecret: process.env.GOOGLE_CLIENT_SECRET,
};

function setLocalEnv() {
  process.env.APP_ENV = "test";
  delete process.env.DATABASE_URL;
  delete process.env.BETTER_AUTH_SECRET;
  delete process.env.BETTER_AUTH_URL;
  delete process.env.GOOGLE_CLIENT_ID;
  delete process.env.GOOGLE_CLIENT_SECRET;
}

function restoreEnv() {
  for (const [key, value] of Object.entries({
    APP_ENV: originalEnv.appEnv,
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
  beforeAll(setLocalEnv);
  afterAll(restoreEnv);

  it("exports the Better Auth identity tables and keeps the local profile credential-free", () => {
    expect(getTableName(schema.users)).toBe("app_user");
    expect(getTableName(schema.sessions)).toBe("session");
    expect(getTableName(schema.accounts)).toBe("account");
    expect(getTableName(schema.verifications)).toBe("verification");
  });

  it("creates a test fixture session with an httpOnly cookie and exposes a safe projection", async () => {
    const signIn = await localSignIn(new NextRequest("http://127.0.0.1:3012/api/auth/local/sign-in", { method: "POST", body: "{}" }));
    expect(signIn.status).toBe(200);
    const setCookie = signIn.headers.get("set-cookie") ?? "";
    expect(setCookie).toMatch(new RegExp(`${localSessionCookie}=${localDemoSession.session.id}`));
    expect(setCookie).toMatch(/HttpOnly/i);

    const session = await getSession(new NextRequest("http://127.0.0.1:3012/api/auth/session", {
      headers: { cookie: `${localSessionCookie}=${localDemoSession.session.id}` },
    }));
    expect(session.status).toBe(200);
    const body = await session.json() as { session: Record<string, unknown> };
    expect((body.session.user as Record<string, unknown>).email).toBe("demo@example.test");
    expect("accessToken" in body.session).toBe(false);
    expect("refreshToken" in body.session).toBe(false);
  });

  it("keeps regular-user fixture sessions out of admin authorization", async () => {
    const signIn = await localSignIn(new NextRequest("http://127.0.0.1:3012/api/auth/local/sign-in", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ role: "member" }),
    }));
    expect(signIn.status).toBe(200);
    expect(signIn.headers.get("set-cookie") ?? "").toMatch(new RegExp(`${localSessionCookie}=${localMemberSession.session.id}`));

    const session = await getSession(new NextRequest("http://127.0.0.1:3012/api/auth/session", {
      headers: { cookie: `${localSessionCookie}=${localMemberSession.session.id}` },
    }));
    const body = await session.json() as { session: { user: { role: string } } };
    expect(body.session.user.role).toBe("member");
    await expect(requireAdmin(new NextRequest("http://127.0.0.1:3012/api/admin", {
        headers: { cookie: `${localSessionCookie}=${localMemberSession.session.id}` },
      }))).rejects.toThrow(/admin authorization denied/);
  });

  it("returns 403 when a member reaches the foundation admin proxy", async () => {
    const response = await getFoundation(
      new NextRequest("http://127.0.0.1:3012/api/foundation/v1/admin/users", {
        headers: { cookie: `${localSessionCookie}=${localMemberSession.session.id}` },
      }),
      { params: Promise.resolve({ path: ["v1", "admin", "users"] }) },
    );
    expect(response.status).toBe(403);
    expect((await response.json()).error).toBe("admin authorization denied");
  });

  it("returns a safe not-configured response instead of starting OAuth locally", async () => {
    const response = await getAuthCatchAll(new NextRequest("http://127.0.0.1:3012/api/auth/sign-in/social"));
    expect(response.status).toBe(503);
    expect((await response.json()).error).toBe("auth_not_configured");
  });

  it("keeps Google as the only user-facing sign-up and sign-in path", () => {
    const configured = renderToStaticMarkup(createElement(GoogleLoginForm, { googleConfigured: true, callbackURL: "/app" }));
    expect(configured).toMatch(/Continue with Google/);
    expect(configured).not.toMatch(/local|mock/i);

    const unconfigured = renderToStaticMarkup(createElement(GoogleLoginForm, { googleConfigured: false, callbackURL: "/app" }));
    expect(unconfigured).toMatch(/Open Google OAuth setup guide/);
    expect(unconfigured).not.toMatch(/member|admin session/i);
  });

  it("does not expose the local demo sign-in route outside test runtime", async () => {
    process.env.APP_ENV = "local";
    const response = await localSignIn(new NextRequest("http://127.0.0.1:3012/api/auth/local/sign-in", { method: "POST" }));
    expect(response.status).toBe(404);
    expect((await response.json()).error).toBe("test_auth_only");
    setLocalEnv();
  });

  it("revokes the local cookie and never accepts local fallback in production", async () => {
    const signedOut = await localSignOut();
    expect(signedOut.status).toBe(200);
    expect(signedOut.headers.get("set-cookie") ?? "").toMatch(/Expires=Thu, 01 Jan 1970/i);

    process.env.APP_ENV = "production";
    const session = await getSession(new NextRequest("http://127.0.0.1:3012/api/auth/session", {
      headers: { cookie: `${localSessionCookie}=${localDemoSession.session.id}` },
    }));
    expect(session.status).toBe(503);
    await expect(requireAdmin(new NextRequest("http://127.0.0.1:3012/api/admin"))).rejects.toThrow(/Google auth is not configured|authorization required/);
    setLocalEnv();
  });
});
