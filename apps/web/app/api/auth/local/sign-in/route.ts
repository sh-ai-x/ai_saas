import { NextResponse } from "next/server";

import { localDemoSession, localMemberSession, localSessionCookie } from "@/lib/auth/local-session";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  let role: "admin" | "member" = "admin";
  try {
    const body = (await request.json()) as { role?: string };
    if (body.role === "member") role = "member";
  } catch {
    // Empty bodies preserve the original local-admin demo behavior.
  }
  const session = role === "member" ? localMemberSession : localDemoSession;
  const response = NextResponse.json({ session });
  response.cookies.set(localSessionCookie, session.session.id, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 24,
  });
  return response;
}
