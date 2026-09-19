import type { PricingOption, PricingProvider } from "@/lib/pricing/types";

export type CheckoutInput = {
  option: PricingOption;
  tenantId: string;
  accountId: string;
  orderId: string;
  idempotencyKey: string;
};

export type CheckoutHandoff = {
  orderId: string;
  provider: PricingProvider;
  mode: PricingOption["mode"];
  interval: PricingOption["interval"];
  amountMinor: number;
  currency: string;
  testMode: boolean;
  checkoutUrl: string;
  checkoutContext: Record<string, unknown>;
  source: "foundation-api" | "catalog-adapter";
};

const foundationApiUrl = () => process.env.FOUNDATION_API_URL ?? "http://127.0.0.1:8080";

export async function createCatalogCheckout(input: CheckoutInput): Promise<CheckoutHandoff> {
  const provider = input.option.provider;
  const foundation = await tryFoundationCheckout(input);
  if (foundation) return foundation;

  if (provider === "mock") {
    return {
      orderId: input.orderId,
      provider,
      mode: input.option.mode,
      interval: input.option.interval,
      amountMinor: input.option.amountMinor,
      currency: input.option.currency,
      testMode: true,
      checkoutUrl: `/app?checkout=${encodeURIComponent(input.orderId)}`,
      checkoutContext: { adapter: "mock", idempotency_key: input.idempotencyKey },
      source: "catalog-adapter",
    };
  }

  if (provider === "toss") {
    const clientKey = process.env.TOSS_CLIENT_KEY;
    if (!clientKey) throw new Error("TOSS_CLIENT_KEY is required for Toss checkout");
    return {
      orderId: input.orderId,
      provider,
      mode: input.option.mode,
      interval: input.option.interval,
      amountMinor: input.option.amountMinor,
      currency: input.option.currency,
      testMode: true,
      checkoutUrl: "",
      checkoutContext: {
        adapter: "toss",
        client_key: clientKey,
        order_id: input.orderId,
        order_name: input.option.interval === "one_time" ? "AI SaaS one-time plan" : "AI SaaS subscription plan",
        amount: { value: input.option.amountMinor, currency: input.option.currency },
        success_url: `${process.env.APP_BASE_URL ?? "http://127.0.0.1:3000"}/payments/toss/success`,
        fail_url: `${process.env.APP_BASE_URL ?? "http://127.0.0.1:3000"}/payments/toss/fail`,
      },
      source: "catalog-adapter",
    };
  }

  const storeId = process.env.LEMONSQUEEZY_STORE_ID;
  const variantId = input.option.providerProductRef ?? process.env.LEMONSQUEEZY_VARIANT_ID;
  if (!storeId || !variantId) throw new Error("LEMONSQUEEZY_STORE_ID and variant reference are required");
  return {
    orderId: input.orderId,
    provider,
    mode: input.option.mode,
    interval: input.option.interval,
    amountMinor: input.option.amountMinor,
    currency: input.option.currency,
    testMode: true,
    checkoutUrl: `https://checkout.lemonsqueezy.com/buy/${encodeURIComponent(variantId)}`,
    checkoutContext: {
      adapter: "lemon-squeezy",
      store_id: storeId,
      variant_id: variantId,
      order_id: input.orderId,
      checkout_data: { custom: { order_id: input.orderId } },
    },
    source: "catalog-adapter",
  };
}

async function tryFoundationCheckout(input: CheckoutInput): Promise<CheckoutHandoff | null> {
  if (input.option.provider === "mock" && input.option.mode === "subscription") return null;
  try {
    const response = await fetch(`${foundationApiUrl().replace(/\/$/, "")}/v1/billing/orders`, {
      method: "POST",
      headers: { "content-type": "application/json", "x-tenant-id": input.tenantId },
      body: JSON.stringify({
        order_id: input.orderId,
        tenant_id: input.tenantId,
        account_id: input.accountId,
        plan_id: input.option.planId,
        amount_minor: input.option.amountMinor,
        currency: input.option.currency,
        credit_grant: 0,
        idempotency_key: input.idempotencyKey,
      }),
      cache: "no-store",
      signal: AbortSignal.timeout(1200),
    });
    if (!response.ok) return null;
    const body = (await response.json()) as Record<string, unknown>;
    return {
      orderId: input.orderId,
      provider: input.option.provider,
      mode: input.option.mode,
      interval: input.option.interval,
      amountMinor: input.option.amountMinor,
      currency: input.option.currency,
      testMode: Boolean(body.test_mode ?? true),
      checkoutUrl: String(body.checkout_url ?? ""),
      checkoutContext: (body.checkout_context as Record<string, unknown> | undefined) ?? {},
      source: "foundation-api",
    };
  } catch {
    return null;
  }
}
