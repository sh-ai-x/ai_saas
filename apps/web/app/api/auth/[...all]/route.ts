import { NextRequest, NextResponse } from "next/server";
import { toNextJsHandler } from "better-auth/next-js";

import { getAuth } from "@/auth";
import { isGoogleAuthConfigured, safeAuthError } from "@/lib/auth/config";

export const dynamic = "force-dynamic";

async function configuredHandler(request: NextRequest) {
  const auth = getAuth();
  const handler = toNextJsHandler(auth);
  return request.method === "GET" ? handler.GET(request) : handler.POST(request);
}

async function handle(request: NextRequest) {
  if (!isGoogleAuthConfigured()) {
    return NextResponse.json({ error: "auth_not_configured", message: "Configure Google OAuth before using the authentication API." }, { status: 503 });
  }
  try {
    return await configuredHandler(request);
  } catch (error) {
    const safe = safeAuthError(error);
    return NextResponse.json(safe, { status: 503 });
  }
}

export async function GET(request: NextRequest) {
  return handle(request);
}

export async function POST(request: NextRequest) {
  return handle(request);
}
