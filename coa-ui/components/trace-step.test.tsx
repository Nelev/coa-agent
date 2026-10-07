import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { TraceList } from "@/components/trace-list"
import { TraceStep } from "@/components/trace-step"
import { step } from "@/test/fixtures"
import { useRunStore } from "@/store/run-store"

describe("TraceStep", () => {
  it("shows the tool, its arguments, why, and what it cost", () => {
    render(
      <ul>
        <TraceStep
          step={step({
            tool: "get_lot_history",
            input: { test: "assay" },
            reasoning: "Checking whether 9.85 is a typo",
          })}
        />
      </ul>,
    )
    expect(screen.getByText("get_lot_history")).toBeInTheDocument()
    expect(screen.getByText("test=assay")).toBeInTheDocument()
    expect(
      screen.getByText("Checking whether 9.85 is a typo"),
    ).toBeInTheDocument()
    expect(screen.getByText(/1200\+300 tokens · 2100 ms/)).toBeInTheDocument()
  })

  it("marks a refused call", () => {
    render(
      <ul>
        <TraceStep
          step={step({ output: "Error: read_coa has not been run yet" })}
        />
      </ul>,
    )
    expect(screen.getByText("refused")).toBeInTheDocument()
    expect(screen.getByTestId("trace-step")).toHaveClass("border-red-300")
  })

  it("marks the pause for the user", () => {
    render(
      <ul>
        <TraceStep
          step={step({
            tool: "ask_user",
            output: { waiting_for_user: { question: "Which?", options: [] } },
          })}
        />
      </ul>,
    )
    expect(screen.getByText("waiting for the user")).toBeInTheDocument()
  })

  it("names a model reply that called no tool", () => {
    render(
      <ul>
        <TraceStep
          step={step({ tool: null, output: null, reasoning: "Looks fine." })}
        />
      </ul>,
    )
    expect(screen.getByText("model reply")).toBeInTheDocument()
  })
})

describe("TraceList", () => {
  it("totals the calls, tokens and tool time", () => {
    useRunStore.getState().addStep(step({ seq: 1 }))
    useRunStore
      .getState()
      .addStep(step({ seq: 2, tool: "normalize", ms: 1000 }))
    render(<TraceList phase="done" />)
    expect(screen.getByTestId("totals")).toHaveTextContent(
      "2 tool calls · 3000 tokens · 3.1 s in tools",
    )
    expect(screen.getAllByTestId("trace-step")).toHaveLength(2)
  })

  it("says it is starting, and that it is working", () => {
    const { rerender } = render(<TraceList phase="running" />)
    expect(screen.getByText("Starting…")).toBeInTheDocument()
    useRunStore.getState().addStep(step())
    rerender(<TraceList phase="running" />)
    expect(screen.getByRole("status")).toHaveTextContent("Working")
  })
})
