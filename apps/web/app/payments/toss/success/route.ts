import { NextRequest, NextResponse } from "next/server";

const foundationApiUrl = process.env.FOUNDATION_API_URL ?? "http://127.0.0.1:8080";

export async function GET(request: NextRequest) {
  const paymentKey = request.nextUrl.searchParams.get("paymentKey") ?? "";
  const orderId = request.nextUrl.searchParams.get("orderId") ?? "";
  const amount = Number(request.nextUrl.searchParams.get("amount") ?? "NaN");
  if (!paymentKey || !orderId || !Number.isInteger(amount) || amount <= 0) {
    return NextResponse.redirect(new URL("/?payment=invalid", request.url));
  }

  const upstream = await fetch(`${foundationApiUrl.replace(/\/$/, "")}/v1/billing/toss/confirm`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      cookie: request.headers.get("cookie") ?? "",
    },
    body: JSON.stringify({
      order_id: orderId,
      payment_key: paymentKey,
      amount_minor: amount,
      idempotency_key: `toss-confirm-${paymentKey}`,
    }),
    cache: "no-store",
  });
  return NextResponse.redirect(
    new URL(upstream.ok ? "/?payment=success" : "/?payment=failed", request.url),
  );
}
