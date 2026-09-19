"use client";

import { useState } from "react";

import { authClient } from "@/lib/auth-client";

export function GoogleLoginForm({ googleConfigured }: { googleConfigured: boolean }) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function signIn() {
    setPending(true);
    setError(null);
    if (!googleConfigured) {
      const response = await fetch("/api/auth/local/sign-in", { method: "POST" });
      if (!response.ok) setError("Local demo sign-in is unavailable.");
      else window.location.assign("/app");
      setPending(false);
      return;
    }

    const result = await authClient.signIn.social({ provider: "google", callbackURL: "/app" });
    if (result.error) setError("Google sign-in could not be started. Check the configured redirect URI.");
    setPending(false);
  }

  return (
    <div className="auth-actions">
      <button className="button button-primary" type="button" onClick={signIn} disabled={pending}>
        {pending ? "Opening sign-in…" : googleConfigured ? "Continue with Google" : "Use local demo session"}
      </button>
      {error ? <p className="form-error" role="alert">{error}</p> : null}
    </div>
  );
}
