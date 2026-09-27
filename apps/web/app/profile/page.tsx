import { redirect } from "next/navigation";

import { ProfileSubscription } from "@/components/profile-subscription";
import { getSafeSession } from "@/lib/auth/session";

export const dynamic = "force-dynamic";

export default async function ProfilePage() {
  const session = await getSafeSession();
  if (!session) redirect("/login?next=/profile");
  return <ProfileSubscription user={session.user} />;
}
