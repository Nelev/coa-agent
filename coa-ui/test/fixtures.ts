// API response shapes, in one place so a contract change is a one-file edit.
import type { Run } from "@/model/Run"
import type { Step } from "@/model/Step"
import type { RunJson, StepJson } from "@/model/api"

export const runResponse: RunJson = {
  id: "run1",
  kind: "agent",
  pdf_id: "pdf1",
  phase: "done",
  pending_question: null,
  result: {
    status: "REVIEW",
    summary: "Assay 9.85 % is ten times the lot history; likely a typo.",
    draft: { subject: "Assay on lot NC-26-0413", body: "Dear Nordchem," },
    findings: [
      {
        test: "assay",
        kind: "oos",
        value: 9.85,
        limit: "98.0-102.0 %",
        severity: "review",
        spec_ref: "SPEC-1",
        likely_coa_error: true,
        evidence: "last 10 lots between 98.8 and 99.2",
      },
    ],
  },
}

export const stepEvent: StepJson = {
  seq: 1,
  tool: "read_coa",
  input: {},
  output: { supplier: "Acme" },
  reasoning: null,
  tokens_in: 1200,
  tokens_out: 300,
  ms: 2100,
}

export const step = (overrides: Partial<Step> = {}): Step => ({
  seq: 1,
  tool: "read_coa",
  input: {},
  output: { supplier: "Acme" },
  reasoning: null,
  tokensIn: 1200,
  tokensOut: 300,
  ms: 2100,
  ...overrides,
})

export const run = (overrides: Partial<Run> = {}): Run => ({
  id: "run1",
  kind: "agent",
  pdfId: "pdf1",
  phase: "running",
  pendingQuestion: null,
  result: null,
  ...overrides,
})

export const samples = [
  { file: "coa_01_clean.pdf", scenario: 1, title: "All values in spec" },
  { file: "coa_02_typo.pdf", scenario: 2, title: "Assay printed 9.85 %" },
]
