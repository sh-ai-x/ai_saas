import { createFaqHttp } from '@/lib/faq/http';
import { createOpenAiProvider } from '@/lib/faq/openai';
import { faqRepository } from '@/lib/faq/repository';
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
const handlers = createFaqHttp(faqRepository, createOpenAiProvider({ enabled: process.env.FAQ_OPENAI_ENABLED === 'true', key: process.env.OPENAI_API_KEY, endpoint: process.env.OPENAI_API_URL, model: process.env.OPENAI_MODEL, timeoutMs: Number(process.env.OPENAI_TIMEOUT_MS) || undefined }));
export const GET = handlers.GET;
export const POST = handlers.POST;
