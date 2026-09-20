import nextJest from "next/jest.js";

const createJestConfig = nextJest({ dir: "./" });

const customJestConfig = {
  rootDir: ".",
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],
  testEnvironment: "node",
  testMatch: ["<rootDir>/tests/**/*.test.ts"],
  modulePathIgnorePatterns: ["<rootDir>/.next/"],
};

// Next/Jest emits CommonJS, so allow only the ESM Markdown dependency graph through SWC.
const esmPackages = [
  "escape-string-regexp",
  "markdown-table",
  "react-markdown",
  "remark-[^/]+",
  "unified",
  "mdast-util-[^/]+",
  "micromark(?:-[^/]+)?",
  "hast-util-[^/]+",
  "unist-util-[^/]+",
  "vfile(?:-[^/]+)?",
  "estree-util-[^/]+",
  "property-information",
  "space-separated-tokens",
  "comma-separated-tokens",
  "character-entities(?:-[^/]+)?",
  "decode-named-character-reference",
  "stringify-entities",
  "zwitch",
  "trough",
  "bail",
  "devlop",
  "is-plain-obj",
  "ccount",
  "longest-streak",
  "trim-lines",
  "html-url-attributes",
  "web-namespaces",
  "parse-entities",
].join("|");

export default async () => {
  const config = await createJestConfig(customJestConfig)();

  return {
    ...config,
    transformIgnorePatterns: [
      `node_modules/.pnpm/(?!(?:${esmPackages})@)`,
      `node_modules/(?!(?:\\.pnpm|${esmPackages})/)`,
    ],
  };
};
