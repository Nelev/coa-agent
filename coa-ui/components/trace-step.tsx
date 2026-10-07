import { memo } from "react"

import type { Step } from "@/model/Step"
import { cn } from "@/lib/utils"

const formatArgs = (input: Step["input"]) =>
  Object.entries(input ?? {})
    .map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`)
    .join(", ")

// Text in the document that addresses the reader (read_coa reports it apart from
// the results, as data). Shown on the step itself: that it was seen, and what
// the run did next, is the point of the injection scenario.
const documentNotes = (step: Step): string | null =>
  step.tool === "read_coa" &&
  typeof step.output === "object" &&
  step.output !== null &&
  typeof step.output.document_notes === "string"
    ? step.output.document_notes
    : null

const formatOutput = (output: Step["output"]) =>
  typeof output === "string" ? output : JSON.stringify(output, null, 2)

// One step of the run (FR8): what was called, why, what came back, what it cost.
export const TraceStep = memo(function TraceStep({ step }: { step: Step }) {
  const failed =
    typeof step.output === "string" && step.output.startsWith("Error:")
  const waiting =
    typeof step.output === "object" &&
    step.output !== null &&
    "waiting_for_user" in step.output
  const args = formatArgs(step.input)
  const notes = documentNotes(step)

  return (
    <li
      data-testid="trace-step"
      className={cn(
        "rounded border p-3 text-sm",
        failed && "border-red-300 bg-red-50",
        waiting && "border-amber-300 bg-amber-50",
      )}
    >
      <div className="flex flex-wrap items-baseline gap-x-2">
        <span className="text-muted-foreground font-mono text-xs">
          {step.seq}
        </span>
        <span className="font-mono font-semibold">
          {step.tool ?? "model reply"}
        </span>
        {args && (
          <span className="text-muted-foreground font-mono text-xs break-all">
            {args}
          </span>
        )}
      </div>

      {notes && (
        <p
          role="note"
          className="mt-1 rounded border border-amber-300 bg-amber-50 p-2 text-xs"
        >
          The document contains text addressed to the reader: <q>{notes}</q> It
          is treated as data, not as an instruction.
        </p>
      )}

      {step.reasoning && (
        <p className="text-muted-foreground mt-1 italic">{step.reasoning}</p>
      )}

      {step.output !== null && (
        <details className="mt-1" open={failed || waiting}>
          <summary className="text-muted-foreground cursor-pointer text-xs">
            {failed ? "refused" : waiting ? "waiting for the user" : "output"}
          </summary>
          <pre className="mt-1 max-h-60 overflow-auto rounded bg-neutral-100 p-2 text-xs whitespace-pre-wrap">
            {formatOutput(step.output)}
          </pre>
        </details>
      )}

      <div className="text-muted-foreground mt-1 text-xs">
        {step.tokensIn + step.tokensOut > 0 &&
          `${step.tokensIn}+${step.tokensOut} tokens · `}
        {step.ms} ms
      </div>
    </li>
  )
})
