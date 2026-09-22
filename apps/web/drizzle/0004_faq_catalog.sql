CREATE TABLE "faq_entries" (
	"id" text PRIMARY KEY NOT NULL,
	"slug" text NOT NULL,
	"locale" text DEFAULT 'ko' NOT NULL,
	"category" text NOT NULL,
	"question" text NOT NULL,
	"answer" text NOT NULL,
	"aliases" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"active" boolean DEFAULT true NOT NULL,
	"display_order" integer DEFAULT 0 NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX "faq_entries_locale_slug_idx" ON "faq_entries" USING btree ("locale","slug");--> statement-breakpoint
CREATE INDEX "faq_entries_active_order_idx" ON "faq_entries" USING btree ("locale","active","display_order");--> statement-breakpoint
CREATE INDEX "faq_entries_category_active_idx" ON "faq_entries" USING btree ("locale","category","active");
--> statement-breakpoint
INSERT INTO "faq_entries" ("id", "slug", "locale", "category", "question", "answer", "aliases", "display_order") VALUES
  ('faq-getting-started', 'getting-started', 'ko', 'general', 'AI SaaS Foundation은 무엇인가요?', 'AI SaaS Foundation은 인증, 프로젝트 실행, 결제, 관리자 기능을 하나의 웹 콘솔에서 확인할 수 있는 기반 서비스입니다.', '["서비스 소개", "무엇을 할 수 있나요?"]'::jsonb, 10),
  ('faq-google-login', 'google-login', 'ko', 'authentication', 'Google로 로그인하려면 어떻게 하나요?', '로그인 화면에서 Continue with Google을 선택하세요. Google OAuth가 아직 설정되지 않은 환경에서는 설정 안내가 표시됩니다.', '["구글 로그인", "로그인 방법", "회원가입"]'::jsonb, 20),
  ('faq-local-development', 'local-development', 'ko', 'development', '로컬에서 어떻게 실행하나요?', '저장소 루트에서 pnpm install 후 Docker는 pnpm docker:local, 웹 콘솔만 실행할 때는 pnpm --filter ai-saas-foundation-web dev를 사용하세요.', '["로컬 실행", "개발 환경", "시작 방법"]'::jsonb, 30),
  ('faq-agent-run', 'agent-run', 'ko', 'runs', 'Agent run은 어떻게 시작하나요?', '웹 콘솔의 프로젝트 화면에서 실행을 시작할 수 있습니다. 실행 상태와 이벤트는 실행 상세 화면에서 확인합니다.', '["실행 시작", "에이전트 실행", "run 사용법"]'::jsonb, 40),
  ('faq-pricing-billing', 'pricing-billing', 'ko', 'billing', '요금제와 결제 옵션은 어디서 확인하나요?', '공개 Pricing 화면에서 활성 요금제와 결제 옵션을 확인할 수 있습니다. 관리자는 Admin Pricing에서 카탈로그와 청구 모드를 관리합니다.', '["가격", "결제", "플랜", "요금제"]'::jsonb, 50),
  ('faq-support', 'support', 'ko', 'support', 'FAQ에서 답을 찾지 못하면 어떻게 하나요?', '질문을 조금 더 구체적으로 다시 입력해 보세요. 그래도 해결되지 않으면 지원 요청을 통해 문의해 주세요.', '["문의", "지원 요청", "해결되지 않음", "사람에게 문의"]'::jsonb, 60)
ON CONFLICT ("id") DO NOTHING;
