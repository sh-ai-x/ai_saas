import { createFaqHttp } from '@/lib/faq/http';
import { createJevProvider } from '@/lib/faq/jev';
import { faqRepository } from '@/lib/faq/repository';
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
const handlers = createFaqHttp(faqRepository, createJevProvider({ enabled: process.env.FAQ_JEV_ENABLED === 'true', key: process.env.JEV_API_KEY }));
export const GET = handlers.GET;
export const POST = handlers.POST;
