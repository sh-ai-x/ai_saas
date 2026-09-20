jest.mock("better-auth", () => ({ betterAuth: jest.fn() }));
jest.mock("better-auth/adapters/drizzle", () => ({ drizzleAdapter: jest.fn() }));
jest.mock("better-auth/plugins", () => ({ admin: jest.fn(() => ({})) }));
jest.mock("better-auth/next-js", () => ({
  nextCookies: jest.fn(() => ({})),
  toNextJsHandler: jest.fn(() => ({ GET: jest.fn(), POST: jest.fn() })),
}));
jest.mock("better-auth/react", () => ({
  createAuthClient: jest.fn(() => ({ signOut: jest.fn() })),
}));
