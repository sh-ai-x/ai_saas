CREATE TABLE IF NOT EXISTS "pricing_catalog_settings" (
	"id" text PRIMARY KEY NOT NULL,
	"billing_mode" text DEFAULT 'subscription' NOT NULL,
	"currency" text DEFAULT 'USD' NOT NULL,
	"updated_by" text,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "pricing_plans" ADD COLUMN IF NOT EXISTS "billing_mode" text DEFAULT 'subscription' NOT NULL;
