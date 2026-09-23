import { createFaqHttp } from '@/lib/faq/http';
import { createJevProvider } from '@/lib/faq/jev';
import { createOpenAiProvider } from '@/lib/faq/openai';
import { faqRepository } from '@/lib/faq/repository';
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
const provider = process.env.FAQ_PROVIDER === 'jev'
  ? createJevProvider({ enabled: true, key: process.env.JEV_API_KEY, endpoint: process.env.JEV_API_URL, model: process.env.JEV_MODEL, timeoutMs: Number(process.env.JEV_TIMEOUT_MS) || undefined })
  : createOpenAiProvider({ enabled: process.env.FAQ_OPENAI_ENABLED === 'true', key: process.env.OPENAI_API_KEY, endpoint: process.env.OPENAI_API_URL, model: process.env.OPENAI_MODEL, timeoutMs: Number(process.env.OPENAI_TIMEOUT_MS) || undefined });
const handlers = createFaqHttp(faqRepository, provider);
export const GET = handlers.GET;
export const POST = handlers.POST;
