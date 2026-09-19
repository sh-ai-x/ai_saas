import { GoogleLoginForm } from "@/components/auth/google-login-form";
import { isGoogleAuthConfigured } from "@/lib/auth/config";

export const dynamic = "force-dynamic";

function safeNext(value: string | undefined) {
  return value && value.startsWith("/") && !value.startsWith("//") ? value : "/app";
}

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const params = await searchParams;
  const googleConfigured = isGoogleAuthConfigured() && process.env.NEXT_PUBLIC_GOOGLE_AUTH_ENABLED === "true";
  const callbackURL = safeNext(params.next);
  return (
    <main className="auth-page">
      <div className="auth-card">
        <a className="auth-back" href="/">← Public landing</a>
        <p className="eyebrow accent">IDENTITY / SERVER SESSION</p>
        <h1>Sign up or sign in with Google.</h1>
        <p>Google is the only account entry point. Your first authorization creates a regular account; existing accounts sign in. Tenant, billing, agent, and admin permissions remain server-side.</p>
        <GoogleLoginForm googleConfigured={googleConfigured} callbackURL={callbackURL} />
        <p className="auth-note">{googleConfigured ? `Google OAuth is configured. You will return to ${callbackURL}.` : "Google OAuth is not configured for this environment. Configure it from the setup guide; no local or mock login is available."}</p>
      </div>
    </main>
  );
}
