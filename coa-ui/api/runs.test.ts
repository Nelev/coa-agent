import { describe, expect, it, vi } from "vitest"

import { answerRun, startRun } from "@/api/runs"
import { runResponse } from "@/test/fixtures"

const stubFetch = (body: unknown, ok = true, status = 200) => {
  const fetch = vi.fn().mockResolvedValue({
    ok,
    status,
    json: async () => body,
  })
  vi.stubGlobal("fetch", fetch)
  return fetch
}

describe("api/runs", () => {
  it("maps the API's snake_case to camelCase", async () => {
    stubFetch(runResponse)
    const run = await startRun(new FormData())

    expect(run.pendingQuestion).toBeNull()
    expect(run.result?.draftId).toBe("d1")
    expect(run.result?.findings[0]).toMatchObject({
      specRef: "SPEC-1",
      likelyCoaError: true,
    })
  })

  it("sends the answer as JSON to the run's answer route", async () => {
    const fetch = stubFetch(runResponse)
    await answerRun("run1", "Material B")

    const [url, init] = fetch.mock.calls[0]
    expect(url).toBe("http://localhost:8000/runs/run1/answer")
    expect(JSON.parse(init.body)).toEqual({ answer: "Material B" })
  })

  it("throws on a refused request rather than rendering it", async () => {
    stubFetch({}, false, 415)
    await expect(startRun(new FormData())).rejects.toThrow("415")
  })
})
