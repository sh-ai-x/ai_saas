"use client";

import React, { useRef, useState } from "react";

import { authClient } from "@/lib/auth-client";

export function GoogleLoginForm({ googleConfigured, callbackURL }: { googleConfigured: boolean; callbackURL: string }) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const signInInFlight = useRef(false);

  async function signIn() {
    if (signInInFlight.current) return;
    signInInFlight.current = true;
    setPending(true);
    setError(null);
    try {
      const result = await authClient.signIn.social({ provider: "google", callbackURL });
      if (result.error) setError("Google sign-in could not be started. Check the configured redirect URI.");
    } catch {
      setError("Google sign-in could not be started. Check the configured redirect URI.");
    } finally {
      signInInFlight.current = false;
      setPending(false);
    }
  }

  return (
    <div className="auth-actions">
      {googleConfigured ? <button className="button button-primary" type="button" onClick={() => void signIn()} disabled={pending}>{pending ? "Opening sign-in…" : "Continue with Google"}</button> : <a className="button button-primary" href="/guides?guide=google-oauth">Open Google OAuth setup guide</a>}
      {error ? <p className="form-error" role="alert">{error}</p> : null}
    </div>
  );
}
