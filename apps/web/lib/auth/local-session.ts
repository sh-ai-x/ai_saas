import { cookies } from "next/headers";

export const localSessionCookie = "ai_saas_demo_session";

export type SafeAuthSession = {
  user: {
    id: string;
    name: string;
    email: string;
    image: string | null;
    role: string;
  };
  session: {
    id: string;
    expiresAt: string;
  };
};

export const localDemoSession: SafeAuthSession = {
  user: {
    id: "demo-user",
    name: "Local Demo",
    email: "demo@example.test",
    image: null,
    role: "admin",
  },
  session: {
    id: "demo-session",
    expiresAt: "2099-01-01T00:00:00.000Z",
  },
};

export async function readLocalSession(): Promise<SafeAuthSession | null> {
  const jar = await cookies();
  return jar.get(localSessionCookie)?.value === localDemoSession.session.id ? localDemoSession : null;
}
