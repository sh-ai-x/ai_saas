import { PublicLanding } from "@/components/public-landing";
import { SessionControl } from "@/components/auth/session-control";
import { applySelectedPaymentProvider, getBillingPolicy, listPricingCatalog, selectedPaymentProvider } from "@/lib/pricing/repository";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const [plans, billing, provider] = await Promise.all([listPricingCatalog(true), getBillingPolicy(), selectedPaymentProvider()]);
  return <PublicLanding plans={applySelectedPaymentProvider(plans, provider)} source={process.env.DATABASE_URL ? "neon" : "local-seed"} billingMode={billing.billingMode} sessionControl={<SessionControl />} />;
}
