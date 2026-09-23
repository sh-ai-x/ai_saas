UPDATE "faq_entries"
SET "locale" = 'en', "category" = 'general', "question" = 'What is AI Change Impact Workbench?', "answer" = 'AI Change Impact Workbench compares an AI engineering proposal with a local Git repository and presents bounded implementation and code-impact evidence.', "aliases" = '["service overview", "what can I do here?"]'::jsonb, "updated_at" = now()
WHERE "id" = 'faq-getting-started';
--> statement-breakpoint
UPDATE "faq_entries"
SET "locale" = 'en', "category" = 'authentication', "question" = 'How do I sign in with Google?', "answer" = 'Select Continue with Google on the login screen. If Google OAuth is not configured, the login screen shows setup guidance.', "aliases" = '["Google login", "how to log in", "sign up"]'::jsonb, "updated_at" = now()
WHERE "id" = 'faq-google-login';
--> statement-breakpoint
UPDATE "faq_entries"
SET "locale" = 'en', "category" = 'development', "question" = 'How do I run the project locally?', "answer" = 'From the repository root, run pnpm install. Use pnpm docker:local for Docker or pnpm --filter ai-saas-foundation-web dev to run the web workbench.', "aliases" = '["local setup", "development environment", "getting started"]'::jsonb, "updated_at" = now()
WHERE "id" = 'faq-local-development';
--> statement-breakpoint
DELETE FROM "faq_entries" WHERE "id" = 'faq-agent-run';
--> statement-breakpoint
UPDATE "faq_entries"
SET "locale" = 'en', "category" = 'billing', "question" = 'Where can I check pricing and billing options?', "answer" = 'Check the public Pricing screen for active plans and billing options. Administrators can manage the catalog and billing mode in Admin Pricing.', "aliases" = '["pricing", "billing", "plans", "subscription"]'::jsonb, "updated_at" = now()
WHERE "id" = 'faq-pricing-billing';
--> statement-breakpoint
UPDATE "faq_entries"
SET "locale" = 'en', "category" = 'support', "question" = 'What if the FAQ does not answer my question?', "answer" = 'Try asking a more specific question. If you still need help, use the support guide to contact the team.', "aliases" = '["contact support", "support request", "not resolved", "talk to a person"]'::jsonb, "updated_at" = now()
WHERE "id" = 'faq-support';
