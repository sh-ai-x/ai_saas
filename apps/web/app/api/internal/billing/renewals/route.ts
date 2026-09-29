import { NextRequest, NextResponse } from "next/server";

import { renewDueTossSubscriptions } from "@/lib/payments/toss-settlement";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const configured = process.env.BILLING_CRON_SECRET?.trim();
  const received = request.headers.get("authorization")?.replace(/^Bearer\s+/i, "").trim();
  if (!configured || !received || configured !== received) return NextResponse.json({ error: "billing scheduler authorization required" }, { status: 401 });
  try {
    const results = await renewDueTossSubscriptions();
    return NextResponse.json({ processed: results.length, renewed: results.filter((result) => result.status === "renewed").length, failed: results.filter((result) => result.status === "failed").length, results });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "billing renewal failed" }, { status: 503 });
  }
}
