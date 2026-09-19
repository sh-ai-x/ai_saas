import { PublicLanding } from "@/components/public-landing";
import { SessionControl } from "@/components/auth/session-control";
import { getBillingPolicy, listPricingCatalog } from "@/lib/pricing/repository";

export default async function HomePage() {
  const [plans, billing] = await Promise.all([listPricingCatalog(true), getBillingPolicy()]);
  return <PublicLanding plans={plans} source={process.env.DATABASE_URL ? "neon" : "local-seed"} billingMode={billing.billingMode} sessionControl={<SessionControl />} />;
}
