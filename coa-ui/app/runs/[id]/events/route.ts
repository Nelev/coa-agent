// Proxies the API's event stream. The browser never calls the API directly
// (and so the API needs no CORS): API_BASE_URL is read here, on the server.
const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000"

export async function GET(
  request: Request,
  ctx: RouteContext<"/runs/[id]/events">,
) {
  const { id } = await ctx.params

  const headers: Record<string, string> = { Accept: "text/event-stream" }
  const lastEventId = request.headers.get("last-event-id")
  if (lastEventId) headers["Last-Event-ID"] = lastEventId

  const upstream = await fetch(`${API_BASE_URL}/runs/${id}/events`, {
    headers,
    // Closing the browser tab closes the upstream stream too.
    signal: request.signal,
  })

  if (!upstream.ok || !upstream.body) {
    return new Response(null, { status: upstream.status || 502 })
  }

  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  })
}
