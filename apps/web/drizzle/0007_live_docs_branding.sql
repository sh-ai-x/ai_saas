UPDATE "faq_entries"
SET "question" = 'Live Docs는 무엇인가요?',
    "answer" = 'Live Docs는 인증, 프로젝트 실행, 결제, 관리자 기능과 문서·코드 변경 영향 분석을 하나의 웹 콘솔에서 확인할 수 있는 서비스입니다.',
    "aliases" = '["Live Docs", "서비스 소개", "무엇을 할 수 있나요?"]'::jsonb,
    "updated_at" = now()
WHERE "id" = 'faq-getting-started' AND "locale" = 'ko';
--> statement-breakpoint
UPDATE "faq_entries"
SET "question" = 'What is Live Docs?',
    "answer" = 'Live Docs compares an AI engineering proposal with a local Git repository and presents bounded implementation and code-impact evidence.',
    "aliases" = '["Live Docs", "service overview", "what can I do here?"]'::jsonb,
    "updated_at" = now()
WHERE "id" = 'faq-getting-started' AND "locale" = 'en';
