import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

describe("Markdown setup guide renderer", () => {
  it("strips frontmatter and renders headings, tables, links, and fenced code", () => {
    const raw = readFileSync(new URL("../content/guides/01-google-oauth.md", import.meta.url), "utf8");
    const content = raw.replace(/^---\n[\s\S]*?\n---\n?/, "");
    assert.doesNotMatch(content, /^---/);

    const html = renderToStaticMarkup(createElement(ReactMarkdown, {
      remarkPlugins: [remarkGfm],
      children: content,
    }));

    assert.match(html, /<h1>Google OAuth Live Setup<\/h1>/);
    assert.match(html, /<table>/);
    assert.match(html, /<a href="https:\/\/console\.cloud\.google\.com\//);
    assert.match(html, /<pre><code class="language-bash">/);
    assert.doesNotMatch(html, /id:\s*google-oauth/);
  });
});
