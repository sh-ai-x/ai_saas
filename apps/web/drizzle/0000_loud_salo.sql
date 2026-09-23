CREATE TABLE "admin_audit_events" (
	"id" text PRIMARY KEY NOT NULL,
	"actor_user_id" text NOT NULL,
	"action" text NOT NULL,
	"resource_type" text NOT NULL,
	"resource_id" text NOT NULL,
	"reason" text NOT NULL,
	"before_json" jsonb,
	"after_json" jsonb,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "billing_events" (
	"id" text PRIMARY KEY NOT NULL,
	"provider" text NOT NULL,
	"external_event_id" text NOT NULL,
	"raw_body_hash" text NOT NULL,
	"normalized_payload" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"verification_status" text DEFAULT 'received' NOT NULL,
	"processed_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "payment_orders" (
	"id" text PRIMARY KEY NOT NULL,
	"tenant_id" text NOT NULL,
	"user_id" text,
	"pricing_option_id" text NOT NULL,
	"provider" text NOT NULL,
	"mode" text NOT NULL,
	"status" text DEFAULT 'pending' NOT NULL,
	"external_order_ref" text,
	"external_payment_ref" text,
	"amount_minor" integer NOT NULL,
	"currency" text NOT NULL,
	"idempotency_key" text NOT NULL,
	"metadata" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "payment_provider_settings" (
	"id" text PRIMARY KEY NOT NULL,
	"provider" text NOT NULL,
	"enabled" boolean DEFAULT false NOT NULL,
	"sandbox" boolean DEFAULT true NOT NULL,
	"public_config" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"secret_ref" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "pricing_options" (
	"id" text PRIMARY KEY NOT NULL,
	"plan_id" text NOT NULL,
	"mode" text NOT NULL,
	"interval" text NOT NULL,
	"provider" text NOT NULL,
	"currency" text DEFAULT 'USD' NOT NULL,
	"amount_minor" integer NOT NULL,
	"compare_at_amount_minor" integer,
	"provider_product_ref" text,
	"provider_price_ref" text,
	"active" boolean DEFAULT true NOT NULL,
	"metadata" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "pricing_plans" (
	"id" text PRIMARY KEY NOT NULL,
	"tenant_id" text DEFAULT 'platform' NOT NULL,
	"code" text NOT NULL,
	"name" text NOT NULL,
	"description" text DEFAULT '' NOT NULL,
	"billing_mode" text DEFAULT 'subscription' NOT NULL,
	"active" boolean DEFAULT true NOT NULL,
	"is_default" boolean DEFAULT false NOT NULL,
	"display_order" integer DEFAULT 0 NOT NULL,
	"features" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"quotas" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "subscriptions" (
	"id" text PRIMARY KEY NOT NULL,
	"tenant_id" text NOT NULL,
	"user_id" text,
	"pricing_option_id" text NOT NULL,
	"provider" text NOT NULL,
	"external_customer_ref" text,
	"external_subscription_ref" text,
	"status" text DEFAULT 'pending' NOT NULL,
	"current_period_start" timestamp with time zone,
	"current_period_end" timestamp with time zone,
	"cancel_at_period_end" boolean DEFAULT false NOT NULL,
	"metadata" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "pricing_catalog_settings" (
	"id" text PRIMARY KEY NOT NULL,
	"billing_mode" text DEFAULT 'subscription' NOT NULL,
	"currency" text DEFAULT 'USD' NOT NULL,
	"updated_by" text,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "payment_orders" ADD CONSTRAINT "payment_orders_pricing_option_id_pricing_options_id_fk" FOREIGN KEY ("pricing_option_id") REFERENCES "public"."pricing_options"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "pricing_options" ADD CONSTRAINT "pricing_options_plan_id_pricing_plans_id_fk" FOREIGN KEY ("plan_id") REFERENCES "public"."pricing_plans"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "subscriptions" ADD CONSTRAINT "subscriptions_pricing_option_id_pricing_options_id_fk" FOREIGN KEY ("pricing_option_id") REFERENCES "public"."pricing_options"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "admin_audit_events_resource_idx" ON "admin_audit_events" USING btree ("resource_type","resource_id","created_at");--> statement-breakpoint
CREATE UNIQUE INDEX "billing_events_provider_event_idx" ON "billing_events" USING btree ("provider","external_event_id");--> statement-breakpoint
CREATE UNIQUE INDEX "payment_orders_idempotency_idx" ON "payment_orders" USING btree ("idempotency_key");--> statement-breakpoint
CREATE UNIQUE INDEX "payment_orders_external_order_idx" ON "payment_orders" USING btree ("provider","external_order_ref");--> statement-breakpoint
CREATE INDEX "payment_orders_tenant_status_idx" ON "payment_orders" USING btree ("tenant_id","status");--> statement-breakpoint
CREATE UNIQUE INDEX "payment_provider_settings_provider_idx" ON "payment_provider_settings" USING btree ("provider");--> statement-breakpoint
CREATE UNIQUE INDEX "pricing_options_identity_idx" ON "pricing_options" USING btree ("plan_id","mode","interval","provider");--> statement-breakpoint
CREATE INDEX "pricing_options_plan_active_idx" ON "pricing_options" USING btree ("plan_id","active");--> statement-breakpoint
CREATE UNIQUE INDEX "pricing_plans_tenant_code_idx" ON "pricing_plans" USING btree ("tenant_id","code");--> statement-breakpoint
CREATE INDEX "pricing_plans_active_order_idx" ON "pricing_plans" USING btree ("tenant_id","active","display_order");--> statement-breakpoint
CREATE UNIQUE INDEX "subscriptions_external_ref_idx" ON "subscriptions" USING btree ("provider","external_subscription_ref");--> statement-breakpoint
CREATE INDEX "subscriptions_tenant_status_idx" ON "subscriptions" USING btree ("tenant_id","status");
--> statement-breakpoint
ALTER TABLE "pricing_options" ADD CONSTRAINT "pricing_options_mode_interval_check" CHECK (("mode" = 'one_time' AND "interval" = 'one_time') OR ("mode" = 'subscription' AND "interval" IN ('month', 'year')));
--> statement-breakpoint
ALTER TABLE "pricing_options" ADD CONSTRAINT "pricing_options_amount_positive_check" CHECK ("amount_minor" > 0);
--> statement-breakpoint
ALTER TABLE "pricing_plans" ADD CONSTRAINT "pricing_plans_billing_mode_check" CHECK ("billing_mode" IN ('one_time', 'subscription'));
--> statement-breakpoint
INSERT INTO "pricing_plans" ("id", "tenant_id", "code", "name", "description", "billing_mode", "is_default", "display_order", "features", "quotas") VALUES
  ('plan-starter', 'platform', 'starter', 'Starter', 'A small, production-shaped workspace for trying the foundation.', 'subscription', true, 10, '["1 workspace", "100 proposal reviews", "Mock or sandbox checkout"]'::jsonb, '{"monthlyRuns":100,"members":1}'::jsonb),
  ('plan-pro', 'platform', 'pro', 'Pro', 'A portfolio-ready plan with higher bounded usage and team handoff.', 'subscription', false, 20, '["5 workspaces", "1,000 proposal reviews", "Usage and audit history"]'::jsonb, '{"monthlyRuns":1000,"members":5}'::jsonb),
  ('plan-lifetime', 'platform', 'lifetime', 'Lifetime', 'A separate one-time product. It is not mixed with subscription plans.', 'one_time', false, 30, '["One payment", "No recurring renewal", "Bounded portfolio license"]'::jsonb, '{"monthlyRuns":1000,"members":1}'::jsonb)
ON CONFLICT ("id") DO NOTHING;
--> statement-breakpoint
INSERT INTO "pricing_options" ("id", "plan_id", "mode", "interval", "provider", "currency", "amount_minor", "compare_at_amount_minor") VALUES
  ('option-starter-monthly', 'plan-starter', 'subscription', 'month', 'mock', 'USD', 900, NULL),
  ('option-starter-yearly', 'plan-starter', 'subscription', 'year', 'mock', 'USD', 9000, 10800),
  ('option-pro-monthly', 'plan-pro', 'subscription', 'month', 'mock', 'USD', 2900, 3900),
  ('option-pro-yearly', 'plan-pro', 'subscription', 'year', 'mock', 'USD', 29000, 34800),
  ('option-lifetime-onetime', 'plan-lifetime', 'one_time', 'one_time', 'mock', 'USD', 7900, NULL)
ON CONFLICT ("id") DO NOTHING;
--> statement-breakpoint
INSERT INTO "pricing_catalog_settings" ("id", "billing_mode", "currency", "updated_by") VALUES
  ('platform', 'subscription', 'USD', 'migration-seed')
ON CONFLICT ("id") DO NOTHING;
--> statement-breakpoint
INSERT INTO "payment_provider_settings" ("id", "provider", "enabled", "sandbox", "secret_ref") VALUES
  ('provider-mock', 'mock', true, true, NULL),
  ('provider-toss', 'toss', false, true, 'TOSS_SECRET_KEY'),
  ('provider-lemon-squeezy', 'lemon-squeezy', false, true, 'LEMONSQUEEZY_API_KEY')
ON CONFLICT ("provider") DO NOTHING;
