CREATE TABLE "faq_entries" (
	"id" text PRIMARY KEY NOT NULL,
	"category" text NOT NULL,
	"question" text NOT NULL,
	"aliases" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"answer" text NOT NULL,
	"active" boolean DEFAULT true NOT NULL
);
--> statement-breakpoint
INSERT INTO "faq_entries" ("id", "category", "question", "aliases", "answer") VALUES
('guides', 'guides', 'Where are the setup guides?', '["setup guides","documentation"]', 'Open Guides from the main navigation to find setup instructions and troubleshooting information.'),
('workspace', 'product', 'Where is the workspace?', '["open workspace","workspace"]', 'Open Workspace from the main navigation to access the application console.'),
('support', 'support', 'How can I get more help?', '["support","help"]', 'Use the Support guide link below for setup and troubleshooting help. This FAQ cannot access or change your account.');
