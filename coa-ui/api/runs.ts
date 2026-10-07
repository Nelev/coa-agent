"use server"

import { toRun, type RunJson } from "@/model/api"
import type { Run, Sample } from "@/model/Run"
import { API_BASE_URL } from "@/lib/server-api"

// Server Actions: the browser calls these, but the fetch runs on the Next
// server, so the API's origin stays out of the bundle.

const call = async <T>(path: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    cache: "no-store",
    ...init,
  })

  if (!response.ok) {
    throw new Error(`Request to ${path} failed (${response.status})`)
  }

  return response.json()
}

const post = (path: string, body: unknown): Promise<RunJson> =>
  call(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })

// The 8 sample CoAs.
export async function listSamples(): Promise<Sample[]> {
  return call("/samples")
}

// What the user is told, by what the API said: its refusals are specific
// (a file that is not a PDF, one that is too large), and a Server Action can
// not carry an Error's own message to the browser in production.
const START_ERRORS: Record<number, string> = {
  413: "That file is over the 10 MB limit.",
  415: "That file is not a PDF.",
  503: "The agent is not available. Is OPENROUTER_API_KEY set for the API?",
}

export type StartResult = { run: Run } | { error: string }

// POST /runs: uploads the PDF (field `file`) or picks a sample (field
// `sample`) and starts the agent run.
export async function startRun(form: FormData): Promise<StartResult> {
  try {
    return {
      run: toRun(await call<RunJson>("/runs", { method: "POST", body: form })),
    }
  } catch (error) {
    const status = Number(String(error).match(/\((\d+)\)/)?.[1])
    return { error: START_ERRORS[status] ?? "The run could not be started." }
  }
}

// POST /baseline: the fixed pipeline on the same PDF.
export async function startBaseline(pdfId: string): Promise<Run> {
  return toRun(await post("/baseline", { pdf_id: pdfId }))
}

// POST /runs/{id}/answer: resumes a run that is waiting on ask_user. What the
// run does next arrives on its event stream, not here.
export async function answerRun(id: string, answer: string): Promise<void> {
  await post(`/runs/${id}/answer`, { answer })
}
