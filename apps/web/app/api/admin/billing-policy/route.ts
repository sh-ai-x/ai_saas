import { NextRequest, NextResponse } from "next/server";

import { requireAdmin } from "@/lib/admin-guard";
import { getBillingPolicy, setBillingMode } from "@/lib/pricing/repository";
import type { BillingMode } from "@/lib/pricing/types";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  try {
    await requireAdmin(request);
    return NextResponse.json({ billing: await getBillingPolicy() });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "admin authorization required" }, { status: 403 });
  }
}

export async function PATCH(request: NextRequest) {
  try {
    const { actorUserId } = await requireAdmin(request);
    const body = (await request.json()) as { billingMode?: BillingMode; reason?: string };
    if (!body.billingMode) throw new Error("billingMode is required");
    return NextResponse.json({ billing: await setBillingMode(body.billingMode, actorUserId, body.reason ?? "") });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "could not update billing policy" }, { status: 400 });
  }
}
