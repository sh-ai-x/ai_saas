"use client";

import { useEffect, useRef, useState } from "react";

import { authClient } from "@/lib/auth-client";

type Session = {
  user: { name: string; email: string; role: string };
  session: { expiresAt: string };
} | null;

export function SessionControl() {
  const [session, setSession] = useState<Session | undefined>();
  const [isSigningOut, setIsSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState("");
  const signOutInFlight = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    void fetch("/api/auth/session", { cache: "no-store", signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`Session request failed: ${response.status}`);
        return response.json();
      })
      .then((body: { session?: Session }) => setSession(body.session ?? null))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setSession(null);
      });
    return () => controller.abort();
  }, []);

  async function signOut() {
    if (signOutInFlight.current) return;
    signOutInFlight.current = true;
    setIsSigningOut(true);
    setSignOutError("");
    try {
      if (process.env.NEXT_PUBLIC_GOOGLE_AUTH_ENABLED === "true") {
        await authClient.signOut();
      } else {
        const response = await fetch("/api/auth/local/sign-out", { method: "POST" });
        if (!response.ok) throw new Error(`Sign-out request failed: ${response.status}`);
      }
      window.location.assign("/");
    } catch {
      signOutInFlight.current = false;
      setIsSigningOut(false);
      setSignOutError("로그아웃에 실패했습니다. 잠시 후 다시 시도해 주세요.");
    }
  }

  if (session === undefined) return <span className="session-control muted">Checking session…</span>;
  if (!session) return <a className="button button-quiet" href="/login">Sign in</a>;
  return (
    <span className="session-control">
      <span>{session.user.name} · {session.user.role}</span>
      <button type="button" onClick={signOut} disabled={isSigningOut} aria-busy={isSigningOut}>
        {isSigningOut ? "Signing out…" : "Sign out"}
      </button>
      {signOutError ? <span className="session-error" role="alert" aria-live="polite">{signOutError}</span> : null}
    </span>
  );
}
