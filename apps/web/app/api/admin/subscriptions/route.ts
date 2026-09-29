import { NextRequest, NextResponse } from "next/server";

import { requireAdmin } from "@/lib/admin-guard";
import { listAdminSubscriptions } from "@/lib/pricing/repository";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  try {
    await requireAdmin(request);
    const rows = await listAdminSubscriptions({
      query: request.nextUrl.searchParams.get("q") ?? undefined,
      status: request.nextUrl.searchParams.get("status") ?? undefined,
    });
    return NextResponse.json({ subscriptions: rows.map((row) => ({
      ...row,
      subscription: row.subscription ? {
        id: row.subscription.id,
        pricingOptionId: row.subscription.pricingOptionId,
        provider: row.subscription.provider,
        status: row.subscription.status,
        providerStatus: row.subscription.providerStatus ?? null,
        cancelAtPeriodEnd: row.subscription.cancelAtPeriodEnd,
        currentPeriodStart: row.subscription.currentPeriodStart?.toISOString() ?? null,
        currentPeriodEnd: row.subscription.currentPeriodEnd?.toISOString() ?? null,
        cancelRequestedAt: row.subscription.cancelRequestedAt?.toISOString() ?? null,
        canceledAt: row.subscription.canceledAt?.toISOString() ?? null,
        endedAt: row.subscription.endedAt?.toISOString() ?? null,
        nextBillingAt: row.subscription.nextBillingAt?.toISOString() ?? null,
        graceUntil: row.subscription.graceUntil?.toISOString() ?? null,
        lastPaymentAt: row.subscription.lastPaymentAt?.toISOString() ?? null,
      } : null,
      usage: {
        ...row.usage,
        periodStart: row.usage.periodStart.toISOString(),
        periodEnd: row.usage.periodEnd.toISOString(),
      },
      transitions: row.transitions.map((transition) => ({ ...transition, occurredAt: transition.occurredAt.toISOString() })),
    })) });
  } catch (error) {
    const message = error instanceof Error ? error.message : "admin subscription list unavailable";
    return NextResponse.json({ error: message }, { status: message.includes("authorization") ? 403 : 503 });
  }
}
