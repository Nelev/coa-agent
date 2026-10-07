"use client"

import { useEffect } from "react"

import { useRunStore } from "@/store/run-store"
import type { Step } from "@/model/Step"

// The stream's payload, as the API writes it.
interface StepEvent {
  seq: number
  tool: string | null
  input: Step["input"]
  output: Step["output"]
  reasoning: string | null
  tokens_in: number
  tokens_out: number
  ms: number
}

export const toStep = (e: StepEvent): Step => ({
  seq: e.seq,
  tool: e.tool,
  input: e.input,
  output: e.output,
  reasoning: e.reasoning,
  tokensIn: e.tokens_in,
  tokensOut: e.tokens_out,
  ms: e.ms,
})

// Subscribes to the run's steps. Same origin: the route handler under
// app/runs/[id]/events proxies the API, so the browser never calls it.
// EventSource reconnects on its own and sends Last-Event-ID; the API resumes
// from there, and the store ignores a seq it already has.
export function useRunEvents(runId: string | null) {
  const addStep = useRunStore((s) => s.addStep)

  useEffect(() => {
    if (!runId) return
    const source = new EventSource(`/runs/${runId}/events`)
    source.addEventListener("step", (ev) =>
      addStep(toStep(JSON.parse((ev as MessageEvent).data))),
    )
    // The API closes the stream with a `done` event once the run is over;
    // closing here stops EventSource from reconnecting to a finished run.
    source.addEventListener("done", () => source.close())
    return () => source.close()
  }, [runId, addStep])
}
