import { describe, expect, it, vi } from "vitest"

import { answerRun, listSamples, startBaseline, startRun } from "@/api/runs"
import { runResponse, samples } from "@/test/fixtures"

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
  it("maps the API's snake_case to camelCase, draft included", async () => {
    stubFetch(runResponse)
    const started = await startRun(new FormData())
    if (!("run" in started)) throw new Error("expected a run")
    const { run } = started

    expect(run.pdfId).toBe("pdf1")
    expect(run.pendingQuestion).toBeNull()
    expect(run.result?.draft).toEqual({
      subject: "Assay on lot NC-26-0413",
      body: "Dear Nordchem,",
    })
    expect(run.result?.findings[0]).toMatchObject({
      kind: "oos",
      specRef: "SPEC-1",
      likelyCoaError: true,
    })
  })

  it("posts the form to /runs and nothing else", async () => {
    const fetch = stubFetch(runResponse)
    const form = new FormData()
    form.set("sample", "coa_02_typo.pdf")
    await startRun(form)

    const [url, init] = fetch.mock.calls[0]
    expect(url).toBe("http://localhost:8000/runs")
    expect(init.method).toBe("POST")
    expect(init.body).toBe(form)
  })

  it("sends the baseline's pdf id as JSON", async () => {
    const fetch = stubFetch({ ...runResponse, kind: "baseline" })
    await startBaseline("pdf1")

    const [url, init] = fetch.mock.calls[0]
    expect(url).toBe("http://localhost:8000/baseline")
    expect(JSON.parse(init.body)).toEqual({ pdf_id: "pdf1" })
  })

  it("sends the answer as JSON to the run's answer route", async () => {
    const fetch = stubFetch(runResponse)
    await answerRun("run1", "Material B")

    const [url, init] = fetch.mock.calls[0]
    expect(url).toBe("http://localhost:8000/runs/run1/answer")
    expect(JSON.parse(init.body)).toEqual({ answer: "Material B" })
  })

  it("lists the samples", async () => {
    stubFetch(samples)
    expect(await listSamples()).toEqual(samples)
  })

  it.each([
    [413, /over the 10 MB limit/],
    [415, /not a PDF/],
    [503, /OPENROUTER_API_KEY/],
    [500, /could not be started/],
  ])(
    "says what a %i from the API means for a start",
    async (status, message) => {
      stubFetch({}, false, status)
      expect(await startRun(new FormData())).toEqual({
        error: expect.stringMatching(message),
      })
    },
  )

  it("throws for the other actions, which the UI reports as a failure", async () => {
    stubFetch({}, false, 409)
    await expect(answerRun("run1", "x")).rejects.toThrow("409")
    await expect(startBaseline("pdf1")).rejects.toThrow("409")
  })

  it("does not cache what it reads", async () => {
    const fetch = stubFetch(runResponse)
    await listSamples()
    expect(fetch.mock.calls[0][1].cache).toBe("no-store")
  })
})
