import { create } from "zustand"

import type { Run } from "@/model/Run"
import type { Step } from "@/model/Step"

interface RunStore {
  agent: Run | null
  baseline: Run | null
  // Steps of the agent run, in seq order; the baseline's are not streamed.
  steps: Step[]
  setAgent: (run: Run | null) => void
  setBaseline: (run: Run | null) => void
  // Idempotent on seq: EventSource reconnects replay from Last-Event-ID, and
  // a step must never be shown twice.
  addStep: (step: Step) => void
  reset: () => void
}

export const useRunStore = create<RunStore>()((set) => ({
  agent: null,
  baseline: null,
  steps: [],
  setAgent: (agent) => set({ agent }),
  setBaseline: (baseline) => set({ baseline }),
  addStep: (step) =>
    set((s) =>
      s.steps.some((x) => x.seq === step.seq)
        ? s
        : { steps: [...s.steps, step].sort((a, b) => a.seq - b.seq) },
    ),
  reset: () => set({ agent: null, baseline: null, steps: [] }),
}))
