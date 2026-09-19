import { timingSafeEqual } from "node:crypto";
import { NextRequest } from "next/server";

/**
 * Local admin mode is intentionally explicit and is never accepted in
 * production. A deployed admin API uses a server-provisioned bearer token
 * until the Better Auth session is wired to this route group.
 */
export function requireAdmin(request: NextRequest) {
  const appEnv = process.env.APP_ENV ?? "local";
  if ((appEnv === "local" || appEnv === "test") && process.env.ALLOW_LOCAL_ADMIN !== "false") {
    return { actorUserId: "local-admin" };
  }

  const expected = process.env.ADMIN_API_TOKEN;
  const received = request.headers.get("authorization")?.replace(/^Bearer\s+/i, "");
  if (!expected || !received) throw new Error("admin authorization required");
  const expectedBytes = Buffer.from(expected);
  const receivedBytes = Buffer.from(received);
  if (expectedBytes.length !== receivedBytes.length || !timingSafeEqual(expectedBytes, receivedBytes)) {
    throw new Error("admin authorization denied");
  }
  return { actorUserId: process.env.ADMIN_ACTOR_ID ?? "configured-admin" };
}
