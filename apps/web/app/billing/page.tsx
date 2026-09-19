import { BillingCatalogPage } from "@/components/billing-catalog-page";
import { getSafeSession } from "@/lib/auth/session";
import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

export default async function BillingPage() {
  const session = await getSafeSession();
  if (!session) redirect("/login?next=/billing");
  return <BillingCatalogPage />;
}
