"use server"

import type { Run, RunResult } from "@/model/Run"

// Server Actions: the browser calls these, but the fetch runs on the Next
// server, so the API's origin stays out of the bundle. Read at request time,
// so one build runs in any environment.
const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000"

// What the API answers, in snake_case; mapped to camelCase below so the
// convention stops at this boundary.
interface RunResponse {
  id: string
  kind: Run["kind"]
  phase: Run["phase"]
  pending_question: Run["pendingQuestion"]
  result: {
    status: RunResult["status"]
    findings: {
      test: string
      value: number | null
      limit: string
      severity: "fail" | "review"
      spec_ref: string | null
      likely_coa_error: boolean
      evidence: string | null
    }[]
    summary: string
    draft_id: string | null
  } | null
}

export const toRun = (r: RunResponse): Run => ({
  id: r.id,
  kind: r.kind,
  phase: r.phase,
  pendingQuestion: r.pending_question,
  result: r.result && {
    status: r.result.status,
    summary: r.result.summary,
    draftId: r.result.draft_id,
    findings: r.result.findings.map((f) => ({
      test: f.test,
      value: f.value,
      limit: f.limit,
      severity: f.severity,
      specRef: f.spec_ref,
      likelyCoaError: f.likely_coa_error,
      evidence: f.evidence,
    })),
  },
})

const request = async (path: string, init: RequestInit): Promise<Run> => {
  const response = await fetch(`${API_BASE_URL}${path}`, init)

  if (!response.ok) {
    throw new Error(`Request to ${path} failed (${response.status})`)
  }

  return toRun(await response.json())
}

// POST /runs: uploads the PDF and starts the agent run.
export async function startRun(form: FormData): Promise<Run> {
  return request("/runs", { method: "POST", body: form })
}

// POST /baseline: the fixed pipeline on the same PDF.
export async function startBaseline(pdfId: string): Promise<Run> {
  return request("/baseline", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pdf_id: pdfId }),
  })
}

export async function getRun(id: string): Promise<Run> {
  return request(`/runs/${id}`, { cache: "no-store" })
}

// POST /runs/{id}/answer: resumes a run that is waiting on ask_user.
export async function answerRun(id: string, answer: string): Promise<Run> {
  return request(`/runs/${id}/answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answer }),
  })
}
