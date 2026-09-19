import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import process from "node:process";

const root = new URL("..", import.meta.url).pathname.replace(/\/$/, "");
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
serverEnv.TOSS_CLIENT_KEY = "e2e_toss_client_key";
serverEnv.LEMONSQUEEZY_STORE_ID = "e2e_store";
serverEnv.LEMONSQUEEZY_VARIANT_ID = "e2e_variant";
delete serverEnv.PAYMENT_PROVIDER;

const server = spawn(
  "pnpm",
  ["--filter", "ai-saas-foundation-web", "exec", "next", "dev", "--hostname", "localhost", "--port", port],
  { cwd: root, env: serverEnv, stdio: ["ignore", "pipe", "pipe"] },
);

let output = "";
server.stdout.on("data", (chunk) => { output += chunk.toString(); });
server.stderr.on("data", (chunk) => { output += chunk.toString(); });

async function stopServer() {
  if (server.exitCode === null && !server.killed) {
    server.kill("SIGTERM");
    await Promise.race([once(server, "exit"), new Promise((resolve) => setTimeout(resolve, 2_000))]);
  }
}

async function waitForServer() {
  const deadline = Date.now() + 45_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${baseUrl}/login`, { redirect: "manual" });
      if (response.status === 200) return;
    } catch {
      // Next.js is still compiling or binding the port.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`web E2E server did not become ready\n${output}`);
}

function cookieFrom(response) {
  const values = typeof response.headers.getSetCookie === "function"
    ? response.headers.getSetCookie()
    : [response.headers.get("set-cookie") ?? ""];
  return values
    .map((value) => value.split(";", 1)[0])
    .filter(Boolean)
    .join("; ");
}

async function request(path, init = {}, cookie = "") {
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

function jsonInit(method, value) {
  return { method, headers: { "content-type": "application/json" }, body: JSON.stringify(value) };
}

function assertPage(result, path) {
  assert.equal(result.response.status, 200, `${path} should load: ${result.text.slice(0, 300)}`);
  assert.ok(result.text.includes("<body"), `${path} should render a document`);
  assert.doesNotMatch(result.text, /Application error|Unhandled Runtime Error|NEXT_HTTP_ERROR_FALLBACK/, `${path} contains a framework error`);
}

function assertRedirect(result, path) {
  assert.ok([307, 308].includes(result.response.status), `${path} should redirect, got ${result.response.status}`);
  assert.match(result.response.headers.get("location") ?? "", /\/login\?next=/, `${path} should redirect to login`);
}

async function signIn(role) {
  const result = await request("/api/auth/local/sign-in", jsonInit("POST", { role }));
  assert.equal(result.response.status, 200);
  assert.equal(result.body?.session?.user?.role, role);
  const cookie = cookieFrom(result.response);
  assert.match(cookie, /ai_saas_demo_session=/);
  return cookie;
}

async function getJson(path, cookie = "") {
  const result = await request(path, {}, cookie);
  assert.ok(result.body, `${path} returned non-JSON: ${result.text.slice(0, 300)}`);
  return result;
}

async function run() {
  await waitForServer();

  const landing = await request("/");
  assertPage(landing, "/");
  assert.match(landing.text, /Public landing|AI SaaS Foundation/);

  const login = await request("/login");
  assertPage(login, "/login");
  assert.match(login.text, /Google/);
  assert.doesNotMatch(login.text, /Local Demo|Local Member|demo session|member session/i);

  const unauthenticatedSession = await getJson("/api/auth/session");
  assert.equal(unauthenticatedSession.response.status, 200);
  assert.equal(unauthenticatedSession.body.session, null);
  assertRedirect(await request("/app"), "/app");
  assertRedirect(await request("/admin"), "/admin");

  const googleNotConfigured = await request("/api/auth/sign-in/social", jsonInit("POST", { provider: "google" }));
  assert.equal(googleNotConfigured.response.status, 503);
  assert.equal(googleNotConfigured.body.error, "auth_not_configured");
  assert.match(googleNotConfigured.body.message, /Google OAuth/);

  const memberCookie = await signIn("member");
  const memberSession = await getJson("/api/auth/session", memberCookie);
  assert.equal(memberSession.body.session.user.role, "member");
  assertPage(await request("/app", {}, memberCookie), "/app as member");
  assertRedirect(await request("/admin", {}, memberCookie), "/admin as member");
  const memberAdminApi = await getJson("/api/admin/billing-policy", memberCookie);
  assert.equal(memberAdminApi.response.status, 403);
  assert.equal(memberAdminApi.body.error, "admin authorization denied");

  const signedOut = await request("/api/auth/local/sign-out", { method: "POST" }, memberCookie);
  assert.equal(signedOut.response.status, 200);
  const revokedCookie = cookieFrom(signedOut.response);
  const afterSignOut = await getJson("/api/auth/session", revokedCookie);
  assert.equal(afterSignOut.body.session, null);
  assertRedirect(await request("/app", {}, revokedCookie), "/app after sign-out");

  const adminCookie = await signIn("admin");
  assertPage(await request("/admin", {}, adminCookie), "/admin as admin");
  assertPage(await request("/admin/pricing", {}, adminCookie), "/admin/pricing");
  assertPage(await request("/admin/payments", {}, adminCookie), "/admin/payments");
  assertPage(await request("/billing", {}, adminCookie), "/billing");

  const policy = await getJson("/api/admin/billing-policy", adminCookie);
  assert.equal(policy.response.status, 200);
  assert.equal(policy.body.billing.billingMode, "subscription");
  const subscriptionPricing = await getJson("/api/pricing");
  assert.equal(subscriptionPricing.body.billing.billingMode, "subscription");
  const subscriptionOptions = subscriptionPricing.body.plans.flatMap((plan) => plan.options);
  const subscriptionOption = subscriptionOptions.find((option) => option.interval === "year" && option.amountMinor === 29000);
  assert.ok(subscriptionOption, "a yearly subscription option is required");
  assert.equal(subscriptionOption.amountMinor, 29000);

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
  assert.equal(createdPlan.response.status, 201, createdPlan.text);
  assert.equal(createdPlan.body.plan.options[0].mode, "subscription");

  const switched = await request("/api/admin/billing-policy", jsonInit("PATCH", {
    billingMode: "one_time",
    reason: "HTTP E2E one-time policy transition",
  }), adminCookie);
  assert.equal(switched.response.status, 200);
  const oneTimePricing = await getJson("/api/pricing");
  assert.equal(oneTimePricing.body.billing.billingMode, "one_time");
  const oneTimeOption = oneTimePricing.body.plans.flatMap((plan) => plan.options)[0];
  assert.equal(oneTimeOption.interval, "one_time");
  assert.equal(oneTimeOption.amountMinor, 7900);
  const blockedSubscription = await request("/api/pricing/checkout", jsonInit("POST", { optionId: subscriptionOption.id }), adminCookie);
  assert.equal(blockedSubscription.response.status, 409);
  const oneTimeCheckout = await request("/api/pricing/checkout", jsonInit("POST", { optionId: oneTimeOption.id }), adminCookie);
  assert.equal(oneTimeCheckout.response.status, 201, oneTimeCheckout.text);
  assert.equal(oneTimeCheckout.body.mode, "one_time");
  assert.equal(oneTimeCheckout.body.amountMinor, 7900);
  assert.equal(oneTimeCheckout.body.testMode, true);

  const invalidCheckout = await request("/api/pricing/checkout", jsonInit("POST", {}), adminCookie);
  assert.equal(invalidCheckout.response.status, 400);
  assert.match(invalidCheckout.body.error, /optionId is required/);
  const missingOption = await request("/api/pricing/checkout", jsonInit("POST", { optionId: "does-not-exist" }), adminCookie);
  assert.equal(missingOption.response.status, 404);

  const restored = await request("/api/admin/billing-policy", jsonInit("PATCH", {
    billingMode: "subscription",
    reason: "HTTP E2E restore subscription policy",
  }), adminCookie);
  assert.equal(restored.response.status, 200);

  const providers = await getJson("/api/admin/payment-providers", adminCookie);
  assert.equal(providers.response.status, 200);
  assert.deepEqual(providers.body.providers.map((provider) => provider.provider).sort(), ["lemon-squeezy", "mock", "toss"]);

  // Sandbox adapters are exercised through the same catalog checkout endpoint
  // used by the billing UI. The provider registry is restored in the finally
  // block so a failed assertion cannot leave the test process in live mode.
  try {
    for (const provider of ["toss", "lemon-squeezy"]) {
      const disableMock = await request("/api/admin/payment-providers", jsonInit("PATCH", {
        provider: "mock", enabled: false, sandbox: true, reason: `HTTP E2E select ${provider}`,
      }), adminCookie);
      assert.equal(disableMock.response.status, 200, disableMock.text);
      const enableProvider = await request("/api/admin/payment-providers", jsonInit("PATCH", {
        provider, enabled: true, sandbox: true, reason: `HTTP E2E enable ${provider} sandbox`,
      }), adminCookie);
      assert.equal(enableProvider.response.status, 200, enableProvider.text);
      const sandboxPricing = await getJson("/api/pricing");
      const sandboxOption = sandboxPricing.body.plans.flatMap((plan) => plan.options).find((option) => option.interval === "year");
      assert.ok(sandboxOption);
      const sandboxCheckout = await request("/api/pricing/checkout", jsonInit("POST", { optionId: sandboxOption.id }), adminCookie);
      assert.equal(sandboxCheckout.response.status, 201, sandboxCheckout.text);
      assert.equal(sandboxCheckout.body.provider, provider);
      assert.equal(sandboxCheckout.body.testMode, true);
      if (provider === "toss") {
        assert.equal(sandboxCheckout.body.checkoutContext.client_key, "e2e_toss_client_key");
        assert.equal("secret_key" in sandboxCheckout.body.checkoutContext, false);
      } else {
        assert.match(sandboxCheckout.body.checkoutUrl, /checkout\.lemonsqueezy\.com\/buy\/e2e_variant/);
        assert.deepEqual(sandboxCheckout.body.checkoutContext.checkout_data.custom, { order_id: sandboxCheckout.body.orderId });
      }
      const disableProvider = await request("/api/admin/payment-providers", jsonInit("PATCH", {
        provider, enabled: false, sandbox: true, reason: `HTTP E2E disable ${provider} sandbox`,
      }), adminCookie);
      assert.equal(disableProvider.response.status, 200, disableProvider.text);
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
  assert.equal(foundationUnavailable.response.status, 503);
  assert.equal(foundationUnavailable.body.error, "foundation_unavailable");
  assert.match(foundationUnavailable.body.message, /unavailable/);

  console.log("web E2E passed: landing, Google fail-closed, session signup/login/logout, member/admin guards, subscription policy, checkout errors, Toss/Lemon sandbox adapters, and foundation outage handling");
}

try {
  await run();
} catch (error) {
  console.error(error instanceof Error ? error.stack : error);
  console.error(output);
  process.exitCode = 1;
} finally {
  await stopServer();
}
