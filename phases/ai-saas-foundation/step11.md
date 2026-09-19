Status: completed
Name: setup-guide-console

Task:
Add detailed setup guides as a dedicated `/guides` route. Import the source
Markdown files at build time, render them in a read-only Markdown-editor view,
organize guides by category in a hierarchical left sidebar with separate Toss
and Lemon Squeezy payment pages, and link back to the `/` operator console.

Acceptance:
- Categories cover local start, Google OAuth, Toss payments, Lemon Squeezy
  payments, Agent providers,
  verification, and operations/troubleshooting.
- The sidebar is keyboard accessible, responsive, and does not remove the
  existing run/admin/payment console.
- Guides explicitly identify secrets, callback URLs, sandbox behavior,
  rollback, and expected API responses.
- `apps/web/content/guides/*.md` is the web source of truth; the UI exposes the
  imported path, line numbers, raw Markdown, and copy action without a runtime
  filesystem dependency.
- `/` is the landing/operator console and `/guides` is the documentation
  surface; the two entry points do not render the same screen.
- Local no-credential mode remains runnable.

Verification:
```bash
npm --prefix apps/web run lint
npm --prefix apps/web run build
```
