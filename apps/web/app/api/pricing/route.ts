import { NextResponse } from "next/server";

import { applySelectedPaymentProvider, getBillingPolicy, listPricingCatalog, selectedPaymentProvider } from "@/lib/pricing/repository";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const [plans, billing, provider] = await Promise.all([listPricingCatalog(true), getBillingPolicy(), selectedPaymentProvider()]);
    const effectivePlans = applySelectedPaymentProvider(plans, provider);
    return NextResponse.json({ plans: effectivePlans, billing, source: process.env.DATABASE_URL ? "neon" : "local-seed" });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "pricing unavailable" }, { status: 503 });
  }
}
