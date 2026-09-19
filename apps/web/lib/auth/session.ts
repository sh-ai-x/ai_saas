import type { NextRequest } from "next/server";
import { cookies, headers } from "next/headers";

import { getAuth } from "@/auth";
import { authRuntimeProfile, isGoogleAuthConfigured } from "./config";
import { localDemoSession, localSessionCookie, type SafeAuthSession } from "./local-session";

export async function getSafeSession(request?: NextRequest): Promise<SafeAuthSession | null> {
  if (!isGoogleAuthConfigured()) {
    if (!["local", "test"].includes(authRuntimeProfile())) {
      throw new Error("Google auth is not configured for this environment");
    }
    const cookie = request?.cookies.get(localSessionCookie)?.value ?? (await cookies()).get(localSessionCookie)?.value;
    return cookie === localDemoSession.session.id ? localDemoSession : null;
  }

  const auth = getAuth();
  const session = await auth.api.getSession({ headers: request?.headers ?? await headers() });
  if (!session?.user || !session.session) return null;
  return {
    user: {
      id: session.user.id,
      name: session.user.name,
      email: session.user.email,
      image: session.user.image ?? null,
      role: String((session.user as { role?: string }).role ?? "user"),
    },
    session: {
      id: session.session.id,
      expiresAt: new Date(session.session.expiresAt).toISOString(),
    },
  };
}
