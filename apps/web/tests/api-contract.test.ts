import { NextRequest } from "next/server";

import { GET as getPublicPricing } from "@/app/api/pricing/route";
import { POST as postCheckout } from "@/app/api/pricing/checkout/route";
import { GET as getAdminPolicy, PATCH as patchAdminPolicy } from "@/app/api/admin/billing-policy/route";
import { GET as getAdminPricing, POST as postAdminPricing } from "@/app/api/admin/pricing/route";
import { GET as getAdminProviders, PATCH as patchAdminProvider } from "@/app/api/admin/payment-providers/route";
import { getBillingPolicy, getPaymentOrder, listPricingCatalog, setBillingMode } from "@/lib/pricing/repository";
import { localDemoSession, localSessionCookie } from "@/lib/auth/local-session";

process.env.APP_ENV = "test";
process.env.FOUNDATION_API_URL = "http://127.0.0.1:9";
delete process.env.DATABASE_URL;

type NextRequestInit = ConstructorParameters<typeof NextRequest>[1];

const request = (url: string, init?: NextRequestInit) => new NextRequest(`http://127.0.0.1:3012${url}`, {
  ...init,
  headers: {
    cookie: `${localSessionCookie}=${localDemoSession.session.id}`,
    ...(init?.headers ?? {}),
  },
});
const json = (body: unknown, init?: NextRequestInit) => request("/", {
  ...init,
  headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  body: JSON.stringify(body),
});

async function bodyOf(response: Response) {
  return response.json() as Promise<Record<string, any>>;
}

