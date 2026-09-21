import { NextRequest, NextResponse } from "next/server";

import { requireAdmin } from "@/lib/admin-guard";
import { assertSandboxTossConfiguration } from "@/lib/payments/toss-billing";
import { listProviderSettings, updateProviderSetting } from "@/lib/pricing/repository";
import type { PricingProvider } from "@/lib/pricing/types";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  try {
    await requireAdmin(request);
    return NextResponse.json({ providers: await listProviderSettings() });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "admin authorization required" }, { status: 403 });
  }
}

export async function PATCH(request: NextRequest) {
  try {
    const { actorUserId } = await requireAdmin(request);
    const body = (await request.json()) as {
      provider?: PricingProvider;
      enabled?: boolean;
      sandbox?: boolean;
      publicConfig?: Record<string, unknown>;
      secretRef?: string | null;
      reason?: string;
    };
    if (!body.provider || !["mock", "toss", "lemon-squeezy"].includes(body.provider)) throw new Error("valid provider is required");
    const sandbox = body.sandbox ?? true;
    if (body.provider === "toss" && body.enabled && sandbox) assertSandboxTossConfiguration();
    if (body.provider === "toss" && body.enabled && !sandbox && process.env.APP_ENV !== "production") {
      throw new Error("Toss live mode can only be enabled in production");
    }
    const setting = await updateProviderSetting(body.provider, {
      enabled: body.enabled ?? false,
      sandbox,
      publicConfig: body.publicConfig ?? {},
      secretRef: body.secretRef ?? null,
    }, actorUserId, body.reason ?? "");
    return NextResponse.json({ provider: setting });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "could not update provider" }, { status: 400 });
  }
}
