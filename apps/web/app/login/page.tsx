import { GoogleLoginForm } from "@/components/auth/google-login-form";
import { isGoogleAuthConfigured } from "@/lib/auth/config";

export const dynamic = "force-dynamic";

export default function LoginPage() {
  const googleConfigured = isGoogleAuthConfigured() && process.env.NEXT_PUBLIC_GOOGLE_AUTH_ENABLED === "true";
  return (
    <main className="auth-page">
      <div className="auth-card">
        <a className="auth-back" href="/">← Public landing</a>
        <p className="eyebrow accent">IDENTITY / SERVER SESSION</p>
        <h1>Sign in to the foundation.</h1>
        <p>Google proves identity. Tenant, billing, agent, and admin permissions remain server-side.</p>
        <GoogleLoginForm googleConfigured={googleConfigured} />
        <p className="auth-note">{googleConfigured ? "Google OAuth is configured for this environment." : "Local profile: no Google credentials are required."}</p>
      </div>
    </main>
  );
}
