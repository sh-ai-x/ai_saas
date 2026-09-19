import assert from "node:assert/strict";
import { after, before, describe, it } from "node:test";

import {
  createPricingPlan,
  getBillingPolicy,
  listPricingCatalog,
  listProviderSettings,
  setBillingMode,
  updateProviderSetting,
} from "@/lib/pricing/repository";

process.env.APP_ENV = "test";
delete process.env.DATABASE_URL;

const subscriptionProYearly = () =>
  listPricingCatalog(true).then((plans) =>
    plans.flatMap((plan) => plan.options).find((option) => option.interval === "year" && option.amountMinor === 29000),
  );

describe("pricing repository invariants", () => {
  before(async () => {
    await setBillingMode("subscription", "test-suite", "reset before pricing repository tests");
  });

  after(async () => {
    await setBillingMode("subscription", "test-suite", "restore subscription catalog after pricing repository tests");
  });

  it("publishes only the globally selected billing mode", async () => {
    const subscription = await listPricingCatalog(true);
    assert.equal((await getBillingPolicy()).billingMode, "subscription");
    assert.ok(subscription.length > 0);
    assert.ok(subscription.every((plan) => plan.billingMode === "subscription"));
    assert.ok(subscription.every((plan) => plan.options.every((option) => option.mode === "subscription")));
    assert.equal((await subscriptionProYearly())?.amountMinor, 29000);
    assert.equal(subscription.flatMap((plan) => plan.options).some((option) => option.amountMinor === 7900), false);

    await setBillingMode("one_time", "test-suite", "verify exclusive one-time catalog");
    const oneTime = await listPricingCatalog(true);
    assert.ok(oneTime.length > 0);
    assert.ok(oneTime.every((plan) => plan.billingMode === "one_time"));
    assert.deepEqual(oneTime.flatMap((plan) => plan.options).map((option) => option.interval), ["one_time"]);
    assert.equal(oneTime.flatMap((plan) => plan.options)[0]?.amountMinor, 7900);
    assert.equal(oneTime.flatMap((plan) => plan.options).some((option) => option.interval === "year"), false);
  });

  it("requires an audit reason for policy changes", async () => {
    await assert.rejects(
      () => setBillingMode("one_time", "test-suite", ""),
      /reason is required/,
    );
  });

  it("rejects plans and options that do not match the active mode", async () => {
    await setBillingMode("subscription", "test-suite", "test mode compatibility");
    await assert.rejects(
      () => createPricingPlan({
        code: "invalid-one-time",
        name: "Invalid one-time plan",
        billingMode: "one_time",
        options: [],
      }, "test-suite", "should reject mode mismatch"),
      /must match active catalog mode/,
    );

    await assert.rejects(
      () => createPricingPlan({
        code: "invalid-interval",
        name: "Invalid interval plan",
        billingMode: "subscription",
        options: [{ mode: "subscription", interval: "one_time", provider: "mock", currency: "USD", amountMinor: 100 }],
      }, "test-suite", "should reject invalid interval"),
      /subscription options must use interval month or year/,
    );

    await assert.rejects(
      () => createPricingPlan({
        code: "invalid-amount",
        name: "Invalid amount plan",
        billingMode: "subscription",
        options: [{ mode: "subscription", interval: "month", provider: "mock", currency: "USD", amountMinor: 0 }],
      }, "test-suite", "should reject invalid amount"),
      /amountMinor must be a positive integer/,
    );
  });

  it("prevents two live payment providers from being enabled", async () => {
    const initial = await listProviderSettings();
    const toss = initial.find((setting) => setting.provider === "toss");
    const lemon = initial.find((setting) => setting.provider === "lemon-squeezy");
    assert.ok(toss);
    assert.ok(lemon);

    await updateProviderSetting("toss", { enabled: true, sandbox: false, publicConfig: {}, secretRef: "test/toss" }, "test-suite", "enable one live provider");
    await assert.rejects(
      () => updateProviderSetting("lemon-squeezy", { enabled: true, sandbox: false, publicConfig: {}, secretRef: "test/lemon" }, "test-suite", "reject live provider conflict"),
      /only one live provider may be enabled/,
    );
    await updateProviderSetting("toss", { enabled: false, sandbox: true, publicConfig: {}, secretRef: null }, "test-suite", "restore provider test state");
  });
});
