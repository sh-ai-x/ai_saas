import { NextResponse } from "next/server";

import { getBillingPolicy, listPricingCatalog } from "@/lib/pricing/repository";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const [plans, billing] = await Promise.all([listPricingCatalog(true), getBillingPolicy()]);
    return NextResponse.json({ plans, billing, source: process.env.DATABASE_URL ? "neon" : "local-seed" });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "pricing unavailable" }, { status: 503 });
  }
}
