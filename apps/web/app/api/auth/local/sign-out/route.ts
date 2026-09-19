import { NextResponse } from "next/server";

import { localSessionCookie } from "@/lib/auth/local-session";

export const dynamic = "force-dynamic";

export async function POST() {
  const response = NextResponse.json({ ok: true });
  response.cookies.set(localSessionCookie, "", { httpOnly: true, expires: new Date(0), path: "/" });
  return response;
}
