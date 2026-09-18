import { NextRequest, NextResponse } from "next/server";

const foundationApiUrl = process.env.FOUNDATION_API_URL ?? "http://127.0.0.1:8080";

export async function GET(request: NextRequest) {
  const state = request.nextUrl.searchParams.get("state") ?? "";
  const code = request.nextUrl.searchParams.get("code") ?? "";
  const redirectUri = request.nextUrl.origin + "/auth/callback";
  if (!state || !code) {
    return NextResponse.redirect(new URL("/?auth=invalid_callback", request.url));
  }

  const upstream = await fetch(`${foundationApiUrl.replace(/\/$/, "")}/v1/auth/google/callback`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ state, code, redirect_uri: redirectUri }),
    cache: "no-store",
  });
  if (!upstream.ok) {
    return NextResponse.redirect(new URL("/?auth=failed", request.url));
  }

  const response = NextResponse.redirect(new URL("/?auth=connected", request.url));
  const setCookie = upstream.headers.get("set-cookie");
  if (setCookie) response.headers.set("set-cookie", setCookie);
  return response;
}
