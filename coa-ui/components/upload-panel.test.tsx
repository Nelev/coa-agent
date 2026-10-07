import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { UploadPanel } from "@/components/upload-panel"
import { run, samples, step } from "@/test/fixtures"
import { useRunStore } from "@/store/run-store"

vi.mock("@/api/runs", () => ({ startRun: vi.fn(), startBaseline: vi.fn() }))
import { startBaseline, startRun } from "@/api/runs"

beforeEach(() => {
  vi.mocked(startRun).mockReset().mockResolvedValue({ run: run() })
  vi.mocked(startBaseline)
    .mockReset()
    .mockResolvedValue(run({ id: "b1", kind: "baseline", phase: "done" }))
})

const runButton = () => screen.getByRole("button", { name: /^Run$|Starting/ })

describe("UploadPanel", () => {
  it("cannot run until a file or a sample is chosen", () => {
    render(<UploadPanel samples={samples} />)
    expect(runButton()).toBeDisabled()
  })

  it("lists the samples by scenario", () => {
    render(<UploadPanel samples={samples} />)
    expect(
      screen.getByRole("option", { name: "2. Assay printed 9.85 %" }),
    ).toBeInTheDocument()
  })

  it("starts the agent on a sample, then the baseline on the same PDF", async () => {
    render(<UploadPanel samples={samples} />)
    await userEvent.selectOptions(
      screen.getByLabelText("or a sample"),
      "coa_02_typo.pdf",
    )
    await userEvent.click(runButton())

    const form = vi.mocked(startRun).mock.calls[0][0]
    expect(form.get("sample")).toBe("coa_02_typo.pdf")
    expect(form.get("file")).toBeNull()
    expect(useRunStore.getState().agent?.id).toBe("run1")
    expect(startBaseline).toHaveBeenCalledWith("pdf1")
    await vi.waitFor(() =>
      expect(useRunStore.getState().baseline?.id).toBe("b1"),
    )
  })

  it("uploads a file instead, and disables the sample list", async () => {
    render(<UploadPanel samples={samples} />)
    const file = new File(["%PDF-1.4"], "my coa.pdf", {
      type: "application/pdf",
    })
    await userEvent.upload(screen.getByLabelText("Upload a CoA (PDF)"), file)

    expect(screen.getByLabelText("or a sample")).toBeDisabled()
    await userEvent.click(runButton())
    const form = vi.mocked(startRun).mock.calls[0][0]
    expect((form.get("file") as File).name).toBe("my coa.pdf")
    expect(form.get("sample")).toBeNull()
  })

  it("skips the baseline when asked to", async () => {
    render(<UploadPanel samples={samples} />)
    await userEvent.click(screen.getByLabelText("Also run the baseline"))
    await userEvent.selectOptions(
      screen.getByLabelText("or a sample"),
      "coa_01_clean.pdf",
    )
    await userEvent.click(runButton())
    expect(startBaseline).not.toHaveBeenCalled()
  })

  it("clears the previous run before starting another", async () => {
    useRunStore.getState().setAgent(run({ id: "old" }))
    useRunStore.getState().addStep(step())
    render(<UploadPanel samples={samples} />)
    await userEvent.selectOptions(
      screen.getByLabelText("or a sample"),
      "coa_01_clean.pdf",
    )
    await userEvent.click(runButton())
    expect(useRunStore.getState().steps).toEqual([])
    expect(useRunStore.getState().agent?.id).toBe("run1")
  })

  it("shows the API's reason when the run cannot start, and starts nothing", async () => {
    vi.mocked(startRun).mockResolvedValue({ error: "That file is not a PDF." })
    render(<UploadPanel samples={samples} />)
    await userEvent.selectOptions(
      screen.getByLabelText("or a sample"),
      "coa_01_clean.pdf",
    )
    await userEvent.click(runButton())

    expect(useRunStore.getState().error).toBe("That file is not a PDF.")
    expect(useRunStore.getState().agent).toBeNull()
    expect(startBaseline).not.toHaveBeenCalled()
    expect(runButton()).toBeEnabled()
  })

  it("reports a baseline that fails without losing the agent's run", async () => {
    vi.mocked(startBaseline).mockRejectedValue(new Error("500"))
    render(<UploadPanel samples={samples} />)
    await userEvent.selectOptions(
      screen.getByLabelText("or a sample"),
      "coa_01_clean.pdf",
    )
    await userEvent.click(runButton())
    await vi.waitFor(() =>
      expect(useRunStore.getState().error).toMatch(/baseline/),
    )
    expect(useRunStore.getState().agent?.id).toBe("run1")
  })
})
