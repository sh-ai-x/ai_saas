import { NextRequest, NextResponse } from "next/server";

import { getSafeSession } from "@/lib/auth/session";
import { cancelSubscriptionAtPeriodEnd, getSubscriptionSummary, resumeSubscription } from "@/lib/pricing/repository";

export const dynamic = "force-dynamic";

function serialized(summary: Awaited<ReturnType<typeof getSubscriptionSummary>>) {
  return {
    ...summary,
    subscription: summary.subscription ? {
      id: summary.subscription.id,
      pricingOptionId: summary.subscription.pricingOptionId,
      provider: summary.subscription.provider,
      status: summary.subscription.status,
      providerStatus: summary.subscription.providerStatus ?? null,
      cancelAtPeriodEnd: summary.subscription.cancelAtPeriodEnd,
      currentPeriodStart: summary.subscription.currentPeriodStart.toISOString(),
      currentPeriodEnd: summary.subscription.currentPeriodEnd.toISOString(),
      cancelRequestedAt: summary.subscription.cancelRequestedAt?.toISOString() ?? null,
      canceledAt: summary.subscription.canceledAt?.toISOString() ?? null,
      endedAt: summary.subscription.endedAt?.toISOString() ?? null,
      nextBillingAt: summary.subscription.nextBillingAt?.toISOString() ?? null,
      graceUntil: summary.subscription.graceUntil?.toISOString() ?? null,
      lastPaymentAt: summary.subscription.lastPaymentAt?.toISOString() ?? null,
    } : null,
    usage: {
      ...summary.usage,
      periodStart: summary.usage.periodStart.toISOString(),
      periodEnd: summary.usage.periodEnd.toISOString(),
    },
    transitions: summary.transitions.map((transition) => ({ ...transition, occurredAt: transition.occurredAt.toISOString() })),
  };
}

export async function GET(request: NextRequest) {
  try {
    const session = await getSafeSession(request);
    if (!session) return NextResponse.json({ error: "authentication required" }, { status: 401 });
    return NextResponse.json(serialized(await getSubscriptionSummary(session.user.id)));
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "subscription unavailable" }, { status: 503 });
  }
}

export async function POST(request: NextRequest) {
  try {
    const session = await getSafeSession(request);
    if (!session) return NextResponse.json({ error: "authentication required" }, { status: 401 });
    const body = (await request.json()) as { action?: string; idempotencyKey?: string };
    const idempotencyKey = body.idempotencyKey?.trim() || `profile-${body.action ?? "unknown"}-${session.user.id}-${crypto.randomUUID()}`;
    if (body.action === "cancel") {
      const subscription = await cancelSubscriptionAtPeriodEnd(session.user.id, idempotencyKey);
      if (!subscription) return NextResponse.json({ error: "active subscription not found" }, { status: 404 });
    } else if (body.action === "resume") {
      const subscription = await resumeSubscription(session.user.id, idempotencyKey);
      if (!subscription) return NextResponse.json({ error: "scheduled subscription cancellation not found" }, { status: 404 });
    } else {
      return NextResponse.json({ error: "action must be cancel or resume" }, { status: 400 });
    }
    return NextResponse.json(serialized(await getSubscriptionSummary(session.user.id)));
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "subscription update failed" }, { status: 400 });
  }
}
