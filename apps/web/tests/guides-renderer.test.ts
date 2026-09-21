import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

describe("Markdown setup guide renderer", () => {
  it("strips frontmatter and renders headings, tables, links, and fenced code", () => {
    const raw = readFileSync(resolve(__dirname, "../content/guides/01-google-oauth.md"), "utf8");
    const content = raw.replace(/^---\n[\s\S]*?\n---\n?/, "");
    expect(content).not.toMatch(/^---/);

    const html = renderToStaticMarkup(createElement(ReactMarkdown, {
      remarkPlugins: [remarkGfm],
      children: content,
    }));

    expect(html).toMatch(/<h1>Google OAuth Live Setup<\/h1>/);
    expect(html).toMatch(/<table>/);
    expect(html).toMatch(/<a href="https:\/\/console\.cloud\.google\.com\//);
    expect(html).toMatch(/<pre><code class="language-bash">/);
    expect(html).not.toMatch(/id:\s*google-oauth/);
  });
});
