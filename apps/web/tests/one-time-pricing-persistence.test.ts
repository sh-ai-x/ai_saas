import assert from "node:assert/strict";

import {
  getBillingPolicy,
  listPricingCatalog,
  setBillingMode,
  updatePricingPlan,
} from "@/lib/pricing/repository";

process.env.APP_ENV = "test";
delete process.env.DATABASE_URL;

describe("one-time pricing persistence", () => {
  before(async () => {
    await setBillingMode("subscription", "one-time-pricing-test", "reset one-time pricing fixture");
  });

  after(async () => {
    const lifetime = (await listPricingCatalog(false)).find((plan) => plan.id === "plan-lifetime");
    assert.ok(lifetime, "seed must contain the lifetime plan");
    await updatePricingPlan("plan-lifetime", {
      tenantId: lifetime.tenantId,
      code: lifetime.code,
      name: lifetime.name,
      description: lifetime.description,
      billingMode: lifetime.billingMode,
      active: lifetime.active,
      isDefault: lifetime.isDefault,
      displayOrder: lifetime.displayOrder,
      features: lifetime.features,
      quotas: lifetime.quotas,
      options: lifetime.options.map((option) => ({ ...option, amountMinor: 7900 })),
    }, "one-time-pricing-test", "restore one-time pricing fixture");
    await setBillingMode("subscription", "one-time-pricing-test", "restore subscription policy");
  });

  it("saves a one-time price before the one-time billing policy is active", async () => {
    const lifetime = (await listPricingCatalog(false)).find((plan) => plan.id === "plan-lifetime");
    assert.ok(lifetime, "seed must contain the lifetime plan");
    assert.equal((await getBillingPolicy()).billingMode, "subscription");

    const updated = await updatePricingPlan("plan-lifetime", {
      tenantId: lifetime.tenantId,
      code: lifetime.code,
      name: lifetime.name,
      description: lifetime.description,
      billingMode: lifetime.billingMode,
      active: lifetime.active,
      isDefault: lifetime.isDefault,
      displayOrder: lifetime.displayOrder,
      features: lifetime.features,
      quotas: lifetime.quotas,
      options: lifetime.options.map((option) => ({ ...option, amountMinor: 12345 })),
    }, "one-time-pricing-test", "save one-time price before policy activation");

    assert.equal(updated?.options[0]?.amountMinor, 12345);
    const stored = (await listPricingCatalog(false)).find((plan) => plan.id === "plan-lifetime");
    assert.equal(stored?.options[0]?.amountMinor, 12345);

    const subscriptionCatalog = await listPricingCatalog(true);
    assert.equal(subscriptionCatalog.some((plan) => plan.id === "plan-lifetime"), false);

    await setBillingMode("one_time", "one-time-pricing-test", "publish saved one-time price");
    const oneTimeCatalog = await listPricingCatalog(true);
    assert.equal(oneTimeCatalog.find((plan) => plan.id === "plan-lifetime")?.options[0]?.amountMinor, 12345);
  });
});
