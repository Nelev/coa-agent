// API response shapes, in one place so a contract change is a one-file edit.
export const runResponse = {
  id: "run1",
  kind: "agent",
  phase: "done",
  pending_question: null,
  result: {
    status: "REVIEW",
    summary: "Assay 9.85 % is ten times the lot history; likely a typo.",
    draft_id: "d1",
    findings: [
      {
        test: "assay",
        kind: "oos",
        value: 9.85,
        limit: "98.0-102.0 %",
        severity: "fail",
        spec_ref: "SPEC-1",
        likely_coa_error: true,
        evidence: "last 10 lots between 98.8 and 99.2",
      },
    ],
  },
}

export const stepEvent = {
  seq: 1,
  tool: "read_coa",
  input: {},
  output: { supplier: "Acme" },
  reasoning: null,
  tokens_in: 1200,
  tokens_out: 300,
  ms: 2100,
}
