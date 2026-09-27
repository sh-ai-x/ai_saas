import {
  cancelSubscriptionAtPeriodEnd,
  getSubscriptionSummary,
  listDueTossSubscriptions,
  recordTokenUsage,
  recordTossRenewal,
  recordTossRenewalFailure,
  recordTossSubscription,
  expireEndedSubscriptions,
  resumeSubscription,
} from "@/lib/pricing/repository";

process.env.APP_ENV = "test";
delete process.env.DATABASE_URL;

describe("profile subscription lifecycle", () => {
  const userId = `profile-test-${Date.now()}`;

  async function seedSubscription(forUserId: string) {
    await recordTossSubscription({
      order: {
        id: `order-${forUserId}`,
        tenantId: "tenant-test",
        userId: forUserId,
        pricingOptionId: "option-pro-monthly",
        provider: "toss",
        mode: "subscription",
        status: "succeeded",
        externalOrderRef: `order-${forUserId}`,
        externalPaymentRef: `payment-${forUserId}`,
        amountMinor: 2900,
        currency: "KRW",
        idempotencyKey: `order-key-${forUserId}`,
        metadata: { interval: "month", orderName: "Pro" },
      },
      customerKey: `customer-${forUserId}`,
      billingKey: `billing-${forUserId}`,
    });
  }

  beforeAll(async () => {
    await seedSubscription(userId);
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

  it("resets usage only after a successful renewal and rejects a stale retry", async () => {
    const renewalUserId = `profile-renewal-${Date.now()}`;
    await seedSubscription(renewalUserId);
    const before = await getSubscriptionSummary(renewalUserId);
    await recordTokenUsage({ userId: renewalUserId, inputTokens: 100, outputTokens: 50, idempotencyKey: `usage-${renewalUserId}` });
    const staleSubscription = { ...before.subscription!, currentPeriodEnd: new Date(Date.now() - 1_000), version: before.subscription!.version };
    const renewed = await recordTossRenewal({
      subscription: staleSubscription,
      paymentOrder: {
        id: `renewal-order-${renewalUserId}`,
        tenantId: "tenant-test",
        userId: renewalUserId,
        pricingOptionId: "option-pro-monthly",
        provider: "toss",
        mode: "subscription",
        status: "succeeded",
        externalOrderRef: `renewal-order-${renewalUserId}`,
        externalPaymentRef: `renewal-payment-${renewalUserId}`,
        amountMinor: 2900,
        currency: "KRW",
        idempotencyKey: `renewal-key-${renewalUserId}`,
        metadata: { interval: "month" },
      },
      paymentRef: `renewal-payment-${renewalUserId}`,
    });

    expect(renewed.status).toBe("active");
    expect((await getSubscriptionSummary(renewalUserId)).usage.totalUsed).toBe(0);
    await expect(recordTossRenewal({
      subscription: staleSubscription,
      paymentOrder: {
        id: `duplicate-renewal-order-${renewalUserId}`,
        tenantId: "tenant-test",
        userId: renewalUserId,
        pricingOptionId: "option-pro-monthly",
        provider: "toss",
        mode: "subscription",
        status: "succeeded",
        externalOrderRef: `duplicate-renewal-order-${renewalUserId}`,
        externalPaymentRef: null,
        amountMinor: 2900,
        currency: "KRW",
        idempotencyKey: `duplicate-renewal-key-${renewalUserId}`,
        metadata: { interval: "month" },
      },
      paymentRef: "duplicate",
    })).rejects.toThrow(/version conflict/);
  });

  it("keeps a failed renewal in grace, retries before expiry, then expires", async () => {
    const failureUserId = `profile-failure-${Date.now()}`;
    await seedSubscription(failureUserId);
    const current = (await getSubscriptionSummary(failureUserId)).subscription;
    if (!current) throw new Error("subscription fixture was not created");

    const failed = await recordTossRenewalFailure(current, "card declined");
    expect(failed.status).toBe("past_due");
    expect(failed.graceUntil && failed.graceUntil.getTime()).toBeGreaterThan(Date.now());
    expect((await getSubscriptionSummary(failureUserId)).access).toBe("grace");

    const retryCandidates = await listDueTossSubscriptions(new Date(Date.now() + 25 * 60 * 60 * 1000));
    expect(retryCandidates.some((candidate) => candidate.id === failed.id)).toBe(true);

    const expired = await expireEndedSubscriptions(new Date(Date.now() + 73 * 60 * 60 * 1000));
    expect(expired).toBeGreaterThanOrEqual(1);
    expect((await getSubscriptionSummary(failureUserId)).access).toBe("expired");
  });
});
