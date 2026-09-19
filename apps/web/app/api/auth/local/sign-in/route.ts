import { NextResponse } from "next/server";

import { authRuntimeProfile } from "@/lib/auth/config";
import { localDemoSession, localMemberSession, localSessionCookie } from "@/lib/auth/local-session";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  if (authRuntimeProfile() !== "test") {
    return NextResponse.json({ error: "test_auth_only", message: "Local demo sign-in is only available to automated tests." }, { status: 404 });
  }
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
