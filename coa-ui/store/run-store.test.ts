import { describe, expect, it } from "vitest"

import { useRunStore } from "@/store/run-store"
import type { Step } from "@/model/Step"

const step = (seq: number): Step => ({
  seq,
  tool: "check_spec",
  input: null,
  output: null,
  reasoning: null,
  tokensIn: 0,
  tokensOut: 0,
  ms: 0,
})

describe("run store", () => {
  it("ignores a replayed step and keeps seq order", () => {
    const { addStep } = useRunStore.getState()
    addStep(step(2))
    addStep(step(1))
    addStep(step(2))

    expect(useRunStore.getState().steps.map((s) => s.seq)).toEqual([1, 2])
  })
})
