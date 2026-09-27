import {
  cancelSubscriptionAtPeriodEnd,
  getSubscriptionSummary,
  recordTokenUsage,
  recordTossSubscription,
  resumeSubscription,
} from "@/lib/pricing/repository";

process.env.APP_ENV = "test";
delete process.env.DATABASE_URL;

describe("profile subscription lifecycle", () => {
  const userId = `profile-test-${Date.now()}`;

  beforeAll(async () => {
    const start = new Date();
    const end = new Date(start);
    end.setUTCMonth(end.getUTCMonth() + 1);
    await recordTossSubscription({
      order: {
        id: `order-${userId}`,
        tenantId: "tenant-test",
        userId,
        pricingOptionId: "option-pro-monthly",
        provider: "toss",
        mode: "subscription",
        status: "succeeded",
        externalOrderRef: `order-${userId}`,
        externalPaymentRef: `payment-${userId}`,
        amountMinor: 2900,
        currency: "KRW",
        idempotencyKey: `order-key-${userId}`,
        metadata: { interval: "month", orderName: "Pro" },
      },
      customerKey: `customer-${userId}`,
      billingKey: `billing-${userId}`,
    });
  });

  it("keeps paid access while cancellation is scheduled and supports resume", async () => {
    const active = await getSubscriptionSummary(userId);
    expect(active.subscription?.status).toBe("active");
    expect(active.access).toBe("paid");

    const canceled = await cancelSubscriptionAtPeriodEnd(userId, `cancel-${userId}`);
    expect(canceled?.status).toBe("cancel_scheduled");
    expect(canceled?.cancelAtPeriodEnd).toBe(true);
    expect((await getSubscriptionSummary(userId)).access).toBe("paid");

    const resumed = await resumeSubscription(userId, `resume-${userId}`);
    expect(resumed?.status).toBe("active");
    expect(resumed?.cancelAtPeriodEnd).toBe(false);
  });

  it("records token usage idempotently for the profile projection", async () => {
    const first = await recordTokenUsage({ userId, inputTokens: 12, outputTokens: 8, idempotencyKey: `usage-${userId}` });
    const duplicate = await recordTokenUsage({ userId, inputTokens: 12, outputTokens: 8, idempotencyKey: `usage-${userId}` });
    expect(first.totalUsed).toBe(20);
    expect(duplicate.totalUsed).toBe(20);
    expect((await getSubscriptionSummary(userId)).usage.totalUsed).toBe(20);
  });
});
