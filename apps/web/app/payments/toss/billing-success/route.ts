import { NextRequest, NextResponse } from "next/server";

import { settleTossSubscription } from "@/lib/payments/toss-settlement";

export async function GET(request: NextRequest) {
  const customerKey = request.nextUrl.searchParams.get("customerKey") ?? "";
  const authKey = request.nextUrl.searchParams.get("authKey") ?? "";
  if (!customerKey || !authKey) return NextResponse.redirect(new URL("/billing?payment=invalid", request.url));

  try {
    await settleTossSubscription({ customerKey, authKey });
    return NextResponse.redirect(new URL("/billing?payment=success", request.url));
  } catch {
    return NextResponse.redirect(new URL("/billing?payment=failed", request.url));
  }
}
