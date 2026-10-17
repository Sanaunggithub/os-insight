type RouteContext = {
  params: Promise<{ path: string[] }>;
};

async function proxyToApi(request: Request, context: RouteContext) {
  const apiBaseUrl = process.env.API_BASE_URL?.replace(/\/+$/, "");
  if (!apiBaseUrl) {
    return Response.json(
      { detail: "API_BASE_URL is not configured" },
      { status: 503 },
    );
  }

  const { path } = await context.params;
  const incomingUrl = new URL(request.url);
  const endpoint = path.map(encodeURIComponent).join("/");
  const targetUrl = `${apiBaseUrl}/${endpoint}${incomingUrl.search}`;
  const contentType = request.headers.get("content-type");

  try {
    const upstream = await fetch(targetUrl, {
      method: request.method,
      headers: {
        accept: request.headers.get("accept") ?? "application/json",
        ...(contentType ? { "content-type": contentType } : {}),
      },
      body:
        request.method === "GET" || request.method === "HEAD"
          ? undefined
          : await request.arrayBuffer(),
      cache: "no-store",
    });
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        "content-type":
          upstream.headers.get("content-type") ?? "application/json",
        "cache-control": "no-store",
      },
    });
  } catch (error) {
    console.error("API proxy request failed", error);
    return Response.json({ detail: "API service is unavailable" }, { status: 502 });
  }
}

export const GET = proxyToApi;
export const POST = proxyToApi;
