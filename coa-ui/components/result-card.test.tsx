import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { ResultCard } from "@/components/result-card"
import { toRun } from "@/model/api"
import type { Run } from "@/model/Run"
import { run, runResponse } from "@/test/fixtures"

const card = (r: Run | null) =>
  render(<ResultCard title="Agent result" run={r} emptyText="Upload a CoA." />)

describe("ResultCard", () => {
  it("says what it is waiting for before there is a run", () => {
    card(null)
    expect(screen.getByText("Upload a CoA.")).toBeInTheDocument()
  })

  it("shows progress while the run has no result", () => {
    card(run({ phase: "running" }))
    expect(screen.getByRole("status")).toHaveTextContent("Running")
  })

  it("says when it is the user's turn, and when the run failed", () => {
    const { unmount } = card(run({ phase: "waiting" }))
    expect(screen.getByRole("status")).toHaveTextContent(
      "Waiting for your answer",
    )
    unmount()
    card(run({ phase: "error" }))
    expect(screen.getByRole("status")).toHaveTextContent("The run failed")
  })

  it("shows the status, the summary, the finding with its evidence and the draft", () => {
    card(toRun(runResponse))
    expect(screen.getByTestId("status")).toHaveTextContent("REVIEW")
    expect(screen.getByText(/ten times the lot history/)).toBeInTheDocument()
    expect(screen.getByText("assay")).toBeInTheDocument()
    expect(
      screen.getByText(/Likely CoA error: last 10 lots/),
    ).toBeInTheDocument()
    expect(screen.getByText(/not sent/i)).toBeInTheDocument()
    expect(screen.getByText("Assay on lot NC-26-0413")).toBeInTheDocument()
  })

  it("describes a missing test and an expired approval in words", () => {
    const base = toRun(runResponse)
    const findings = [
      {
        ...base.result!.findings[0],
        test: "residual_solvents",
        kind: "missing" as const,
        value: null,
        likelyCoaError: false,
      },
      {
        ...base.result!.findings[0],
        test: "supplier",
        kind: "expired" as const,
        value: null,
        likelyCoaError: false,
        evidence: "approval expired on 2026-09-15",
      },
    ]
    card({
      ...base,
      result: { ...base.result!, status: "FAIL", findings, draft: null },
    })
    expect(screen.getByText(/required test missing/)).toBeInTheDocument()
    expect(
      screen.getByText(/approval expired on 2026-09-15/),
    ).toBeInTheDocument()
    expect(screen.queryByText(/not sent/i)).not.toBeInTheDocument()
  })

  it("shows a baseline that could not run as ERROR", () => {
    const base = toRun({ ...runResponse, kind: "baseline" })
    card({
      ...base,
      result: {
        ...base.result!,
        status: "ERROR",
        findings: [],
        summary: "The pipeline cannot ask.",
        draft: null,
      },
    })
    expect(screen.getByTestId("status")).toHaveTextContent("ERROR")
  })
})
