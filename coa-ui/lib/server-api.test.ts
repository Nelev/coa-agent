import { describe, expect, it, vi } from "vitest"

import { proxy } from "@/lib/server-api"

describe("proxy", () => {
  it("passes the API's body through with the headers it was given", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("pdf bytes")))
    const response = await proxy("/pdfs/x", {
      "Content-Type": "application/pdf",
    })

    expect(response.headers.get("content-type")).toBe("application/pdf")
    expect(await response.text()).toBe("pdf bytes")
  })

  it("asks the API at API_BASE_URL, uncached, with the caller's request options", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response("x"))
    vi.stubGlobal("fetch", fetch)
    await proxy("/runs/r/events", {}, { headers: { "Last-Event-ID": "4" } })

    const [url, init] = fetch.mock.calls[0]
    expect(url).toBe("http://localhost:8000/runs/r/events")
    expect(init).toMatchObject({
      cache: "no-store",
      headers: { "Last-Event-ID": "4" },
    })
  })

  it("answers with the API's status and no body when it refuses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("nope", { status: 404 })),
    )
    const response = await proxy("/pdfs/x", {})
    expect(response.status).toBe(404)
    expect(await response.text()).toBe("")
  })

  it("is a 502 when the API cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("ECONNREFUSED")))
    expect((await proxy("/pdfs/x", {})).status).toBe(502)
  })
})
