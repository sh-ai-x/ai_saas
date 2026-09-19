import { NextRequest, NextResponse } from "next/server";

import { requireAdmin } from "@/lib/admin-guard";
import { listProviderSettings, updateProviderSetting } from "@/lib/pricing/repository";
import type { PricingProvider } from "@/lib/pricing/types";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  try {
    requireAdmin(request);
    return NextResponse.json({ providers: await listProviderSettings() });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "admin authorization required" }, { status: 403 });
  }
}

export async function PATCH(request: NextRequest) {
  try {
    const { actorUserId } = requireAdmin(request);
    const body = (await request.json()) as {
      provider?: PricingProvider;
      enabled?: boolean;
      sandbox?: boolean;
      publicConfig?: Record<string, unknown>;
      secretRef?: string | null;
      reason?: string;
    };
    if (!body.provider || !["mock", "toss", "lemon-squeezy"].includes(body.provider)) throw new Error("valid provider is required");
    const setting = await updateProviderSetting(body.provider, {
      enabled: body.enabled ?? false,
      sandbox: body.sandbox ?? true,
      publicConfig: body.publicConfig ?? {},
      secretRef: body.secretRef ?? null,
    }, actorUserId, body.reason ?? "");
    return NextResponse.json({ provider: setting });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "could not update provider" }, { status: 400 });
  }
}
