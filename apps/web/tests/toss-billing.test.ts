import { approveTossBilling, confirmTossPayment, issueTossBillingKey } from "@/lib/payments/toss-billing";

process.env.APP_ENV = "test";
process.env.PAYMENT_SANDBOX = "true";
process.env.TOSS_CLIENT_KEY = "test_ck_example";
process.env.TOSS_SECRET_KEY = "test_sk_example";
process.env.TOSS_API_BASE_URL = "https://toss.test";

const response = (body: Record<string, unknown>, status = 200) => new Response(JSON.stringify(body), {
  status,
  headers: { "content-type": "application/json" },
});

describe("Toss server billing adapter", () => {
  it("issues a billing key with the secret key and validates customer identity", async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    const request: typeof fetch = async (url, init) => {
      calls.push({ url: String(url), init });
      return response({ customerKey: "customer-1", billingKey: "billing-1" });
    };

    await expect(issueTossBillingKey({ authKey: "auth-1", customerKey: "customer-1" }, request)).resolves.toEqual({
      billingKey: "billing-1",
      customerKey: "customer-1",
    });
    expect(calls[0]?.url).toBe("https://toss.test/v1/billing/authorizations/issue");
    expect(calls[0]?.init?.headers).toEqual(expect.objectContaining({
      Authorization: `Basic ${Buffer.from("test_sk_example:").toString("base64")}`,
    }));
  });

  it("approves recurring billing with an idempotency key and validates the amount", async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    const request: typeof fetch = async (url, init) => {
      calls.push({ url: String(url), init });
      return response({ orderId: "order-1", totalAmount: 29000, status: "DONE", paymentKey: "pay-1" });
    };

    await expect(approveTossBilling({
      billingKey: "billing/1",
      customerKey: "customer-1",
      orderId: "order-1",
      orderName: "AI SaaS subscription",
      amount: 29000,
      idempotencyKey: "order-1-key",
    }, request)).resolves.toEqual(expect.objectContaining({ orderId: "order-1", status: "DONE" }));
    expect(calls[0]?.url).toBe("https://toss.test/v1/billing/billing%2F1");
    expect(calls[0]?.init?.headers).toEqual(expect.objectContaining({ "Idempotency-Key": "order-1-key" }));
  });

  it("confirms a one-time payment only when Toss returns the pending order amount", async () => {
    const request: typeof fetch = async (_url, init) => {
      expect(JSON.parse(String(init?.body))).toEqual({ paymentKey: "pay-1", orderId: "order-1", amount: 7900 });
      return response({ paymentKey: "pay-1", orderId: "order-1", totalAmount: 7900, status: "DONE" });
    };

    await expect(confirmTossPayment({ paymentKey: "pay-1", orderId: "order-1", amount: 7900, idempotencyKey: "order-1-key" }, request))
      .resolves.toEqual(expect.objectContaining({ orderId: "order-1", status: "DONE" }));
  });

  it("fails closed on a mismatched Toss confirmation amount", async () => {
    const request: typeof fetch = async () => response({ paymentKey: "pay-1", orderId: "order-1", totalAmount: 1, status: "DONE" });
    await expect(confirmTossPayment({ paymentKey: "pay-1", orderId: "order-1", amount: 7900, idempotencyKey: "order-1-key" }, request))
      .rejects.toThrow(/does not match/);
  });
});
