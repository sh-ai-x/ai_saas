import { readFileSync } from "node:fs";
import { join } from "node:path";

import { GET as getPricing } from "@/app/api/pricing/route";
import { applySelectedPaymentProvider, getBillingPolicy, selectedPaymentProvider } from "@/lib/pricing/repository";
import { seededPricingCatalog } from "@/lib/pricing/seed";
import { updateProviderSetting } from "@/lib/pricing/repository";
import { createCatalogCheckout } from "@/lib/payments/catalog-checkout";

process.env.APP_ENV = "test";
delete process.env.DATABASE_URL;

describe("the existing Starter and Pro catalog is Toss-compatible", () => {
  it("keeps the existing plan and option IDs while using KRW amounts", () => {
    const plans = seededPricingCatalog.filter((plan) => plan.code === "starter" || plan.code === "pro");
    const options = plans.flatMap((plan) => plan.options);

    expect(options.map((option) => option.id)).toEqual([
      "option-starter-monthly",
      "option-starter-yearly",
      "option-pro-monthly",
      "option-pro-yearly",
    ]);
    expect(options.every((option) => option.currency === "KRW")).toBe(true);
    expect(options.map((option) => option.amountMinor)).toEqual([900, 9000, 2900, 29000]);
  });

  it("uses KRW as the local catalog currency", async () => {
    await expect(getBillingPolicy()).resolves.toMatchObject({ billingMode: "subscription", currency: "KRW" });
  });

  it("exposes the existing options as Toss options when Toss is enabled", async () => {
    await updateProviderSetting("toss", { enabled: true, sandbox: true, publicConfig: {}, secretRef: "TOSS_SECRET_KEY" }, "test-suite", "use Toss catalog provider");
    try {
      const response = await getPricing();
      const body = (await response.json()) as { plans: Array<{ code: string; options: Array<{ provider: string; currency: string }> }> };
      const pro = body.plans.find((plan) => plan.code === "pro");
      expect(response.status).toBe(200);
      expect(pro?.options).toHaveLength(2);
      expect(pro?.options.every((option) => option.provider === "toss" && option.currency === "KRW")).toBe(true);
    } finally {
      await updateProviderSetting("mock", { enabled: true, sandbox: true, publicConfig: {}, secretRef: null }, "test-suite", "restore mock catalog provider");
    }
  });

  it("does not expose a provider-specific sandbox plan in the public catalog", () => {
    const providerSpecificPlan = {
      id: "plan-manual-toss-sandbox",
      tenantId: "platform",
      code: "manual-toss-sandbox",
      name: "Manual Toss Sandbox",
      description: "Provider-only test fixture",
      billingMode: "subscription" as const,
      active: true,
      isDefault: false,
      displayOrder: 99,
      features: [],
      quotas: {},
      options: [{
        id: "option-manual-toss-sandbox",
        planId: "plan-manual-toss-sandbox",
        mode: "subscription" as const,
        interval: "month" as const,
        provider: "toss" as const,
        currency: "KRW",
        amountMinor: 10,
        compareAtAmountMinor: null,
        providerProductRef: null,
        providerPriceRef: null,
        active: true,
      }],
    };
    const starter = seededPricingCatalog.find((plan) => plan.code === "starter");
    if (!starter) throw new Error("seeded Starter plan is missing");

    const publicPlans = applySelectedPaymentProvider([starter, providerSpecificPlan], "mock");

    expect(publicPlans.map((plan) => plan.code)).toEqual(["starter"]);
    expect(publicPlans[0]?.options.every((option) => option.provider === "mock")).toBe(true);
  });

  it("honors an explicit live provider over the seeded mock provider", async () => {
    process.env.PAYMENT_PROVIDER = "toss";
    try {
      await expect(selectedPaymentProvider()).resolves.toBe("toss");
    } finally {
      delete process.env.PAYMENT_PROVIDER;
    }
  });

  it("creates Toss billing authorization from the existing Pro option", async () => {
    const originalClientKey = process.env.TOSS_CLIENT_KEY;
    process.env.TOSS_CLIENT_KEY = "test_ck_existing_pro";
    try {
      const pro = seededPricingCatalog.find((plan) => plan.code === "pro");
      const option = pro?.options.find((candidate) => candidate.id === "option-pro-monthly");
      if (!option) throw new Error("seeded Pro option is missing");
      const handoff = await createCatalogCheckout({
        option: { ...option, provider: "toss" },
        tenantId: "tenant-test",
        accountId: "account-test",
        orderId: "existing-pro-order",
        idempotencyKey: "existing-pro-order-key",
      });

      expect(handoff.provider).toBe("toss");
      expect(handoff.amountMinor).toBe(2900);
      expect(handoff.currency).toBe("KRW");
      expect(handoff.checkoutContext.billing_auth).toBe(true);
    } finally {
      if (originalClientKey === undefined) delete process.env.TOSS_CLIENT_KEY;
      else process.env.TOSS_CLIENT_KEY = originalClientKey;
    }
  });

  it("upgrades already-migrated USD rows without changing option identity", () => {
    const migration = readFileSync(join(process.cwd(), "drizzle", "0003_toss_catalog_krw.sql"), "utf8");

    expect(migration).toContain("option-starter-monthly");
    expect(migration).toContain("option-starter-yearly");
    expect(migration).toContain("option-pro-monthly");
    expect(migration).toContain("option-pro-yearly");
    expect(migration).toContain('"currency" = \'KRW\'');
  });
});
