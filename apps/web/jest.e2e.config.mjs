import baseConfig from "./jest.config.mjs";

export default async () => ({
  ...(await baseConfig()),
  testMatch: ["<rootDir>/tests/web-e2e.e2e.ts"],
});
