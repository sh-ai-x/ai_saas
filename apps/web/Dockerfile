# syntax=docker/dockerfile:1

FROM node:22-alpine AS base

WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

RUN apk add --no-cache libc6-compat
RUN corepack enable

FROM base AS deps

COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web/package.json ./apps/web/package.json
RUN pnpm install --frozen-lockfile --filter ai-saas-foundation-web...

FROM deps AS builder

ARG NEXT_PUBLIC_GOOGLE_AUTH_ENABLED=true
ENV NEXT_PUBLIC_GOOGLE_AUTH_ENABLED=$NEXT_PUBLIC_GOOGLE_AUTH_ENABLED

COPY apps/web/ ./apps/web/
RUN pnpm --filter ai-saas-foundation-web build

# Local Docker uses Next dev mode so an 8 GB developer machine does not need
# to spend several minutes producing standalone tracing output on every
# rebuild. The production runner above remains unchanged for release-shaped
# images.
FROM deps AS development

COPY apps/web/ ./apps/web/
ENV NODE_ENV=development

# This target is used by docker/prod/compose.yaml as a one-shot migration job.
# It intentionally retains drizzle-kit and the TypeScript source files.
FROM deps AS migrator

COPY apps/web/ ./apps/web/
ENV NODE_ENV=production

FROM base AS runner

ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3000

RUN addgroup --system --gid 1001 nodejs \
  && adduser --system --uid 1001 nextjs

COPY --from=builder --chown=nextjs:nodejs /app/apps/web/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/apps/web/.next/static ./apps/web/.next/static

USER nextjs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:3000').then(() => process.exit(0)).catch(() => process.exit(1))"

CMD ["node", "apps/web/server.js"]
