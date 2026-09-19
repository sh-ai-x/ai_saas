import { NextRequest, NextResponse } from "next/server";

import { requireAdmin } from "@/lib/admin-guard";
import { updatePricingPlan } from "@/lib/pricing/repository";

export const dynamic = "force-dynamic";

export async function PATCH(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  try {
    const { actorUserId } = await requireAdmin(request);
    const { id } = await context.params;
    const body = (await request.json()) as { reason?: string; plan?: Parameters<typeof updatePricingPlan>[1] };
    if (!body.plan) throw new Error("plan is required");
    const plan = await updatePricingPlan(id, body.plan, actorUserId, body.reason ?? "");
    if (!plan) return NextResponse.json({ error: "plan not found" }, { status: 404 });
    return NextResponse.json({ plan });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "could not update plan" }, { status: 400 });
  }
}
