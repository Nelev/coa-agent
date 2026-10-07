// The API answers in snake_case; everything is mapped to camelCase here, so
// the convention stops at this boundary. Used by the Server Actions and by the
// event stream hook alike (it is not a "use server" module).
import type { Draft, Finding, Run, RunResult } from "@/model/Run"
import type { Step } from "@/model/Step"

export interface FindingJson {
  test: string
  kind: Finding["kind"]
  value: number | null
  limit: string
  severity: Finding["severity"]
  spec_ref: string | null
  likely_coa_error: boolean
  evidence: string | null
}

export interface ResultJson {
  status: RunResult["status"]
  findings: FindingJson[]
  summary: string
  draft?: Draft | null
}

export interface StepJson {
  seq: number
  tool: string | null
  input: Step["input"]
  output: Step["output"]
  reasoning: string | null
  tokens_in: number
  tokens_out: number
  ms: number
}

export interface RunJson {
  id: string
  kind: Run["kind"]
  pdf_id: string
  phase: Run["phase"]
  pending_question: Run["pendingQuestion"]
  result: ResultJson | null
}

export const toResult = (r: ResultJson): RunResult => ({
  status: r.status,
  summary: r.summary,
  draft: r.draft ?? null,
  findings: r.findings.map((f) => ({
    test: f.test,
    kind: f.kind,
    value: f.value,
    limit: f.limit,
    severity: f.severity,
    specRef: f.spec_ref,
    likelyCoaError: f.likely_coa_error,
    evidence: f.evidence,
  })),
})

export const toStep = (e: StepJson): Step => ({
  seq: e.seq,
  tool: e.tool,
  input: e.input,
  output: e.output,
  reasoning: e.reasoning,
  tokensIn: e.tokens_in,
  tokensOut: e.tokens_out,
  ms: e.ms,
})

export const toRun = (r: RunJson): Run => ({
  id: r.id,
  kind: r.kind,
  pdfId: r.pdf_id,
  phase: r.phase,
  pendingQuestion: r.pending_question,
  result: r.result && toResult(r.result),
})
