import { createPaymentOrder, getPricingOffer } from "@/lib/pricing/repository";
import { settleTossOneTimePayment, settleTossSubscription } from "@/lib/payments/toss-settlement";

process.env.APP_ENV = "test";
delete process.env.DATABASE_URL;
process.env.PAYMENT_SANDBOX = "true";
process.env.TOSS_CLIENT_KEY = "test_ck_example";
process.env.TOSS_SECRET_KEY = "test_sk_example";
process.env.TOSS_API_BASE_URL = "https://toss.test";

const jsonResponse = (body: Record<string, unknown>) => new Response(JSON.stringify(body), {
  status: 200,
  headers: { "content-type": "application/json" },
});

describe("Toss catalog settlement", () => {
  it("exchanges authKey, charges the first subscription period, and is replay-safe", async () => {
    const offer = await getPricingOffer("option-pro-yearly");
    if (!offer) throw new Error("seeded offer is missing");
    const orderId = `subscription-settlement-${crypto.randomUUID()}`;
    await createPaymentOrder({
      id: orderId,
      tenantId: "tenant-test",
      option: { ...offer.option, provider: "toss", currency: "KRW" },
      idempotencyKey: `${orderId}-key`,
      metadata: { customerKey: "customer-settlement", orderName: "AI SaaS annual subscription", interval: "year" },
    });
    const calls: string[] = [];
    const request: typeof fetch = async (url) => {
      calls.push(String(url));
      return calls.length === 1
        ? jsonResponse({ customerKey: "customer-settlement", billingKey: "billing-settlement" })
        : jsonResponse({ orderId, totalAmount: offer.option.amountMinor, status: "DONE", paymentKey: "payment-settlement" });
    };

    const settled = await settleTossSubscription({ customerKey: "customer-settlement", authKey: "auth-settlement", request });
    expect(settled.status).toBe("succeeded");
    expect(settled.externalPaymentRef).toBe("payment-settlement");
    expect(calls).toHaveLength(2);

    await settleTossSubscription({ customerKey: "customer-settlement", authKey: "auth-should-not-be-used", request });
    expect(calls).toHaveLength(2);
  });

  it("confirms a one-time Toss order against the server-owned amount", async () => {
    const offer = await getPricingOffer("option-lifetime-onetime");
    if (!offer) throw new Error("seeded offer is missing");
    const orderId = `one-time-settlement-${crypto.randomUUID()}`;
    await createPaymentOrder({
      id: orderId,
      tenantId: "tenant-test",
      option: { ...offer.option, provider: "toss", currency: "KRW" },
      idempotencyKey: `${orderId}-key`,
    });
    const request: typeof fetch = async () => jsonResponse({ paymentKey: "payment-one-time", orderId, totalAmount: offer.option.amountMinor, status: "DONE" });
    const settled = await settleTossOneTimePayment({ paymentKey: "payment-one-time", orderId, amount: offer.option.amountMinor, request });
    expect(settled.status).toBe("succeeded");
  });
});
