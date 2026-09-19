import { NextRequest, NextResponse } from "next/server";

import { safeAuthError } from "@/lib/auth/config";
import { getSafeSession } from "@/lib/auth/session";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  try {
    return NextResponse.json({ session: await getSafeSession(request) });
  } catch (error) {
    return NextResponse.json(safeAuthError(error), { status: 503 });
  }
}
