import { renderHook } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { useRunEvents } from "@/hooks/use-run-events"
import { run, runResponse, stepEvent } from "@/test/fixtures"
import { useRunStore } from "@/store/run-store"

// Just enough of EventSource to drive the hook by hand.
class FakeEventSource {
  static instances: FakeEventSource[] = []
  listeners: Record<string, ((ev: MessageEvent) => void)[]> = {}
  closed = false
  constructor(public url: string) {
    FakeEventSource.instances.push(this)
  }
  addEventListener(type: string, fn: (ev: MessageEvent) => void) {
    ;(this.listeners[type] ??= []).push(fn)
  }
  close() {
    this.closed = true
  }
  emit(type: string, data: unknown) {
    for (const fn of this.listeners[type] ?? [])
      fn({ data: JSON.stringify(data) } as MessageEvent)
  }
}

const source = () => FakeEventSource.instances.at(-1)!

beforeEach(() => {
  FakeEventSource.instances = []
  vi.stubGlobal("EventSource", FakeEventSource)
})

describe("useRunEvents", () => {
  it("opens nothing without a run", () => {
    renderHook(() => useRunEvents(null))
    expect(FakeEventSource.instances).toHaveLength(0)
  })

  it("subscribes to the run on this origin", () => {
    renderHook(() => useRunEvents("run1"))
    expect(source().url).toBe("/runs/run1/events")
  })

  it("adds each step once, even when a reconnect replays it", () => {
    renderHook(() => useRunEvents("run1"))
    source().emit("step", stepEvent)
    source().emit("step", { ...stepEvent, seq: 2, tool: "normalize" })
    source().emit("step", stepEvent)

    expect(useRunStore.getState().steps.map((s) => s.tool)).toEqual([
      "read_coa",
      "normalize",
    ])
    expect(useRunStore.getState().steps[0].tokensIn).toBe(1200)
  })

  it("shows the question when the run is waiting", () => {
    useRunStore.getState().setAgent(run({ id: "run1" }))
    renderHook(() => useRunEvents("run1"))
    source().emit("phase", {
      phase: "waiting",
      pending_question: { question: "Which?", options: ["A", "B"] },
      result: null,
    })

    expect(useRunStore.getState().agent).toMatchObject({
      phase: "waiting",
      pendingQuestion: { question: "Which?", options: ["A", "B"] },
    })
  })

  it("ignores a phase for a run that is no longer the one on screen", () => {
    useRunStore.getState().setAgent(run({ id: "another" }))
    renderHook(() => useRunEvents("run1"))
    source().emit("phase", {
      phase: "done",
      pending_question: null,
      result: null,
    })
    expect(useRunStore.getState().agent?.phase).toBe("running")
  })

  it("a done phase brings the result and its draft, with nothing to fetch", () => {
    useRunStore.getState().setAgent(run({ id: "run1" }))
    renderHook(() => useRunEvents("run1"))
    source().emit("phase", {
      phase: "done",
      pending_question: null,
      result: runResponse.result,
    })
    source().emit("done", { phase: "done" })

    expect(useRunStore.getState().agent).toMatchObject({
      phase: "done",
      result: {
        status: "REVIEW",
        draft: { subject: "Assay on lot NC-26-0413" },
      },
    })
    expect(source().closed).toBe(true)
  })

  it("closes the stream when the run changes or the page goes away", () => {
    const { rerender, unmount } = renderHook(({ id }) => useRunEvents(id), {
      initialProps: { id: "run1" },
    })
    const first = source()
    rerender({ id: "run2" })
    expect(first.closed).toBe(true)
    const second = source()
    unmount()
    expect(second.closed).toBe(true)
  })
})
