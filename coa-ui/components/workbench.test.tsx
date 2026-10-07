import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { Workbench } from "@/components/workbench"
import { run, samples, step } from "@/test/fixtures"
import { useRunStore } from "@/store/run-store"

vi.mock("@/api/runs", () => ({
  startRun: vi.fn(),
  startBaseline: vi.fn(),
  answerRun: vi.fn(),
  getRun: vi.fn(),
}))
vi.mock("@/hooks/use-run-events", () => ({ useRunEvents: vi.fn() }))
import { useRunEvents } from "@/hooks/use-run-events"

describe("Workbench", () => {
  it("starts empty, with nothing streaming", () => {
    render(<Workbench samples={samples} />)
    expect(screen.getByText("Upload a CoA to start.")).toBeInTheDocument()
    expect(
      screen.getByText("The CoA appears here once uploaded."),
    ).toBeInTheDocument()
    expect(useRunEvents).toHaveBeenLastCalledWith(null)
  })

  it("follows the agent run and shows its PDF, steps and question together", () => {
    useRunStore.getState().setAgent(
      run({
        phase: "waiting",
        pendingQuestion: { question: "Which material?", options: ["A"] },
      }),
    )
    useRunStore.getState().addStep(step())
    render(<Workbench samples={samples} />)

    expect(useRunEvents).toHaveBeenLastCalledWith("run1")
    expect(screen.getByTitle("Certificate of Analysis")).toHaveAttribute(
      "src",
      "/pdfs/pdf1",
    )
    expect(screen.getByText("Which material?")).toBeInTheDocument()
    expect(screen.getAllByTestId("trace-step")).toHaveLength(1)
  })

  it("shows an error, and a load error from the page", () => {
    useRunStore.getState().setError("The run could not be started.")
    const { rerender } = render(<Workbench samples={samples} />)
    expect(screen.getByRole("alert")).toHaveTextContent("could not be started")

    useRunStore.getState().setError(null)
    rerender(<Workbench samples={[]} loadError="The API is not reachable" />)
    expect(screen.getByRole("alert")).toHaveTextContent("not reachable")
  })
})
