// One saved step of a run (FR8), as the UI uses it. The API answers in
// snake_case; api/runs.ts and hooks/use-run-events.ts map it here.
export interface Step {
  seq: number
  tool: string | null
  input: Record<string, unknown> | null
  output: Record<string, unknown> | string | null
  reasoning: string | null
  tokensIn: number
  tokensOut: number
  ms: number
}
