import { create } from "zustand"

import type { Run } from "@/model/Run"
import type { Step } from "@/model/Step"

interface RunStore {
  agent: Run | null
  baseline: Run | null
  // Steps of the agent run, in seq order; the baseline's are not streamed.
  steps: Step[]
  // Something the user should see went wrong (a refused upload, API down).
  error: string | null
  setAgent: (run: Run | null) => void
  setBaseline: (run: Run | null) => void
  setError: (error: string | null) => void
  // Idempotent on seq: EventSource reconnects replay from Last-Event-ID, and
  // a step must never be shown twice.
  addStep: (step: Step) => void
  // Changes part of the agent run, but only if it is still the one on screen:
  // an event for a run the user has since replaced is dropped.
  patchAgent: (runId: string, patch: Partial<Run>) => void
  reset: () => void
}

export const useRunStore = create<RunStore>()((set) => ({
  agent: null,
  baseline: null,
  steps: [],
  error: null,
  setAgent: (agent) => set({ agent }),
  setBaseline: (baseline) => set({ baseline }),
  setError: (error) => set({ error }),
  addStep: (step) =>
    set((s) =>
      s.steps.some((x) => x.seq === step.seq)
        ? s
        : { steps: [...s.steps, step].sort((a, b) => a.seq - b.seq) },
    ),
  patchAgent: (runId, patch) =>
    set((s) =>
      s.agent?.id === runId ? { agent: { ...s.agent, ...patch } } : s,
    ),
  reset: () => set({ agent: null, baseline: null, steps: [], error: null }),
}))
