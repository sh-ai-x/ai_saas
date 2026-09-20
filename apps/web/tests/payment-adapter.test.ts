import { createCatalogCheckout } from "@/lib/payments/catalog-checkout";
import type { PricingOption } from "@/lib/pricing/types";

process.env.APP_ENV = "test";
process.env.FOUNDATION_API_URL = "http://127.0.0.1:9";

const option = (overrides: Partial<PricingOption> = {}): PricingOption => ({
  id: "option-test",
  planId: "plan-test",
  mode: "subscription",
  interval: "year",
  provider: "mock",
  currency: "USD",
  amountMinor: 29000,
  compareAtAmountMinor: null,
  providerProductRef: null,
  providerPriceRef: null,
  active: true,
  ...overrides,
});

const input = (pricingOption: PricingOption) => ({
  option: pricingOption,
  tenantId: "tenant-test",
  accountId: "account-test",
  orderId: "order-test",
  idempotencyKey: "idempotency-test",
});

describe("payment adapter contracts", () => {
  const originalTossKey = process.env.TOSS_CLIENT_KEY;
  const originalStoreId = process.env.LEMONSQUEEZY_STORE_ID;
  const originalVariantId = process.env.LEMONSQUEEZY_VARIANT_ID;

  beforeAll(() => {
    process.env.TOSS_CLIENT_KEY = "test_toss_client_key";
    process.env.LEMONSQUEEZY_STORE_ID = "test-store";
    process.env.LEMONSQUEEZY_VARIANT_ID = "test-variant";
  });

  afterAll(() => {
    if (originalTossKey === undefined) delete process.env.TOSS_CLIENT_KEY;
    else process.env.TOSS_CLIENT_KEY = originalTossKey;
    if (originalStoreId === undefined) delete process.env.LEMONSQUEEZY_STORE_ID;
    else process.env.LEMONSQUEEZY_STORE_ID = originalStoreId;
    if (originalVariantId === undefined) delete process.env.LEMONSQUEEZY_VARIANT_ID;
    else process.env.LEMONSQUEEZY_VARIANT_ID = originalVariantId;
  });

  it("creates a mock subscription handoff without exposing provider secrets", async () => {
    const handoff = await createCatalogCheckout(input(option()));
    expect(handoff.provider).toBe("mock");
    expect(handoff.mode).toBe("subscription");
    expect(handoff.amountMinor).toBe(29000);
    expect(handoff.testMode).toBe(true);
    expect(handoff.checkoutUrl).toMatch(/^\/app\?checkout=/);
    expect("TOSS_CLIENT_KEY" in handoff.checkoutContext).toBe(false);
  });

  it("creates a Toss client-side context without returning secret keys", async () => {
    const handoff = await createCatalogCheckout(input(option({ provider: "toss", currency: "KRW" })));
    expect(handoff.provider).toBe("toss");
    expect(handoff.checkoutUrl).toBe("");
    expect(handoff.checkoutContext.adapter).toBe("toss");
    expect(handoff.checkoutContext.client_key).toBe("test_toss_client_key");
    expect(handoff.checkoutContext.billing_auth).toBe(true);
    expect(handoff.checkoutContext.customer_key).toMatch(/^customer-/);
    expect("secret_key" in handoff.checkoutContext).toBe(false);
    expect(handoff.checkoutContext.amount).toBeInstanceOf(Object);
  });

  it("keeps one-time Toss checkout on the payment authorization path", async () => {
    const handoff = await createCatalogCheckout(input(option({ provider: "toss", mode: "one_time", interval: "one_time", currency: "KRW" })));
    expect(handoff.checkoutContext.billing_auth).toBe(false);
    expect(handoff.checkoutContext.success_url).toContain("/payments/toss/success");
  });

  it("rejects Toss options that are not denominated in KRW", async () => {
    await expect(createCatalogCheckout(input(option({ provider: "toss", currency: "USD" })))).rejects.toThrow(/currency must be KRW/);
  });

  it("creates a Lemon Squeezy sandbox checkout URL with custom order context", async () => {
    const handoff = await createCatalogCheckout(input(option({ provider: "lemon-squeezy" })));
    expect(handoff.provider).toBe("lemon-squeezy");
    expect(handoff.checkoutUrl).toBe("https://checkout.lemonsqueezy.com/buy/test-variant");
    expect(handoff.checkoutContext.checkout_data).toEqual({ custom: { order_id: "order-test" } });
    expect(handoff.testMode).toBe(true);
  });

  it("rejects live-provider checkout when required configuration is absent", async () => {
    delete process.env.TOSS_CLIENT_KEY;
    await expect(createCatalogCheckout(input(option({ provider: "toss" })))).rejects.toThrow(/TOSS_CLIENT_KEY is required/);

    delete process.env.LEMONSQUEEZY_STORE_ID;
    await expect(createCatalogCheckout(input(option({ provider: "lemon-squeezy" })))).rejects.toThrow(/LEMONSQUEEZY_STORE_ID and variant reference are required/);
  });
});
