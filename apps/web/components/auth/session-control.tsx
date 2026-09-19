"use client";

import { useEffect, useState } from "react";

import { authClient } from "@/lib/auth-client";

type Session = {
  user: { name: string; email: string; role: string };
  session: { expiresAt: string };
} | null;

export function SessionControl() {
  const [session, setSession] = useState<Session | undefined>();

  useEffect(() => {
    void fetch("/api/auth/session", { cache: "no-store" })
      .then((response) => response.json())
      .then((body: { session?: Session }) => setSession(body.session ?? null))
      .catch(() => setSession(null));
  }, []);

  async function signOut() {
    if (process.env.NEXT_PUBLIC_GOOGLE_AUTH_ENABLED === "true") await authClient.signOut();
    else await fetch("/api/auth/local/sign-out", { method: "POST" });
    window.location.assign("/");
  }

  if (session === undefined) return <span className="session-control muted">Checking session…</span>;
  if (!session) return <a className="button button-quiet" href="/login">Sign in</a>;
  return (
    <span className="session-control">
      <span>{session.user.name} · {session.user.role}</span>
      <button type="button" onClick={signOut}>Sign out</button>
    </span>
  );
}
