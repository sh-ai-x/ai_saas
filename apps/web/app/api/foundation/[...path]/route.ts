import { NextRequest } from "next/server";

const foundationApiUrl =
  process.env.FOUNDATION_API_URL ?? "http://127.0.0.1:8080";

type RouteContext = { params: Promise<{ path: string[] }> };

async function proxy(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  const target = `${foundationApiUrl.replace(/\/$/, "")}/${path.join("/")}${
    request.nextUrl.search
  }`;
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  const tenantId = request.headers.get("x-tenant-id");
  const sessionId = request.headers.get("x-session-id");
  const lastEventId = request.headers.get("last-event-id");
  const cookie = request.headers.get("cookie");
  if (contentType) headers.set("content-type", contentType);
  if (tenantId) headers.set("x-tenant-id", tenantId);
  if (sessionId) headers.set("x-session-id", sessionId);
  if (lastEventId) headers.set("last-event-id", lastEventId);
  if (cookie) headers.set("cookie", cookie);

  // Materialize the incoming body before forwarding it. Passing the
  // NextRequest stream directly can result in an empty upstream body when
  // the route is exercised through the App Router dev server.
  const body =
    request.method === "GET" || request.method === "HEAD"
      ? undefined
      : await request.arrayBuffer();

  const upstream = await fetch(target, {
    method: request.method,
    headers,
    body,
    cache: "no-store",
  } as RequestInit);

  const responseHeaders = new Headers();
  const responseType = upstream.headers.get("content-type");
  const setCookie = upstream.headers.get("set-cookie");
  if (responseType) responseHeaders.set("content-type", responseType);
  if (setCookie) responseHeaders.set("set-cookie", setCookie);
  responseHeaders.set("cache-control", "no-store");
  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export const GET = proxy;
export const POST = proxy;
