UPDATE "faq_entries"
SET "locale" = 'en', "category" = 'general', "question" = 'What is AI SaaS Foundation?', "answer" = 'AI SaaS Foundation is a foundation service for authentication, project runs, billing, and administration in one web console.', "aliases" = '["service overview", "what can I do here?"]'::jsonb, "updated_at" = now()
WHERE "id" = 'faq-getting-started';
--> statement-breakpoint
UPDATE "faq_entries"
SET "locale" = 'en', "category" = 'authentication', "question" = 'How do I sign in with Google?', "answer" = 'Select Continue with Google on the login screen. If Google OAuth is not configured, the login screen shows setup guidance.', "aliases" = '["Google login", "how to log in", "sign up"]'::jsonb, "updated_at" = now()
WHERE "id" = 'faq-google-login';
--> statement-breakpoint
UPDATE "faq_entries"
SET "locale" = 'en', "category" = 'development', "question" = 'How do I run the project locally?', "answer" = 'From the repository root, run pnpm install. Use pnpm docker:local for Docker or pnpm --filter ai-saas-foundation-web dev to run only the web console.', "aliases" = '["local setup", "development environment", "getting started"]'::jsonb, "updated_at" = now()
WHERE "id" = 'faq-local-development';
--> statement-breakpoint
UPDATE "faq_entries"
SET "locale" = 'en', "category" = 'runs', "question" = 'How do I start an agent run?', "answer" = 'Start a run from the project screen in the web console. Review its status and events on the run details screen.', "aliases" = '["start a run", "run an agent", "run usage"]'::jsonb, "updated_at" = now()
WHERE "id" = 'faq-agent-run';
--> statement-breakpoint
UPDATE "faq_entries"
SET "locale" = 'en', "category" = 'billing', "question" = 'Where can I check pricing and billing options?', "answer" = 'Check the public Pricing screen for active plans and billing options. Administrators can manage the catalog and billing mode in Admin Pricing.', "aliases" = '["pricing", "billing", "plans", "subscription"]'::jsonb, "updated_at" = now()
WHERE "id" = 'faq-pricing-billing';
--> statement-breakpoint
UPDATE "faq_entries"
SET "locale" = 'en', "category" = 'support', "question" = 'What if the FAQ does not answer my question?', "answer" = 'Try asking a more specific question. If you still need help, use the support guide to contact the team.', "aliases" = '["contact support", "support request", "not resolved", "talk to a person"]'::jsonb, "updated_at" = now()
WHERE "id" = 'faq-support';
