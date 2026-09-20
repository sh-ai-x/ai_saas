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
  beforeAll(async () => {
    await setBillingMode("subscription", "test-suite", "reset before pricing repository tests");
  });

  afterAll(async () => {
    await setBillingMode("subscription", "test-suite", "restore subscription catalog after pricing repository tests");
  });

  it("publishes only the globally selected billing mode", async () => {
    const subscription = await listPricingCatalog(true);
    expect((await getBillingPolicy()).billingMode).toBe("subscription");
    expect(subscription.length).toBeGreaterThan(0);
    expect(subscription.every((plan) => plan.billingMode === "subscription")).toBe(true);
    expect(subscription.every((plan) => plan.options.every((option) => option.mode === "subscription"))).toBe(true);
    expect((await subscriptionProYearly())?.amountMinor).toBe(29000);
    expect(subscription.flatMap((plan) => plan.options).some((option) => option.amountMinor === 7900)).toBe(false);

    await setBillingMode("one_time", "test-suite", "verify exclusive one-time catalog");
    const oneTime = await listPricingCatalog(true);
    expect(oneTime.length).toBeGreaterThan(0);
    expect(oneTime.every((plan) => plan.billingMode === "one_time")).toBe(true);
    expect(oneTime.flatMap((plan) => plan.options).map((option) => option.interval)).toEqual(["one_time"]);
    expect(oneTime.flatMap((plan) => plan.options)[0]?.amountMinor).toBe(7900);
    expect(oneTime.flatMap((plan) => plan.options).some((option) => option.interval === "year")).toBe(false);
  });

  it("requires an audit reason for policy changes", async () => {
    await expect(setBillingMode("one_time", "test-suite", "")).rejects.toThrow(/reason is required/);
  });

  it("rejects plans and options that do not match the active mode", async () => {
    await setBillingMode("subscription", "test-suite", "test mode compatibility");
    await expect(createPricingPlan({
        code: "invalid-one-time",
        name: "Invalid one-time plan",
        billingMode: "one_time",
        options: [],
      }, "test-suite", "should reject mode mismatch")).rejects.toThrow(/must match active catalog mode/);

    await expect(createPricingPlan({
        code: "invalid-interval",
        name: "Invalid interval plan",
        billingMode: "subscription",
        options: [{ mode: "subscription", interval: "one_time", provider: "mock", currency: "USD", amountMinor: 100 }],
      }, "test-suite", "should reject invalid interval")).rejects.toThrow(/subscription options must use interval month or year/);

    await expect(createPricingPlan({
        code: "invalid-amount",
        name: "Invalid amount plan",
        billingMode: "subscription",
        options: [{ mode: "subscription", interval: "month", provider: "mock", currency: "USD", amountMinor: 0 }],
      }, "test-suite", "should reject invalid amount")).rejects.toThrow(/amountMinor must be a positive integer/);
  });

  it("prevents two live payment providers from being enabled", async () => {
    const initial = await listProviderSettings();
    const toss = initial.find((setting) => setting.provider === "toss");
    const lemon = initial.find((setting) => setting.provider === "lemon-squeezy");
    expect(toss).toBeTruthy();
    expect(lemon).toBeTruthy();
    if (!toss || !lemon) throw new Error("expected seeded provider settings");

    await updateProviderSetting("toss", { enabled: true, sandbox: false, publicConfig: {}, secretRef: "test/toss" }, "test-suite", "enable one live provider");
    await expect(updateProviderSetting("lemon-squeezy", { enabled: true, sandbox: false, publicConfig: {}, secretRef: "test/lemon" }, "test-suite", "reject live provider conflict")).rejects.toThrow(/only one live provider may be enabled/);
    await updateProviderSetting("toss", { enabled: false, sandbox: true, publicConfig: {}, secretRef: null }, "test-suite", "restore provider test state");
  });
});
