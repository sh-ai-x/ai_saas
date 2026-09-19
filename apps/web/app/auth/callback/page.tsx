import Link from "next/link";

export const dynamic = "force-dynamic";

export default async function AuthCallbackPage({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  const params = await searchParams;
  return (
    <main className="auth-page">
      <div className="auth-card">
        <p className="eyebrow accent">IDENTITY / CALLBACK</p>
        <h1>{params.error ? "Sign-in could not be completed." : "Sign-in is continuing."}</h1>
        <p>{params.error ? "No account or session was created. Return to sign in and try again." : "If the redirect did not continue, restart the sign-in flow."}</p>
        <Link className="button button-primary" href="/login">Back to sign in</Link>
      </div>
    </main>
  );
}
