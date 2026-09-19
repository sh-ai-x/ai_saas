import assert from "node:assert/strict";
import { after, before, describe, it } from "node:test";
import { NextRequest } from "next/server";

import { GET as getPublicPricing } from "@/app/api/pricing/route";
import { POST as postCheckout } from "@/app/api/pricing/checkout/route";
import { GET as getAdminPolicy, PATCH as patchAdminPolicy } from "@/app/api/admin/billing-policy/route";
import { GET as getAdminPricing, POST as postAdminPricing } from "@/app/api/admin/pricing/route";
import { GET as getAdminProviders, PATCH as patchAdminProvider } from "@/app/api/admin/payment-providers/route";
import { getBillingPolicy, listPricingCatalog, setBillingMode } from "@/lib/pricing/repository";
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
  before(async () => {
    await setBillingMode("subscription", "api-test", "reset before API contract tests");
  });

  after(async () => {
    await setBillingMode("subscription", "api-test", "restore subscription catalog after API contract tests");
    process.env.APP_ENV = "test";
    delete process.env.ADMIN_API_TOKEN;
  });

  it("returns the subscription catalog with annual Pro at 290 USD", async () => {
    const response = await getPublicPricing();
    assert.equal(response.status, 200);
    const body = await bodyOf(response);
    assert.equal(body.billing.billingMode, "subscription");
    const options = body.plans.flatMap((plan: any) => plan.options);
    assert.ok(options.some((option: any) => option.interval === "year" && option.amountMinor === 29000));
    assert.equal(options.some((option: any) => option.amountMinor === 7900), false);
  });

  it("switches the public API atomically to one-time and blocks subscription checkout", async () => {
    const switched = await patchAdminPolicy(json({ billingMode: "one_time", reason: "API contract mode switch" }, { method: "PATCH" }));
    assert.equal(switched.status, 200);

    const catalog = await getPublicPricing();
    assert.equal(catalog.status, 200);
    const catalogBody = await bodyOf(catalog);
    assert.equal(catalogBody.billing.billingMode, "one_time");
    const options = catalogBody.plans.flatMap((plan: any) => plan.options);
    assert.deepEqual(options.map((option: any) => option.interval), ["one_time"]);
    assert.equal(options[0].amountMinor, 7900);

    const allPlans = await listPricingCatalog(false);
    const subscriptionOption = allPlans.flatMap((plan) => plan.options).find((option) => option.interval === "year");
    assert.ok(subscriptionOption);
    const subscriptionCheckout = await postCheckout(json({ optionId: subscriptionOption.id }, { method: "POST" }));
    assert.equal(subscriptionCheckout.status, 409);

    const oneTimeOption = options[0];
    const oneTimeCheckout = await postCheckout(json({ optionId: oneTimeOption.id }, { method: "POST" }));
    assert.equal(oneTimeCheckout.status, 201);
    const checkoutBody = await bodyOf(oneTimeCheckout);
    assert.equal(checkoutBody.amountMinor, 7900);
    assert.equal(checkoutBody.mode, "one_time");
    assert.equal(checkoutBody.testMode, true);

    await setBillingMode("subscription", "api-test", "restore subscription mode");
  });

  it("requires admin authorization outside local/test mode", async () => {
    process.env.APP_ENV = "production";
    delete process.env.ADMIN_API_TOKEN;
    const denied = await getAdminPolicy(request("/api/admin/billing-policy"));
    assert.equal(denied.status, 403);

    process.env.ADMIN_API_TOKEN = "test-admin-token";
    const accepted = await getAdminPolicy(request("/api/admin/billing-policy", {
      headers: { authorization: "Bearer test-admin-token" },
    }));
    assert.equal(accepted.status, 200);
    process.env.APP_ENV = "test";
  });

  it("requires reasons for admin writes and exposes provider settings", async () => {
    const pricing = await getAdminPricing(request("/api/admin/pricing"));
    assert.equal(pricing.status, 200);
    assert.ok((await bodyOf(pricing)).plans.length >= 3);

    const missingReason = await postAdminPricing(json({
      plan: { code: "missing-reason", name: "Missing reason", billingMode: "subscription", options: [] },
    }, { method: "POST" }));
    assert.equal(missingReason.status, 400);

    const providers = await getAdminProviders(request("/api/admin/payment-providers"));
    assert.equal(providers.status, 200);
    assert.ok((await bodyOf(providers)).providers.some((provider: any) => provider.provider === "toss"));

    const missingProviderReason = await patchAdminProvider(json({
      provider: "toss", enabled: false, sandbox: true,
    }, { method: "PATCH" }));
    assert.equal(missingProviderReason.status, 400);
  });

  it("rejects unknown and inactive checkout options", async () => {
    const unknown = await postCheckout(json({ optionId: "does-not-exist" }, { method: "POST" }));
    assert.equal(unknown.status, 404);
    assert.equal((await bodyOf(unknown)).error, "pricing option is not available");

    assert.equal((await getBillingPolicy()).billingMode, "subscription");
  });
});
