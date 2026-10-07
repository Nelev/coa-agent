import { proxy } from "@/lib/server-api"

// The uploaded PDF for the viewer. Like the event stream, it keeps the browser
// off the API.
export async function GET(_request: Request, ctx: RouteContext<"/pdfs/[id]">) {
  const { id } = await ctx.params

  return proxy(`/pdfs/${encodeURIComponent(id)}`, {
    "Content-Type": "application/pdf",
  })
}
