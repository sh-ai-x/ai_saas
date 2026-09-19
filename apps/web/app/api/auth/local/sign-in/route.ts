import { NextResponse } from "next/server";

import { localDemoSession, localSessionCookie } from "@/lib/auth/local-session";

export const dynamic = "force-dynamic";

export async function POST() {
  const response = NextResponse.json({ session: localDemoSession });
  response.cookies.set(localSessionCookie, localDemoSession.session.id, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 24,
  });
  return response;
}
