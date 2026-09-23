UPDATE "pricing_plans"
SET "features" = '["1 workspace", "100 proposal reviews", "Mock or sandbox checkout"]'::jsonb
WHERE "id" = 'plan-starter';
--> statement-breakpoint
UPDATE "pricing_plans"
SET "features" = '["5 workspaces", "1,000 proposal reviews", "Usage and audit history"]'::jsonb
WHERE "id" = 'plan-pro';
