import { timingSafeEqual } from "node:crypto";
import { NextRequest } from "next/server";

import { getSafeSession } from "@/lib/auth/session";

/**
 * Admin APIs accept either a server-provisioned bearer token or a
 * server-resolved Better Auth session with an admin role. There is no
 * credential-free local bypass: local demos must use the explicit admin
 * session cookie.
 */
export async function requireAdmin(request: NextRequest) {
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
