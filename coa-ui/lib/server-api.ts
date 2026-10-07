// Server-only: where the API is, and how a route handler passes its answer on.
// API_BASE_URL is read at request time (so one build runs anywhere) and is never
// a NEXT_PUBLIC_ variable: the browser must not know the API's address.
export const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000"

// Streams the API's answer to `path` through, with `responseHeaders` on it; or
// an empty response with the API's status, and 502 when it cannot be reached.
export async function proxy(
  path: string,
  responseHeaders: HeadersInit,
  init?: RequestInit,
): Promise<Response> {
  try {
    const upstream = await fetch(`${API_BASE_URL}${path}`, {
      cache: "no-store",
      ...init,
    })

    return upstream.ok
      ? new Response(upstream.body, { headers: responseHeaders })
      : new Response(null, { status: upstream.status })
  } catch {
    return new Response(null, { status: 502 })
  }
}
