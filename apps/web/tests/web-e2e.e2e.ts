import { once } from "node:events";
import { resolve } from "node:path";
import { spawn, type ChildProcess } from "node:child_process";

const root = resolve(__dirname, "../../..");
const port = process.env.WEB_E2E_PORT ?? "3015";
const baseUrl = `http://localhost:${port}`;
const serverEnv = { ...process.env };

// This profile intentionally has no provider credentials. It exercises the
// fail-closed Google route, test-only auth fixture, local pricing repository,
// and provider-neutral sandbox handoffs without touching Neon or a live PSP.
serverEnv.APP_ENV = "test";
serverEnv.NEXT_PUBLIC_GOOGLE_AUTH_ENABLED = "false";
serverEnv.FOUNDATION_API_URL = "http://127.0.0.1:9";
serverEnv.APP_BASE_URL = baseUrl;
serverEnv.BETTER_AUTH_URL = baseUrl;
serverEnv.DATABASE_URL = "";
serverEnv.BETTER_AUTH_SECRET = "";
serverEnv.GOOGLE_CLIENT_ID = "";
serverEnv.GOOGLE_CLIENT_SECRET = "";
serverEnv.PAYMENT_SANDBOX = "true";
serverEnv.TOSS_CLIENT_KEY = "test_ck_e2e_toss_client_key";
serverEnv.TOSS_SECRET_KEY = "test_sk_e2e_toss_secret_key";
serverEnv.LEMONSQUEEZY_STORE_ID = "e2e_store";
serverEnv.LEMONSQUEEZY_VARIANT_ID = "e2e_variant";
delete serverEnv.PAYMENT_PROVIDER;

let server: ChildProcess | undefined;
let output = "";

function startServer() {
  const child = spawn(
    "pnpm",
    ["--filter", "ai-saas-foundation-web", "exec", "next", "dev", "--hostname", "localhost", "--port", port],
    { cwd: root, env: serverEnv, stdio: ["ignore", "pipe", "pipe"] },
  );
  server = child;
  child.stdout?.on("data", (chunk) => { output += chunk.toString(); });
  child.stderr?.on("data", (chunk) => { output += chunk.toString(); });
}

async function stopServer() {
  const child = server;
  if (child && child.exitCode === null && !child.killed) {
    child.kill("SIGTERM");
    await Promise.race([once(child, "exit"), new Promise((resolve) => setTimeout(resolve, 2_000))]);
  }
  child?.stdout?.destroy();
  child?.stderr?.destroy();
  server = undefined;
}

