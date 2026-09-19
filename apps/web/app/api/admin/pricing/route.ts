import { NextRequest, NextResponse } from "next/server";

import { requireAdmin } from "@/lib/admin-guard";
import { createPricingPlan, listPricingCatalog } from "@/lib/pricing/repository";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  try {
    await requireAdmin(request);
    return NextResponse.json({ plans: await listPricingCatalog(false) });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "admin authorization required" }, { status: 403 });
  }
}

export async function POST(request: NextRequest) {
  try {
    const { actorUserId } = await requireAdmin(request);
    const body = (await request.json()) as { reason?: string; plan?: Parameters<typeof createPricingPlan>[0] };
    if (!body.plan) throw new Error("plan is required");
    const plan = await createPricingPlan(body.plan, actorUserId, body.reason ?? "");
    return NextResponse.json({ plan }, { status: 201 });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "could not create plan" }, { status: 400 });
  }
}
