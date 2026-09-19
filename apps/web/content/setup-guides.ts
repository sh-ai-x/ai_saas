import localFoundationMarkdown from "./guides/00-local-foundation.md";
import googleOAuthMarkdown from "./guides/01-google-oauth.md";
import tossPaymentsMarkdown from "./guides/02-payment-toss.md";
import lemonSqueezyPaymentsMarkdown from "./guides/03-payment-lemonsqueezy.md";
import agentProvidersMarkdown from "./guides/04-agent-providers.md";
import verificationMarkdown from "./guides/05-verification.md";
import operationsMarkdown from "./guides/06-operations.md";
import neonDatabaseMarkdown from "./guides/07-neon-database.md";

export type SetupGuideStep = {
  title: string;
  body: string;
  code?: string;
};

export type SetupGuide = {
  id: string;
  category: string;
  title: string;
  summary: string;
  path: string;
  markdown: string;
  steps: SetupGuideStep[];
};

type MarkdownSource = {
  path: string;
  raw: string;
};

const markdownSources: MarkdownSource[] = [
  { path: "apps/web/content/guides/00-local-foundation.md", raw: localFoundationMarkdown },
  { path: "apps/web/content/guides/01-google-oauth.md", raw: googleOAuthMarkdown },
  { path: "apps/web/content/guides/02-payment-toss.md", raw: tossPaymentsMarkdown },
  { path: "apps/web/content/guides/03-payment-lemonsqueezy.md", raw: lemonSqueezyPaymentsMarkdown },
  { path: "apps/web/content/guides/04-agent-providers.md", raw: agentProvidersMarkdown },
  { path: "apps/web/content/guides/05-verification.md", raw: verificationMarkdown },
  { path: "apps/web/content/guides/06-operations.md", raw: operationsMarkdown },
  { path: "apps/web/content/guides/07-neon-database.md", raw: neonDatabaseMarkdown },
];

function parseFrontmatter(raw: string) {
  const normalized = raw.replace(/\r\n/g, "\n");
  const match = normalized.match(/^---\n([\s\S]*?)\n---\n?/);
  if (!match) return { metadata: {} as Record<string, string>, body: normalized };

  const metadata: Record<string, string> = {};
  for (const line of match[1].split("\n")) {
    const separator = line.indexOf(":");
    if (separator < 0) continue;
    const key = line.slice(0, separator).trim();
    const value = line.slice(separator + 1).trim().replace(/^['"]|['"]$/g, "");
    metadata[key] = value;
  }
  return { metadata, body: normalized.slice(match[0].length) };
}

function parseGuide(source: MarkdownSource): SetupGuide {
  const markdown = source.raw.replace(/\r\n/g, "\n").trimEnd() + "\n";
  const { metadata, body } = parseFrontmatter(markdown);
  const title = metadata.title ?? body.match(/^#\s+(.+)$/m)?.[1]?.trim() ?? source.path;
  const headings = [...body.matchAll(/^##\s+(.+)$/gm)];
  const steps = headings.map((heading, index) => {
    const sectionStart = (heading.index ?? 0) + heading[0].length;
    const sectionEnd = headings[index + 1]?.index ?? body.length;
    const section = body.slice(sectionStart, sectionEnd).trim();
    const codeMatch = section.match(/```(?:[a-zA-Z0-9_-]+)?\n([\s\S]*?)```/);
    const code = codeMatch?.[1]?.trimEnd();
    const readableBody = section.replace(/```(?:[a-zA-Z0-9_-]+)?\n[\s\S]*?```/g, "").trim();
    return {
      title: heading[1].trim(),
      body: readableBody,
      ...(code ? { code } : {}),
    };
  });

  return {
    id: metadata.id ?? title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, ""),
    category: metadata.category ?? "GUIDE",
    title,
    summary: metadata.summary ?? "",
    path: source.path,
    markdown,
    steps,
  };
}

/** Build-time imports keep the browser bundle independent from a server filesystem. */
export const setupGuides: SetupGuide[] = markdownSources.map(parseGuide);