async function waitForServer() {
  const deadline = Date.now() + 120_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${baseUrl}/login`, { redirect: "manual", signal: AbortSignal.timeout(10_000) });
      if (response.status === 200) return;
    } catch {
      // Next.js is still compiling or binding the port.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`web E2E server did not become ready\n${output}`);
}

function cookieFrom(response: Response) {
  const values = typeof response.headers.getSetCookie === "function"
    ? response.headers.getSetCookie()
    : [response.headers.get("set-cookie") ?? ""];
  return values
    .map((value) => value.split(";", 1)[0])
    .filter(Boolean)
    .join("; ");
}

type RequestResult = { response: Response; text: string; body: any };

async function request(path: string, init: RequestInit = {}, cookie = ""): Promise<RequestResult> {
  const headers = new Headers(init.headers);
  if (cookie) headers.set("cookie", cookie);
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers,
    redirect: init.redirect ?? "manual",
  });
  const text = await response.text();
  let body = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    // HTML is useful evidence for an unexpected framework error.
  }
  return { response, text, body };
}

function jsonInit(method: string, value: unknown): RequestInit {
  return { method, headers: { "content-type": "application/json" }, body: JSON.stringify(value) };
}

function assertPage(result: RequestResult, path: string) {
  expect(result.response.status).toBe(200);
  expect(result.text).toContain("<body");
  expect(result.text).not.toMatch(/Application error|Unhandled Runtime Error|NEXT_HTTP_ERROR_FALLBACK/);
}

function assertRedirect(result: RequestResult) {
  expect([307, 308]).toContain(result.response.status);
  expect(result.response.headers.get("location") ?? "").toMatch(/\/login\?next=/);
}

async function signIn(role: string) {
  const result = await request("/api/auth/local/sign-in", jsonInit("POST", { role }));
  expect(result.response.status).toBe(200);
  expect(result.body?.session?.user?.role).toBe(role);
  const cookie = cookieFrom(result.response);
  expect(cookie).toMatch(/ai_saas_demo_session=/);
  return cookie;
}

async function getJson(path: string, cookie = "") {
  const result = await request(path, {}, cookie);
  expect(result.body).toBeTruthy();
  return result;
}

describe("web HTTP E2E contracts", () => {
  beforeAll(async () => {
    startServer();
    await waitForServer();
  }, 60_000);

  afterAll(async () => {
    await stopServer();
  });

  it("covers the local auth, pricing, payment, and outage flows", async () => {
    const landing = await request("/");
    assertPage(landing, "/");
    expect(landing.text).toMatch(/Public landing|AI SaaS Foundation/);

    const login = await request("/login");
    assertPage(login, "/login");
    expect(login.text).toMatch(/Google/);
    expect(login.text).not.toMatch(/Local Demo|Local Member|demo session|member session/i);

    const unauthenticatedSession = await getJson("/api/auth/session");
    expect(unauthenticatedSession.response.status).toBe(200);
    expect(unauthenticatedSession.body.session).toBeNull();
    assertRedirect(await request("/app"));
    assertRedirect(await request("/admin"));

    const googleNotConfigured = await request("/api/auth/sign-in/social", jsonInit("POST", { provider: "google" }));
    expect(googleNotConfigured.response.status).toBe(503);
    expect(googleNotConfigured.body.error).toBe("auth_not_configured");
    expect(googleNotConfigured.body.message).toMatch(/Google OAuth/);

    const memberCookie = await signIn("member");
    const memberSession = await getJson("/api/auth/session", memberCookie);
    expect(memberSession.body.session.user.role).toBe("member");
    assertPage(await request("/app", {}, memberCookie), "/app as member");
    assertRedirect(await request("/admin", {}, memberCookie));
    const memberAdminApi = await getJson("/api/admin/billing-policy", memberCookie);
    expect(memberAdminApi.response.status).toBe(403);
    expect(memberAdminApi.body.error).toBe("admin authorization denied");

    const signedOut = await request("/api/auth/local/sign-out", { method: "POST" }, memberCookie);
    expect(signedOut.response.status).toBe(200);
    const revokedCookie = cookieFrom(signedOut.response);
    const afterSignOut = await getJson("/api/auth/session", revokedCookie);
    expect(afterSignOut.body.session).toBeNull();
    assertRedirect(await request("/app", {}, revokedCookie));

    const adminCookie = await signIn("admin");
    assertPage(await request("/admin", {}, adminCookie), "/admin as admin");
    assertPage(await request("/admin/pricing", {}, adminCookie), "/admin/pricing");
    assertPage(await request("/admin/payments", {}, adminCookie), "/admin/payments");
    assertPage(await request("/billing", {}, adminCookie), "/billing");

    const policy = await getJson("/api/admin/billing-policy", adminCookie);
    expect(policy.response.status).toBe(200);
    expect(policy.body.billing.billingMode).toBe("subscription");
    const subscriptionPricing = await getJson("/api/pricing");
    expect(subscriptionPricing.body.billing.billingMode).toBe("subscription");
    const subscriptionOptions = subscriptionPricing.body.plans.flatMap((plan: any) => plan.options);
    const subscriptionOption = subscriptionOptions.find((option: any) => option.interval === "year" && option.amountMinor === 29000);
    expect(subscriptionOption).toBeTruthy();
    expect(subscriptionOption.amountMinor).toBe(29000);

    const createdPlan = await request("/api/admin/pricing", jsonInit("POST", {
      reason: "HTTP E2E subscription catalog coverage",
      plan: {
        code: `e2e-${Date.now()}`,
        name: "HTTP E2E Plan",
        description: "Created and validated only inside the test process.",
        billingMode: "subscription",
        options: [{ mode: "subscription", interval: "month", provider: "mock", currency: "USD", amountMinor: 1900 }],
      },
    }), adminCookie);
    expect(createdPlan.response.status).toBe(201);
    expect(createdPlan.body.plan.options[0].mode).toBe("subscription");

    const switched = await request("/api/admin/billing-policy", jsonInit("PATCH", {
      billingMode: "one_time",
      reason: "HTTP E2E one-time policy transition",
    }), adminCookie);
    expect(switched.response.status).toBe(200);
    const oneTimePricing = await getJson("/api/pricing");
    expect(oneTimePricing.body.billing.billingMode).toBe("one_time");
    const oneTimeOption = oneTimePricing.body.plans.flatMap((plan: any) => plan.options)[0];
    expect(oneTimeOption.interval).toBe("one_time");
    expect(oneTimeOption.amountMinor).toBe(7900);
    const blockedSubscription = await request("/api/pricing/checkout", jsonInit("POST", { optionId: subscriptionOption.id }), adminCookie);
    expect(blockedSubscription.response.status).toBe(409);
    const oneTimeCheckout = await request("/api/pricing/checkout", jsonInit("POST", { optionId: oneTimeOption.id }), adminCookie);
    expect(oneTimeCheckout.response.status).toBe(201);
    expect(oneTimeCheckout.body.mode).toBe("one_time");
    expect(oneTimeCheckout.body.amountMinor).toBe(7900);
    expect(oneTimeCheckout.body.testMode).toBe(true);

    const invalidCheckout = await request("/api/pricing/checkout", jsonInit("POST", {}), adminCookie);
    expect(invalidCheckout.response.status).toBe(400);
    expect(invalidCheckout.body.error).toMatch(/optionId is required/);
    const missingOption = await request("/api/pricing/checkout", jsonInit("POST", { optionId: "does-not-exist" }), adminCookie);
    expect(missingOption.response.status).toBe(404);

    const restored = await request("/api/admin/billing-policy", jsonInit("PATCH", {
      billingMode: "subscription",
      reason: "HTTP E2E restore subscription policy",
    }), adminCookie);
    expect(restored.response.status).toBe(200);

    const providers = await getJson("/api/admin/payment-providers", adminCookie);
    expect(providers.response.status).toBe(200);
    expect(providers.body.providers.map((provider: any) => provider.provider).sort()).toEqual(["lemon-squeezy", "mock", "toss"]);

    const tossPlan = await request("/api/admin/pricing", jsonInit("POST", {
      reason: "HTTP E2E Toss KRW sandbox catalog",
      plan: {
        code: `e2e-toss-${Date.now()}`,
        name: "HTTP E2E Toss Plan",
        description: "KRW option used only by the sandbox contract.",
        billingMode: "subscription",
        options: [{ mode: "subscription", interval: "year", provider: "toss", currency: "KRW", amountMinor: 1000 }],
      },
    }), adminCookie);
    expect(tossPlan.response.status).toBe(201);

    try {
      for (const provider of ["toss", "lemon-squeezy"]) {
        const disableMock = await request("/api/admin/payment-providers", jsonInit("PATCH", {
          provider: "mock", enabled: false, sandbox: true, reason: `HTTP E2E select ${provider}`,
        }), adminCookie);
        expect(disableMock.response.status).toBe(200);
        const enableProvider = await request("/api/admin/payment-providers", jsonInit("PATCH", {
          provider, enabled: true, sandbox: true, reason: `HTTP E2E enable ${provider} sandbox`,
        }), adminCookie);
        expect(enableProvider.response.status).toBe(200);
        const sandboxPricing = await getJson("/api/pricing");
        const sandboxOption = sandboxPricing.body.plans.flatMap((plan: any) => plan.options).find((option: any) => provider === "toss" ? option.provider === "toss" : option.interval === "year");
        expect(sandboxOption).toBeTruthy();
        const sandboxCheckout = await request("/api/pricing/checkout", jsonInit("POST", { optionId: sandboxOption.id }), adminCookie);
        expect(sandboxCheckout.response.status).toBe(201);
        expect(sandboxCheckout.body.provider).toBe(provider);
        expect(sandboxCheckout.body.testMode).toBe(true);
        if (provider === "toss") {
          expect(sandboxCheckout.body.checkoutContext.client_key).toBe("e2e_toss_client_key");
          expect("secret_key" in sandboxCheckout.body.checkoutContext).toBe(false);
        } else {
          expect(sandboxCheckout.body.checkoutUrl).toMatch(/checkout\.lemonsqueezy\.com\/buy\/e2e_variant/);
          expect(sandboxCheckout.body.checkoutContext.checkout_data.custom).toEqual({ order_id: sandboxCheckout.body.orderId });
        }
        const disableProvider = await request("/api/admin/payment-providers", jsonInit("PATCH", {
          provider, enabled: false, sandbox: true, reason: `HTTP E2E disable ${provider} sandbox`,
        }), adminCookie);
        expect(disableProvider.response.status).toBe(200);
      }
    } finally {
      await request("/api/admin/payment-providers", jsonInit("PATCH", {
        provider: "toss", enabled: false, sandbox: true, reason: "HTTP E2E restore provider registry",
      }), adminCookie);
      await request("/api/admin/payment-providers", jsonInit("PATCH", {
        provider: "lemon-squeezy", enabled: false, sandbox: true, reason: "HTTP E2E restore provider registry",
      }), adminCookie);
      await request("/api/admin/payment-providers", jsonInit("PATCH", {
        provider: "mock", enabled: true, sandbox: true, reason: "HTTP E2E restore mock provider",
      }), adminCookie);
    }

    const foundationUnavailable = await getJson("/api/foundation/healthz", adminCookie);
    expect(foundationUnavailable.response.status).toBe(503);
    expect(foundationUnavailable.body.error).toBe("foundation_unavailable");
    expect(foundationUnavailable.body.message).toMatch(/unavailable/);
  }, 300_000);
});
