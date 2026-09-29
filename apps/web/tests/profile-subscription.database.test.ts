import { recordTossRenewal, recordTossSubscription, getSubscriptionSummary, recordTokenUsage, cancelSubscriptionAtPeriodEnd, resumeSubscription } from "@/lib/pricing/repository";

const databaseUrl = process.env.PROFILE_SUBSCRIPTION_DATABASE_URL?.trim();
const databaseSuite = databaseUrl ? describe : describe.skip;

databaseSuite("subscription lifecycle database integration", () => {
  const userId = `profile-db-${Date.now()}`;

  beforeAll(async () => {
    process.env.APP_ENV = "test";
    process.env.DATABASE_URL = databaseUrl;
    await recordTossSubscription({
      order: {
        id: `db-order-${userId}`,
        tenantId: "profile-db-tenant",
        userId,
        pricingOptionId: "option-pro-monthly",
        provider: "toss",
        mode: "subscription",
        status: "succeeded",
        externalOrderRef: `db-order-${userId}`,
        externalPaymentRef: `db-payment-${userId}`,
        amountMinor: 2900,
        currency: "KRW",
        idempotencyKey: `db-order-key-${userId}`,
        metadata: { interval: "month", orderName: "Pro" },
      },
      customerKey: `db-customer-${userId}`,
      billingKey: `db-server-only-billing-key`,
    });
  });

  afterAll(() => {
    delete process.env.DATABASE_URL;
  });

  it("uses period snapshots and atomic idempotent usage increments", async () => {
    const initial = await getSubscriptionSummary(userId);
    expect(initial.subscription?.status).toBe("active");
    expect(initial.usage.totalLimit).toBe(1_500_000);

    const first = await recordTokenUsage({ userId, inputTokens: 120, outputTokens: 80, idempotencyKey: `db-usage-${userId}` });
    const duplicate = await recordTokenUsage({ userId, inputTokens: 120, outputTokens: 80, idempotencyKey: `db-usage-${userId}` });
    expect(first.totalUsed).toBe(200);
    expect(duplicate.totalUsed).toBe(200);

    const current = (await getSubscriptionSummary(userId)).subscription;
    if (!current) throw new Error("database subscription fixture was not created");
    const renewalInput = { ...current };
    const results = await Promise.allSettled([
      recordTossRenewal({
        subscription: renewalInput,
        paymentOrder: {
          id: `db-renewal-${userId}`,
          tenantId: "profile-db-tenant",
          userId,
          pricingOptionId: "option-pro-monthly",
          provider: "toss",
          mode: "subscription",
          status: "succeeded",
          externalOrderRef: `db-renewal-${userId}`,
          externalPaymentRef: `db-renewal-payment-${userId}`,
          amountMinor: 2900,
          currency: "KRW",
          idempotencyKey: `db-renewal-key-${userId}`,
          metadata: { interval: "month" },
        },
        paymentRef: `db-renewal-payment-${userId}`,
      }),
      recordTossRenewal({
        subscription: renewalInput,
        paymentOrder: {
          id: `db-renewal-replay-${userId}`,
          tenantId: "profile-db-tenant",
          userId,
          pricingOptionId: "option-pro-monthly",
          provider: "toss",
          mode: "subscription",
          status: "succeeded",
          externalOrderRef: `db-renewal-replay-${userId}`,
          externalPaymentRef: `db-renewal-replay-payment-${userId}`,
          amountMinor: 2900,
          currency: "KRW",
          idempotencyKey: `db-renewal-replay-key-${userId}`,
          metadata: { interval: "month" },
        },
        paymentRef: `db-renewal-replay-payment-${userId}`,
      }),
    ]);
    expect(results.filter((result) => result.status === "fulfilled")).toHaveLength(1);
    expect((await getSubscriptionSummary(userId)).usage.totalUsed).toBe(0);

    const canceled = await cancelSubscriptionAtPeriodEnd(userId, `db-cancel-${userId}`);
    expect(canceled?.status).toBe("cancel_scheduled");
    expect((await getSubscriptionSummary(userId)).access).toBe("paid");
    expect((await resumeSubscription(userId, `db-resume-${userId}`))?.status).toBe("active");
  });
});
