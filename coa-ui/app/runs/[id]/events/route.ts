import { proxy } from "@/lib/server-api"

// Proxies the API's event stream, so the browser never calls the API (and the
// API needs no CORS).
export async function GET(
  request: Request,
  ctx: RouteContext<"/runs/[id]/events">,
) {
  const { id } = await ctx.params
  const headers: Record<string, string> = { Accept: "text/event-stream" }
  const lastEventId = request.headers.get("last-event-id")
  if (lastEventId) headers["Last-Event-ID"] = lastEventId

  return proxy(
    `/runs/${encodeURIComponent(id)}/events`,
    {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
    },
    // Closing the browser tab closes the upstream stream too.
    { headers, signal: request.signal },
  )
}
