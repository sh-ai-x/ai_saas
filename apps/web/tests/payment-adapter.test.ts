import assert from "node:assert/strict";
import { after, before, describe, it } from "node:test";

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

  before(() => {
    process.env.TOSS_CLIENT_KEY = "test_toss_client_key";
    process.env.LEMONSQUEEZY_STORE_ID = "test-store";
    process.env.LEMONSQUEEZY_VARIANT_ID = "test-variant";
  });

  after(() => {
    if (originalTossKey === undefined) delete process.env.TOSS_CLIENT_KEY;
    else process.env.TOSS_CLIENT_KEY = originalTossKey;
    if (originalStoreId === undefined) delete process.env.LEMONSQUEEZY_STORE_ID;
    else process.env.LEMONSQUEEZY_STORE_ID = originalStoreId;
    if (originalVariantId === undefined) delete process.env.LEMONSQUEEZY_VARIANT_ID;
    else process.env.LEMONSQUEEZY_VARIANT_ID = originalVariantId;
  });

  it("creates a mock subscription handoff without exposing provider secrets", async () => {
    const handoff = await createCatalogCheckout(input(option()));
    assert.equal(handoff.provider, "mock");
    assert.equal(handoff.mode, "subscription");
    assert.equal(handoff.amountMinor, 29000);
    assert.equal(handoff.testMode, true);
    assert.match(handoff.checkoutUrl, /^\/app\?checkout=/);
    assert.equal("TOSS_CLIENT_KEY" in handoff.checkoutContext, false);
  });

  it("creates a Toss client-side context without returning secret keys", async () => {
    const handoff = await createCatalogCheckout(input(option({ provider: "toss" })));
    assert.equal(handoff.provider, "toss");
    assert.equal(handoff.checkoutUrl, "");
    assert.equal(handoff.checkoutContext.adapter, "toss");
    assert.equal(handoff.checkoutContext.client_key, "test_toss_client_key");
    assert.equal("secret_key" in handoff.checkoutContext, false);
    assert.equal(handoff.checkoutContext.amount instanceof Object, true);
  });

  it("creates a Lemon Squeezy sandbox checkout URL with custom order context", async () => {
    const handoff = await createCatalogCheckout(input(option({ provider: "lemon-squeezy" })));
    assert.equal(handoff.provider, "lemon-squeezy");
    assert.equal(handoff.checkoutUrl, "https://checkout.lemonsqueezy.com/buy/test-variant");
    assert.deepEqual(handoff.checkoutContext.checkout_data, { custom: { order_id: "order-test" } });
    assert.equal(handoff.testMode, true);
  });

  it("rejects live-provider checkout when required configuration is absent", async () => {
    delete process.env.TOSS_CLIENT_KEY;
    await assert.rejects(
      () => createCatalogCheckout(input(option({ provider: "toss" }))),
      /TOSS_CLIENT_KEY is required/,
    );

    delete process.env.LEMONSQUEEZY_STORE_ID;
    await assert.rejects(
      () => createCatalogCheckout(input(option({ provider: "lemon-squeezy" }))),
      /LEMONSQUEEZY_STORE_ID and variant reference are required/,
    );
  });
});
