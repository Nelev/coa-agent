"use client"

import { useEffect } from "react"

import { toResult, toStep, type ResultJson, type StepJson } from "@/model/api"
import type { Run } from "@/model/Run"
import { useRunStore } from "@/store/run-store"

// What a `phase` event carries.
interface PhaseJson {
  phase: Run["phase"]
  pending_question: Run["pendingQuestion"]
  result: ResultJson | null
}

// Follows the agent run: each step as it is written, and the phase (running,
// waiting for an answer, done with its result and draft). Same origin: the
// route handler under app/runs/[id]/events proxies the API, so the browser
// never calls it. EventSource reconnects on its own and sends Last-Event-ID;
// the API resumes from there, and the store ignores a seq it already has.
export function useRunEvents(runId: string | null) {
  useEffect(() => {
    if (!runId) return
    const { addStep, patchAgent } = useRunStore.getState()
    const source = new EventSource(`/runs/${runId}/events`)

    source.addEventListener("step", (ev) =>
      addStep(toStep(JSON.parse((ev as MessageEvent).data) as StepJson)),
    )

    source.addEventListener("phase", (ev) => {
      const p = JSON.parse((ev as MessageEvent).data) as PhaseJson
      patchAgent(runId, {
        phase: p.phase,
        pendingQuestion: p.pending_question,
        result: p.result && toResult(p.result),
      })
    })

    // The API ends the stream once the run is over. Closing here stops
    // EventSource from reconnecting to a finished run.
    source.addEventListener("done", () => source.close())

    return () => source.close()
  }, [runId])
}