describe("pricing and admin API contracts", () => {
  beforeAll(async () => {
    await setBillingMode("subscription", "api-test", "reset before API contract tests");
  });

  afterAll(async () => {
    await setBillingMode("subscription", "api-test", "restore subscription catalog after API contract tests");
    process.env.APP_ENV = "test";
    delete process.env.ADMIN_API_TOKEN;
  });

  it("returns the subscription catalog with annual Pro at 290 USD", async () => {
    const response = await getPublicPricing();
    expect(response.status).toBe(200);
    const body = await bodyOf(response);
    expect(body.billing.billingMode).toBe("subscription");
    const options = body.plans.flatMap((plan: any) => plan.options);
    expect(options.some((option: any) => option.interval === "year" && option.amountMinor === 29000)).toBe(true);
    expect(options.some((option: any) => option.amountMinor === 7900)).toBe(false);
  });

  it("switches the public API atomically to one-time and blocks subscription checkout", async () => {
    const switched = await patchAdminPolicy(json({ billingMode: "one_time", reason: "API contract mode switch" }, { method: "PATCH" }));
    expect(switched.status).toBe(200);

    const catalog = await getPublicPricing();
    expect(catalog.status).toBe(200);
    const catalogBody = await bodyOf(catalog);
    expect(catalogBody.billing.billingMode).toBe("one_time");
    const options = catalogBody.plans.flatMap((plan: any) => plan.options);
    expect(options.map((option: any) => option.interval)).toEqual(["one_time"]);
    expect(options[0].amountMinor).toBe(7900);

    const allPlans = await listPricingCatalog(false);
    const subscriptionOption = allPlans.flatMap((plan) => plan.options).find((option) => option.interval === "year");
    expect(subscriptionOption).toBeTruthy();
    if (!subscriptionOption) throw new Error("seeded subscription option is missing");
    const subscriptionCheckout = await postCheckout(json({ optionId: subscriptionOption.id }, { method: "POST" }));
    expect(subscriptionCheckout.status).toBe(409);

    const oneTimeOption = options[0];
    const oneTimeCheckout = await postCheckout(json({ optionId: oneTimeOption.id }, { method: "POST" }));
    expect(oneTimeCheckout.status).toBe(201);
    const checkoutBody = await bodyOf(oneTimeCheckout);
    expect(checkoutBody.amountMinor).toBe(7900);
    expect(checkoutBody.mode).toBe("one_time");
    expect(checkoutBody.testMode).toBe(true);

    await setBillingMode("subscription", "api-test", "restore subscription mode");
  });

  it("requires admin authorization outside local/test mode", async () => {
    process.env.APP_ENV = "production";
    delete process.env.ADMIN_API_TOKEN;
    const denied = await getAdminPolicy(request("/api/admin/billing-policy"));
    expect(denied.status).toBe(403);

    process.env.ADMIN_API_TOKEN = "test-admin-token";
    const accepted = await getAdminPolicy(request("/api/admin/billing-policy", {
      headers: { authorization: "Bearer test-admin-token" },
    }));
    expect(accepted.status).toBe(200);
    process.env.APP_ENV = "test";
  });

  it("requires reasons for admin writes and exposes provider settings", async () => {
    const pricing = await getAdminPricing(request("/api/admin/pricing"));
    expect(pricing.status).toBe(200);
    expect((await bodyOf(pricing)).plans.length).toBeGreaterThanOrEqual(3);

    const missingReason = await postAdminPricing(json({
      plan: { code: "missing-reason", name: "Missing reason", billingMode: "subscription", options: [] },
    }, { method: "POST" }));
    expect(missingReason.status).toBe(400);

    const providers = await getAdminProviders(request("/api/admin/payment-providers"));
    expect(providers.status).toBe(200);
    expect((await bodyOf(providers)).providers.some((provider: any) => provider.provider === "toss")).toBe(true);

    const missingProviderReason = await patchAdminProvider(json({
      provider: "toss", enabled: false, sandbox: true,
    }, { method: "PATCH" }));
    expect(missingProviderReason.status).toBe(400);
  });

  it("requires matching Toss sandbox keys before admin can enable Toss", async () => {
    const originalClientKey = process.env.TOSS_CLIENT_KEY;
    const originalSecretKey = process.env.TOSS_SECRET_KEY;
    process.env.PAYMENT_SANDBOX = "true";
    delete process.env.TOSS_CLIENT_KEY;
    delete process.env.TOSS_SECRET_KEY;

    const missingKeys = await patchAdminProvider(json({
      provider: "toss", enabled: true, sandbox: true, reason: "reject unconfigured Toss sandbox",
    }, { method: "PATCH" }));
    expect(missingKeys.status).toBe(400);
    expect((await bodyOf(missingKeys)).error).toMatch(/TOSS_CLIENT_KEY and TOSS_SECRET_KEY/);

    process.env.TOSS_CLIENT_KEY = "test_ck_example";
    process.env.TOSS_SECRET_KEY = "test_sk_example";
    const enabled = await patchAdminProvider(json({
      provider: "toss", enabled: true, sandbox: true, reason: "enable configured Toss sandbox",
    }, { method: "PATCH" }));
    expect(enabled.status).toBe(200);
    expect((await bodyOf(enabled)).provider.provider).toBe("toss");

    const tossPlan = await postAdminPricing(json({
      reason: "create Toss KRW API contract option",
      plan: {
        code: `api-toss-${Date.now()}`,
        name: "API Toss sandbox plan",
        description: "test-only Toss option",
        billingMode: "subscription",
        options: [{ mode: "subscription", interval: "month", provider: "toss", currency: "KRW", amountMinor: 1000 }],
      },
    }, { method: "POST" }));
    expect(tossPlan.status).toBe(201);
    const tossOption = (await bodyOf(tossPlan)).plan.options[0];
    const tossCheckout = await postCheckout(json({ optionId: tossOption.id }, { method: "POST" }));
    expect(tossCheckout.status).toBe(201);
    const tossCheckoutBody = await bodyOf(tossCheckout);
    expect(tossCheckoutBody.provider).toBe("toss");
    expect(tossCheckoutBody.checkoutContext.billing_auth).toBe(true);
    expect(tossCheckoutBody.checkoutContext.client_key).toBe("test_ck_example");
    expect(await getPaymentOrder(tossCheckoutBody.orderId)).toEqual(expect.objectContaining({ status: "pending", currency: "KRW" }));

    await patchAdminProvider(json({ provider: "toss", enabled: false, sandbox: true, reason: "restore Toss provider" }, { method: "PATCH" }));
    await patchAdminProvider(json({ provider: "mock", enabled: true, sandbox: true, reason: "restore mock provider" }, { method: "PATCH" }));
    if (originalClientKey === undefined) delete process.env.TOSS_CLIENT_KEY;
    else process.env.TOSS_CLIENT_KEY = originalClientKey;
    if (originalSecretKey === undefined) delete process.env.TOSS_SECRET_KEY;
    else process.env.TOSS_SECRET_KEY = originalSecretKey;
  });

  it("rejects unknown and inactive checkout options", async () => {
    const unknown = await postCheckout(json({ optionId: "does-not-exist" }, { method: "POST" }));
    expect(unknown.status).toBe(404);
    expect((await bodyOf(unknown)).error).toBe("pricing option is not available");

    expect((await getBillingPolicy()).billingMode).toBe("subscription");
  });
});
