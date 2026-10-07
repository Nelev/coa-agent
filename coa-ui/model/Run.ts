export type BaselineStatus = "PASS" | "REVIEW" | "FAIL" | "ERROR"
// Where a run is in its life. "waiting" is the agent asking the user.
export type RunPhase = "running" | "waiting" | "done" | "error"

export type FindingKind =
  "oos" | "missing" | "expired" | "unapproved" | "unreadable"

export interface Finding {
  test: string
  kind: FindingKind
  value: number | null
  limit: string
  severity: "fail" | "review"
  specRef: string | null
  likelyCoaError: boolean
  evidence: string | null
}

export interface Question {
  question: string
  options: string[]
}

// A drafted supplier request. Shown, never sent.
export interface Draft {
  subject: string
  body: string
}

// The outcome of a run. The baseline's has no draft.
export interface RunResult {
  status: BaselineStatus
  findings: Finding[]
  summary: string
  draft: Draft | null
}

export interface Run {
  id: string
  kind: "agent" | "baseline"
  pdfId: string
  phase: RunPhase
  pendingQuestion: Question | null
  result: RunResult | null
}

// One of the 8 sample CoAs the API offers.
export interface Sample {
  file: string
  scenario: number
  title: string
}
