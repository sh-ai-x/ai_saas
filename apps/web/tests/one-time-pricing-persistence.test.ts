import assert from "node:assert/strict";

import {
  getBillingPolicy,
  listPricingCatalog,
  setBillingMode,
  updatePricingPlan,
} from "@/lib/pricing/repository";
import type { PricingPlan, PricingPlanInput } from "@/lib/pricing/types";

process.env.APP_ENV = "test";
delete process.env.DATABASE_URL;

const withAmountMinor = (plan: PricingPlan, amountMinor: number): PricingPlanInput => ({
  tenantId: plan.tenantId,
  code: plan.code,
  name: plan.name,
  description: plan.description,
  billingMode: plan.billingMode,
  active: plan.active,
  isDefault: plan.isDefault,
  displayOrder: plan.displayOrder,
  features: plan.features,
  quotas: plan.quotas,
  options: plan.options.map((option) => ({ ...option, amountMinor })),
});

describe("one-time pricing persistence", () => {
  beforeAll(async () => {
    await setBillingMode("subscription", "one-time-pricing-test", "reset one-time pricing fixture");
  });

  afterAll(async () => {
    // Always restore the subscription policy first so a failed assertion in
    // the test body does not leave `setBillingMode("one_time", ...)` standing
    // for the sibling pricing-repository suite.
    await setBillingMode("subscription", "one-time-pricing-test", "restore subscription policy");
    const lifetime = (await listPricingCatalog(false)).find((plan) => plan.id === "plan-lifetime");
    if (!lifetime) return;
    await updatePricingPlan("plan-lifetime", withAmountMinor(lifetime, 7900), "one-time-pricing-test", "restore one-time pricing fixture");
  });

  it("saves a one-time price before the one-time billing policy is active", async () => {
    const lifetime = (await listPricingCatalog(false)).find((plan) => plan.id === "plan-lifetime");
    assert.ok(lifetime, "seed must contain the lifetime plan");
    assert.equal((await getBillingPolicy()).billingMode, "subscription");

    const updated = await updatePricingPlan("plan-lifetime", withAmountMinor(lifetime, 12345), "one-time-pricing-test", "save one-time price before policy activation");

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
