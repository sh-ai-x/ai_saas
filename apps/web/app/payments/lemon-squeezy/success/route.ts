import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  // Lemon Squeezy entitlement is webhook-authoritative. The redirect is only
  // a user-facing acknowledgement and never grants credits.
  return NextResponse.redirect(new URL("/?payment=awaiting_webhook", request.url));
}
