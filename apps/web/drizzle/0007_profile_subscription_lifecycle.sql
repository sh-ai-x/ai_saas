ALTER TABLE "subscriptions" ADD COLUMN IF NOT EXISTS "provider_status" text;
--> statement-breakpoint
ALTER TABLE "subscriptions" ADD COLUMN IF NOT EXISTS "cancel_requested_at" timestamp with time zone;
--> statement-breakpoint
ALTER TABLE "subscriptions" ADD COLUMN IF NOT EXISTS "canceled_at" timestamp with time zone;
--> statement-breakpoint
ALTER TABLE "subscriptions" ADD COLUMN IF NOT EXISTS "ended_at" timestamp with time zone;
--> statement-breakpoint
ALTER TABLE "subscriptions" ADD COLUMN IF NOT EXISTS "next_billing_at" timestamp with time zone;
--> statement-breakpoint
ALTER TABLE "subscriptions" ADD COLUMN IF NOT EXISTS "grace_until" timestamp with time zone;
--> statement-breakpoint
ALTER TABLE "subscriptions" ADD COLUMN IF NOT EXISTS "last_payment_at" timestamp with time zone;
--> statement-breakpoint
ALTER TABLE "subscriptions" ADD COLUMN IF NOT EXISTS "last_payment_error" text;
--> statement-breakpoint
ALTER TABLE "subscriptions" ADD COLUMN IF NOT EXISTS "version" integer DEFAULT 1 NOT NULL;
--> statement-breakpoint
ALTER TABLE "billing_events" ADD COLUMN IF NOT EXISTS "event_type" text;
--> statement-breakpoint
ALTER TABLE "billing_events" ADD COLUMN IF NOT EXISTS "aggregate_id" text;
--> statement-breakpoint
ALTER TABLE "billing_events" ADD COLUMN IF NOT EXISTS "occurred_at" timestamp with time zone;
--> statement-breakpoint
ALTER TABLE "billing_events" ADD COLUMN IF NOT EXISTS "applied" boolean DEFAULT false NOT NULL;
--> statement-breakpoint
ALTER TABLE "billing_events" ADD COLUMN IF NOT EXISTS "failure_reason" text;
--> statement-breakpoint
ALTER TABLE "billing_events" ADD COLUMN IF NOT EXISTS "payload_version" integer DEFAULT 1 NOT NULL;
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS "subscription_transitions" (
  "id" text PRIMARY KEY NOT NULL,
  "subscription_id" text NOT NULL REFERENCES "subscriptions"("id") ON DELETE cascade,
  "user_id" text,
  "from_status" text,
  "to_status" text NOT NULL,
  "event_type" text NOT NULL,
  "reason" text,
  "idempotency_key" text NOT NULL,
  "occurred_at" timestamp with time zone NOT NULL,
  "metadata" jsonb DEFAULT '{}'::jsonb NOT NULL,
  "created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX IF NOT EXISTS "subscription_transitions_idempotency_idx" ON "subscription_transitions" USING btree ("idempotency_key");
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "subscription_transitions_subscription_idx" ON "subscription_transitions" USING btree ("subscription_id", "occurred_at");
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "subscription_transitions_user_idx" ON "subscription_transitions" USING btree ("user_id", "occurred_at");
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS "token_usage_periods" (
  "id" text PRIMARY KEY NOT NULL,
  "user_id" text NOT NULL,
  "subscription_id" text,
  "plan_id" text NOT NULL,
  "period_start" timestamp with time zone NOT NULL,
  "period_end" timestamp with time zone NOT NULL,
  "input_limit" integer DEFAULT 0 NOT NULL,
  "output_limit" integer DEFAULT 0 NOT NULL,
  "total_limit" integer DEFAULT 0 NOT NULL,
  "input_used" integer DEFAULT 0 NOT NULL,
  "output_used" integer DEFAULT 0 NOT NULL,
  "total_used" integer DEFAULT 0 NOT NULL,
  "status" text DEFAULT 'active' NOT NULL,
  "created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX IF NOT EXISTS "token_usage_periods_user_period_idx" ON "token_usage_periods" USING btree ("user_id", "period_start");
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "token_usage_periods_subscription_idx" ON "token_usage_periods" USING btree ("subscription_id", "period_start");
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS "token_usage_entries" (
  "id" text PRIMARY KEY NOT NULL,
  "user_id" text NOT NULL,
  "subscription_id" text,
  "period_id" text,
  "run_id" text,
  "request_id" text,
  "input_tokens" integer DEFAULT 0 NOT NULL,
  "output_tokens" integer DEFAULT 0 NOT NULL,
  "total_tokens" integer DEFAULT 0 NOT NULL,
  "status" text DEFAULT 'committed' NOT NULL,
  "idempotency_key" text NOT NULL,
  "metadata" jsonb DEFAULT '{}'::jsonb NOT NULL,
  "created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX IF NOT EXISTS "token_usage_entries_idempotency_idx" ON "token_usage_entries" USING btree ("idempotency_key");
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "token_usage_entries_user_created_idx" ON "token_usage_entries" USING btree ("user_id", "created_at");
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "token_usage_entries_period_created_idx" ON "token_usage_entries" USING btree ("period_id", "created_at");
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "subscriptions_user_status_idx" ON "subscriptions" USING btree ("user_id", "status");
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "subscriptions_next_billing_idx" ON "subscriptions" USING btree ("next_billing_at", "status");
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "subscriptions_period_end_idx" ON "subscriptions" USING btree ("current_period_end", "status");
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "billing_events_aggregate_idx" ON "billing_events" USING btree ("aggregate_id", "occurred_at");
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "payment_orders_toss_customer_key_idx"
  ON "payment_orders" USING btree (("metadata"->>'customerKey'))
  WHERE "provider" = 'toss';
--> statement-breakpoint
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM "subscriptions"
    WHERE "user_id" IS NOT NULL
      AND "status" IN ('pending', 'active', 'cancel_scheduled', 'past_due')
    GROUP BY "tenant_id", "user_id"
    HAVING COUNT(*) > 1
  ) THEN
    RAISE EXCEPTION 'cannot enforce one open subscription per tenant/user while duplicate rows exist';
  END IF;
END $$;
--> statement-breakpoint
CREATE UNIQUE INDEX IF NOT EXISTS "subscriptions_one_open_per_user_idx"
  ON "subscriptions" USING btree ("tenant_id", "user_id")
  WHERE "user_id" IS NOT NULL AND "status" IN ('pending', 'active', 'cancel_scheduled', 'past_due');
--> statement-breakpoint
UPDATE "pricing_plans"
SET "quotas" = CASE
  WHEN "code" = 'starter' THEN "quotas" || jsonb_build_object(
    'monthlyInputTokens', COALESCE("quotas"->'monthlyInputTokens', '200000'::jsonb),
    'monthlyOutputTokens', COALESCE("quotas"->'monthlyOutputTokens', '100000'::jsonb),
    'monthlyTokens', COALESCE("quotas"->'monthlyTokens', '300000'::jsonb)
  )
  WHEN "code" IN ('pro', 'lifetime') THEN "quotas" || jsonb_build_object(
    'monthlyInputTokens', COALESCE("quotas"->'monthlyInputTokens', '1000000'::jsonb),
    'monthlyOutputTokens', COALESCE("quotas"->'monthlyOutputTokens', '500000'::jsonb),
    'monthlyTokens', COALESCE("quotas"->'monthlyTokens', '1500000'::jsonb)
  )
  ELSE "quotas"
END
WHERE "code" IN ('starter', 'pro', 'lifetime');
