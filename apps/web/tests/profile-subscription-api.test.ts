import { NextRequest } from "next/server";

import { GET as getAdminSubscriptions } from "@/app/api/admin/subscriptions/route";
import { POST as postRenewals } from "@/app/api/internal/billing/renewals/route";
import { GET as getProfileSubscription, POST as postProfileSubscription } from "@/app/api/profile/subscription/route";
import { localDemoSession, localMemberSession, localSessionCookie } from "@/lib/auth/local-session";
import { recordTossSubscription } from "@/lib/pricing/repository";

process.env.APP_ENV = "test";
delete process.env.DATABASE_URL;
delete process.env.BETTER_AUTH_SECRET;
delete process.env.BETTER_AUTH_URL;
delete process.env.GOOGLE_CLIENT_ID;
delete process.env.GOOGLE_CLIENT_SECRET;

function request(path: string, sessionId?: string, init: ConstructorParameters<typeof NextRequest>[1] = {}) {
  return new NextRequest(`https://unit.test${path}`, {
    ...init,
    headers: {
      ...(sessionId ? { cookie: `${localSessionCookie}=${sessionId}` } : {}),
      ...(init.headers ?? {}),
    },
  });
}

function jsonRequest(path: string, body: unknown, sessionId?: string) {
  return request(path, sessionId, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function bodyOf(response: Response) {
  return response.json() as Promise<Record<string, any>>;
}

describe("subscription API authorization and response boundaries", () => {
  beforeAll(async () => {
    await recordTossSubscription({
      order: {
        id: `api-profile-order-${Date.now()}`,
        tenantId: "tenant-test",
        userId: localDemoSession.user.id,
        pricingOptionId: "option-pro-monthly",
        provider: "toss",
        mode: "subscription",
        status: "succeeded",
        externalOrderRef: "api-profile-order",
        externalPaymentRef: "api-profile-payment",
        amountMinor: 2900,
        currency: "KRW",
        idempotencyKey: `api-profile-order-key-${Date.now()}`,
        metadata: { interval: "month", orderName: "Pro" },
      },
      customerKey: "api-profile-customer",
      billingKey: "server-only-billing-key",
    });
  });

  it("requires authentication for the profile endpoint", async () => {
    const response = await getProfileSubscription(request("/api/profile/subscription"));
    expect(response.status).toBe(401);
    expect((await bodyOf(response)).error).toBe("authentication required");
  });

  it("supports cancel/resume idempotently and never serializes billing credentials", async () => {
    const initial = await getProfileSubscription(request("/api/profile/subscription", localDemoSession.session.id));
    expect(initial.status).toBe(200);
    const initialBody = await bodyOf(initial);
    expect(initialBody.subscription.status).toBe("active");
    expect(initialBody.subscription.metadata).toBeUndefined();
    expect(JSON.stringify(initialBody)).not.toContain("server-only-billing-key");

    const cancel = await postProfileSubscription(jsonRequest(
      "/api/profile/subscription",
      { action: "cancel", idempotencyKey: "api-profile-cancel-key" },
      localDemoSession.session.id,
    ));
    expect(cancel.status).toBe(200);
    const canceledBody = await bodyOf(cancel);
    expect(canceledBody.subscription.status).toBe("cancel_scheduled");
    expect(canceledBody.access).toBe("paid");
    expect(canceledBody.subscription.nextBillingAt).toBeTruthy();

    const duplicateCancel = await postProfileSubscription(jsonRequest(
      "/api/profile/subscription",
      { action: "cancel", idempotencyKey: "api-profile-cancel-key" },
      localDemoSession.session.id,
    ));
    expect(duplicateCancel.status).toBe(200);
    expect((await bodyOf(duplicateCancel)).subscription.status).toBe("cancel_scheduled");

    const resume = await postProfileSubscription(jsonRequest(
      "/api/profile/subscription",
      { action: "resume", idempotencyKey: "api-profile-resume-key" },
      localDemoSession.session.id,
    ));
    expect(resume.status).toBe(200);
    expect((await bodyOf(resume)).subscription.status).toBe("active");
  });

  it("enforces admin authorization and scopes the directory response", async () => {
    const denied = await getAdminSubscriptions(request("/api/admin/subscriptions", localMemberSession.session.id));
    expect(denied.status).toBe(403);

    const allowed = await getAdminSubscriptions(request("/api/admin/subscriptions", localDemoSession.session.id));
    expect(allowed.status).toBe(200);
    const body = await bodyOf(allowed);
    const row = body.subscriptions.find((candidate: any) => candidate.user.id === localDemoSession.user.id);
    expect(row).toBeTruthy();
    expect(row.subscription.metadata).toBeUndefined();
    expect(JSON.stringify(body)).not.toContain("server-only-billing-key");
  });

  it("requires the billing scheduler secret", async () => {
    process.env.BILLING_CRON_SECRET = "api-renewal-secret";
    const denied = await postRenewals(request("/api/internal/billing/renewals"));
    expect(denied.status).toBe(401);

    const allowed = await postRenewals(request("/api/internal/billing/renewals", undefined, {
      method: "POST",
      headers: { authorization: "Bearer api-renewal-secret" },
    }));
    expect(allowed.status).toBe(200);
    expect((await bodyOf(allowed)).processed).toBeGreaterThanOrEqual(0);
    delete process.env.BILLING_CRON_SECRET;
  });
});
