import { timingSafeEqual } from "node:crypto";
import { NextRequest } from "next/server";

import { getSafeSession } from "@/lib/auth/session";

/**
 * Local admin mode is intentionally explicit and is never accepted in
 * production. A deployed admin API uses a server-provisioned bearer token
 * until the Better Auth session is wired to this route group.
 */
export async function requireAdmin(request: NextRequest) {
  const appEnv = process.env.APP_ENV ?? "local";
  if ((appEnv === "local" || appEnv === "test") && process.env.ALLOW_LOCAL_ADMIN !== "false") {
    return { actorUserId: "local-admin" };
  }

  const expected = process.env.ADMIN_API_TOKEN;
  const received = request.headers.get("authorization")?.replace(/^Bearer\s+/i, "");
  if (expected && received) {
    const expectedBytes = Buffer.from(expected);
    const receivedBytes = Buffer.from(received);
    if (expectedBytes.length === receivedBytes.length && timingSafeEqual(expectedBytes, receivedBytes)) {
      return { actorUserId: process.env.ADMIN_ACTOR_ID ?? "configured-admin" };
    }
  }

  const session = await getSafeSession(request);
  if (!session) throw new Error("admin authorization required");
  if (!["admin", "super_admin"].includes(session.user.role)) throw new Error("admin authorization denied");
  return { actorUserId: session.user.id };
}
