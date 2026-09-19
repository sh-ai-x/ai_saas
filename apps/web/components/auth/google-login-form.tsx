"use client";

import { useState } from "react";

import { authClient } from "@/lib/auth-client";

export function GoogleLoginForm({ googleConfigured, callbackURL }: { googleConfigured: boolean; callbackURL: string }) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function signIn(localRole: "admin" | "member" = "member") {
    setPending(true);
    setError(null);
    if (!googleConfigured) {
      const response = await fetch("/api/auth/local/sign-in", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ role: localRole }),
      });
      if (!response.ok) setError("Local demo sign-in is unavailable.");
      else window.location.assign(callbackURL);
      setPending(false);
      return;
    }

    const result = await authClient.signIn.social({ provider: "google", callbackURL });
    if (result.error) setError("Google sign-in could not be started. Check the configured redirect URI.");
    setPending(false);
  }

  return (
    <div className="auth-actions">
      {googleConfigured ? <button className="button button-primary" type="button" onClick={() => void signIn()} disabled={pending}>{pending ? "Opening sign-in…" : "Continue with Google"}</button> : <><button className="button button-primary" type="button" onClick={() => void signIn("member")} disabled={pending}>{pending ? "Opening workspace…" : "Use local member session"}</button><button className="button button-quiet" type="button" onClick={() => void signIn("admin")} disabled={pending}>Use local admin session</button></>}
      {error ? <p className="form-error" role="alert">{error}</p> : null}
    </div>
  );
}
