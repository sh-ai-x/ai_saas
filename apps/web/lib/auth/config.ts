export type AuthRuntimeProfile = "local" | "test" | "staging" | "production";

const requiredKeys = [
  "DATABASE_URL",
  "BETTER_AUTH_SECRET",
  "BETTER_AUTH_URL",
  "GOOGLE_CLIENT_ID",
  "GOOGLE_CLIENT_SECRET",
] as const;

export function authRuntimeProfile(): AuthRuntimeProfile {
  const value = process.env.APP_ENV;
  if (value === "production" || value === "staging" || value === "test") return value;
  return "local";
}

export function missingAuthConfiguration(): string[] {
  return requiredKeys.filter((key) => !process.env[key]?.trim());
}

export function isGoogleAuthConfigured(): boolean {
  return missingAuthConfiguration().length === 0;
}

export function assertGoogleAuthConfiguration(): void {
  const missing = missingAuthConfiguration();
  if (missing.length && ["production", "staging"].includes(authRuntimeProfile())) {
    throw new Error(`Google auth configuration incomplete: ${missing.join(", ")}`);
  }
}

export function safeAuthError(error: unknown): { code: string; message: string } {
  if (error instanceof Error && error.message.includes("configuration incomplete")) {
    return { code: "auth_not_configured", message: "Google sign-in is not configured for this environment." };
  }
  return { code: "auth_unavailable", message: "Authentication is temporarily unavailable. Please try again." };
}
