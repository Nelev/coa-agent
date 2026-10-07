export type Status = "PASS" | "REVIEW" | "FAIL"
// The baseline can also fail to run at all.
export type BaselineStatus = Status | "ERROR"
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

export interface RunResult {
  status: Status | BaselineStatus
  findings: Finding[]
  summary: string
  draftId: string | null
}

export interface Run {
  id: string
  kind: "agent" | "baseline"
  phase: RunPhase
  pendingQuestion: Question | null
  result: RunResult | null
}
