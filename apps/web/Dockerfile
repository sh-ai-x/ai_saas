# syntax=docker/dockerfile:1

FROM node:22-alpine AS base

WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

RUN apk add --no-cache libc6-compat

FROM base AS deps

COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

FROM deps AS builder

COPY apps/web/ ./
RUN npm run build

# This target is used by docker/prod/compose.yaml as a one-shot migration job.
# It intentionally retains drizzle-kit and the TypeScript source files.
FROM deps AS migrator

COPY apps/web/ ./
ENV NODE_ENV=production

FROM base AS runner

ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3000

RUN addgroup --system --gid 1001 nodejs \
  && adduser --system --uid 1001 nextjs

COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:3000').then(() => process.exit(0)).catch(() => process.exit(1))"

CMD ["node", "server.js"]
