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
        <h1>Sign in to the foundation.</h1>
        <p>Google proves identity. Tenant, billing, agent, and admin permissions remain server-side.</p>
        <GoogleLoginForm googleConfigured={googleConfigured} callbackURL={callbackURL} />
        <p className="auth-note">{googleConfigured ? `Google OAuth is configured. You will return to ${callbackURL}.` : "Local profile: choose a member or admin demo session. Admin routes require the admin session."}</p>
      </div>
    </main>
  );
}
