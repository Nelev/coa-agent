import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { AskBox } from "@/components/ask-box"
import { run } from "@/test/fixtures"
import { useRunStore } from "@/store/run-store"

vi.mock("@/api/runs", () => ({ answerRun: vi.fn() }))
import { answerRun } from "@/api/runs"

const waiting = run({
  phase: "waiting",
  pendingQuestion: {
    question: "Which material is this CoA for?",
    options: ["Paracetamol API", "Paracetamol DC Granules 90%"],
  },
})

describe("AskBox", () => {
  it("is not there unless the run is waiting", () => {
    const { container, rerender } = render(<AskBox run={null} />)
    expect(container).toBeEmptyDOMElement()
    rerender(<AskBox run={run({ phase: "running" })} />)
    expect(container).toBeEmptyDOMElement()
  })

  it("shows the question and an option per candidate", () => {
    render(<AskBox run={waiting} />)
    expect(
      screen.getByText("Which material is this CoA for?"),
    ).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Paracetamol API" }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Paracetamol DC Granules 90%" }),
    ).toBeInTheDocument()
  })

  it("answers with the chosen option and shows the run as running again", async () => {
    useRunStore.getState().setAgent(waiting)
    vi.mocked(answerRun).mockResolvedValue()
    render(<AskBox run={waiting} />)
    await userEvent.click(
      screen.getByRole("button", { name: "Paracetamol API" }),
    )

    expect(answerRun).toHaveBeenCalledWith("run1", "Paracetamol API")
    expect(useRunStore.getState().agent?.phase).toBe("running")
  })

  it("sends a typed answer, trimmed, and not an empty one", async () => {
    vi.mocked(answerRun).mockResolvedValue()
    render(<AskBox run={waiting} />)
    const send = screen.getByRole("button", { name: "Send" })
    expect(send).toBeDisabled()

    await userEvent.type(screen.getByLabelText("Your answer"), "  MAT-001 ")
    await userEvent.click(send)
    expect(answerRun).toHaveBeenCalledWith("run1", "MAT-001")
  })

  it("reports a failed send instead of failing silently", async () => {
    vi.mocked(answerRun).mockRejectedValue(new Error("409"))
    render(<AskBox run={waiting} />)
    await userEvent.click(
      screen.getByRole("button", { name: "Paracetamol API" }),
    )
    expect(useRunStore.getState().error).toMatch(/could not be sent/)
  })
})
